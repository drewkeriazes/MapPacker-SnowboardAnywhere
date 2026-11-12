"""FEAT-230: split a built pack into a small boot zip round the start and a rest zip, so a resort plays before the
whole pack has downloaded.

The boot zip holds everything the game needs to load and ride from the start: meta.json, features.json, every
`far`, `mid` and `coarse` (FEAT-229, 4 m) height tile, the cover levels, and, of the tiled sets, only the tiles
within `radius` of a boot centre or `corridor` of a run that passes the centre (the first runs down from it). It
also carries `boot.json`, which lists those tiles, so the game asks for nothing else until the rest has arrived
(docs/pack-format.md > Boot and rest). The rest zip holds every other file the full zip holds. The two together are
exactly the full zip's files, so unzipping both gives the same pack.

Boot centres: `meta.start`, any `--at x,y`, and the game's own Free ride start for the resort when the game
checkout is there (a `start` landmark or a placed start in game/src/world/Landmarks.ts, until FEAT-243 moves them
into the pack), since that is where the game spawns.

    python pipeline/boot_split.py packs/vail <out_dir> [--at x,y ...] [--radius 1000] [--corridor 300] [--game-repo <dir>]

writes <out_dir>/<slug>-boot.zip and <slug>-rest.zip and prints their sizes and sha256 (publish_pack.py does this
for every resort it publishes; this CLI is for trying a split without publishing).
"""
import argparse
import json
import math
import os
import re
import shutil
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

RADIUS = 1000.0     # m round each boot centre: a straight tuck from the Vail start leaves 1 km in 45 to 50 s
CORRIDOR = 300.0    # m either side of a run that passes a boot centre, for its whole length
RUN_NEAR = 150.0    # m: a run passes the centre when one of its points is this close
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
BOOT_JSON = "boot.json"
# tiled sets the boot cuts to its area: height and mask-grid sets by meta key, instance cells on the instance grid
TILE_SETS = ("fine", "mask", "ao", "dir", "moguls")
CELL_SETS = ("trees", "rocks", "shrubs", "stands", "farTrees")
REST_ONLY = ("report.json", "report.md")   # the scorecard: the game never reads it


def tile_grid(meta: dict, kind: str) -> dict | None:
    """(minX, minY, size) of a tiled set's grid, or None when the pack has no such set"""
    if kind in TILE_SETS:
        m = meta["terrain"].get(kind) if kind == "fine" else meta.get(kind)
        return m and {"minX": m["minX"], "minY": m["minY"], "size": m["res"] * m["tileSize"]}
    inst = meta.get("instances")
    return inst and {"minX": inst["minX"], "minY": inst["minY"], "size": inst["cellSize"]}


def seg_dist(px, py, ax, ay, bx, by) -> float:
    ex, ey = bx - ax, by - ay
    l2 = ex * ex + ey * ey
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((px - ax) * ex + (py - ay) * ey) / l2))
    return math.hypot(px - (ax + t * ex), py - (ay + t * ey))


def seg_crosses(a, b, x0, y0, x1, y1) -> bool:
    """does segment a-b touch the rectangle (Liang-Barsky clip)"""
    t0, t1 = 0.0, 1.0
    dx, dy = b[0] - a[0], b[1] - a[1]
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def rect_dist(x0, y0, x1, y1, px, py) -> float:
    return math.hypot(max(x0 - px, 0.0, px - x1), max(y0 - py, 0.0, py - y1))


def first_runs(features: dict, centres: list, near: float = RUN_NEAR) -> list:
    """the runs (point lists) that pass within `near` m of a boot centre"""
    out = []
    for r in features.get("runs", []):
        pts = r.get("points") or []
        if any(math.hypot(p[0] - cx, p[1] - cy) <= near for p in pts for cx, cy in centres):
            out.append(pts)
    return out


def in_area(x0, y0, x1, y1, centres, radius, runs, corridor) -> bool:
    """does the rectangle come within radius of a centre, or within corridor of one of the runs"""
    if any(rect_dist(x0, y0, x1, y1, cx, cy) <= radius for cx, cy in centres):
        return True
    if corridor <= 0:
        return False
    for pts in runs:
        for a, b in zip(pts, pts[1:]):
            # the segment's distance to the rectangle: 0 if it crosses it, else the nearest of its ends and the corners
            sx0, sx1 = min(a[0], b[0]), max(a[0], b[0])
            sy0, sy1 = min(a[1], b[1]), max(a[1], b[1])
            if sx1 < x0 - corridor or sx0 > x1 + corridor or sy1 < y0 - corridor or sy0 > y1 + corridor:
                continue
            if seg_crosses(a, b, x0, y0, x1, y1):
                return True
            # apart, the nearest points are a segment end or a corner of the rectangle
            d = min(rect_dist(x0, y0, x1, y1, a[0], a[1]), rect_dist(x0, y0, x1, y1, b[0], b[1]),
                    *(seg_dist(cx, cy, a[0], a[1], b[0], b[1]) for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))))
            if d <= corridor:
                return True
    return False


def _num(block: str, key: str) -> float | None:
    m = re.search(rf"\b{key}:\s*(-?\d+(?:\.\d+)?)", block)
    return float(m.group(1)) if m else None


def game_start(slug: str, game: str | None) -> tuple | None:
    """the game's Free ride start for the resort (FEAT-132 / FEAT-219), read from its Landmarks.ts, or None"""
    if not game:
        return None
    p = os.path.join(game, "game", "src", "world", "Landmarks.ts")
    if not os.path.isfile(p):
        return None
    src = open(p, encoding="utf-8").read()
    key = re.escape(slug) if re.fullmatch(r"[a-z0-9_]+", slug) else f"'{re.escape(slug)}'"
    lm = re.search(r"export const LANDMARKS[^=]*=\s*\{(.*?)\n\};", src, re.S)
    if lm:
        m = re.search(rf"\n  {key}: \[(.*?)\n  \],", lm.group(1), re.S)
        if m:
            for block in re.split(r"\n    \},", m.group(1)):
                if re.search(r"\bstart:\s*true", block):
                    x, y, h = _num(block, "x"), _num(block, "y"), _num(block, "heading")
                    if x is not None and y is not None:
                        h = math.radians(h or 0.0)   # the rider spawns 15 m uphill of the landmark (START_BACK)
                        return (x - math.sin(h) * 15.0, y - math.cos(h) * 15.0)
    st = re.search(r"const STARTS[^=]*=\s*\{(.*?)\n\};", src, re.S)
    if st:
        m = re.search(rf"\n  {key}: \{{(.*?)\n  \}},", st.group(1), re.S)
        if m:
            x, y = _num(m.group(1), "x"), _num(m.group(1), "y")
            if x is not None and y is not None:
                return (x, y)
    return None


def boot_centres(meta: dict, extra=(), game: str | None = None) -> list:
    out = []
    s = meta.get("start")
    if s:
        out.append((float(s["x"]), float(s["y"])))
    g = game_start(meta["slug"], game)
    if g:
        out.append(g)
    out += [tuple(map(float, c)) for c in extra]
    # one centre per spot (a landmark start a few metres from meta.start adds nothing)
    uniq = []
    for c in out:
        if all(math.hypot(c[0] - u[0], c[1] - u[1]) > 50 for u in uniq):
            uniq.append(c)
    return uniq


def split(pack_dir: str, files: list, centres: list, radius: float = RADIUS, corridor: float = CORRIDOR) -> tuple:
    """(boot files, rest files, boot.json dict) for the pack's zip file list"""
    meta = json.load(open(os.path.join(pack_dir, "meta.json"), encoding="utf-8"))
    fpath = os.path.join(pack_dir, "features.json")
    features = json.load(open(fpath, encoding="utf-8")) if os.path.isfile(fpath) else {}
    runs = first_runs(features, centres) if corridor > 0 else []
    grids = {k: tile_grid(meta, k) for k in TILE_SETS + CELL_SETS}
    boot, rest, tiles = [], [], {}
    for rel in files:
        top, _, name = rel.partition("/")
        if rel in REST_ONLY:
            rest.append(rel)
            continue
        g = grids.get(top) if name and "/" not in name else None
        m = re.fullmatch(r"(-?\d+)_(-?\d+)\.(png|bin)", name) if g else None
        if not m:
            boot.append(rel)                      # meta, features, far / mid / coarse, cover, anything new: all of it
            continue
        tx, ty = int(m.group(1)), int(m.group(2))
        x0, y0 = g["minX"] + tx * g["size"], g["minY"] + ty * g["size"]
        if in_area(x0, y0, x0 + g["size"], y0 + g["size"], centres, radius, runs, corridor):
            boot.append(rel)
            tiles.setdefault(top, []).append(f"{tx}_{ty}")
        else:
            rest.append(rel)
    # every cut set is listed, even with no tile in the area, so the game knows to wait for all of it
    for k in TILE_SETS + CELL_SETS:
        if grids.get(k) and os.path.isdir(os.path.join(pack_dir, k)):
            tiles.setdefault(k, [])
    info = {"boot": 1, "centres": [[round(x, 1), round(y, 1)] for x, y in centres], "radius": radius,
            "corridor": corridor, "runs": len(runs), "tiles": {k: sorted(v) for k, v in sorted(tiles.items())}}
    return boot, rest, info


def write_zip(pack_dir: str, files: list, zip_path: str, extra: dict | None = None) -> tuple:
    """stored zip of `files` (and `extra` {name: bytes}), fixed timestamps; returns (bytes, sha256)"""
    import hashlib
    entries = sorted([(f, None) for f in files] + [(k, v) for k, v in (extra or {}).items()])
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for rel, data in entries:
            info = zipfile.ZipInfo(rel, ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            if data is not None:
                z.writestr(info, data)
                continue
            with open(os.path.join(pack_dir, rel), "rb") as src, z.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return os.path.getsize(zip_path), h.hexdigest()


def write_split(pack_dir: str, files: list, out_dir: str, slug: str, centres: list, radius: float = RADIUS,
                corridor: float = CORRIDOR) -> dict:
    """<out_dir>/<slug>-boot.zip and <slug>-rest.zip; returns {"boot": {path, bytes, sha256, files}, "rest": ..., "info"}"""
    boot, rest, info = split(pack_dir, files, centres, radius, corridor)
    sizes = lambda fs: sum(os.path.getsize(os.path.join(pack_dir, f)) for f in fs)
    info["bootBytes"], info["restBytes"] = sizes(boot), sizes(rest)
    out = {"info": info}
    for part, fs, extra in (("boot", boot, {BOOT_JSON: json.dumps(info, indent=1).encode()}), ("rest", rest, None)):
        zp = os.path.join(out_dir, f"{slug}-{part}.zip")
        size, sha = write_zip(pack_dir, fs, zp, extra)
        out[part] = {"path": zp, "bytes": size, "sha256": sha, "files": len(fs)}
    return out


def by_set(pack_dir: str, files: list) -> dict:
    """bytes per top-level folder (or file), for the printout"""
    out = {}
    for f in files:
        k = f.split("/")[0]
        out[k] = out.get(k, 0) + os.path.getsize(os.path.join(pack_dir, f))
    return out


def main(argv=None) -> None:
    from publish_pack import pack_files
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pack_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--at", action="append", default=[], help="another boot centre, x,y in pack metres")
    ap.add_argument("--radius", type=float, default=RADIUS)
    ap.add_argument("--corridor", type=float, default=CORRIDOR)
    ap.add_argument("--game-repo", help="the game checkout, for its start (default: SBA_GAME_REPO or next to this repo)")
    a = ap.parse_args(argv)
    meta = json.load(open(os.path.join(a.pack_dir, "meta.json"), encoding="utf-8"))
    game = a.game_repo or (paths.game_repo() if paths.has_game(paths.game_repo()) else None)
    centres = boot_centres(meta, [c.split(",") for c in a.at], game)
    os.makedirs(a.out_dir, exist_ok=True)
    files = pack_files(a.pack_dir)
    r = write_split(a.pack_dir, files, a.out_dir, meta["slug"], centres, a.radius, a.corridor)
    info = r["info"]
    print(f"boot centres {info['centres']}, radius {a.radius:.0f} m, {info['runs']} runs with a {a.corridor:.0f} m corridor")
    boot, rest, _ = split(a.pack_dir, files, centres, a.radius, a.corridor)
    b, t = by_set(a.pack_dir, boot), by_set(a.pack_dir, files)
    for k in sorted(t, key=lambda k: -t[k]):
        print(f"  {k:<14} boot {b.get(k, 0) / 1e6:7.1f} MB of {t[k] / 1e6:7.1f} MB"
              + (f"  ({len(info['tiles'][k])} tiles)" if k in info["tiles"] else ""))
    for part in ("boot", "rest"):
        p = r[part]
        print(f"{p['path']}: {p['bytes'] / 1e6:.1f} MB, {p['files']} files, sha256 {p['sha256']}")


if __name__ == "__main__":
    main()
