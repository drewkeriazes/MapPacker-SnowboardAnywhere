#!/usr/bin/env python3
"""FEAT-175 step 4: a resort's default start and its main menu shots, generated from its own pack.

    python pipeline/gen_content.py <pack_dir> [--config resorts/<slug>/<slug>.json] [--shots 5] [--dry-run]

Reads only the pack (meta.json, features.json, the height sets, the mask, trees and stands) and the config's
`start_run`. Writes into the pack, without a new build stamp (`write_meta(..., stamp=False)`), so a menu still
rendered from this build stays valid:

- **start** (`meta.start`): the top of the highest lift, on the config's `start_run` when it names one, else on the
  most-ridden run from there (most grooming reports, then groomed, then the easiest of intermediate / easy /
  advanced, then the longest). The rider stands on the run's centre line where it is on snow (mask rock and scree
  under half), clear of trees (no crown edge within 3 m, no stand with a stem chance over 0.25 within 6 m: the
  same rule as `pack_report.py` line 10), 20 m clear of any lift station, on a slope that falls 4 to 35 degrees
  along the run and where the run falls on (6 m over the next 60 m of its centre line, never rising 0.3 m above the
  start on the way, so the rider rolls off rather than stopping in a flat); facing down it. `{x, y, heading, run, lift, label, source: "generated"}`. Lifts are tried highest
  top first; expert and freeride runs only when nothing else leaves a lift.
- **menu shots** (`attract/shots.json`, `attract/index.json`, and `meta.attract = {"generated": true}` so the game
  knows to ask for them): about five camera spots from the lift tops, the named peaks inside the bounds and the start.
  From each, a panorama is ray-marched over the height sets (fine, then mid, then far; the earth's curvature
  included) and every heading and pitch is scored by how much of the frame is terrain against sky (best near 60 %
  terrain) and how far you can see (the median and the far tenth of the hit distances), less any slope that blocks
  the upper half close by. The first shot, the one the menu uses, must see the start run (and still score at least
  60 % of the best view) (the ghost riders ride it,
  `game/tools/auto_attract.mjs`); the rest are the best of the other spots, at least 250 m apart. Each is an
  `AttractShot` (`game/src/world/AttractShots.ts`) in the default conditions, with a `note` giving its numbers.
  The folder has the shape FEAT-243 gives the pack's `attract/`: `index.json` is one resort's manifest entry
  (`shots`, `stills`, `ghosts`, `looks`, `shotGhosts`) plus `generated: true`. A pack whose `attract/` is hand-made
  (an `index.json` without `generated`) is left alone; a rerun that picks the same shots keeps the still and the
  takes `auto_attract.mjs` added, one that picks new shots drops them.

The game's hand-made content still wins in the game: `world/Landmarks.ts` starts and the menu in
`game/public/attract/<slug>/` (Vail, Breckenridge) until FEAT-243 moves them into the pack.
"""
import argparse
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pack_report import (AERIAL, START_CLEAR_M, START_STAND_MAX, distance_to_polyline, grid_top,  # noqa: E402
                         load_json, polyline_length, read_heights, read_instances, read_mask, read_stands, resample)
from packwriter import write_meta  # noqa: E402

GENERATOR = "gen_content.py (FEAT-175)"
# start
START_FROM_TOP_M = 15.0        # the walk down the run starts this far from the top station
START_WALK_M = 400.0           # and gives up this far down
START_STEP_M = 3.0
START_LIFT_CLEAR_M = 20.0      # closer, the chase camera starts inside the terminal (FEAT-219)
START_SLOPE_DEG = (4.0, 35.0)  # the fall along the run over START_SLOPE_M: the rider must move, but not off a cliff
START_SLOPE_M = 12.0
START_ROLL_M = 60.0            # and the run falls on from there: START_ROLL_DROP over this, never rising START_ROLL_RISE
START_ROLL_DROP = 6.0
START_ROLL_RISE = 0.3
RUN_NEAR_TOP_M = 120.0         # a run leaves a lift when it passes this close to its top station
LIFT_TRIES = 6                 # highest lift tops tried
DIFF_RANK = {"intermediate": 0, "easy": 1, "novice": 1, "advanced": 2}
EXPERT = {"expert", "extreme", "freeride"}
# shots
SHOTS = 5
SHOT_FOV = 60.0                # vertical, degrees; 16:9 frame
ASPECT = 16 / 9
SHOT_PITCHES = (-14.0, -10.0, -6.0, -2.0)
START_PITCHES = (-22.0, -16.0, -10.0)
HEADING_STEP = 10.0
AZ_STEP, EL_STEP = 2.0, 1.25   # panorama ray spacing, degrees
EL_RANGE = (-56.0, 32.0)
MARCH = (3.0, 1.025, 40000.0)  # first step m, growth per step, farthest m
EARTH_R = 6371000.0 / 0.87     # curvature with standard refraction (k = 0.13)
LIFT_PAST_M = (30.0, 70.0)     # camera spots this far past a lift's top station, along the lift
START_BACK_M = (40.0, 80.0)    # and this far up the start run behind the start
START_HIGH_EYE = 30.0          # each also this high, to see out of a bowl (Big Sky's Powder Seeker top)
EYE_MIN, EYE_MAX = 10.0, 32.0  # camera height over the snow; raised over the trees round it
TREE_LOOK_M = 25.0
SHOT_APART_M = 250.0
TERRAIN_BEST, TERRAIN_SPAN = 0.6, 0.35
FAR_NEAR_M, FAR_FAR_M = 300.0, 30000.0
BLOCK_M = 150.0
RUN_VIEW_M = (20.0, 700.0)     # the stretch of the start run the menu shot should see
MENU_RUN_MIN = 0.2             # share of it in view, unoccluded
MENU_RUN_WEIGHT = 1.2           # the menu shot: its view score plus this times the start run in view
MENU_VIEW_SHARE = 0.6          # and its view score at least this share of the best spot's
RUN_CLOSE_M = 120.0            # a point of it further from the camera counts for RUN_CLOSE_M / distance
STATION_NEAR_M = 90.0          # a lift station this close in the frame is a roof in the foreground
STATION_PENALTY = 0.3
DEFAULT_CONDITIONS = {"clouds": "few", "timeOfDay": "pack", "month": 2, "newSnow": "none", "snowDay": "mid",
                      "valleyFog": False, "cloudTime": 0}


NUMBER_WORDS = {w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten".split())}


def run_key(name):
    """a run name for matching the config's start_run: case, apostrophes and number words aside ("Four O'Clock"
    is OSM's "4 O'Clock")"""
    words = re.sub(r"[‘’'`]", "", (name or "").lower()).split()
    return " ".join(NUMBER_WORDS.get(w, w) for w in words)


def slugify(s):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:40].strip("-") or "shot"


# ------------------------------------------------------------------ the ground

class Ground:
    """ground height at local (x, y) from the finest height set that covers it (nearest sample; NaN off every set)"""

    def __init__(self, pack_dir, meta, fine_step=2):
        self.sets = []
        for name, step in (("fine", fine_step), ("mid", 1), ("far", 1)):
            m = meta.get("terrain", {}).get(name)
            if not m:
                continue
            arr, _ = read_heights(pack_dir, m, name, step)
            self.sets.append((arr, m["minX"], grid_top(m), m["res"] * step))

    def z(self, x, y):
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        out = np.full(np.broadcast(x, y).shape, np.nan, np.float32)
        x, y = np.broadcast_to(x, out.shape), np.broadcast_to(y, out.shape)
        for arr, x0, top, res in self.sets:
            need = np.isnan(out)
            if not need.any():
                break
            c = np.floor((x - x0) / res).astype(np.int64)
            r = np.floor((top - y) / res).astype(np.int64)
            ok = need & (r >= 0) & (r < arr.shape[0]) & (c >= 0) & (c < arr.shape[1])
            out[ok] = arr[r[ok], c[ok]]
        return out

    def at(self, x, y):
        return float(self.z(np.array([x]), np.array([y]))[0])


# ------------------------------------------------------------------ the start

def downhill(points):
    """a run's points ordered from its high end"""
    return points[::-1] if points[0][2] < points[-1][2] else points


def lift_tops(lifts):
    """(top station x, y, z, lift) for every aerial lift, highest first"""
    out = []
    for lf in lifts:
        st = lf.get("stations") or []
        if (lf.get("type") or "") not in AERIAL or len(st) < 2:
            continue
        top = max(st, key=lambda s: s[2])
        out.append((top[0], top[1], top[2], lf))
    return sorted(out, key=lambda t: -t[2])


def run_rank(r):
    """lower is more ridden: grooming reports, groomed, intermediate before easy before advanced, longer"""
    return (-(r.get("groomNights") or 0), 0 if r.get("groomed") else 1, DIFF_RANK.get(r.get("difficulty") or "", 3),
            -polyline_length(r["points"]))


def runs_from(runs, x, y, near=RUN_NEAR_TOP_M):
    """line runs that pass within `near` of (x, y) and carry on downhill from there"""
    out = []
    for r in runs:
        if r.get("area") or len(r.get("points") or []) < 2 or not r.get("name"):
            continue
        if distance_to_polyline(x, y, r["points"]) > near:
            continue
        out.append(r)
    return out


def walk_from(points, x, y):
    """the run's centre line from the point nearest (x, y) on down, every START_STEP_M (x, y, z, metres down)"""
    p = resample(downhill(points), 1.0)
    i = int(np.argmin(np.hypot(p[:, 0] - x, p[:, 1] - y)))
    rest = resample(p[i:], START_STEP_M)
    d = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(rest[:, :2], axis=0).T))])
    return rest, d


class StartCheck:
    """the start rules over the pack's mask, trees and stands"""

    def __init__(self, meta, ground, mask, trees, stands, lifts):
        self.meta, self.ground, self.mask, self.trees, self.stands = meta, ground, mask, trees, stands
        self.stations = np.array([s[:2] for lf in lifts for s in (lf.get("stations") or [])] or np.zeros((0, 2)))

    def rolls_on(self, pts, d, i):
        return rolls_on(self.ground, pts, d, i)

    def why_not(self, x, y, ux, uy):
        """None when (x, y) facing (ux, uy) is a good start, else the reason"""
        b = self.meta["bounds"]
        if not (b["minX"] + 20 <= x < b["maxX"] - 20 and b["minY"] + 20 <= y < b["maxY"] - 20):
            return "outside the bounds"
        if len(self.stations) and np.hypot(self.stations[:, 0] - x, self.stations[:, 1] - y).min() < START_LIFT_CLEAR_M:
            return "by a lift station"
        if self.mask is not None:
            m = self.meta["mask"]
            res = m["res"]
            c = int(math.floor((x - m["minX"]) / res))
            r = int(math.floor((grid_top(m) - y) / res))
            win = self.mask[max(0, r - 1):r + 2, max(0, c - 1):c + 2]
            if win.size and (win[..., 0].max() >= 128 or win[..., 1].max() >= 128):
                return "on rock or scree"
        if len(self.trees):
            d = np.hypot(self.trees[:, 0] - x, self.trees[:, 1] - y) - self.trees[:, 4]
            if (d < START_CLEAR_M).any():
                return "by a tree"
        if self.stands is not None and len(self.stands):
            near = np.hypot(self.stands[:, 0] - x, self.stands[:, 1] - y) < 6
            if near.any() and self.stands[near, 3].max() > START_STAND_MAX:
                return "in a stand"
        z0 = self.ground.at(x, y)
        z1 = self.ground.at(x + ux * START_SLOPE_M, y + uy * START_SLOPE_M)
        if not (np.isfinite(z0) and np.isfinite(z1)):
            return "no ground"
        slope = math.degrees(math.atan2(z0 - z1, START_SLOPE_M))
        if not START_SLOPE_DEG[0] <= slope <= START_SLOPE_DEG[1]:
            return f"slope {slope:.0f} deg"
        return None


def rolls_on(ground, pts, d, i):
    """None when the run falls on from point i (the ground along its centre line drops START_ROLL_DROP over the next
    START_ROLL_M and never rises over START_ROLL_RISE above the start on the way), else the reason. A rider dropped
    on a flat or into a dip just stops (Big Sky's Morningstar under the Powder Seeker top, 2026-11-12)"""
    ahead = (d > d[i]) & (d <= d[i] + START_ROLL_M)
    if not ahead.any() or d[ahead][-1] < d[i] + START_ROLL_M * 0.8:
        return "run ends"
    z0 = ground.at(pts[i, 0], pts[i, 1])
    z = ground.z(pts[ahead, 0], pts[ahead, 1])
    if not np.isfinite(z0) or not np.isfinite(z).all():
        return "no ground"
    if z.max() > z0 + START_ROLL_RISE:
        return f"the run rises {z.max() - z0:.1f} m ahead"
    if z0 - z[-1] < START_ROLL_DROP:
        return f"the run falls only {z0 - z[-1]:.1f} m in {START_ROLL_M:.0f} m"
    return None


def place_on(run, tx, ty, check):
    """the first good start on `run` walking down from the point nearest (tx, ty); (x, y, heading) or (None, why)"""
    pts, d = walk_from(run["points"], tx, ty)
    why = "run too short"
    for i in range(len(pts)):
        if d[i] < START_FROM_TOP_M - 1e-6:
            continue
        if d[i] > START_WALK_M:
            break
        j = min(len(pts) - 1, i + max(1, int(round(20.0 / START_STEP_M))))
        if j == i:
            break
        ux, uy = pts[j, 0] - pts[i, 0], pts[j, 1] - pts[i, 1]
        L = math.hypot(ux, uy) or 1.0
        ux, uy = ux / L, uy / L
        why = check.why_not(pts[i, 0], pts[i, 1], ux, uy) or check.rolls_on(pts, d, i)
        if why is None:
            return (float(pts[i, 0]), float(pts[i, 1]), math.atan2(ux, uy)), None
    return None, why


def choose_start(meta, features, check, start_run=None, log=print):
    """the generated start: {x, y, heading, run, lift, label, source} or None"""
    runs = [r for r in features.get("runs", []) if not r.get("area") and len(r.get("points") or []) >= 2]
    tops = lift_tops(features.get("lifts", []))
    tries = []
    if start_run:
        named = [r for r in runs if run_key(r.get("name")) == run_key(start_run)]
        if not named:
            log(f"  start_run {start_run!r} is not a run in features.json: picking one")
        else:
            # the named run at the highest lift top it leaves, else its own top
            for tx, ty, tz, lf in tops:
                for r in named:
                    if distance_to_polyline(tx, ty, r["points"]) <= RUN_NEAR_TOP_M:
                        tries.append((r, tx, ty, lf))
            for r in sorted(named, key=lambda r: -max(p[2] for p in r["points"])):
                hi = downhill(r["points"])[0]
                tries.append((r, hi[0], hi[1], None))
    for tx, ty, tz, lf in tops[:LIFT_TRIES]:
        cands = runs_from(runs, tx, ty)
        easy = [r for r in cands if (r.get("difficulty") or "") not in EXPERT]
        for r in sorted(easy or cands, key=run_rank):
            tries.append((r, tx, ty, lf))
    seen = set()
    for r, tx, ty, lf in tries:
        key = (id(r), round(tx), round(ty))
        if key in seen:
            continue
        seen.add(key)
        got, why = place_on(r, tx, ty, check)
        lname = (lf or {}).get("name")
        if got is None:
            log(f"  no start on {r['name']} below {lname or 'its top'}: {why}")
            continue
        x, y, h = got
        start = {"x": round(x, 2), "y": round(y, 2), "heading": round(h, 5), "run": r["name"],
                 "label": f"Starts at the top of {lname}" if lname else f"Starts at the top of {r['name']}",
                 "source": "generated"}
        if lname:
            start["lift"] = lname
        return start
    return None


# ------------------------------------------------------------------ the shots

class Panorama:
    """first terrain hit per ray from a camera, over azimuths (clockwise from north) and elevations; inf = sky"""

    def __init__(self, ground, x, y, z):
        self.az = np.arange(0.0, 360.0, AZ_STEP)
        self.el = np.arange(EL_RANGE[0], EL_RANGE[1] + 1e-6, EL_STEP)
        s0, k, smax = MARCH
        steps = s0 * k ** np.arange(int(math.log(smax / s0) / math.log(k)) + 1)
        A, E = np.meshgrid(np.radians(self.az), np.radians(self.el))       # rows: elevation, cols: azimuth
        dx, dy, dz = np.cos(E) * np.sin(A), np.cos(E) * np.cos(A), np.sin(E)
        hit = np.full(A.shape, np.inf)
        alive = np.ones(A.shape, bool)
        for s in steps:                       # step by step over the rays still in the air
            if not alive.any():
                break
            idx = np.nonzero(alive)
            h = s * np.cos(E[idx])
            gz = ground.z(x + dx[idx] * s, y + dy[idx] * s)
            pz = z + dz[idx] * s - h * h / (2 * EARTH_R)
            under = np.isfinite(gz) & (pz <= gz)
            rr, cc = idx[0][under], idx[1][under]
            hit[rr, cc] = s
            alive[rr, cc] = False
        self.hit = hit

    def window(self, heading, pitch, fov=SHOT_FOV):
        """the hits inside a frame centred on (heading, pitch)"""
        half_v = fov / 2
        half_h = math.degrees(math.atan(math.tan(math.radians(half_v)) * ASPECT))
        da = (self.az - heading + 180) % 360 - 180
        cols = np.abs(da) <= half_h
        rows = np.abs(self.el - pitch) <= half_v
        return self.hit[np.ix_(rows, cols)]


def score_view(win):
    """(score, numbers) for one frame of hit distances (rows top = low elevation first)"""
    hits = np.isfinite(win)
    terrain = float(hits.mean()) if win.size else 0.0
    if not hits.any():
        return -1.0, {"terrain": 0.0}
    d = win[hits]
    med, far = float(np.median(d)), float(np.percentile(d, 90))
    upper = win[win.shape[0] // 2:]
    block = float((np.isfinite(upper) & (upper < BLOCK_M)).mean()) if upper.size else 0.0
    s_terrain = max(0.0, 1 - abs(terrain - TERRAIN_BEST) / TERRAIN_SPAN)
    span = math.log(FAR_FAR_M / FAR_NEAR_M)
    s_far = 0.5 * sum(min(1.0, max(0.0, math.log(max(v, 1.0) / FAR_NEAR_M) / span)) for v in (med, far))
    score = 0.4 * s_terrain + 0.6 * s_far - 0.8 * block
    return score, {"terrain": round(terrain, 3), "medianM": round(med), "farM": round(far), "block": round(block, 3)}


def in_frame(cam, h, p, x, y, z, fov=SHOT_FOV, margin=1.0):
    """is (x, y, z) inside the (perspective) frame of a camera at `cam` looking at heading h, pitch p?"""
    hr, pr = math.radians(h), math.radians(p)
    f = (math.sin(hr) * math.cos(pr), math.cos(hr) * math.cos(pr), math.sin(pr))
    r = (math.cos(hr), -math.sin(hr), 0.0)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    d = (x - cam[0], y - cam[1], z - cam[2])
    depth = sum(a * b for a, b in zip(d, f))
    if depth <= 0.5:
        return False
    tv = math.tan(math.radians(fov / 2))
    nx = sum(a * b for a, b in zip(d, r)) / depth / (tv * ASPECT)
    ny = sum(a * b for a, b in zip(d, u)) / depth / tv
    return abs(nx) <= margin and abs(ny) <= margin


def station_penalty(cam, h, p, stations):
    """STATION_PENALTY when a lift station close by is in the frame (its roof fills the foreground)"""
    for x, y, z in stations:
        if math.hypot(x - cam[0], y - cam[1]) < STATION_NEAR_M and any(
                in_frame(cam, h, p, x + ox, y + oy, z + oz) for ox, oy in ((0, 0), (6, 0), (-6, 0), (0, 6), (0, -6)) for oz in (0, 6)):
            return STATION_PENALTY
    return 0.0


def best_view(pano, headings, pitches, cam=None, stations=()):
    best = None
    for h in headings:
        for p in pitches:
            s, n = score_view(pano.window(h % 360, p))
            s -= station_penalty(cam, h % 360, p, stations) if cam else 0.0
            if best is None or s > best[0]:
                best = (s, h % 360, p, n)
    return best


def visible_share(ground, cam, h, p, pts, fov=SHOT_FOV):
    """share of `pts` (x, y, z) inside the frame and not behind terrain, each weighted down past RUN_CLOSE_M"""
    if not len(pts):
        return 0.0
    cx, cy, cz = cam
    seen = 0.0
    for x, y, z in pts:
        dx, dy, dz = x - cx, y - cy, z + 1.5 - cz
        dist = math.hypot(dx, dy)
        if dist < 1 or not in_frame(cam, h, p, x, y, z + 1.5, fov, margin=0.95):
            continue
        k = np.linspace(0.03, 0.97, 48)
        gz = ground.z(cx + dx * k, cy + dy * k)
        if np.any(np.isfinite(gz) & (gz > cz + dz * k + 0.5)):
            continue
        seen += min(1.0, RUN_CLOSE_M / math.hypot(dist, dz))   # a rider far off is a few pixels: counts for less
    return seen / len(pts)


def eye_height(trees, x, y):
    """over the crowns round the camera, so it sees past them"""
    if not len(trees):
        return EYE_MIN
    near = np.hypot(trees[:, 0] - x, trees[:, 1] - y) < TREE_LOOK_M
    top = float(trees[near, 3].max()) + 3.0 if near.any() else 0.0
    return float(min(EYE_MAX, max(EYE_MIN, top)))


def viewpoints(meta, features, start, trees, ground):
    """camera spots: past each lift's top station, the named peaks in the bounds, and behind the start"""
    b = meta["bounds"]
    inside = lambda x, y: b["minX"] + 50 <= x < b["maxX"] - 50 and b["minY"] + 50 <= y < b["maxY"] - 50
    out = []
    for tx, ty, tz, lf in lift_tops(features.get("lifts", [])):
        st = sorted(lf["stations"], key=lambda s: s[2])
        bx, by = st[0][0], st[0][1]
        ux, uy = tx - bx, ty - by
        L = math.hypot(ux, uy) or 1.0
        for past in LIFT_PAST_M:                      # on past the top, off the terminal
            x, y = tx + ux / L * past, ty + uy / L * past
            if inside(x, y):
                out.append({"kind": "lift", "x": x, "y": y, "name": lf.get("name") or "the lift", "z": tz})
    for pk in features.get("peaks", []):
        if pk.get("name") and inside(pk["x"], pk["y"]):
            out.append({"kind": "peak", "x": pk["x"], "y": pk["y"], "name": pk["name"], "z": pk.get("z")})
    if start:
        hx, hy = math.sin(start["heading"]), math.cos(start["heading"])
        for back in START_BACK_M:
            for lift in (0.0, START_HIGH_EYE):      # and high, to see out of a bowl
                out.append({"kind": "start", "x": start["x"] - hx * back, "y": start["y"] - hy * back,
                            "name": start.get("run"), "z": None, "eyeMin": lift})
    for v in out:
        g = ground.at(v["x"], v["y"])
        v["ground"] = g
        v["eye"] = max(eye_height(trees, v["x"], v["y"]), v.get("eyeMin", 0.0))
    return [v for v in out if np.isfinite(v["ground"])]


def start_run_points(features, start):
    """the start run below the start, RUN_VIEW_M along it, every 10 m (x, y, z)"""
    if not start or not start.get("run"):
        return np.zeros((0, 3))
    best = None
    for r in features.get("runs", []):
        if r.get("name") != start["run"] or r.get("area") or len(r["points"]) < 2:
            continue
        d = distance_to_polyline(start["x"], start["y"], r["points"])
        if best is None or d < best[0]:
            best = (d, r)
    if best is None:
        return np.zeros((0, 3))
    pts, d = walk_from(best[1]["points"], start["x"], start["y"])
    keep = (d >= RUN_VIEW_M[0]) & (d <= RUN_VIEW_M[1])
    return resample(pts[keep], 10.0) if keep.sum() >= 2 else pts[keep]


def shot_of(v, view, name, region, number):
    s, h, p, n = view
    place = {"lift": f"Top of {v['name']}", "peak": v["name"], "start": v["name"] or name}[v["kind"]]
    shot = {
        "id": slugify(place), "x": round(v["x"], 1), "y": round(v["y"], 1), "h": round(h, 1), "pitch": round(p, 1),
        "fov": SHOT_FOV, "eye": round(v["eye"], 2), "place": place, "region": region,
        "elev": {"m": int(round(v["z"] if v.get("z") is not None else v["ground"])),
                 "where": {"lift": "at the top station", "peak": "the summit", "start": "at the camera"}[v["kind"]]},
        "dolly": 4, "pan": 1.5, "period": 26, "conditions": dict(DEFAULT_CONDITIONS),
        "note": (f"generated by {GENERATOR}, shot {number}: {v['kind']} spot, terrain {n['terrain']:.0%} of the frame, "
                 f"median view {n.get('medianM', 0) / 1000:.1f} km, far tenth {n.get('farM', 0) / 1000:.1f} km, "
                 f"blocked {n.get('block', 0):.0%}, score {s:.2f}"
                 + (f", start run {n['run']:.0%} in view" if "run" in n else "")),
    }
    return shot


def choose_shots(meta, features, ground, trees, start, count=SHOTS, log=print):
    """the menu shots, the one that sees the start run first"""
    region = meta.get("name") or meta.get("slug") or ""
    vps = viewpoints(meta, features, start, trees, ground)
    run_pts = start_run_points(features, start)
    stations = [tuple(st[:3]) for lf in features.get("lifts", []) for st in (lf.get("stations") or [])]
    scored = []
    for v in vps:
        cam = (v["x"], v["y"], v["ground"] + v["eye"])
        pano = Panorama(ground, *cam)
        best = best_view(pano, np.arange(0, 360, HEADING_STEP), SHOT_PITCHES, cam, stations)
        menu = None
        if len(run_pts):
            # the menu candidate: aimed at the start run (its middle) and around it, scored with the run in view
            mid = run_pts[len(run_pts) // 2]
            aim = math.degrees(math.atan2(mid[0] - cam[0], mid[1] - cam[1]))
            d = math.hypot(mid[0] - cam[0], mid[1] - cam[1])
            if d < 3000:
                for h in aim + np.arange(-30, 31, 10):
                    for p in START_PITCHES + SHOT_PITCHES:
                        s, n = score_view(pano.window(h % 360, p))
                        s -= station_penalty(cam, h % 360, p, stations)
                        vis = visible_share(ground, cam, h % 360, p, run_pts)
                        if vis < MENU_RUN_MIN:
                            continue
                        total = s + MENU_RUN_WEIGHT * vis
                        if menu is None or total > menu[0]:
                            menu = (total, h % 360, p, {**n, "run": round(vis, 3)}, s)
        scored.append((v, best, menu))
        log(f"  {v['kind']:5} {v['name'][:30]:30} eye {v['eye']:4.1f} m: best {best[1]:5.1f} deg pitch {best[2]:5.1f} "
            f"score {best[0]:.2f} {best[3]}" + (f"; sees the start run {menu[3]['run']:.0%} at {menu[1]:.0f} deg" if menu else ""))
    shots = []
    picked = []
    # the menu's view must still be a view: at least MENU_VIEW_SHARE of the best spot's score (Big Sky picked a
    # spot staring into the slope above the start once, for its run in view)
    top = max((t[1][0] for t in scored), default=0.0)
    with_run = [t for t in scored if t[2] is not None and t[2][4] >= MENU_VIEW_SHARE * top]
    if with_run:
        v, _, m = max(with_run, key=lambda t: t[2][0])
        shots.append(shot_of(v, (m[4], m[1], m[2], m[3]), region, region, 1))
        picked.append(v)
    elif start:
        log("  no spot sees the start run: the menu shot is the best view (its ghosts may ride out of sight)")
    for v, best, _ in sorted(scored, key=lambda t: -t[1][0]):
        if len(shots) >= count:
            break
        if any(math.hypot(v["x"] - q["x"], v["y"] - q["y"]) < SHOT_APART_M for q in picked):
            continue
        shots.append(shot_of(v, best, region, region, len(shots) + 1))
        picked.append(v)
    ids = set()
    for s in shots:                                   # unique ids
        base, k = s["id"], 2
        while s["id"] in ids:
            s["id"] = f"{base}-{k}"
            k += 1
        ids.add(s["id"])
    return shots


# ------------------------------------------------------------------ writing

def read_index(pack_dir):
    p = os.path.join(pack_dir, "attract", "index.json")
    return load_json(p) if os.path.isfile(p) else None


def write_attract(pack_dir, shots, log=print):
    """attract/shots.json and attract/index.json; a hand-made folder is left alone. -> written?"""
    d = os.path.join(pack_dir, "attract")
    old = read_index(pack_dir)
    if old is not None and not old.get("generated"):
        log("  attract/ is hand-made (index.json without generated): left alone")
        return False
    os.makedirs(d, exist_ok=True)
    sp = os.path.join(d, "shots.json")
    old_shots = load_json(sp) if os.path.isfile(sp) else None
    if old is not None and old_shots == shots:
        log("  the same shots as before: the still and ghost takes stay")
        return True
    # new shots: the stills and takes rendered for the old ones go (they belong to the old cameras)
    for f in (old or {}).get("ghosts", []) + [f"{s}.jpg" for s in (old or {}).get("stills", [])]:
        p = os.path.join(d, os.path.basename(f))
        if os.path.isfile(p):
            os.remove(p)
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(shots, f, indent=2)
        f.write("\n")
    with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"shots": True, "generated": True, "stills": [], "ghosts": [], "looks": {}, "shotGhosts": {}}, f, indent=2)
        f.write("\n")
    return True


def generate(pack_dir, config=None, count=SHOTS, dry=False, log=print):
    meta = load_json(os.path.join(pack_dir, "meta.json"))
    features = load_json(os.path.join(pack_dir, "features.json"))
    cfg = load_json(config) if config and os.path.isfile(config) else {}
    log(f"{meta.get('slug')}: reading the pack")
    ground = Ground(pack_dir, meta)
    mask = read_mask(pack_dir, meta["mask"]) if meta.get("mask") else None
    trees = read_instances(pack_dir, "trees")
    stands = read_stands(pack_dir, meta)
    check = StartCheck(meta, ground, mask, trees, stands, features.get("lifts", []))
    log("start")
    start = choose_start(meta, features, check, cfg.get("start_run"), log=log)
    if start:
        log(f"  {start['label']}, on {start['run']} at {start['x']:.0f}, {start['y']:.0f}, "
            f"heading {math.degrees(start['heading']) % 360:.0f} deg")
    else:
        log(f"  no generated start: meta.start stays {meta.get('start')}")
    log("shots")
    shots = choose_shots(meta, features, ground, trees, start or meta.get("start"), count, log=log)
    for i, s in enumerate(shots):
        log(f"  {i + 1}. {s['id']}: {s['place']} at {s['x']}, {s['y']}, heading {s['h']}, pitch {s['pitch']}, "
            f"{s['eye']} m up ({s['note'].split(': ', 1)[1]})")
    if dry:
        return start, shots
    if start:
        meta["start"] = start
    if shots and write_attract(pack_dir, shots, log=log):
        meta["attract"] = {"generated": True}
    write_meta(pack_dir, meta, stamp=False)       # same build: a still rendered from it stays valid
    log(f"wrote meta.json (build {meta.get('build')} kept)" + (f", attract/ ({len(shots)} shots)" if shots else ""))
    return start, shots


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pack_dir")
    ap.add_argument("--config", help="the resort config (default resorts/<slug>/<slug>.json), for start_run")
    ap.add_argument("--shots", type=int, default=SHOTS)
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    a = ap.parse_args(argv)
    if not os.path.isfile(os.path.join(a.pack_dir, "meta.json")):
        ap.error(f"no meta.json in {a.pack_dir}")
    config = a.config
    if not config:
        import paths
        slug = load_json(os.path.join(a.pack_dir, "meta.json")).get("slug")
        config = paths.config_path(slug) if slug else None
    generate(a.pack_dir, config, a.shots, a.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
