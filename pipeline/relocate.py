#!/usr/bin/env python3
"""FEAT-249: move an area of a resort next to the rest, so the pack's box is the rideable area.

Boston Mills and Brandywine are one resort 2.5 km apart across the Cuyahoga valley; a box round both is 3.9 x 5.1 km
of valley and woods. The config's `relocate` list cuts each far area out (a box in the config's UTM) and pastes it
near the rest, turned if asked:

    "relocate": [{"name": "Brandywine", "from": [x0, y0, x1, y1], "to": [x, y], "turn_deg": 0, "feather_m": 50}]

`from` is the source box (UTM metres), `to` where its centre lands (UTM), `turn_deg` the turn about that centre,
clockwise seen from above (a slope facing north faces east after 90), `feather_m` the seam: over that band inside
the box's edge the pasted heights blend into the ground there, and every class layer (canopy, imagery, LANDFIRE,
lidar returns) switches from one side to the other along a ragged line through it. `dz_m` (optional) fixes the
height shift; without it the build takes the median step between the ground there and the patch over the band's
outer half, so the patch's rim meets the ground and its own relief is kept whole.

`pack_bbox` (UTM) is the box the pack is built on; `utm_bbox` stays the box the raw data was fetched for (DEM
chunks, NAIP crops, EPT nodes, the far tree ring), so moving an area needs no new download as long as the pack box
and every source box are inside it. `python pipeline/relocate.py <slug>` prints the moves and the pack box: the runs
and lifts after the move plus a buffer (ride_buffer: 300 m at least for a small hill), grown until every pasted
patch is inside it; `--write` puts that box in the config. build_pack.py logs each patch's height shift.

build_pack.py composes the inputs, not the outputs: the DEM, lidar returns, NAIP, LANDFIRE and OSM are moved first,
and the masks, trees, stands, moguls, piste directions and AO are then built from the composed inputs as for any
resort. The mid and far rings stay real (the original site keeps its hill, outside the pack). Pure helpers; tested
in tests/test_relocate.py.
"""
import json, math, os, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

NOISE_CELL_M = 24.0      # the ragged switch line through the seam: value noise on this lattice
NOISE_SPREAD = 0.6       # the switch happens where the seam weight passes 0.5 +- 0.3
SMALL_HILL_M = 2000.0    # a rideable area whose diagonal is under this gets the small-hill buffer
SMALL_HILL_BUFFER_M = 300.0
RIDE_PISTES = ("downhill", "snow_park")
NO_LIFT = ("goods", "zip_line", "station", "pylon")


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


class Move:
    """one relocated area: source box -> destination centre and turn"""

    def __init__(self, spec):
        self.name = spec["name"]
        self.src = [float(v) for v in spec["from"]]
        x0, y0, x1, y1 = self.src
        if not (x1 > x0 and y1 > y0):
            raise ValueError(f"relocate {self.name}: from box {spec['from']} is empty")
        self.to = (float(spec["to"][0]), float(spec["to"][1]))
        self.turn = float(spec.get("turn_deg", 0.0))
        self.feather = float(spec.get("feather_m", 50.0))
        if not 0 < self.feather * 2 < min(x1 - x0, y1 - y0):
            raise ValueError(f"relocate {self.name}: feather_m {self.feather} does not fit in the from box")
        self.dz = spec.get("dz_m")
        self.c = ((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        t = math.radians(self.turn)
        self.cos, self.sin = math.cos(t), math.sin(t)

    def dest_of(self, xs, ys):
        """source UTM -> destination UTM"""
        dx = np.asarray(xs, np.float64) - self.c[0]; dy = np.asarray(ys, np.float64) - self.c[1]
        return self.to[0] + dx * self.cos + dy * self.sin, self.to[1] - dx * self.sin + dy * self.cos

    def src_of(self, xd, yd):
        """destination UTM -> source UTM"""
        dx = np.asarray(xd, np.float64) - self.to[0]; dy = np.asarray(yd, np.float64) - self.to[1]
        return self.c[0] + dx * self.cos - dy * self.sin, self.c[1] + dx * self.sin + dy * self.cos

    def weight_src(self, xs, ys):
        """the seam weight at source points: 1 deeper than feather_m inside the from box, easing to 0 at its edge"""
        x0, y0, x1, y1 = self.src
        xs = np.asarray(xs, np.float64); ys = np.asarray(ys, np.float64)
        d = np.minimum(np.minimum(xs - x0, x1 - xs), np.minimum(ys - y0, y1 - ys))
        return smoothstep(d / self.feather)

    def weight(self, xd, yd):
        """the seam weight at destination points"""
        return self.weight_src(*self.src_of(xd, yd))

    def dest_corners(self):
        x0, y0, x1, y1 = self.src
        return np.stack(self.dest_of([x0, x1, x1, x0], [y0, y0, y1, y1]), axis=1)

    def dest_box(self):
        c = self.dest_corners()
        return [float(c[:, 0].min()), float(c[:, 1].min()), float(c[:, 0].max()), float(c[:, 1].max())]

    def facing(self, az_deg):
        """a compass azimuth in the source -> the same direction after the move"""
        return (az_deg + self.turn) % 360.0

    def record(self):
        return {"name": self.name, "from": self.src, "to": list(self.to), "turnDeg": self.turn,
                "featherM": self.feather, "dzM": None if self.dz is None else round(float(self.dz), 2)}


def _hash01(ix, iy):
    h = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + 1013904223) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return ((h ^ (h >> 16)) & 0xFFFF).astype(np.float64) / 65535.0


def value_noise(x, y, cell=NOISE_CELL_M):
    """smooth 0..1 noise at UTM points, the same wherever and in whatever order it is asked"""
    fx = np.asarray(x, np.float64) / cell; fy = np.asarray(y, np.float64) / cell
    ix = np.floor(fx); iy = np.floor(fy)
    tx = smoothstep(fx - ix); ty = smoothstep(fy - iy)
    ix = ix.astype(np.int64); iy = iy.astype(np.int64)
    a = _hash01(ix, iy); b = _hash01(ix + 1, iy); c = _hash01(ix, iy + 1); d = _hash01(ix + 1, iy + 1)
    return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


class Relocation:
    """the config's moves; falsy when there are none"""

    def __init__(self, cfg):
        self.moves = [Move(s) for s in cfg.get("relocate") or []]
        if len({m.name for m in self.moves}) != len(self.moves):
            raise ValueError("relocate: two moves share a name")

    def __bool__(self):
        return bool(self.moves)

    def threshold(self, xd, yd):
        return 0.5 + NOISE_SPREAD * (value_noise(xd, yd) - 0.5)

    def select(self, xd, yd):
        """per destination point: the index of the move whose patch is drawn there, or -1 for the ground that is
        there. The switch line runs through the seam, ragged (value noise), the same for every layer."""
        xd = np.asarray(xd, np.float64); yd = np.asarray(yd, np.float64)
        sel = np.full(xd.shape, -1, np.int16)
        if not self.moves:
            return sel
        thr = self.threshold(xd, yd)
        for k, m in enumerate(self.moves):
            sel[(sel < 0) & (m.weight(xd, yd) > thr)] = k
        return sel

    def source_xy(self, xd, yd, sel=None):
        """where a destination point's classes are read: its source inside a patch, itself elsewhere"""
        xd = np.asarray(xd, np.float64); yd = np.asarray(yd, np.float64)
        if not self.moves:
            return xd, yd
        sel = self.select(xd, yd) if sel is None else sel
        xs, ys = xd.copy(), yd.copy()
        for k, m in enumerate(self.moves):
            on = sel == k
            if on.any():
                xs[on], ys[on] = m.src_of(xd[on], yd[on])
        return xs, ys

    def check_inside(self, frame, box):
        """the pack box and every source box must lie in the fetched frame (utm_bbox), and every pasted patch in
        the pack box (outside it the mid ring is the real ground, and a patch cut by the pack's edge would step
        against it); messages, empty when fine"""
        def within(b, f):
            return b[0] >= f[0] and b[1] >= f[1] and b[2] <= f[2] and b[3] <= f[3]
        out = []
        if not within(box, frame):
            out.append(f"pack_bbox {box} is not inside utm_bbox {frame} (the raw data covers utm_bbox only)")
        for m in self.moves:
            if not within(m.src, frame):
                out.append(f"relocate {m.name}: from box {m.src} is not inside utm_bbox {frame}")
            d = [round(v) for v in m.dest_box()]
            if not within(d, box):
                out.append(f"relocate {m.name}: the pasted patch {d} is not inside the pack box {box}")
        return out

    # ------------------------------------------------------------------------------------ OSM
    def _labels(self, xs, ys):
        """per source point: move index when it rides along with a patch, -1 to stay, -2 when a patch covers it"""
        xs = np.asarray(xs, np.float64); ys = np.asarray(ys, np.float64)
        lab = np.full(xs.shape, -1, np.int16)
        for k, m in enumerate(self.moves):
            lab[(lab == -1) & (m.weight_src(xs, ys) > 0.5)] = k
        stay = lab == -1
        if stay.any():
            for m in self.moves:
                cover = stay & (m.weight(xs, ys) > 0.5)
                lab[cover] = -2
                stay &= ~cover
        return lab

    def osm(self, doc, to_utm, to_ll, whole=False):
        """an Overpass JSON doc with every element inside a source box moved with it (lon/lat rewritten) and the
        ground a patch covers cleared. Ways that cross a seam are split there (roads, streams); closed ways
        (buildings, water) and, with `whole`, every way (runs and lifts, whose nodes list must stay whole) go
        where most of their points are. Returns (doc, {move name: elements moved})."""
        if not self.moves:
            return doc, {}
        moved = {m.name: 0 for m in self.moves}
        out = []

        def geo(pts):
            lon = np.array([p["lon"] for p in pts], np.float64); lat = np.array([p["lat"] for p in pts], np.float64)
            return to_utm.transform(lon, lat)

        def put(pts, xs, ys, k):
            if k < 0:
                return [dict(p) for p in pts]
            m = self.moves[k]
            dx, dy = m.dest_of(xs, ys)
            lon, lat = to_ll.transform(dx, dy)
            return [{**p, "lon": float(a), "lat": float(b)} for p, a, b in zip(pts, np.atleast_1d(lon), np.atleast_1d(lat))]

        def majority(lab):
            vals, cnt = np.unique(lab, return_counts=True)
            return int(vals[np.argmax(cnt)])

        for el in doc.get("elements", []):
            t = el.get("type")
            if t == "node" and "lat" in el:
                xs, ys = geo([el])
                k = int(self._labels(xs, ys)[0])
                if k == -2:
                    continue
                if k >= 0:
                    p = put([{"lon": el["lon"], "lat": el["lat"]}], xs, ys, k)[0]
                    el = {**el, "lon": p["lon"], "lat": p["lat"]}
                    moved[self.moves[k].name] += 1
                out.append(el)
            elif t == "way" and el.get("geometry"):
                g = el["geometry"]
                xs, ys = geo(g)
                lab = self._labels(xs, ys)
                closed = len(g) > 3 and g[0] == g[-1]
                if whole or closed or (lab == lab[0]).all():
                    k = majority(lab)
                    if k == -2:
                        continue
                    e = {k_: v for k_, v in el.items() if k_ != "bounds"}
                    e["geometry"] = put(g, xs, ys, k)
                    if k >= 0:
                        moved[self.moves[k].name] += 1
                    out.append(e)
                    continue
                # split an open way at every seam crossing
                nodes = el.get("nodes")
                i = 0
                while i < len(g):
                    j = i
                    while j + 1 < len(g) and lab[j + 1] == lab[i]:
                        j += 1
                    k = int(lab[i])
                    if k != -2 and j > i:
                        e = {k_: v for k_, v in el.items() if k_ not in ("bounds", "geometry", "nodes")}
                        e["geometry"] = put(g[i:j + 1], xs[i:j + 1], ys[i:j + 1], k)
                        if nodes and len(nodes) == len(g):
                            e["nodes"] = nodes[i:j + 1]
                        if k >= 0:
                            moved[self.moves[k].name] += 1
                        out.append(e)
                    i = j + 1
            elif t == "relation" and el.get("members"):
                mem = [mm for mm in el["members"] if mm.get("geometry")]
                if not mem:
                    out.append(el); continue
                allg = [p for mm in mem for p in mm["geometry"]]
                xs, ys = geo(allg)
                k = majority(self._labels(xs, ys))
                if k == -2:
                    continue
                if k >= 0:
                    members = []
                    for mm in el["members"]:
                        if mm.get("geometry"):
                            mx, my = geo(mm["geometry"])
                            mm = {**mm, "geometry": put(mm["geometry"], mx, my, k)}
                        members.append(mm)
                    el = {k_: v for k_, v in el.items() if k_ != "bounds"}
                    el["members"] = members
                    moved[self.moves[k].name] += 1
                out.append(el)
            else:
                out.append(el)
        return {**doc, "elements": out}, moved


# ------------------------------------------------------------------------------------------------ grids
# A grid is an array (..., H, W) over a UTM box at `res` metres, row 0 north, cell centres half a cell in. The
# fetched frame (utm_bbox) and the pack box are both on whole 100 m, so the pack's cells are the frame's cells.

def grid_shape(box, res):
    return int(round((box[3] - box[1]) / res)), int(round((box[2] - box[0]) / res))


def sample(src, frame, res, xs, ys, order=0):
    """a frame grid at UTM points: nearest cell (order 0) or bilinear (order 1); leading axes are bands"""
    c = (np.asarray(xs, np.float64) - frame[0]) / res - 0.5
    r = (frame[3] - np.asarray(ys, np.float64)) / res - 0.5
    if order == 0:
        ri = np.clip(np.rint(r).astype(np.int64), 0, src.shape[-2] - 1)
        ci = np.clip(np.rint(c).astype(np.int64), 0, src.shape[-1] - 1)
        return src[..., ri, ci]
    from scipy import ndimage
    if src.ndim == 2:
        return ndimage.map_coordinates(src, [r, c], order=1, mode="nearest")
    return np.stack([ndimage.map_coordinates(b, [r, c], order=1, mode="nearest") for b in src])


def crop(src, frame, res, box):
    """the pack box's cells of a frame grid (a view)"""
    c0 = (box[0] - frame[0]) / res; r0 = (frame[3] - box[3]) / res
    if abs(c0 - round(c0)) > 1e-6 or abs(r0 - round(r0)) > 1e-6:
        raise ValueError(f"box {box} is not on the {res:g} m grid of {frame}")
    h, w = grid_shape(box, res); c0, r0 = int(round(c0)), int(round(r0))
    return src[..., r0:r0 + h, c0:c0 + w]


def _windows(rel, box, res):
    """per move: (index, rows slice, cols slice, X, Y): the pack cells under its pasted patch and their centres"""
    h, w = grid_shape(box, res)
    for k, m in enumerate(rel.moves):
        d = m.dest_box()
        c0 = max(0, int(math.floor((d[0] - box[0]) / res))); c1 = min(w, int(math.ceil((d[2] - box[0]) / res)))
        r0 = max(0, int(math.floor((box[3] - d[3]) / res))); r1 = min(h, int(math.ceil((box[3] - d[1]) / res)))
        if c1 <= c0 or r1 <= r0:
            continue
        X, Y = np.meshgrid(box[0] + (np.arange(c0, c1) + 0.5) * res, box[3] - (np.arange(r0, r1) + 0.5) * res)
        yield k, slice(r0, r1), slice(c0, c1), X, Y


def rim_dz(dem, frame, res, move):
    """the height shift that sets a patch on the ground there: the median step between the ground and the patch
    over the outer half of the seam (relief inside the patch is kept whole)"""
    if move.dz is not None:
        return float(move.dz)
    d = move.dest_box()
    X, Y = np.meshgrid(np.arange(d[0] + res / 2, d[2], res), np.arange(d[3] - res / 2, d[1], -res))
    w = move.weight(X, Y)
    band = (w > 0) & (w < 0.5)
    sx, sy = move.src_of(X[band], Y[band])
    return float(np.median(sample(dem, frame, res, X[band], Y[band], 1) - sample(dem, frame, res, sx, sy, 1)))


def compose_heights(dem, frame, res, box, rel, dzs):
    """the pack's heights: the ground in the pack box, each patch pasted with its shift, eased in over the seam"""
    out = np.array(crop(dem, frame, res, box), dtype=dem.dtype)
    for k, rs, cs, X, Y in _windows(rel, box, res):
        m = rel.moves[k]
        w = m.weight(X, Y); on = w > 0
        sx, sy = m.src_of(X[on], Y[on])
        win = out[rs, cs]
        win[on] = (w[on] * (sample(dem, frame, res, sx, sy, 1) + dzs[k]) + (1 - w[on]) * win[on]).astype(dem.dtype)
    return out


def compose_classes(src, frame, res, box, rel):
    """a class or imagery grid (leading axes are bands) for the pack: each cell from its source, nearest cell"""
    out = np.array(crop(src, frame, res, box))
    for k, rs, cs, X, Y in _windows(rel, box, res):
        on = rel.select(X, Y) == k
        if not on.any():
            continue
        sx, sy = rel.moves[k].src_of(X[on], Y[on])
        win = out[..., rs, cs]
        win[..., on] = sample(src, frame, res, sx, sy, 0)
    return out


# ------------------------------------------------------------------------------------------------ the pack box

def ride_points(ski, lonlat_bbox=None):
    """lon/lat points of the downhill runs and lifts in an Overpass ski doc (private ones are the caller's to drop);
    with `lonlat_bbox`, only ways whose first point is inside it"""
    pts = []
    for el in ski.get("elements", []):
        if el.get("type") != "way" or not el.get("geometry"):
            continue
        t = el.get("tags", {})
        if not (t.get("piste:type") in RIDE_PISTES or (t.get("aerialway") and t["aerialway"] not in NO_LIFT)):
            continue
        g = el["geometry"]
        if lonlat_bbox:
            lo0, la0, lo1, la1 = lonlat_bbox
            if not (lo0 <= g[0]["lon"] <= lo1 and la0 <= g[0]["lat"] <= la1):
                continue
        pts.extend((p["lon"], p["lat"]) for p in g)
    return pts


def ride_buffer(diag_m):
    """FEAT-249: the buffer round the rideable area. A small hill (diagonal under 2 km) gets 30 % of it, at least
    300 m; anything bigger keeps resort.py's rule (30 %, 500 to 1000 m)"""
    if diag_m < SMALL_HILL_M:
        return int(round(max(SMALL_HILL_BUFFER_M, 0.3 * diag_m) / 100.0) * 100)
    return int(round(min(1000.0, max(500.0, 0.3 * diag_m)) / 100.0) * 100)


def ride_box(xy):
    """(pack box outward to 100 m, buffer, rideable box, its diagonal) from UTM points of the runs and lifts"""
    xs = [p[0] for p in xy]; ys = [p[1] for p in xy]
    rb = [min(xs), min(ys), max(xs), max(ys)]
    diag = math.hypot(rb[2] - rb[0], rb[3] - rb[1])
    buf = ride_buffer(diag)
    box = [math.floor((rb[0] - buf) / 100) * 100, math.floor((rb[1] - buf) / 100) * 100,
           math.ceil((rb[2] + buf) / 100) * 100, math.ceil((rb[3] + buf) / 100) * 100]
    return box, buf, rb, diag


def grow_to_patches(box, rel):
    """the box grown (to 100 m) until every pasted patch, seam and all, is inside it"""
    box = list(box)
    for m in rel.moves:
        d = m.dest_box()
        box = [min(box[0], math.floor(d[0] / 100) * 100), min(box[1], math.floor(d[1] / 100) * 100),
               max(box[2], math.ceil(d[2] / 100) * 100), max(box[3], math.ceil(d[3] / 100) * 100)]
    return box


# ------------------------------------------------------------------------------------------------ CLI

def main(argv):
    import argparse
    from pyproj import Transformer
    import paths, osm_filter
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--raw", help="the resort's raw folder (default <raw root>/<slug>)")
    ap.add_argument("--write", action="store_true", help="write the pack box into the config as pack_bbox")
    a = ap.parse_args(argv)
    cfg_p = paths.config_path(a.slug)
    cfg = json.load(open(cfg_p, encoding="utf-8"))
    raw = a.raw or os.path.join(paths.raw_root(), a.slug)
    rel = Relocation(cfg)
    to_utm = Transformer.from_crs("EPSG:4326", cfg["crs"], always_xy=True)
    to_ll = Transformer.from_crs(cfg["crs"], "EPSG:4326", always_xy=True)
    ski = json.load(open(os.path.join(raw, "osm", "ski.json"), encoding="utf-8"))
    ski, _ = osm_filter.filter_ski(ski, osm_filter.exclude_areas(cfg.get("exclude"), ski))
    ski, moved = rel.osm(ski, to_utm, to_ll, whole=True)
    for m in rel.moves:
        print(f"{m.name}: from {m.src} to {m.to}, turned {m.turn:+.0f} deg, seam {m.feather:.0f} m; "
              f"{moved.get(m.name, 0)} ski elements move")
    pts = ride_points(ski, None if rel else cfg["lonlat_bbox"])
    if not pts:
        print("no downhill runs or lifts in osm/ski.json"); return 1
    xs, ys = to_utm.transform(np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
    if rel:      # the ski area box, grown to take the moved areas, keeps stray far runs out
        lo0, la0, lo1, la1 = cfg["lonlat_bbox"]
        ex, ey = to_utm.transform(np.array([lo0, lo1, lo0, lo1]), np.array([la0, la0, la1, la1]))
        bx = [min(ex), min(ey), max(ex), max(ey)]
        for m in rel.moves:
            d = m.dest_box(); bx = [min(bx[0], d[0]), min(bx[1], d[1]), max(bx[2], d[2]), max(bx[3], d[3])]
        keep = (xs >= bx[0]) & (xs <= bx[2]) & (ys >= bx[1]) & (ys <= bx[3])
        xs, ys = xs[keep], ys[keep]
    box, buf, rb, diag = ride_box(list(zip(xs, ys)))
    print(f"runs and lifts {rb[2] - rb[0]:.0f} x {rb[3] - rb[1]:.0f} m (diagonal {diag:.0f} m), buffer {buf} m: "
          f"box {box}")
    box = grow_to_patches(box, rel)
    print(f"pack box with every pasted patch inside it: {box}, {(box[2] - box[0]) / 1000:.2f} x "
          f"{(box[3] - box[1]) / 1000:.2f} km")
    fb = cfg["utm_bbox"]
    print(f"fetched box {fb}: the pack is {(box[2] - box[0]) * (box[3] - box[1]) / ((fb[2] - fb[0]) * (fb[3] - fb[1])) * 100:.0f}% of its area")
    bad = rel.check_inside(fb, box)
    for b in bad:
        print("  !", b)
    if a.write:
        if bad:
            print("not written"); return 1
        cfg.pop("pack_bbox", None)      # next to utm_bbox, where a reader looks for the box
        cfg = {k2: v2 for k, v in cfg.items() for k2, v2 in ([(k, v), ("pack_bbox", box)] if k == "utm_bbox" else [(k, v)])}
        with open(cfg_p, "w", encoding="utf-8", newline="\n") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote pack_bbox to {cfg_p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
