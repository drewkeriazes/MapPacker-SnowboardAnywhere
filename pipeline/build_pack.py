#!/usr/bin/env python3
"""Build a resort pack from the raw downloads.

python3 pipeline/build_pack.py vail <raw_dir> <out_dir>

Steps
  1. DEM: mosaic the 1 m 3DEP chunks (F32 GeoTIFF, UTM) -> fine height set
  2. Mid ring: 10 m 3DEP export -> resampled to 16 m -> mid set
  3. Far ring: Mapterhorn z11 WebP tiles (Terrarium, Web Mercator) -> reprojected to a 128 m UTM grid -> far set
  4. Lidar: EPT LAZ nodes -> DSM (max per 2 m cell) -> canopy height model = DSM - DEM
  5. NAIP: 4-band 1 m -> NDVI, brightness -> canopy / aspen / rock / scree / meadow classes
  FEAT-225 Silver and Bronze (tiers.py, tier_sources.py), read from the config: `dem.source` "Mapterhorn" builds
  steps 1 and 2 from Mapterhorn tiles at the plan's zooms; no `lidar` makes step 4's canopy height model the ETH
  10 m canopy height on WorldCover tree cover, with no crowns (the trees are all stands, step 8) and no far tree
  ring; no `naip` makes step 5's masks from the WorldCover classes. `meta.json` records `tier` and `sources`.
  6. OSM: pistes, lifts (+pylons, stations), buildings, roads, water, peaks -> features.json
  7. Masks (2 m): rock, scree, groomed piste corridors, canopy cover; piste direction for the groomers
  8. Trees: crown detection on the CHM/NDVI, species 0..7 (species.py: LANDFIRE class, elevation, aspect,
     water, ridges, grey dead crowns); shrubs from LANDFIRE, streams, NAIP and forest edges; rocks on the rock mask
  9. Write the pack
"""
import json, math, os, sys, glob, time
import numpy as np
from PIL import Image
import tifffile
from scipy import ndimage
from pyproj import Transformer
from packwriter import (FORMAT_VERSION, write_height_set, write_mask_set, write_instances, write_meta, write_features, decode_terrarium)
from piste_dir import piste_direction
from terrain_ao import sky_visibility
from moguls import run_mogul_score, slope_window, paint_field, paint_polygon
from canopy_spots import run_half_width   # run corridor half widths, shared with the BUG-028 canopy measure
import species as spc
import paths
import stands
import tiers
import tier_sources as ts
from species import evt_luts

slug = sys.argv[1]
raw = sys.argv[2]
out = sys.argv[3]
cfg = json.load(open(paths.config_path(slug), encoding="utf-8"))
if cfg.get("source_only"):
    sys.exit(f"{slug} is a relocate source (source_only): it is fetched for another pack, not built")
# FEAT-268: `raw_from` names the resort whose raw data and manifest this config builds on (Ohio Hills is Boston
# Mills' data with Mad River moved in); `raw` is then that resort's raw folder
DATA = cfg.get("raw_from") or slug
manifest = json.load(open(os.path.join(paths.MANIFESTS, f"{DATA}.json"), encoding="utf-8"))
os.makedirs(out, exist_ok=True)
T0 = time.time()
def log(*a):
    print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)

OX, OY = cfg["origin"]
# FEAT-249: the raw data covers utm_bbox (FRAME); the pack is built on pack_bbox, the rideable area, which defaults
# to the same box. The config's `relocate` moves (relocate.py) paste far areas into it. The DEM, lidar returns,
# NAIP, LANDFIRE and OSM are composed first; everything after is built from them as for any resort.
import relocate
try:
    # FEAT-268: a move with a `source` cuts from that place's own raw folder <raw root>/<source> and manifest
    SRC_CFG = relocate.source_configs(cfg)
except ValueError as e:
    sys.exit(str(e))
REL = relocate.Relocation(cfg, {s: c["utm_bbox"] for s, c in SRC_CFG.items()})
SRC_RAW = {s: os.path.join(os.path.dirname(os.path.normpath(raw)), s) for s in SRC_CFG}
SRC_MAN = {}
for _s, _p in SRC_RAW.items():
    _mp = os.path.join(paths.MANIFESTS, f"{_s}.json")
    if not os.path.isfile(os.path.join(_p, "FETCH_COMPLETE.txt")) or not os.path.isfile(_mp):
        sys.exit(f"relocate source {_s}: no fetched raw data in {_p} or no {_mp} "
                 f"(python pipeline/build_resort.py {_s} --stop-after landfire)")
    SRC_MAN[_s] = json.load(open(_mp, encoding="utf-8"))
if DATA != slug:
    _own = json.load(open(paths.config_path(DATA), encoding="utf-8"))
    if _own.get("origin") != cfg.get("origin") or _own.get("utm_bbox") != cfg.get("utm_bbox"):
        sys.exit(f"raw_from {DATA}: origin and utm_bbox must be {DATA}'s (the rings and the frame are its data)")
FRAME = [float(v) for v in cfg["utm_bbox"]]
X0, Y0, X1, Y1 = cfg.get("pack_bbox") or cfg["utm_bbox"]           # UTM metres
COMPOSED = bool(REL) or [X0, Y0, X1, Y1] != FRAME
_bad = REL.check_inside(FRAME, [X0, Y0, X1, Y1])
if _bad:
    sys.exit("; ".join(_bad))
W = X1 - X0; H = Y1 - Y0                   # 1 m grid size
crs = cfg["crs"]
to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
to_utm = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
merc_to_utm = Transformer.from_crs("EPSG:3857", crs, always_xy=True)

def read_tiff(path):
    return tifffile.imread(path)

# FEAT-225: which source builds each layer (tiers.py): Mapterhorn terrain outside the US, stands from the ETH canopy
# height without lidar, masks from WorldCover without NAIP
LIDAR = bool(cfg.get("lidar"))
NAIP = bool(cfg.get("naip"))
SOURCES = tiers.layer_sources(cfg)
if REL.source_slugs() and not (LIDAR and NAIP):
    # landcover2() reads this resort's own WorldCover and ETH canopy only, so a move cut from another place's raw
    # data (FEAT-268) would get this frame's cover pasted at its new place
    sys.exit("a relocate move with a `source` needs lidar and NAIP: the WorldCover and ETH layers a Silver or Bronze "
             "build reads are not taken from the source's raw data yet")
log("sources: " + tiers.summary(SOURCES) + f"; tier {tiers.tier_of({k: v['tier'] for k, v in SOURCES.items()})[0]}")

# ------------------------------------------------------------------ 1. fine DEM (1 m)
log("DEM mosaic")
FX0, FY0, FX1, FY1 = FRAME


def mosaic_dem(raw, manifest, frame, dem_cfg=None):
    """the 1 m DEM of a raw folder on its fetched frame (row 0 = north), small voids filled: the 3DEP chunks, on
    Mapterhorn's tiles at the plan's zoom when `dem_cfg` names Mapterhorn (FEAT-225)"""
    FX0, FY0, FX1, FY1 = frame
    dem = np.full((int(FY1 - FY0), int(FX1 - FX0)), np.nan, np.float32)
    mt = tiers.uses_mapterhorn(dem_cfg)
    if mt:
        # FEAT-225: Mapterhorn's tiles at the plan's zoom (about 0.8 m at 47 deg for z16), bilinear onto the 1 m frame
        dem, _n = ts.mapterhorn_grid(raw, dem_cfg["zoom"], to_ll, FX0, FY1, 1.0, dem.shape[1], dem.shape[0])
        log(f"  Mapterhorn z{dem_cfg['zoom']}: {_n} tiles")
    for it in manifest["items"]:
        if not it["path"].startswith("dem1m/"):
            continue
        p = os.path.join(raw, it["path"])
        if not os.path.exists(p):
            log("  missing", it["path"]); continue
        a = read_tiff(p).astype(np.float32)
        if a.ndim == 3: a = a[..., 0]
        a[a <= -9000] = np.nan
        bx0, by0, bx1, by1 = it["meta"]["bbox"]
        w, h = it["meta"]["size"]
        if a.shape != (h, w):
            log("  unexpected shape", it["path"], a.shape, (h, w))
            a = np.array(Image.fromarray(a).resize((w, h), Image.BILINEAR))
        c0 = int(bx0 - FX0); r0 = int(FY1 - by1)
        dem[r0:r0 + h, c0:c0 + w] = a
    void = np.isnan(dem)
    log(f"  dem {dem.shape}, void {void.mean()*100:.2f}%, range {np.nanmin(dem):.0f}..{np.nanmax(dem):.0f}")
    if void.any():
        # fill small voids by nearest neighbour
        idx = ndimage.distance_transform_edt(void, return_distances=False, return_indices=True)
        dem = dem[tuple(idx)]
    if mt:
        dem = ndimage.gaussian_filter(dem, ts.DEQUANT_SIGMA_M).astype(np.float32)   # FEAT-225: Mapterhorn's height steps
    return dem


dem = mosaic_dem(raw, manifest, FRAME, cfg["dem"])
# FEAT-268: {move index: (DEM, frame)} for the moves cut from another place's raw data
SRC_DEM = {}
for _s in REL.source_slugs():
    log(f"  relocate source {_s}")
    _g = (mosaic_dem(SRC_RAW[_s], SRC_MAN[_s], SRC_CFG[_s]["utm_bbox"], SRC_CFG[_s].get("dem")),
          [float(v) for v in SRC_CFG[_s]["utm_bbox"]])
    SRC_DEM.update({k: _g for k, m in enumerate(REL.moves) if m.source == _s})
dem_f = None    # the frame's DEM, kept while the lidar returns are set on the composed ground
REL_DZ = []
if COMPOSED:
    dem_f = dem
    REL_DZ = [relocate.rim_dz(dem_f, FRAME, 1.0, m, SRC_DEM.get(k)) for k, m in enumerate(REL.moves)]
    for m, dz in zip(REL.moves, REL_DZ):
        m.dz = dz
        log(f"  relocate {m.name}: {m.src}{f' of {m.source}' if m.source else ''} -> centre {m.to}, turned "
            f"{m.turn:+.0f} deg, seam {m.feather:.0f} m, height shift {dz:+.1f} m")
    dem = relocate.compose_heights(dem_f, FRAME, 1.0, [X0, Y0, X1, Y1], REL, REL_DZ, SRC_DEM)
    log(f"  pack box {X1 - X0:.0f} x {Y1 - Y0:.0f} m of the fetched {FX1 - FX0:.0f} x {FY1 - FY0:.0f} m, "
        f"range {dem.min():.0f}..{dem.max():.0f}")
fine_meta = write_height_set(out, "fine", dem, 1.0, X0 - OX, Y0 - OY)
log("  fine written", fine_meta["tilesX"], "x", fine_meta["tilesY"])
# FEAT-229: the 4 m set the 4 and 8 m chunks read instead of the 1 m tiles (coarse_set.py)
from coarse_set import write_coarse
coarse_meta = write_coarse(out, dem, X0 - OX, Y0 - OY)
log("  coarse written", coarse_meta["tilesX"], "x", coarse_meta["tilesY"])

# ------------------------------------------------------------------ 2. mid (16 m from the 10 m export)
log("mid ring")
mid_items = [i for i in manifest["items"] if i["path"].startswith("dem10m/")]
if tiers.uses_mapterhorn(cfg["mid_ring"]):
    # FEAT-225: the mid ring from Mapterhorn at the plan's zoom (z13 is about 6.5 m at 47 deg) on the 10 m grid
    _S = cfg["mid_ring"]["size_m"]; MR = float(cfg["mid_ring"]["res_m"])
    mx0, my0, mx1, my1 = OX - _S / 2, OY - _S / 2, OX + _S / 2, OY + _S / 2
    mW = int(round((mx1 - mx0) / MR)); mH = int(round((my1 - my0) / MR))
    m, _n = ts.mapterhorn_grid(raw, cfg["mid_ring"]["zoom"], to_ll, mx0, my1, MR, mW, mH)
    log(f"  Mapterhorn z{cfg['mid_ring']['zoom']}: {_n} tiles")
else:
    mx0 = min(i["meta"]["bbox"][0] for i in mid_items); my0 = min(i["meta"]["bbox"][1] for i in mid_items)
    mx1 = max(i["meta"]["bbox"][2] for i in mid_items); my1 = max(i["meta"]["bbox"][3] for i in mid_items)
    MR = mid_items[0]["meta"]["res"]
    mW = int(round((mx1 - mx0) / MR)); mH = int(round((my1 - my0) / MR))
    m = np.full((mH, mW), np.nan, np.float32)
for it in mid_items:
    p = os.path.join(raw, it["path"])
    if not os.path.exists(p):
        log("  missing", it["path"]); continue
    a = read_tiff(p).astype(np.float32)
    if a.ndim == 3: a = a[..., 0]
    a[a <= -9000] = np.nan
    bx0, by0, bx1, by1 = it["meta"]["bbox"]; w, h = it["meta"]["size"]
    if a.shape != (h, w):
        a = np.array(Image.fromarray(a).resize((w, h), Image.BILINEAR))
    c0 = int(round((bx0 - mx0) / MR)); r0 = int(round((my1 - by1) / MR))
    m[r0:r0 + h, c0:c0 + w] = a
log(f"  mid {m.shape} at {MR} m, void {np.isnan(m).mean()*100:.2f}%")
# 10 m -> 16 m by resampling
n16 = int((mx1 - mx0) / 16)
m16 = np.array(Image.fromarray(np.nan_to_num(m, nan=np.nanmean(m))).resize((n16, n16), Image.BILINEAR), np.float32)
mid_meta = write_height_set(out, "mid", m16, 16.0, mx0 - OX, my0 - OY)

# ------------------------------------------------------------------ 3. far (128 m from Mapterhorn z11)
log("far ring")
far_size = cfg["far_ring"]["size_m"]
FR = 128.0
nf = int(far_size / FR)
fx0 = OX - far_size / 2; fy0 = OY - far_size / 2
# target grid centres in UTM -> lon/lat -> mercator tile pixel
xs = fx0 + (np.arange(nf) + 0.5) * FR
ys = fy0 + (np.arange(nf)[::-1] + 0.5) * FR   # row 0 = north
GX, GY = np.meshgrid(xs, ys)
lon, lat = to_ll.transform(GX, GY)
z = cfg["far_ring"]["mapterhorn_zoom"]; n = 2 ** z
FAR_DIR = f"mapterhorn/{z}/"      # FEAT-225: the resort box and the mid ring may have tiles at other zooms
px = (lon + 180) / 360 * n * 512
py = (1 - np.log(np.tan(np.radians(lat)) + 1 / np.cos(np.radians(lat))) / np.pi) / 2 * n * 512
far = np.full((nf, nf), np.nan, np.float32)
tiles = {}
for it in manifest["items"]:
    if it["path"].startswith(FAR_DIR):
        p = os.path.join(raw, it["path"])
        if os.path.exists(p):
            tx, ty = os.path.basename(it["path"])[:-5].split("_")
            tiles[(int(tx), int(ty))] = decode_terrarium(np.array(Image.open(p).convert("RGB")))
tx = np.floor(px / 512).astype(int); ty = np.floor(py / 512).astype(int)
cx = np.clip((px - tx * 512).astype(int), 0, 511); cy = np.clip((py - ty * 512).astype(int), 0, 511)
for (ax, ay), arr in tiles.items():
    sel = (tx == ax) & (ty == ay)
    if sel.any():
        far[sel] = arr[cy[sel], cx[sel]]
log(f"  far coverage {np.isfinite(far).mean()*100:.1f}% from {len(tiles)} tiles")
far_meta = write_height_set(out, "far", far, FR, fx0 - OX, fy0 - OY)

# ------------------------------------------------------------------ 4. canopy height model from lidar (or ETH, FEAT-225)
R2 = 2.0
H2, W2 = H // 2, W // 2
PACK_BOX = [X0, Y0, X1, Y1]


def place_returns(ux, uy, zz, cls, src=None):
    """FEAT-249: the returns of one node for the pack: at their own place where the ground there is drawn, at their
    moved place inside a pasted patch (relocate.Relocation.select decides, as for every other layer). A return keeps
    its height above the ground it was flown over, set on the composed ground. `src` (FEAT-268): the node is from
    that relocate source's lidar, so only its moves take returns and the rest of the node is dropped."""
    def inb(x, y):
        return (x >= X0) & (x < X1) & (y >= Y0) & (y < Y1)
    xs, ys, zs, cs = [], [], [], []
    k = inb(ux, uy) if src is None else np.zeros(ux.shape, bool)
    if k.any():
        k[k] = REL.select(ux[k], uy[k]) == -1
    if k.any():
        x, y = ux[k], uy[k]
        xs.append(x); ys.append(y); cs.append(cls[k])
        zs.append(zz[k] - relocate.sample(dem_f, FRAME, 1.0, x, y) + relocate.sample(dem, PACK_BOX, 1.0, x, y))
    for i, m in enumerate(REL.moves):
        if m.source != src:
            continue
        g, gf = SRC_DEM.get(i, (dem_f, FRAME))
        sx0, sy0, sx1, sy1 = m.src
        k = (ux >= sx0) & (ux < sx1) & (uy >= sy0) & (uy < sy1)
        if not k.any():
            continue
        sx, sy, sz, sc = ux[k], uy[k], zz[k], cls[k]
        dx, dy = m.dest_of(sx, sy)
        ok = inb(dx, dy)
        ok[ok] = REL.select(dx[ok], dy[ok]) == i
        if not ok.any():
            continue
        xs.append(dx[ok]); ys.append(dy[ok]); cs.append(sc[ok])
        zs.append(sz[ok] - relocate.sample(g, gf, 1.0, sx[ok], sy[ok]) + relocate.sample(dem, PACK_BOX, 1.0, dx[ok], dy[ok]))
    if not xs:
        return ux[:0], uy[:0], zz[:0], cls[:0]
    return np.concatenate(xs), np.concatenate(ys), np.concatenate(zs), np.concatenate(cs)



FH2, FW2 = int(FY1 - FY0) // 2, int(FX1 - FX0) // 2      # the fetched frame at 2 m (FEAT-249)
_lc = {}


def landcover2():
    """FEAT-225: WorldCover classes and ETH canopy height on the pack's 2 m grid (frame read, then composed)"""
    if not _lc:
        wc_f, eth_f = ts.landcover_grid(raw, to_ll, FX0, FY1, R2, FW2, FH2)
        if COMPOSED:
            wc_f = relocate.compose_classes(wc_f, FRAME, R2, PACK_BOX, REL)
            eth_f = relocate.compose_classes(eth_f, FRAME, R2, PACK_BOX, REL)
        _lc["wc"], _lc["eth"] = wc_f[:H2, :W2], eth_f[:H2, :W2]
        v, c_ = np.unique(_lc["wc"], return_counts=True)
        log("  WorldCover on the pack: " + ", ".join(f"class {int(k)} {n / c_.sum() * 100:.0f}%" for n, k in sorted(zip(c_, v), reverse=True)[:6]))
    return _lc["wc"], _lc["eth"]


def add_laz(p, src=None):
    """one EPT node's returns into the 2 m DSM (`src`: a relocate source's node, FEAT-268)"""
    global n_pts
    try:
        las = laspy.read(p)
    except Exception as e:
        log("  bad laz", p, e); return
    x = np.asarray(las.x); y = np.asarray(las.y); zz = np.asarray(las.z)
    cls = np.asarray(las.classification)
    # EPT is in EPSG:3857; convert to UTM
    ux, uy = merc_to_utm.transform(x, y)
    if COMPOSED:
        ux, uy, zz, cls = place_returns(np.asarray(ux), np.asarray(uy), zz, cls, src)
    col = ((ux - X0) / R2).astype(int); row = ((Y1 - uy) / R2).astype(int)
    ok = (col >= 0) & (col < W2) & (row >= 0) & (row < H2) & (cls != 7) & (cls != 18)  # drop noise classes
    col, row, zz, cls = col[ok], row[ok], zz[ok], cls[ok]
    n_pts += len(zz)
    flat = row * W2 + col
    np.maximum.at(dsm.ravel(), flat, zz.astype(np.float32))
    np.add.at(cnt.ravel(), flat, 1)
    g = cls == 2
    if g.any():
        np.minimum.at(dtm_l.ravel(), flat[g], zz[g].astype(np.float32))


def laz_files(raw):
    """ept/*.laz is the main dataset, ept/<dataset>/*.laz any extra one (cfg["lidar"]["extra"]); all EPSG:3857"""
    return sorted(glob.glob(os.path.join(raw, "ept", "*.laz")) + glob.glob(os.path.join(raw, "ept", "*", "*.laz")))


if LIDAR:
    log("lidar -> DSM")
    import laspy
    dsm = np.full((H2, W2), -1e9, np.float32)
    cnt = np.zeros((H2, W2), np.int32)
    dtm_l = np.full((H2, W2), 1e9, np.float32)
    n_pts = 0
    for p in laz_files(raw):
        add_laz(p)
    for _s in REL.source_slugs():
        _n0 = n_pts
        for p in laz_files(SRC_RAW[_s]):
            add_laz(p, _s)
        log(f"  relocate source {_s}: {(n_pts - _n0) / 1e6:.1f} M points")
    log(f"  {n_pts/1e6:.1f} M points, cells with data {np.mean(cnt>0)*100:.1f}%")
    del dem_f, SRC_DEM
    dsm[cnt == 0] = np.nan
    # cells with a lidar return (dilated by one cell): canopy is only believed where the lidar actually saw something
    has_pts = ndimage.binary_dilation(cnt > 0, iterations=1)
    del cnt, dtm_l
    # DEM at 2 m (mean of 2x2)
    dem2 = dem[:H2 * 2, :W2 * 2].reshape(H2, 2, W2, 2).mean(axis=(1, 3)).astype(np.float32)
    chm = dsm - dem2
    del dsm
    chm[np.isnan(chm)] = 0
    chm = np.clip(chm, 0, 60).astype(np.float32)
    # fill isolated empty cells from neighbours
    chm = ndimage.grey_closing(chm, size=3)
    log(f"  CHM: {np.mean(chm>2)*100:.1f}% of cells > 2 m, p99 {np.percentile(chm, 99):.1f} m")
else:
    # FEAT-225 (Silver trees): no lidar, so no crowns. The canopy height model is the ETH 10 m model, smoothed and
    # kept on WorldCover tree cover; every cell may hold canopy (no lidar return test); the stems come from stage 8.
    log("no lidar: canopy height from the ETH 10 m canopy height on WorldCover tree cover (no crowns)")
    del dem_f, SRC_DEM
    dem2 = dem[:H2 * 2, :W2 * 2].reshape(H2, 2, W2, 2).mean(axis=(1, 3)).astype(np.float32)
    _wc2, _eth2 = landcover2()
    # on WorldCover tree cover only, also with NAIP: the smooth ETH model reads 3 to 5 m over every meadow and run next
    # to a stand, which NAIP's NDVI alone (summer grass is green) can't tell from forest (Boston Mills: 75 % canopy
    # on the run centre lines instead of 1 %)
    chm = ts.canopy_height(_eth2, _wc2, R2)
    has_pts = np.ones((H2, W2), bool)
    log(f"  CHM (ETH): {np.mean(chm>2)*100:.1f}% of cells > 2 m, p99 {np.percentile(chm, 99):.1f} m")

# ------------------------------------------------------------------ 5. NAIP classes (1 m)
# The Planetary Computer crop endpoint capped every crop at 2048 px, so the crops are ~2 m.
# Work at the 2 m grid directly: resample each crop onto its bbox.
def mosaic_naip(raw, manifest, frame):
    """the NAIP crops of a raw folder on its fetched frame at 2 m (FEAT-249): (bands, covered)"""
    FX0, FY0, FX1, FY1 = frame
    FH2, FW2 = int(FY1 - FY0) // 2, int(FX1 - FX0) // 2
    naip2 = np.zeros((4, FH2, FW2), np.uint8)
    have2 = np.zeros((FH2, FW2), bool)
    for it in manifest["items"]:
        if not it["path"].startswith("naip1m/"):
            continue
        p = os.path.join(raw, it["path"])
        if not os.path.exists(p):
            continue
        a = read_tiff(p)
        if a.ndim == 3 and a.shape[0] in (4, 5) and a.shape[0] < a.shape[2]:
            a = np.moveaxis(a, 0, -1)
        bx0, by0, bx1, by1 = it["meta"]["bbox"]
        w2 = int(round((bx1 - bx0) / R2)); h2 = int(round((by1 - by0) / R2))
        bands = np.stack([np.array(Image.fromarray(a[..., b]).resize((w2, h2), Image.BILINEAR)) for b in range(4)], axis=-1)
        c0 = int(round((bx0 - FX0) / R2)); r0 = int(round((FY1 - by1) / R2))
        c0c, r0c = max(c0, 0), max(r0, 0)
        c1c, r1c = min(c0 + w2, FW2), min(r0 + h2, FH2)
        if c1c <= c0c or r1c <= r0c:
            continue
        sub = bands[r0c - r0:r1c - r0, c0c - c0:c1c - c0]
        valid = sub.sum(axis=-1) > 0
        dst = naip2[:, r0c:r1c, c0c:c1c]
        for b in range(4):
            dst[b][valid] = sub[..., b][valid]
        have2[r0c:r1c, c0c:c1c] |= valid
    return naip2, have2


# slope at 2 m
gy, gx = np.gradient(dem2, R2)
slope2 = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
# gx, gy stay alive for the mogul aspect term (freed after scoring)
import naip_calib
if NAIP:
    log("NAIP")
    naip2, have2 = mosaic_naip(raw, manifest, FRAME)
    if COMPOSED:
        SRC_NAIP, SRC_HAVE = {}, {}     # FEAT-268: {move index: (grid, frame)} for the sourced moves
        for _s in REL.source_slugs():
            _f = [float(v) for v in SRC_CFG[_s]["utm_bbox"]]
            _n, _h = mosaic_naip(SRC_RAW[_s], SRC_MAN[_s], _f)
            for k, m in enumerate(REL.moves):
                if m.source == _s:
                    SRC_NAIP[k], SRC_HAVE[k] = (_n, _f), (_h, _f)
        naip2 = relocate.compose_classes(naip2, FRAME, R2, PACK_BOX, REL, SRC_NAIP)
        have2 = relocate.compose_classes(have2, FRAME, R2, PACK_BOX, REL, SRC_HAVE)
        del SRC_NAIP, SRC_HAVE
    log(f"  NAIP coverage {have2.mean()*100:.1f}%")
    red2 = naip2[0].astype(np.float32); grn2 = naip2[1].astype(np.float32); blu2 = naip2[2].astype(np.float32); nir2 = naip2[3].astype(np.float32)
    del naip2
    ndvi2 = ((nir2 - red2) / np.maximum(nir2 + red2, 1)).astype(np.float32)
    bright2 = ((red2 + grn2 + blu2) / 3).astype(np.float32)

    mx2 = np.maximum(np.maximum(red2, grn2), blu2); mn2 = np.minimum(np.minimum(red2, grn2), blu2)
    sat2 = ((mx2 - mn2) / np.maximum(mx2, 1)).astype(np.float32)
    del mx2, mn2
    # FEAT-175: the NDVI, saturation and brightness thresholds below were measured on Vail's 2023 NAIP; each one is
    # moved to the same percentile of this resort's own imagery over two lidar-defined anchors (naip_calib.py), so
    # another state's or year's NAIP (Big Sky 2021 is darker and greyer) is read on its own scale. Vail gets its own.
    # Without lidar (FEAT-225 Silver) the anchors are read on the ETH canopy height instead.
    _forest_a, _bare_a, _z_forest = naip_calib.anchors(chm, dem2, have2 & has_pts & np.isfinite(dem2))
    NT, _nt_info = naip_calib.derive({"ndvi": ndvi2, "sat": sat2, "bright": bright2}, _forest_a, _bare_a, cfg.get("naip_thresholds"))
    log(f"  NAIP thresholds from {int(_forest_a.sum())} forest and {int(_bare_a.sum())} low bare cells (below {_z_forest or 0:.0f} m):")
    for _l in _nt_info:
        log(f"    {_l}")
    del _forest_a, _bare_a

    # classes
    # canopy needs (a) height above ground AND (b) vegetation in NAIP AND (c) a lidar return nearby. (b) and (c)
    # stop steep bare slopes above treeline reading as forest: the DSM is the max point in a 2 m cell and the DEM
    # the mean, so a 35 deg slope alone gives > 2 m of "height", and grey_closing spread that into empty cells.
    canopy = ((chm > 2.5) | ((ndvi2 > NT["canopy.leaf_ndvi"]) & (chm > 1.2))) & (ndvi2 > NT["canopy.veg_ndvi"]) & has_pts & have2
    if LIDAR:
        # BUG-028: that rule finds about a third of the closed stands at Born Free, Mid-Vail and Prima. The lidar return
        # test (has_pts) was not the cause (every forest cell has one within a cell); these two were:
        #  - grey beetle-killed lodgepole: NAIP NDVI under 5 m+ canopy is 0.2 to 0.35 there, under the 0.30 floor;
        #  - the subsampled cloud (about one return per 4 m2) hits a crown at one point, often the ground beside it.
        # So a 5 m+ return counts with NDVI over 0.15 (canopy.grow_ndvi) and stands for a crown about 2 m round, and gaps under 8 m inside a
        # stand close. Steep bare slopes stay out: their DSM-over-DEM artefact is under 2 m and cured meadow has no 5 m
        # returns. This grown part is dropped again on every non-glade run corridor in stage 7, so it never narrows a run.
        crown = ndimage.binary_dilation(chm > 5.0, iterations=1) & (ndvi2 > NT["canopy.grow_ndvi"]) & has_pts & have2
        grown = canopy | crown
        grown |= ndimage.binary_closing(grown, iterations=2) & (ndvi2 > NT["canopy.grow_ndvi"]) & have2
        canopy_grown = grown & ~canopy
        log(f"  canopy {canopy.mean()*100:.1f}% from the lidar and NAIP rule, {canopy_grown.mean()*100:.1f}% more from 5 m+ returns over grey crowns and closed gaps (BUG-028)")
        canopy |= canopy_grown
        del crown, grown
    else:
        # FEAT-225: the ETH model is 10 m and smooth, so a 5 m+ "return" covers whole meadows beside a stand; the
        # NAIP rule alone decides, at the imagery's own edges
        canopy_grown = np.zeros_like(canopy)
        log(f"  canopy {canopy.mean()*100:.1f}% from the ETH canopy height and the NAIP rule")
    # rock: low NDVI, GREY (low colour saturation), not snow. Late-summer NAIP shows cured meadow and
    # groomed pistes as tan grass with NDVI < 0.18 too; saturation 0.22..0.42 for grass vs < 0.15 for rock
    # (measured on the Vail 2023 imagery, rock.grey_sat). Without the saturation test 25 % of the resort came out as rock.
    snowfield = (bright2 > naip_calib.SNOW_BRIGHT) & (ndvi2 < 0.1)
    grey = sat2 < NT["rock.grey_sat"]
    rock = (ndvi2 < NT["rock.ndvi"]) & (bright2 > NT["rock.dark"]) & (bright2 < naip_calib.SNOW_BRIGHT) & grey & have2 & (chm < 1.5)
    meadow = (ndvi2 < NT["rock.bare_ndvi"]) & ~grey & have2 & (chm < 1.5)   # cured grass; no trees, no rock
    del sat2, red2, blu2
    # very steep bare ground is rock whatever colour the imagery gives it (shadowed cliff bands read as dark, not grey)
    rock_steep = (rock & (slope2 > 28)) | ((slope2 > 38) & (ndvi2 < NT["rock.bare_ndvi"]) & (chm < 1.5) & have2)
    scree = rock & (slope2 <= 28) & (slope2 > 12)
    # aspen vs conifer (DATA-015): leaf-on aspen is brighter than conifer in visible and NIR, and lower in NDVI.
    # Per 2 m cell, the canopy's mean brightness and NIR over ~8 m reads a stand through its crown shadows; the
    # thresholds are fitted below (stage 5b) on this pack's own natural aspen and conifer LANDFIRE classes.
    # Leafy crowns only (NDVI > LEAF_NDVI): the BUG-028 canopy also holds a ring of cured grass round every crown,
    # bright and high in NIR, which read as aspen at every forest edge.
    leaf = canopy & (ndvi2 > spc.LEAF_NDVI)
    bright_s2 = spc.canopy_mean(bright2, leaf)
    nir_s2 = spc.canopy_mean(nir2, leaf)
    ndvi_s2 = spc.canopy_mean(ndvi2, leaf)       # lodgepole against spruce-fir on built classes (stage 5b)
    del grn2, nir2, snowfield
    log(f"  canopy {canopy.mean()*100:.1f}%  rock {rock.mean()*100:.1f}%  meadow {meadow.mean()*100:.1f}%")
else:
    # FEAT-225 (Bronze surface): no NAIP. Canopy is WorldCover tree cover the ETH model has at 3 m or more, rock and
    # scree are its bare / sparse ground by slope (tier_sources.bronze_surface). No imagery means no NDVI: the class's
    # typical NDVI stands in where the shrubs read it, Vail's thresholds are logged as the pack's (none derived), no
    # NAIP aspen and no snags.
    log("no NAIP: canopy, rock and scree from ESA WorldCover 10 m")
    _wc2, _eth2 = landcover2()
    _bs = ts.bronze_surface(_wc2, chm, slope2, R2)
    have2, canopy, rock, rock_steep, scree = _bs["have"], _bs["canopy"], _bs["rock"], _bs["rock_steep"], _bs["scree"]
    if LIDAR:      # a lidar canopy height model, but no imagery: the lidar's height keeps the WorldCover edges honest
        canopy &= has_pts & (chm > 2.5)
    ndvi2 = ts.pseudo_ndvi(_wc2, R2)
    NT = naip_calib.vail_thresholds()
    canopy_grown = np.zeros_like(canopy)
    leaf = np.zeros_like(canopy)
    bright_s2 = nir_s2 = ndvi_s2 = np.zeros(canopy.shape, np.float32)
    del _bs
    log(f"  canopy {canopy.mean()*100:.1f}%  rock {rock.mean()*100:.1f}%  scree {scree.mean()*100:.1f}%  (WorldCover covers {have2.mean()*100:.1f}%)")
del has_pts
# DATA-021: the resort's own treeline for the client's procedural forest and snow-ghost band (Colorado's 3,480 m
# put Big Sky's bare upper bowls in forest); cfg["treeline_m"] overrides, None when the box never leaves the forest
import treeline as _tl
treeline_m = cfg.get("treeline_m") or _tl.derive_treeline(dem2, canopy, have2)
# FEAT-234: forest from the bottom of the box to the top is a measured "no treeline" (meta treeline: null), so the
# client draws no snow-ghost band and opens the forest by slope and land cover only
treeline_none = treeline_m is None and _tl.forested_to_top(dem2, canopy, have2)
if treeline_none:
    log("  treeline none: forested to the top of the box (meta treeline null, no snow-ghost band)")
elif treeline_m is None:
    log("  treeline none found (no forest belt in the box); the client uses its 3,480 m default")
else:
    log(f"  treeline {treeline_m} m ({'config' if cfg.get('treeline_m') else 'from the canopy by elevation'})")
# R carries rock the imagery saw, nothing else (FEAT-020): full weight on steep bare ground, half on
# grey rock on gentler slopes, where winter snow covers most of it. The renderer adds rock from slope
# (> ~45 deg) and wind-scoured ridges itself and breaks the weight into crisp patches with noise; a
# slope-only ramp here put 0.3..0.6 rock on every 30..40 deg snow slope and read as a brown wash.
rock_w = rock_steep.astype(np.float32) + (rock & ~rock_steep).astype(np.float32) * 0.5
rock_w = np.clip(ndimage.gaussian_filter(rock_w, 0.75), 0, 1)
scree_w = np.clip(scree.astype(np.float32) * 0.8, 0, 1) * (1 - rock_w)
del scree

# ------------------------------------------------------------------ 5b. LANDFIRE EVT (30 m) species, optional
# raw/<slug>/landfire/*.tif from fetch_landfire.mjs (LFPS, any LF version) + its .tif.vat.dbf class table.
# Classes are matched by NAME, not code: LF 2.4/2.5 renumbered EVT (aspen 3011 -> 7011).
def read_dbf(path):
    f = open(path, "rb").read()
    n = int.from_bytes(f[4:8], "little"); hl = int.from_bytes(f[8:10], "little"); rl = int.from_bytes(f[10:12], "little")
    fields, o = [], 32
    while f[o] != 0x0D:
        fields.append((f[o:o + 11].split(b"\0")[0].decode(), f[o + 16])); o += 32
    rows = []
    for i in range(n):
        rec = f[hl + i * rl + 1:hl + (i + 1) * rl]; p0 = 0; r = {}
        for nm, ln in fields:
            r[nm.upper()] = rec[p0:p0 + ln].decode("latin1").strip(); p0 += ln
        rows.append(r)
    return rows

class LfRaster:
    """A 30 m LANDFIRE clip (EVT, EVC or EVH) and its .vat.dbf class table: the one georeferencing path for every
    product. `data` is the class value per pixel, or with `fn` (a class name -> value parser, species.lf_tree_cover
    or lf_tree_height) that value as float32, NaN off-class. Read per point with .at() or on the 2 m grid with .on2();
    the 2 m indices are worked out per call, so nothing is held on the 2 m grid."""
    def __init__(self, path, fn=None):
        tfw = [float(v) for v in open(path[:-4] + ".tfw").read().split()]
        img = read_tiff(path).astype(np.int32)
        if img.ndim == 3:
            img = img[..., 0] if img.shape[-1] < img.shape[0] else img[0]
        self.table = read_dbf(path + ".vat.dbf") if os.path.exists(path + ".vat.dbf") else []
        self.name = os.path.basename(path)
        self.data = img if fn is None else spc.lf_value_lut(self.table, int(img.max()) + 1, fn)[np.clip(img, 0, None)]
        self.x0, self.y0, self.px = tfw[4], tfw[5], tfw[0]   # top-left pixel centre and pixel size (m)
        h, w = self.data.shape
        self.box = [self.x0 - self.px / 2, self.y0 - (h - 0.5) * self.px, self.x0 + (w - 0.5) * self.px,
                    self.y0 + self.px / 2]

    def paste(self, k, other):
        """FEAT-268: relocate move k's patch, cut from `other` (the source's clip of the same product), pasted into
        this raster on its own 30 m grid, so everything derived from it (natural classes, the fit cores) sees the
        patch as it is drawn; its class table is merged in"""
        d = REL.moves[k].dest_box()
        if not (d[0] >= self.box[0] and d[1] >= self.box[1] and d[2] <= self.box[2] and d[3] <= self.box[3]):
            sys.exit(f"LANDFIRE {self.name} does not cover {REL.moves[k].name}'s pasted patch {d}")
        if self.table or other.table:
            try:
                self.table = relocate.merge_class_tables(self.table, other.table)
            except ValueError as e:
                sys.exit(f"relocate {REL.moves[k].name}: {e}")
        self.data = relocate.compose_classes(self.data, self.box, self.px, self.box, REL,
                                             {k: (other.data.astype(self.data.dtype), other.box, other.px)}, [k])

    def _col(self, x_utm):
        return np.clip(np.round((x_utm - self.x0) / self.px).astype(np.int64), 0, self.data.shape[1] - 1)

    def _row(self, y_utm):
        return np.clip(np.round((self.y0 - y_utm) / self.px).astype(np.int64), 0, self.data.shape[0] - 1)

    def at(self, x_utm, y_utm):
        return self.at_data(self.data, x_utm, y_utm)

    def on2(self, rows=slice(None), cols=slice(None), data=None):
        """the raster (or `data`, another raster on the same 30 m grid) on the 2 m grid, or the rows / columns of it
        given as slices, row 0 = north"""
        gx = X0 + (np.arange(W2)[cols] + 0.5) * R2; gy = Y1 - (np.arange(H2)[rows] + 0.5) * R2
        data = self.data if data is None else data
        if REL:      # FEAT-249: a pasted patch reads its own place
            GX, GY = np.meshgrid(gx, gy)
            return self.at_data(data, GX, GY)
        return data[np.ix_(self._row(gy), self._col(gx))]

    def at_data(self, data, x_utm, y_utm):
        """`data` (a raster on the same 30 m grid) at the points (of the pack: a pasted patch reads its own place)"""
        if REL:      # FEAT-268: a sourced patch is pasted into the raster (paste), so it reads where it is
            x_utm, y_utm = REL.source_xy(x_utm, y_utm, REL.in_frame(REL.select(x_utm, y_utm)) if REL.sourced else None)
        return data[self._row(y_utm), self._col(x_utm)]

    def window(self):
        """the 30 m pixels under the pack, for the log"""
        return self.window_of(self.data)

    def window_of(self, data):
        """`data` (a raster on the same 30 m grid) under the pack"""
        c, r = self._col(np.array([X0, X1])), self._row(np.array([Y1, Y0]))
        return data[r[0]:r[1] + 1, c[0]:c[1] + 1]

evt = None
lf_tifs = sorted(glob.glob(os.path.join(raw, "landfire", "*.tif")))
LANDFIRE_ATTRIBUTION = "Vegetation type: LANDFIRE, USGS and U.S. Forest Service (public domain)"
def paste_sources(lyr, sub, fn=None):
    """FEAT-268: every sourced move's patch of a LANDFIRE product (landfire/<sub>/ of its raw folder) into `lyr`"""
    for k, m in enumerate(REL.moves):
        if not m.source:
            continue
        tifs = sorted(glob.glob(os.path.join(SRC_RAW[m.source], "landfire", sub, "*.tif")))
        if not tifs:
            sys.exit(f"relocate {m.name}: no LANDFIRE {sub or 'EVT'} in {SRC_RAW[m.source]} "
                     f"(python pipeline/build_resort.py {m.source} --stop-after landfire)")
        lyr.paste(k, LfRaster(tifs[-1], fn))
        log(f"  LANDFIRE {sub or 'EVT'}: {m.name}'s patch from {m.source}/{os.path.basename(tifs[-1])}")
    return lyr


if lf_tifs:
    evt_lf = paste_sources(LfRaster(lf_tifs[-1]), "")
    evt_img, table = evt_lf.data, evt_lf.table
    # per class (species.classify_evt, DATA-020): tree group, aspen fraction, forest (Tree life form, not
    # urban), alpine (turf, dwarf-shrubland, bedrock and scree, wet meadow), riparian, sagebrush, Gambel oak
    lut_n = int(evt_img.max()) + 1
    lut = evt_luts(table, lut_n)
    aspen_lut, forest_lut, alpine_lut, group_lut = lut["aspen"], lut["forest"], lut["alpine"], lut["group"]
    evt = evt_lf.at
    # classes on the 2 m grid, for gating the synthetic fill trees
    evt2 = np.clip(evt_lf.on2(), 0, lut_n - 1).astype(np.int16 if lut_n < 32768 else np.int32)
    lf_forest2 = forest_lut[evt2]
    lf_open2 = lut["open"][evt2]   # BUG-027: the fill-tree gate; developed and urban ground is not "open"
    # evt2 stays for the shrubs and the species debug map (stage 8)
    names = {int(float(r.get("VALUE", 0) or 0)): r.get("EVT_NAME", "") for r in table}
    vals, cnts = np.unique(evt_img, return_counts=True)
    top = sorted(zip(cnts, vals), reverse=True)[:5]
    log(f"  LANDFIRE {evt_lf.name} {evt_img.shape}: " + ", ".join(f"{names.get(int(v), v)[:28]} {c/cnts.sum()*100:.0f}%" for c, v in top))
    log(f"  LANDFIRE forest on the 2 m grid {lf_forest2.mean()*100:.1f}%, open {lf_open2.mean()*100:.1f}%, aspen classes {sum(c for c, v in zip(cnts, vals) if aspen_lut[min(v, lut_n-1)] > 0)/cnts.sum()*100:.1f}%")
    # FEAT-233: the forest under the pack by group, and its share in classes species.classify_evt doesn't name (they
    # fall to its catch-all group; over species.UNKNOWN_WARN is worth a card, pack_report.py line 4)
    win_ = evt_lf.window()
    evt_unknown = spc.unknown_forest_share(win_, lut)
    evt_groups = spc.group_shares(win_, lut)
    wv, wc = np.unique(np.clip(win_, 0, lut_n - 1), return_counts=True)
    unk = sorted((c, v) for c, v in zip(wc, wv) if lut["forest"][v] and not lut["known"][v])[::-1]
    log("  LANDFIRE forest under the pack by group: " + ", ".join(f"{spc.GROUP_NAMES[g]} {evt_groups[g] * 100:.0f}%" for g in range(len(evt_groups)) if evt_groups[g] >= 0.005)
        + f"; classes the species rules don't name {evt_unknown * 100:.1f}% of it" + (": " + ", ".join(names.get(int(v), str(v))[:40] for _, v in unk[:4]) if unk else ""))
    del win_, wv, wc, unk
    # DATA-015: Vail's runs and lift lines are `Developed-*` and its in-resort forest `Urban Evergreen Forest`, which
    # name no species. Those pixels take a natural forest class from the stands around them (species.natural_evt);
    # the tree species read evt_nat, everything else (forest gate, shrubs) keeps the real class.
    evt_nat, filled, lp_share = spc.natural_evt(evt_img, lut)
    evt_n = lambda x, y: evt_lf.at_data(evt_nat, x, y)
    lp_at = lambda x, y: evt_lf.at_data(lp_share, x, y)
    win, win_n = evt_lf.window(), np.clip(evt_lf.window_of(evt_nat), 0, lut_n - 1)
    built_w = lut["built"][np.clip(win, 0, lut_n - 1)]
    if built_w.any():
        gf = np.bincount(group_lut[win_n[built_w]], minlength=len(spc.GROUP_NAMES)) / built_w.sum()
        log(f"  LANDFIRE built classes (urban, developed) on {built_w.mean() * 100:.1f}% of the pack, {evt_lf.window_of(filled)[built_w].mean() * 100:.0f}% "
            "of them filled from the natural forest within ~300 m: " + ", ".join(f"{spc.GROUP_NAMES[g]} {gf[g] * 100:.0f}%" for g in range(len(gf)) if gf[g] >= 0.005))
    del win, win_n, built_w
    # NAIP aspen thresholds, fitted on the canopy under the natural aspen and conifer classes (cores: one 30 m
    # pixel in from each class edge)
    natural = forest_lut[np.clip(evt_img, 0, lut_n - 1)] & ~lut["built"][np.clip(evt_img, 0, lut_n - 1)]
    g30, a30 = group_lut[np.clip(evt_img, 0, lut_n - 1)], aspen_lut[np.clip(evt_img, 0, lut_n - 1)]
    asp30 = ndimage.binary_erosion(natural & (g30 == spc.G_ASPEN))
    con30 = ndimage.binary_erosion(natural & np.isin(g30, (spc.G_SPRUCE_FIR, spc.G_LODGEPOLE)) & (a30 == 0))
    tb, tn, fit = spc.fit_aspen(bright_s2, nir_s2, evt_lf.on2(data=asp30) & leaf, evt_lf.on2(data=con30) & leaf)
    lp30 = ndimage.binary_erosion(natural & (g30 == spc.G_LODGEPOLE))
    sf30 = ndimage.binary_erosion(natural & (g30 == spc.G_SPRUCE_FIR) & (a30 == 0))
    t_lp, fit_lp = spc.fit_lodgepole(ndvi_s2, evt_lf.on2(data=lp30) & leaf, evt_lf.on2(data=sf30) & leaf)
    del natural, g30, a30, asp30, con30, lp30, sf30
else:
    log("  no LANDFIRE clip (raw/<slug>/landfire/*.tif); species from elevation, aspect and NAIP colour (species.py fallback)")
    evt_unknown = evt_groups = None
    tb, tn = spc.ASPEN_DEFAULT; fit = {"fitted": False, "aspen": 0, "conifer": 0}
aspen_like = canopy & (bright_s2 > tb) & (nir_s2 > tn)
del bright_s2, nir_s2
lodgepole_like = (canopy & (ndvi_s2 < t_lp) & ~aspen_like) if evt is not None and t_lp is not None else None
del ndvi_s2, leaf
if NAIP:
    log(f"  NAIP aspen: canopy brightness > {tb:.1f} and NIR > {tn:.1f} over ~8 m on {aspen_like.sum() / max(canopy.sum(), 1) * 100:.1f}% of the canopy; "
        + (f"fitted on {fit['aspen']} aspen and {fit['conifer']} conifer cells: aspen found {fit['hit'] * 100:.0f}%, conifer taken for aspen {fit['false'] * 100:.1f}%"
           if fit["fitted"] else f"Vail's fit (this pack's fit doesn't separate them: aspen found {fit['hit'] * 100:.0f}%, conifer taken for aspen {fit['false'] * 100:.1f}%)" if fit.get("weak")
           else f"Vail's fit (too few labelled cells: {fit['aspen']} aspen, {fit['conifer']} conifer)"))
if evt is not None and t_lp is not None:
    log(f"  NAIP lodgepole on built classes: canopy NDVI < {t_lp:.3f} over ~8 m where the forest around is {spc.LODGEPOLE_MIN_SHARE * 100:.0f}%+ lodgepole; "
        f"fitted on {fit_lp['lodgepole']} lodgepole and {fit_lp['spruce_fir']} spruce-fir cells: lodgepole found {fit_lp['hit'] * 100:.0f}%, spruce-fir taken for it {fit_lp['false'] * 100:.0f}%")
elif evt is not None:
    log("  NAIP lodgepole: no tie-breaker on built classes, the built pixels keep their draw from the forest around; "
        + (f"this pack's NDVI doesn't separate lodgepole from spruce-fir (found {fit_lp['hit'] * 100:.0f}%, spruce-fir taken for it {fit_lp['false'] * 100:.0f}%)"
           if fit_lp.get("weak") else f"too few labelled cells ({fit_lp['lodgepole']} lodgepole, {fit_lp['spruce_fir']} spruce-fir)"))

# ------------------------------------------------------------------ 5c. LANDFIRE EVC and EVH (30 m), optional
# DATA-010: existing vegetation cover and height from raw/<slug>/landfire/evc/ and evh/ (fetch_landfire.mjs EVC / EVH),
# read by class NAME like EVT ("Tree Cover = 45%", "Tree Height = 17 meters"). Tree classes only: shrub, herb,
# developed, water and barren cells are NaN, so the lidar and NAIP decide there. Stand density (FEAT-074) and the
# canopy rules (BUG-028) read them with LfRaster (stage 5b) per 2 m cell (.on2()) or per point (.at()).
def load_lf_layer(sub, fn):
    tifs = sorted(glob.glob(os.path.join(raw, "landfire", sub, "*.tif")))
    return paste_sources(LfRaster(tifs[-1], fn), sub, fn) if tifs else None

lf_cover = load_lf_layer("evc", spc.lf_tree_cover)
lf_height = load_lf_layer("evh", spc.lf_tree_height)
for lyr, what, unit, k in ((lf_cover, "EVC tree cover", "%", 100), (lf_height, "EVH tree height", " m", 1)):
    if lyr is None:
        log(f"  no LANDFIRE {what[:3]} (raw/<slug>/landfire/{what[:3].lower()}/*.tif)")
        continue
    w = lyr.window(); t = w[np.isfinite(w)]
    rng_ = f"{t.min() * k:.0f} / {np.median(t) * k:.0f} / {t.max() * k:.0f}{unit} (min / median / max)" if t.size else "none"
    log(f"  LANDFIRE {what} {lyr.name} {lyr.data.shape}: tree classes on {t.size / max(w.size, 1) * 100:.1f}% of the pack, {rng_}")

# ------------------------------------------------------------------ 6. OSM features
log("OSM")
def load_osm(name, raw=raw):
    p = os.path.join(raw, "osm", f"{name}.json")
    if not os.path.exists(p):
        log("  missing osm", name); return {"elements": []}
    return json.load(open(p, encoding="utf-8"))
ski = load_osm("ski"); built = load_osm("built"); natural = load_osm("natural"); peaks_far = load_osm("peaks_far"); places_far = load_osm("places_far")
# DATA-021: members-only neighbours (cfg["exclude"], access=private tags) keep their terrain but lose their runs and lifts
import osm_filter
ski, ski_dropped = osm_filter.filter_ski(ski, osm_filter.exclude_areas(cfg.get("exclude"), ski, lambda m: log("  " + m)))
if ski_dropped:
    log("  private runs and lifts dropped: " + ", ".join(f"{k} {v}" for k, v in sorted(ski_dropped.items())))
if REL:
    # FEAT-249: after the filter, whose hand-drawn rings are in the real places. Runs and lifts move whole (a lift's
    # nodes list must match its geometry); roads and streams split at the seam; the far peaks and places stay real.
    ski, _mv = REL.osm(ski, to_utm, to_ll, whole=True)
    built, _mb = REL.osm(built, to_utm, to_ll)
    natural, _mn = REL.osm(natural, to_utm, to_ll)
    for _s in REL.source_slugs():
        # FEAT-268: a sourced move's runs, lifts, buildings and streams are in its own raw folder: only what its
        # patch takes is kept, moved, and added to the docs
        _sk = load_osm("ski", SRC_RAW[_s])
        _sk, _d = osm_filter.filter_ski(_sk, osm_filter.exclude_areas(SRC_CFG[_s].get("exclude"), _sk, lambda m: log("  " + m)))
        _parts = [(REL.osm(_sk, to_utm, to_ll, whole=True, source=_s), "ski"),
                  (REL.osm(load_osm("built", SRC_RAW[_s]), to_utm, to_ll, source=_s), "built"),
                  (REL.osm(load_osm("natural", SRC_RAW[_s]), to_utm, to_ll, source=_s), "natural")]
        for (_doc, _cnt), _which in _parts:
            _into = {"ski": ski, "built": built, "natural": natural}[_which]
            _into["elements"] = _into["elements"] + _doc["elements"]
            _tot = {"ski": _mv, "built": _mb, "natural": _mn}[_which]
            for _k, _v in _cnt.items():
                _tot[_k] = _tot.get(_k, 0) + _v
    for m in REL.moves:
        log(f"  relocate {m.name}: {_mv[m.name]} ski, {_mb[m.name]} built and {_mn[m.name]} natural elements moved")

def to_local(lon, lat):
    x, y = to_utm.transform(lon, lat)
    return float(x - OX), float(y - OY)

def ground(xl, yl):
    """height from the 1 m DEM at local coords (fallback to mid)"""
    c = int(xl + OX - X0); r = int(Y1 - (yl + OY))
    if 0 <= c < W and 0 <= r < H:
        return float(dem[r, c])
    mc = int((xl + OX - mx0) / 16); mr = int((my1 - (yl + OY)) / 16)
    if 0 <= mc < n16 and 0 <= mr < n16:
        return float(m16[mr, mc])
    return float(cfg["elevation_range_m"][0])

def way_points(el):
    return [to_local(p["lon"], p["lat"]) for p in el.get("geometry", [])]

DIFF = {"novice": "novice", "easy": "easy", "intermediate": "intermediate", "advanced": "advanced", "expert": "expert", "freeride": "freeride", "extreme": "extreme"}
runs = []
piste_polys = []   # (points, difficulty, groomed, width)
for el in ski["elements"]:
    if el.get("type") != "way":
        continue
    t = el.get("tags", {})
    if t.get("piste:type") not in ("downhill", "nordic", "skitour", "sled", "snow_park"):
        continue
    pts = way_points(el)
    if len(pts) < 2:
        continue
    diff = DIFF.get(t.get("piste:difficulty", ""), None)
    grooming = t.get("piste:grooming")
    # groomed only where the map says so (piste:grooming); no guessing from difficulty, and mogul
    # runs are not corduroy. The game is 1:1 with real data: an untagged run stays ungroomed snow.
    groomed = grooming in ("classic", "classic+skating", "skating", "scooter")
    closed = pts[0] == pts[-1] and len(pts) > 3 and t.get("area") == "yes"
    rec = {"name": t.get("name") or t.get("piste:name"), "difficulty": diff, "groomed": bool(groomed),
           "gladed": t.get("piste:gladed") == "yes" or t.get("gladed") == "yes", "osmId": el["id"], "area": closed,
           "points": [[x, y, ground(x, y)] for x, y in pts]}
    if t.get("bridge", "no") != "no":
        rec["bridge"] = True   # bare-earth DEM has no bridge; the client builds a deck
    rec["mogulTag"] = grooming == "mogul"   # FEAT-059: popped before writing
    runs.append(rec)
log(f"  runs {len(runs)}")

# real grooming: the resort's own nightly reports (raw/<slug>/grooming/*.json from fetch_grooming.py).
# A run is groomed if the resort groomed it on any saved night (or OSM tags it groomed above).
# Names are compared with case, spaces and punctuation ignored; "Run - Section" also matches on the
# run ("Simba - Lower" in the report vs one "Simba" way in OSM) when the exact section is not in both.
# cfg["grooming_aliases"] maps report spellings to OSM ones ("mil creek road" -> "mill creek road").
import re as _re
def run_key(n):
    return _re.sub(r"[^a-z0-9]", "", (n or "").lower())
def run_base(n):
    return run_key((n or "").split(" - ")[0])
aliases = {run_key(a): run_key(b) for a, b in cfg.get("grooming_aliases", {}).items()}
groom_nights = {}       # report trail key -> nights groomed
base_nights = {}        # report run base -> nights any section was groomed
listed = set()          # every trail key the reports list, groomed or not
run_base_of = {}        # report trail key -> its run base
reports = sorted(glob.glob(os.path.join(raw, "grooming", "*.json")))
for fp in reports:
    for tr in json.load(open(fp, encoding="utf-8"))["trails"]:
        k = run_key(tr["name"]); k = aliases.get(k, k)
        b = run_base(tr["name"]); b = aliases.get(b, b)
        listed.add(k); run_base_of[k] = b
        groom_nights.setdefault(k, 0); base_nights.setdefault(b, 0)
        if tr["groomed"]:
            groom_nights[k] += 1; base_nights[b] += 1
if reports:
    reported = {k for k, c in groom_nights.items() if c > 0}
    matched = set()
    for r in runs:
        k, b = run_key(r["name"]), run_base(r["name"])
        if not k:
            continue
        if k in listed:                       # the report names this exact run or section
            nights = groom_nights.get(k, 0)
            if nights:
                matched.add(k)
        else:                                 # match on the run, any section
            nights = base_nights.get(b, 0)
            if nights:
                matched.update(x for x in reported if run_base_of.get(x) == b)
        if nights:
            r["groomed"] = True
            r["groomNights"] = nights
    log(f"  grooming reports {len(reports)}: {len(reported)} trails groomed on some night, "
        f"{len(matched)} matched to OSM runs; groomed runs now {sum(1 for r in runs if r['groomed'])}")
    missing = sorted(reported - matched)
    if missing:
        log(f"  groomed in reports but no OSM run of that name: {', '.join(missing[:40])}{' ...' if len(missing) > 40 else ''}")
else:
    log("  no grooming reports (raw/<slug>/grooming/*.json); groomed = OSM piste:grooming tags only")

# lifts: aerialway ways + pylon/station nodes
nodes_by_id = {el["id"]: el for el in ski["elements"] if el.get("type") == "node"}
lifts = []
for el in ski["elements"]:
    if el.get("type") != "way":
        continue
    t = el.get("tags", {})
    aw = t.get("aerialway")
    if not aw or aw in ("goods", "zip_line", "station", "pylon"):
        continue
    pts = way_points(el)
    if len(pts) < 2:
        continue
    towers = []
    for nid, p in zip(el.get("nodes", []), pts):
        nt = nodes_by_id.get(nid, {}).get("tags", {})
        if nt.get("aerialway") == "pylon":
            z = ground(*p)
            towers.append([p[0], p[1], z, 11.0 if aw in ("chair_lift", "gondola", "mixed_lift", "cable_car") else 7.0])
    lifts.append({"name": t.get("name"), "type": aw, "capacity": int(t["aerialway:capacity"]) if t.get("aerialway:capacity", "").isdigit() else None,
                  "stations": [[pts[0][0], pts[0][1], ground(*pts[0])], [pts[-1][0], pts[-1][1], ground(*pts[-1])]],
                  "towers": towers, "cable": [], "osmId": el["id"]})
log(f"  lifts {len(lifts)}")

buildings, roads, water = [], [], []
BIG_LODGE_M2 = 1500  # BUG-024: named buildings bigger than this get a lodge height when OSM has none


def polygon_area(pts):
    """Shoelace area of a closed ring of (x, y) metres."""
    return abs(sum(pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1] for i in range(len(pts) - 1))) / 2

for el in built["elements"]:
    if el.get("type") != "way":
        continue
    t = el.get("tags", {})
    pts = way_points(el)
    if "building" in t and len(pts) >= 4:
        zs = [ground(x, y) for x, y in pts]
        h = None
        h_default = False
        try:
            if "height" in t: h = float(t["height"].split()[0])
            elif "building:levels" in t: h = 3.2 * float(t["building:levels"])
        except ValueError:
            h = None
        if h is None:
            h = 9.0 if t.get("building") in ("hotel", "apartments", "commercial", "retail") else 5.5
            h_default = True
            # BUG-024: a big named lodge with no height or levels in OSM (Eagle's Nest) is 3 to 4 storeys
            if t.get("name") and polygon_area(pts) > BIG_LODGE_M2:
                h = 12.0
                h_default = False
        # BUG-024: the highest ground under the footprint too (corners and centre), so the client can put
        # the roof above the uphill side before any height tiles have loaded
        cx_, cy_ = sum(p[0] for p in pts[:-1]) / (len(pts) - 1), sum(p[1] for p in pts[:-1]) / (len(pts) - 1)
        z_hi = max(zs + [ground(cx_, cy_)])
        buildings.append({"name": t.get("name"), "points": [[x, y] for x, y in pts[:-1]], "zBase": float(min(zs)), "zMax": float(z_hi), "height": h, "heightDefault": h_default, "kind": t.get("building")})
    elif "highway" in t and len(pts) >= 2:
        kind = t["highway"]
        width = {"motorway": 24, "trunk": 14, "primary": 10, "secondary": 8, "tertiary": 7, "residential": 6, "service": 4, "track": 3, "path": 1.5, "footway": 1.5}.get(kind, 4)
        rec = {"name": t.get("name"), "kind": kind, "width": width, "points": [[x, y, ground(x, y)] for x, y in pts]}
        if t.get("bridge", "no") != "no":
            rec["bridge"] = True
        roads.append(rec)
for el in natural["elements"]:
    if el.get("type") == "way" and el.get("tags", {}).get("natural") == "water":
        pts = way_points(el)
        if len(pts) >= 4:
            water.append({"name": el["tags"].get("name"), "points": [[x, y] for x, y in pts[:-1]], "z": float(min(ground(x, y) for x, y in pts))})
# streams and rivers (DATA-020): fir and willow sit near water; not written to features.json
streams = [way_points(el) for el in natural["elements"]
           if el.get("type") == "way" and el.get("tags", {}).get("waterway") in ("stream", "river", "brook", "canal", "ditch")]
def height_at(xl, yl, top=False):
    """ground height at local coords from the finest set that holds them (1 m DEM, 16 m mid ring, 128 m far ring);
    `top`: the highest ground near the point instead (a summit with no ele tag: within 30 m on the 1 m DEM, one
    cell on the coarser sets). NaN off every set."""
    c = int(xl + OX - X0); r = int(Y1 - (yl + OY))
    k = 30 if top else 0
    if k <= c < W - k and k <= r < H - k:
        return float(np.nanmax(dem[r - k:r + k + 1, c - k:c + k + 1]))
    k = 1 if top else 0
    for arr, gx0, gy1, res in ((m16, mx0, my1, 16.0), (far, fx0, fy0 + nf * FR, FR)):
        gc = int((xl + OX - gx0) / res); gr = int((gy1 - (yl + OY)) / res)
        if k <= gc < arr.shape[1] - k and k <= gr < arr.shape[0] - k:
            w = arr[gr - k:gr + k + 1, gc - k:gc + k + 1]
            if np.isfinite(w).any():
                return float(np.nanmax(w))
    return float("nan")
peaks = []
for el in peaks_far["elements"] + natural["elements"]:
    if el.get("type") == "node" and el.get("tags", {}).get("natural") == "peak" and el["tags"].get("name"):
        x, y = to_local(el["lon"], el["lat"])
        try:
            z = float(el["tags"].get("ele", "nan").split()[0].replace("m", ""))
        except ValueError:
            z = float("nan")
        if not math.isfinite(z):
            z = height_at(x, y, top=True)      # FEAT-235: was ground(), the resort's base height off the mid ring
        if math.isfinite(z):
            peaks.append({"name": el["tags"]["name"], "x": x, "y": y, "z": z})
seen = set(); uniq = []
for p in peaks:
    k = (p["name"], round(p["x"] / 50), round(p["y"] / 50))
    if k not in seen:
        seen.add(k); uniq.append(p)
peaks = uniq
# FEAT-235: place names from USGS GNIS (every state the far ring touches) and the Census (towns), in names/
import placenames
far_ll = placenames.far_box_ll(cfg)
NAMES_ATTRIBUTION = "Place names: USGS GNIS; towns: US Census Bureau Gazetteer and population estimates, public domain"
gnis_summits, gnis_states = placenames.load_gnis(raw, far_ll)
census_towns = False
gnis_peaks = []
for f in gnis_summits:
    x, y = to_local(f["lon"], f["lat"])
    z = height_at(x, y, top=True)
    if math.isfinite(z):
        gnis_peaks.append({"name": f["name"], "x": x, "y": y, "z": z})
added = placenames.merge_peaks(peaks, gnis_peaks)
peaks += added
log(f"  GNIS ({', '.join(gnis_states) or 'no names/ files'}): {len(gnis_summits)} summits in the far ring, {len(added)} not in OSM")
labels = [{"name": el["tags"]["name"], "kind": el["tags"].get("place", "place"), "x": to_local(el["lon"], el["lat"])[0], "y": to_local(el["lon"], el["lat"])[1], "z": 0}
          for el in places_far["elements"] if el.get("type") == "node" and el.get("tags", {}).get("place") and el["tags"].get("name")]
if not labels:      # no Overpass places_far (dropped from the manifest): the Census towns
    towns = placenames.load_towns(raw, far_ll)
    census_towns = bool(towns)
    labels = [{"name": t["name"], "kind": t["kind"], "x": to_local(t["lon"], t["lat"])[0], "y": to_local(t["lon"], t["lat"])[1], "z": 0}
              for t in towns]
    log(f"  Census towns: {len(labels)} ({sum(1 for t in towns if t['kind'] == 'city')} cities, "
        f"{sum(1 for t in towns if t['kind'] == 'town')} towns)")
for l in labels:
    z = height_at(l["x"], l["y"])
    l["z"] = z if math.isfinite(z) else 0.0       # 0: the game samples the ground itself
log(f"  buildings {len(buildings)} roads {len(roads)} water {len(water)} peaks {len(peaks)} labels {len(labels)}")
def line_cells(pts):
    """distinct 2 m grid cells along a polyline, as (rows, cols) index arrays, clipped to the grid"""
    cells = set()
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        steps = max(1, int(math.hypot(bx - ax, by - ay) / (R2 * 0.7)))
        for s_ in range(steps + 1):
            t = s_ / steps
            c = int((ax + (bx - ax) * t + OX - X0) / R2); r = int((Y1 - (ay + (by - ay) * t + OY)) / R2)
            if 0 <= r < H2 and 0 <= c < W2:
                cells.add((r, c))
    if not cells:
        return np.array([], int), np.array([], int)
    rc = np.array(sorted(cells))
    return rc[:, 0], rc[:, 1]


# ------------------------------------------------------------------ 6b. mogul score per run (FEAT-059)
# Grooming reports, difficulty, slope and aspect along the centre line, and lift-top traffic; see moguls.py.
report_nights = len(reports)
lift_tops = [(s[0], s[1]) for l in lifts for s in l["stations"]]
for r in runs:
    tag = r.pop("mogulTag", False)
    pts = [(p[0], p[1]) for p in r["points"]]
    rows, cols = line_cells(pts) if len(pts) >= 2 else (np.array([], int), np.array([], int))
    if len(rows):
        slope_med = float(np.percentile(slope2[rows, cols], 75))   # the steep pitch, not the run-out
        dx, dy = float(np.mean(-gx[rows, cols])), float(np.mean(gy[rows, cols]))   # downhill (row 0 = north)
        aspect = math.degrees(math.atan2(dx, dy)) % 360.0 if math.hypot(dx, dy) > 1e-4 else None
    else:
        slope_med, aspect = 0.0, None
    if report_nights:
        groom_frac = r.get("groomNights", 0) / report_nights
    else:
        groom_frac = None
    top = max(r["points"], key=lambda p: p[2])
    near_top = any(math.hypot(top[0] - lx, top[1] - ly) < 150.0 for lx, ly in lift_tops)
    r["mogulScore"] = round(run_mogul_score(r, slope_med, aspect, groom_frac, tag, near_top), 2)
del gx, gy
scored = sorted((r for r in runs if r["mogulScore"] > 0), key=lambda r: -r["mogulScore"])
log(f"  mogul runs: {sum(1 for r in runs if r['mogulScore'] >= 0.3)} of {len(runs)} score 0.3 or more; top: "
    + ", ".join(f"{r['name'] or 'unnamed'} {r['mogulScore']:.2f}" for r in scored[:15]))
write_features(out, {"lifts": lifts, "runs": runs, "buildings": buildings, "roads": roads, "water": water, "peaks": peaks, "labels": labels})
Z_MIN, Z_MAX = float(np.nanmin(dem)), float(np.nanmax(dem))
del dem   # 540 MB; everything from here works on the 2 m grid

# ------------------------------------------------------------------ 7. masks at 2 m
log("masks")
groomed = np.zeros((H2, W2), np.float32)
piste_any = np.zeros((H2, W2), bool)
def rasterize_corridor(target, pts, half_width, value=1.0):
    """paint a corridor along a polyline into a 2 m raster (row 0 = north)"""
    hw = max(1, int(half_width / R2))
    for (ax, ay), (bx, by) in zip(pts[:-1], pts[1:]):
        length = math.hypot(bx - ax, by - ay)
        steps = max(1, int(length / (R2 * 0.7)))
        for s in range(steps + 1):
            t = s / steps
            x = ax + (bx - ax) * t; y = ay + (by - ay) * t
            c = int((x + OX - X0) / R2); r = int((Y1 - (y + OY)) / R2)
            r0, r1 = max(0, r - hw), min(H2, r + hw + 1); c0, c1 = max(0, c - hw), min(W2, c + hw + 1)
            if r1 <= r0 or c1 <= c0:
                continue
            rr, cc = np.ogrid[r0:r1, c0:c1]
            d2 = (rr - r) ** 2 + (cc - c) ** 2
            target[r0:r1, c0:c1] = np.maximum(target[r0:r1, c0:c1], np.where(d2 <= hw * hw, value, 0))


def centerlines(run_list):
    """1-pixel-wide centre lines of the given runs on the 2 m grid"""
    m = np.zeros((H2, W2), bool)
    for r in run_list:
        rows, cols = line_cells([(p[0], p[1]) for p in r["points"]])
        m[rows, cols] = True
    return m


def yield_to_ungroomed(groomed, run_list):
    """BUG-030: a groomed corridor only keeps the cells that are nearer a groomed run's centre line than
    a never-groomed run's, so the corridor painted around a groomer no longer spills corduroy onto the
    ungroomed run beside it. Logs the groomed share along each never-groomed run."""
    lines = [r for r in run_list if not r.get("area") and len(r["points"]) >= 2]
    never = [r for r in lines if not r["groomed"]]
    if not never or not any(r["groomed"] for r in lines):
        return groomed
    d_g = ndimage.distance_transform_edt(~centerlines([r for r in lines if r["groomed"]])).astype(np.float32)
    d_u = ndimage.distance_transform_edt(~centerlines(never)).astype(np.float32)
    before = never_groomed_share(groomed, never)
    cells_before = int((groomed > 0.5).sum())
    groomed = groomed * (d_g <= d_u)
    del d_g, d_u
    after = never_groomed_share(groomed, never)
    cells_after = int((groomed > 0.5).sum())
    log(f"  groomed area {cells_before * R2 * R2 / 1e4:.1f} ha -> {cells_after * R2 * R2 / 1e4:.1f} ha "
        f"({(cells_before - cells_after) / max(1, cells_before) * 100:.1f}% handed to never-groomed runs)")
    if after:
        log(f"  never-groomed runs: mean groomed share along the line {np.mean(list(before.values()))*100:.1f}% -> {np.mean(list(after.values()))*100:.1f}% ({len(after)} runs)")
        worst = sorted(after.items(), key=lambda kv: -kv[1])[:8]
        log("  most groomed never-groomed runs: " + ", ".join(f"{k} {v*100:.0f}%" for k, v in worst))
    return groomed


def never_groomed_share(groomed, never):
    """share of each never-groomed run's centre-line cells that are groomed (> 0.5), by run name"""
    out = {}
    for i, r in enumerate(never):
        rows, cols = line_cells([(p[0], p[1]) for p in r["points"]])
        if len(rows):
            out[r.get("name") or f"unnamed {i}"] = float((groomed[rows, cols] > 0.5).mean())
    return out




piste_f = np.zeros((H2, W2), np.float32)
for run in runs:
    if run.get("area"):
        continue
    pts = [(p[0], p[1]) for p in run["points"]]
    hw = run_half_width(run)
    if not run.get("gladed"):
        rasterize_corridor(piste_f, pts, hw)
    if run["groomed"]:
        rasterize_corridor(groomed, pts, hw)
groomed = yield_to_ungroomed(groomed, runs)
piste_any = piste_f > 0
del piste_f
# BUG-028: the canopy grown from 5 m+ returns and closed gaps never reaches into a run (glades keep it)
cut = canopy_grown & (piste_any | (groomed > 0))
canopy &= ~cut
log(f"  grown canopy kept off runs: {cut.mean()*100:.2f}% of the pack")
del cut, canopy_grown
# built-up: roads and building footprints are grey in NAIP and were classified as rock (I-70, the villages)
built_f = np.zeros((H2, W2), np.float32)
for rd in roads:
    rasterize_corridor(built_f, [(p[0], p[1]) for p in rd["points"]], 8 if rd.get("kind") in ("motorway", "trunk", "primary") else 4)
for b in buildings:
    rasterize_corridor(built_f, [(p[0], p[1]) for p in b["points"]], 6)
built_any = built_f > 0
del built_f
rock_w = rock_w * (~built_any).astype(np.float32)
scree_w = scree_w * (~built_any).astype(np.float32)
log(f"  built-up {built_any.mean()*100:.1f}% removed from rock/scree")
# a groomed corridor is only groomed where there is no canopy (the actual cleared trail)
groomed *= (~canopy).astype(np.float32)
groomed = ndimage.gaussian_filter(groomed, 1.0)
canopy_cover = ndimage.uniform_filter(canopy.astype(np.float32), 5)
rgba = np.stack([rock_w * 255, scree_w * 255, np.clip(groomed, 0, 1) * 255, canopy_cover * 255], axis=-1).astype(np.uint8)
mask_meta = write_mask_set(out, rgba, R2, X0 - OX, Y0 - OY)
del rgba
# piste direction (DATA-002): the groomed runs' axis per cell, for corduroy that follows the run
dir_meta = write_mask_set(out, piste_direction(runs, groomed, R2, X0 - OX, Y1 - OY, log=log), R2, X0 - OX, Y0 - OY, kind="dir", pad=0)
# baked sky visibility (FEAT-047): gullies, couloirs, cirques and cliff feet darken; same grid as the mask.
# A light blur first so 1 m DEM noise does not speckle the tangent plane.
log("  terrain AO")
ao = sky_visibility(ndimage.gaussian_filter(dem2, 1.0), R2, log=log)
log(f"  ao mean {ao.mean():.3f}, p5 {np.percentile(ao, 5):.3f}")
ao_meta = write_mask_set(out, (np.clip(ao, 0, 1) * 255 + 0.5).astype(np.uint8), R2, X0 - OX, Y0 - OY, kind="ao")
del ao

# mogul amplitude (FEAT-059): each scoring run's corridor, fading over the outer 3 m, times the slope
# window; none under canopy, on groomed corduroy, built-up ground or rock. 0..1 m in the greyscale set.
log("  moguls")
mog = np.zeros((H2, W2), np.float32)
for run in runs:
    sc = run.get("mogulScore", 0.0)
    if sc <= 0.05 or len(run["points"]) < 2:
        continue
    pts = [(p[0], p[1]) for p in run["points"]]
    if run.get("area"):
        paint_polygon(mog, pts, sc, R2, X0 - OX, Y1 - OY)
    else:
        hw = run_half_width(run)
        paint_field(mog, pts, hw - 2, sc, R2, X0 - OX, Y1 - OY)
mog *= slope_window(slope2) * (~canopy).astype(np.float32) * (1 - np.clip(groomed, 0, 1)) * (~built_any).astype(np.float32) * (1 - rock_w) * (1 - scree_w)
mog = np.clip(mog, 0, 1)
cells = mog > 0.05
log(f"  mogul fields {cells.sum() * R2 * R2 / 1e4:.1f} ha, mean amplitude {mog[cells].mean() if cells.any() else 0:.2f} m")
mog_meta = write_mask_set(out, (mog * 255 + 0.5).astype(np.uint8), R2, X0 - OX, Y0 - OY, kind="moguls", pad=0)
del mog, cells

# ------------------------------------------------------------------ 8. trees and rocks
log("trees")
# crown detection: local maxima of the smoothed CHM, window scaled with height
chm_s = ndimage.gaussian_filter(chm, 0.8)
maxf = ndimage.maximum_filter(chm_s, size=3)
peaks_mask = (chm_s == maxf) & (chm_s > 2.5) & canopy
if not LIDAR:
    # FEAT-225: the ETH model's smooth 10 m heights have no crowns to find (its flat tops would each read as one);
    # every tree is a stand stem, generated by the client from stands/ (below)
    peaks_mask[:] = False
    log("  no lidar: no detected crowns, the stands carry every tree")
pr, pc = np.nonzero(peaks_mask)
# BUG-023: the smoothed CHM finds the peaks, but a crown's height is the tallest return within one cell of it.
# A lone tree is one return in one 2 m cell, and the blur kept about 0.6 of it (median 6 m drawn against 10 m
# returned in the Back Bowls; NAIP shadow lengths put those trees at 11 to 12 m). Inside stands it was about 0.9.
chm_top = ndimage.maximum_filter(chm, size=3)
tree_rows, tree_cols, tree_h = [pr], [pc], [chm_top[pr, pc]]
# FEAT-074: no fill trees in the pack. Under continuous canopy the subsampled lidar finds a crown every 10 m or
# so; the stems between them are a stand density per 4 m cell (stands/, written below) that the client draws
# near the camera only. (A 10 % fill used to sit in the pack: 0.33 gave 5.26 M trees at Vail, too many to render.)
# Where stems may stand: canopy, not on truly open LANDFIRE classes (BUG-027), groomed corduroy, built-up ground,
# cliffs or under a lift line.
lift_f = np.zeros((H2, W2), np.float32)
for l in lifts:
    (ax_, ay_, _), (bx_, by_, _) = l["stations"]
    rasterize_corridor(lift_f, [(ax_, ay_), (bx_, by_)], 8)            # towers and chairs read as tall grey points
    for sx_, sy_ in ((ax_, ay_), (bx_, by_)):
        rasterize_corridor(lift_f, [(sx_, sy_), (sx_, sy_)], 25)       # terminals
stand_ok = canopy & ~built_any & ~rock_steep & (lift_f == 0) & (groomed < 0.3)
if evt is not None:
    stand_ok &= ~lf_open2
    del lf_open2
rng = np.random.default_rng(3)
rows = np.concatenate(tree_rows); cols = np.concatenate(tree_cols); hgt = np.concatenate(tree_h).astype(np.float32)
# snags (DATA-020, species 7): grey standing dead crowns. Live canopy needs NDVI > 0.30, so the crowns above
# never include them: local CHM maxima over 6 m with NDVI < 0.15 inside forest, off buildings, lifts and cliffs,
# the greyest kept up to 3 % of all trees.
forest_here = lf_forest2 if evt is not None else ndimage.binary_dilation(canopy, iterations=5)
snag_c = ((chm_s == maxf) & (chm_s > 6.0) & (ndvi2 < NT["canopy.grow_ndvi"]) & have2 & forest_here & (slope2 < 40)
          & ~built_any & ~rock_steep & (lift_f == 0))
if not (LIDAR and NAIP):
    snag_c[:] = False     # FEAT-225: a snag is a lidar crown the imagery sees grey; without either there are none
del lift_f, forest_here
sr, sc = np.nonzero(snag_c)
del snag_c
# snags are capped at 3 % of what the client draws: the detected crowns plus the stand's expected stems, estimated
# here with the spruce crown (the stand's own species come below)
h4e = ndimage.maximum_filter(chm_s, 2)[::2, ::2]
stems_est = float((stand_ok[::2, ::2] * stands.K_CLOSE / (np.pi * np.maximum(stands.CROWN_RATIO[0] * np.maximum(h4e, 3.0), 0.5) ** 2)).sum() * 16)
del h4e
keep = spc.cap_snags(ndvi2[sr, sc], len(rows) + max(0.0, stems_est - len(rows)))
log(f"  snag candidates {len(sr)}, kept {len(keep)}")
sr, sc = sr[keep], sc[keep]
is_snag = np.concatenate([np.zeros(len(rows), bool), np.ones(len(sr), bool)])
rows = np.concatenate([rows, sr]); cols = np.concatenate([cols, sc]); hgt = np.concatenate([hgt, chm_top[sr, sc]]).astype(np.float32)
jx = rng.uniform(-0.9, 0.9, len(rows)); jy = rng.uniform(-0.9, 0.9, len(rows))
tx = X0 + (cols + 0.5) * R2 + jx - OX
ty = Y1 - (rows + 0.5) * R2 + jy - OY
tz = dem2[rows, cols].astype(np.float32)
elev = tz
chm_at = chm_top[rows, cols]      # measured canopy height (0 in lidar gaps), before the fill-tree floor
del chm_top
# terrain for the species rules: aspect, crests and valleys, distance to OSM streams
north2, east2, tpi_s2, tpi_l2 = spc.terrain_fields(dem2, R2)
sdist2 = spc.stream_distance(streams, R2, X0 - OX, Y1 - OY, H2, W2)
log(f"  streams {len(streams)}, cells within 25 m {np.mean(sdist2 < 25) * 100:.1f}%")
northeast = (north2[rows, cols] + east2[rows, cols]) / math.sqrt(2)
wet = np.clip(1 - (sdist2[rows, cols] - 30) / 70, 0, 1)
ridge = (tpi_s2[rows, cols] > 1.5) & (tpi_l2[rows, cols] > 15)
n_t = len(rows)
if evt is not None:
    # sample the class 0..15 m off each tree so 30 m pixel edges become ragged stand boundaries
    ang = rng.uniform(0, 2 * np.pi, n_t); rad = rng.uniform(0, 15, n_t)
    px_, py_ = tx + OX + np.cos(ang) * rad, ty + OY + np.sin(ang) * rad
    v = np.clip(evt(px_, py_), 0, lut_n - 1)
    vn = np.clip(evt_n(px_, py_), 0, lut_n - 1)     # DATA-015: built classes filled from the natural forest
    group, a_frac, alpine, naip_dec = group_lut[vn], aspen_lut[vn], alpine_lut[v], lut["built"][v]
    hw_frac = lut["hardwood"][vn]                    # FEAT-233: the eastern classes' bare broadleaf share
    group = spc.naip_conifer_group(group, lp_at(px_, py_), None if lodgepole_like is None else lodgepole_like[rows, cols], naip_dec)
    wet = np.maximum(wet, lut["riparian"][vn].astype(np.float64))
    # inside aspen classes: aspen with that probability; elsewhere keep NAIP-detected groves at 50 %; on built
    # classes NAIP alone decides
    roll = rng.uniform(0, 1, n_t)
    del v, vn, ang, rad, px_, py_
else:
    group = np.zeros(n_t, np.int8); a_frac = np.zeros(n_t, np.float32); alpine = np.zeros(n_t, bool); roll = np.ones(n_t)
    naip_dec = None; hw_frac = None
# FEAT-233: the region the fallbacks pick species by (no LANDFIRE, a class with no group): Colorado's rules in the
# west, bare hardwood and hemlock east of species.EAST_LON
region = spc.region_for(*to_ll.transform(OX, OY))
log(f"  species region {region.name}" + (f", eastern spruce-fir above {region.boreal:.0f} m" if region.east else ""))
# krummholz (BUG-025) stays: only a tree the lidar measured as short (1 to 4 m) near treeline or in an alpine
# LANDFIRE class. Colorado treeline is about 3,500 to 3,600 m; subalpine spruce-fir at Vail is tall right
# up to the summits, so elevation alone never makes a tree krummholz, and no lidar height is capped.
# DATA-021: the species' elevation bands were tuned on Vail, so they see the elevation relative to this resort's
# treeline (Big Sky's is about 500 m lower); no measured treeline (Vail) leaves them as they were.
elev_shift = (treeline_m - spc.COLORADO_TREELINE) if treeline_m else 0.0
log(f"  species elevation bands shifted {elev_shift:+.0f} m for the treeline")
species = spc.assign_species(tx, ty, elev - elev_shift, chm_at, group, a_frac, alpine, aspen_like[rows, cols], northeast, wet, ridge, roll, evt is not None,
                             naip_dec, hw_frac, region.shifted(elev_shift))
species[is_snag] = spc.SNAG
crown = spc.crown_radius(species, hgt)
trees = np.stack([tx, ty, tz, hgt, crown, species.astype(np.float32)], axis=1).astype(np.float32)
CELL = 1000.0
cells_x = int(math.ceil(W / CELL)); cells_y = int(math.ceil(H / CELL))
inst = {"cellSize": CELL, "minX": X0 - OX, "minY": Y0 - OY, "cellsX": cells_x, "cellsY": cells_y}
inst["treeCount"] = write_instances(out, "trees", trees, CELL, X0 - OX, Y0 - OY, cells_x, cells_y)
cnt = np.bincount(species.astype(np.int64), minlength=spc.N_SPECIES)
log(f"  trees {inst['treeCount']}: " + ", ".join(f"{spc.SPECIES_NAMES[i]} {cnt[i]} ({cnt[i] / max(n_t, 1) * 100:.1f}%)" for i in range(spc.N_SPECIES)))
lp = species == spc.LODGEPOLE
log(f"  spruce + fir {(cnt[spc.SPRUCE] + cnt[spc.FIR]) / max(n_t, 1) * 100:.1f}%, lodgepole below 3,100 m {np.mean(elev[lp] < 3100) * 100 if lp.any() else 0:.0f}%, "
    f"krummholz above 3,350 m {np.mean(elev[species == spc.KRUMMHOLZ] > 3350) * 100 if cnt[spc.KRUMMHOLZ] else 0:.0f}%, snags {cnt[spc.SNAG] / max(n_t, 1) * 100:.1f}%, "
    f"median height above 3,350 m {np.median(hgt[elev > 3350]) if (elev > 3350).any() else 0:.1f} m")
for line in spc.band_report(species, elev):
    log("   ", line)
log("  species by LANDFIRE group (built classes filled from the forest around):")   # FEAT-233
for line in spc.group_report(species, group):
    log("   ", line)
tree_species = {spc.SPECIES_NAMES[i]: round(float(cnt[i] / max(n_t, 1)), 4) for i in range(spc.N_SPECIES) if cnt[i]}
os.makedirs(os.path.join(out, "debug"), exist_ok=True)
spc.debug_png(os.path.join(out, "debug", "species.png"), tx, ty, species,
              group_lut[np.clip(evt_lf.on2(data=evt_nat), 0, lut_n - 1)] if evt is not None else None, X0 - OX, Y1 - OY, W, H)
log("  debug/species.png: species per 10 m (left), LANDFIRE group with the built classes filled (right)")
del northeast, wet, ridge, group, a_frac, alpine, roll, naip_dec, hw_frac, trees, crown, is_snag

# FEAT-074: stand density per 4 m cell (stands.py): the chance of a generated stem, the stand height and species,
# and the ground height, per 1 km tree cell. The detected crowns nearby count against the stand.
H4, W4 = H2 // 2, W2 // 2
blk = lambda a: a[:H4 * 2, :W4 * 2].reshape(H4, 2, W4, 2)
canopy4 = blk(stand_ok).mean(axis=(1, 3)).astype(np.float32)
del stand_ok
det4 = np.zeros((H4, W4), np.float32)
okp = (pr < H4 * 2) & (pc < W4 * 2)
np.add.at(det4, (pr[okp] // 2, pc[okp] // 2), 1)
h4 = blk(chm_s).max(axis=(1, 3))
if not LIDAR:
    h4 *= ts.ETH_STAND_K        # FEAT-225: the ETH canopy top stands taller than the trees under it
if lf_height is not None:
    # lidar gaps under the stand: LANDFIRE EVH (DATA-010) where the CHM reads under 4 m
    evh4 = lf_height.on2(slice(0, H4 * 2, 2), slice(0, W4 * 2, 2))
    gap = (h4 < 4) & np.isfinite(evh4)
    h4[gap] = np.maximum(h4[gap], evh4[gap])
    del evh4, gap
h4 = np.clip(h4, 3.0, 45.0).astype(np.float32)
z4 = blk(dem2).mean(axis=(1, 3)).astype(np.float32)
sp4 = np.zeros((H4, W4), np.int16)
si, sj = np.nonzero(canopy4 > 0)
r2_, c2_ = si * 2, sj * 2
sx4 = X0 + (sj + 0.5) * 4.0 - OX; sy4 = Y1 - (si + 0.5) * 4.0 - OY
ne4 = (north2[r2_, c2_] + east2[r2_, c2_]) / math.sqrt(2)
wet4 = np.clip(1 - (sdist2[r2_, c2_] - 30) / 70, 0, 1)
ridge4 = (tpi_s2[r2_, c2_] > 1.5) & (tpi_l2[r2_, c2_] > 15)
if evt is not None:
    v4 = np.clip(evt(sx4 + OX, sy4 + OY), 0, lut_n - 1)
    vn4 = np.clip(evt_n(sx4 + OX, sy4 + OY), 0, lut_n - 1)
    g4, af4, al4, nd4, hw4 = group_lut[vn4], aspen_lut[vn4], alpine_lut[v4], lut["built"][v4], lut["hardwood"][vn4]
    g4 = spc.naip_conifer_group(g4, lp_at(sx4 + OX, sy4 + OY), None if lodgepole_like is None else lodgepole_like[r2_, c2_], nd4)
    wet4 = np.maximum(wet4, lut["riparian"][vn4].astype(np.float64))
    del v4, vn4
else:
    g4 = np.zeros(len(si), np.int8); af4 = np.zeros(len(si), np.float32); al4 = np.zeros(len(si), bool); nd4 = hw4 = None
sp4[si, sj] = spc.assign_species(sx4, sy4, z4[si, sj] - elev_shift, h4[si, sj], g4, af4, al4, aspen_like[r2_, c2_], ne4, wet4, ridge4,
                                 spc.hash01(sx4, sy4, 9), evt is not None, nd4, hw4, region.shifted(elev_shift))
del si, sj, r2_, c2_, sx4, sy4, ne4, wet4, ridge4, g4, af4, al4, nd4, hw4
del lodgepole_like
p4 = stands.stem_chance(canopy4, h4, sp4, det4)
p4[canopy4 <= 0] = 0
log(f"  stands: canopy on {np.mean(canopy4 > 0) * 100:.1f}% of the 4 m cells, {p4.sum() / 1e6:.2f} M expected stems "
    f"({p4.sum() / max(np.count_nonzero(canopy4) * 16 / 1e4, 1e-6):.0f} per hectare of canopy), "
    f"detected crowns {len(pr) / 1e6:.2f} M")
stand_meta = stands.write(out, p4, h4, sp4, z4, CELL, X0 - OX, Y0 - OY, cells_x, cells_y, Z_MIN)
log(f"  stands/: {len(stand_meta['cells'])} cells, {stand_meta['stems'] / 1e6:.2f} M stems at full density")
del canopy4, det4, h4, z4, sp4, p4

# shrubs (DATA-020): willow on creek bottoms, juniper in spruce-fir gaps and on open south crests, sagebrush and
# Gambel oak in their LANDFIRE classes, young conifers along forest edges; density from NAIP NDVI where there is
# no canopy, at most 200 per hectare. Records x, y, z, height, radius, kind.
log("shrubs")
base_ok = have2 & ~built_any & (rock_w < 0.3) & (groomed < 0.3) & (ndvi2 > 0.05) & (slope2 < 40)
open_ = base_ok & ~canopy
low = base_ok & (chm < 4.0)                   # willow carr is short canopy, so it may read as canopy
near_stream = sdist2 < 25
valley = (tpi_l2 < -3) & (slope2 < 20)
south_ridge = (north2 < -0.5) & (tpi_s2 > 0.5) & (dem2 - elev_shift > 2700) & (dem2 - elev_shift < 3600)
del sdist2, tpi_l2, north2, east2, tpi_s2
gap_edge = ndimage.binary_dilation(canopy, iterations=6)            # within 12 m of canopy
edge_band = ndimage.binary_dilation(canopy, iterations=3) & (chm < 6.0)
if evt is not None:
    g2 = group_lut[evt2]
    riparian = lut["riparian"][evt2]; sage = lut["sage"][evt2]; oak = lut["oak"][evt2]
    spruce_fir = g2 == spc.G_SPRUCE_FIR
    conifer = lf_forest2 & ~np.isin(g2, (spc.G_ASPEN, spc.G_HARDWOOD))   # FEAT-233: no young conifers round bare hardwood
    del g2
else:
    riparian = sage = oak = np.zeros((H2, W2), bool)
    spruce_fir = dem2 - elev_shift > 2900
    conifer = dem2 - elev_shift > 2700
p_sh = spc.shrub_probabilities(R2, open_, ndvi2, near_stream, valley, riparian, spruce_fir, gap_edge, south_ridge, sage, oak,
                               edge_band & conifer, low=low)
del base_ok, open_, low, near_stream, valley, south_ridge, gap_edge, edge_band, riparian, sage, oak, spruce_fir, conifer
shrubs = spc.sample_shrubs(p_sh, R2, X0 - OX, Y1 - OY, dem2, np.random.default_rng(20))
del p_sh
inst["shrubCount"] = write_instances(out, "shrubs", shrubs, CELL, X0 - OX, Y0 - OY, cells_x, cells_y)
kc = np.bincount(shrubs[:, 5].astype(np.int64), minlength=len(spc.SHRUB_NAMES))
log(f"  shrubs {inst['shrubCount']}: " + ", ".join(f"{spc.SHRUB_NAMES[i]} {kc[i]}" for i in range(len(kc)))
    + f"; densest 100 m cell {spc.peak_density(shrubs, 100.0):.0f} / ha")
del shrubs

log("rocks")
# rocks draw from their own seed (FEAT-074), so a change to the tree draws above no longer moves them
rng = np.random.default_rng(11)
rr, rc = np.nonzero(rock_steep | (rock & (slope2 > 20)))
pick = rng.uniform(0, 1, len(rr)) < 0.06
rr, rc = rr[pick], rc[pick]
rx = X0 + (rc + rng.uniform(0, 1, len(rc))) * R2 - OX; ry = Y1 - (rr + rng.uniform(0, 1, len(rr))) * R2 - OY
rz = dem2[rr, rc]
size = (rng.gamma(2.5, 0.9, len(rr)) + 0.6).astype(np.float32)
rtype = np.where(slope2[rr, rc] > 35, 0, rng.integers(1, 3, len(rr))).astype(np.float32)
rocks = np.stack([rx, ry, rz, size, rng.uniform(0, 6.283, len(rr)), rtype], axis=1).astype(np.float32)
inst["rockCount"] = write_instances(out, "rocks", rocks, CELL, X0 - OX, Y0 - OY, cells_x, cells_y)
log(f"  rocks {inst['rockCount']}")

# ------------------------------------------------------------------ 9. meta
lon_c, lat_c = to_ll.transform(OX, OY)
# start: on a named groomed run (cfg["start_run"], default: the longest groomed intermediate), 15 m below
# its highest point and facing down the run. A lift top station lands the rider in the trees.
def run_length(r):
    pts = r["points"]
    return sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
# spawn choice only (not surface data): any green or blue run, groomed or not
cands = [r for r in runs if not r.get("area") and (r["groomed"] or r["difficulty"] in ("novice", "easy", "intermediate")) and len(r["points"]) >= 2]
want = cfg.get("start_run")
named = [r for r in cands if want and r["name"] == want]
if named:
    seg = max(named, key=lambda r: max(p[2] for p in r["points"]))
else:
    inter = [r for r in cands if r["difficulty"] == "intermediate" and r["name"]] or cands
    seg = max(inter, key=run_length) if inter else None
start = {"x": 0.0, "y": 0.0, "heading": 0.0}
if seg is not None:
    pts = seg["points"]
    if pts[0][2] < pts[-1][2]:
        pts = pts[::-1]            # make it run downhill
    (x0, y0, _), (x1, y1, _) = pts[0], pts[1]
    dx, dy = x1 - x0, y1 - y0
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    start = {"x": x0 + ux * 15.0, "y": y0 + uy * 15.0, "heading": math.atan2(ux, uy), "run": seg["name"]}
    log(f"  start on {seg['name']} ({seg['difficulty']}) at {start['x']:.0f}, {start['y']:.0f}")
meta = {"version": 1, "formatVersion": FORMAT_VERSION, "slug": slug, "name": cfg["name"], "crs": crs, "origin": [OX, OY], "lonlat": [lon_c, lat_c],
        "bounds": {"minX": X0 - OX, "minY": Y0 - OY, "maxX": X1 - OX, "maxY": Y1 - OY},
        "zRange": [float(np.floor(Z_MIN / 100) * 100 - 100), float(np.ceil(Z_MAX / 100) * 100 + 100)],
        "terrain": {"fine": fine_meta, "coarse": coarse_meta, "mid": mid_meta, "far": far_meta}, "mask": mask_meta, "ao": ao_meta, "dir": dir_meta, "moguls": mog_meta, "instances": inst, "stands": stand_meta, "treeSpecies": spc.TREE_SPECIES_VERSION,
        "start": start, "sun": {"azimuth": 160, "elevation": 30}, "attribution": cfg["attribution"]}
# FEAT-233: what the species rules made of the forest, for pack_report.py line 4 (the client doesn't read it)
meta["vegetation"] = {"region": region.name, "treeSpecies": tree_species,
                      **({"evtUnknown": round(evt_unknown, 4),
                          "evtGroups": {spc.GROUP_NAMES[g]: round(float(evt_groups[g]), 4) for g in range(len(evt_groups)) if evt_groups[g] >= 0.0005}}
                         if evt_unknown is not None else {})}
if (gnis_states or census_towns) and NAMES_ATTRIBUTION not in meta["attribution"]:   # FEAT-235
    meta["attribution"] = meta["attribution"] + [NAMES_ATTRIBUTION]
if lf_tifs and LANDFIRE_ATTRIBUTION not in meta["attribution"]:   # FEAT-175: pack_report.py line 13 checks every credit
    meta["attribution"] = meta["attribution"] + [LANDFIRE_ATTRIBUTION]
# FEAT-225: the pack's tier and the source of each layer (optional fields; the client ignores them). WorldCover and
# ETH credits go in whenever they built the trees or the masks, not only the far cover levels (cover.py)
meta["sources"] = SOURCES
meta["tier"] = tiers.tier_of({k: v["tier"] for k, v in SOURCES.items()})[0]
if not (LIDAR and NAIP):
    from cover import ATTRIBUTION as COVER_ATTRIBUTION
    meta["attribution"] = meta["attribution"] + [a for a in COVER_ATTRIBUTION if a not in meta["attribution"]]
if treeline_m:
    meta["treeline"] = round(float(treeline_m))
elif treeline_none:
    meta["treeline"] = None   # FEAT-234: measured, none; absent still means an older pack (or no forest to measure)
# FEAT-175: the values this build derived for the resort instead of copying Vail's (pack_report.py line 20)
meta["derived"] = {**({k: round(v, 4) for k, v in NT.items()} if NAIP else {}),     # FEAT-225: no NAIP, none read
                   **({"treeline": round(float(treeline_m))} if treeline_m and not cfg.get("treeline_m") else {}),
                   **({"treeline": None} if treeline_none else {})}
if REL:
    # FEAT-249: what was moved, and a credit line saying so (the terrain, trees and runs are the area's own; where
    # it sits is not)
    meta["derived"]["relocated"] = [m.record() for m in REL.moves]
    for m in REL.moves:
        dist = math.hypot(m.to[0] - m.c[0], m.to[1] - m.c[1]) / 1000
        note = (f"{m.name} is moved {dist:.1f} km{f' and turned {abs(m.turn):.0f} degrees' if m.turn else ''} from its real "
                "position to sit next to the rest of the resort; its terrain, trees, imagery and runs are its own")
        if m.source:     # FEAT-268: another resort, moved in for a custom map
            note = (f"{m.name} is moved {dist:.0f} km{f' and turned {abs(m.turn):.0f} degrees' if m.turn else ''} from "
                    "its real position to sit next to the other hills on this custom map; its terrain, trees, imagery "
                    "and runs are its own")
        if note not in meta["attribution"]:
            meta["attribution"] = meta["attribution"] + [note]
write_meta(out, meta)

# ------------------------------------------------------------------ 9b. the far tree ring (BUG-081)
# the lidar crowns on the ridges round the resort (far_trees.py), before the cover, whose land cover levels take
# their forest from them; needs lidar.far in the config and its nodes in raw/<slug>/ept_far/ (ept_select.py)
if (cfg.get("lidar") or {}).get("far") and glob.glob(os.path.join(raw, "ept_far", "*.laz")):
    log("far tree ring")
    import far_trees
    far_trees.main([slug, raw, out])
    meta = json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))
else:
    log("  no far tree ring (lidar.far and raw/<slug>/ept_far/): the ridges round the resort keep the land cover alone"
        + ("" if LIDAR else " (no lidar here, FEAT-225)"))

# ------------------------------------------------------------------ 10. forest cover levels for the far terrain (FEAT-153)
log("cover")
from cover import build_cover
meta["cover"] = build_cover(out, raw, cfg, log=log)
if any(lv["name"] in ("mid", "far") for lv in meta["cover"]["levels"]):   # DATA-019 land cover
    from cover import ATTRIBUTION as COVER_ATTRIBUTION
    meta["attribution"] = meta["attribution"] + [a for a in COVER_ATTRIBUTION if a not in meta["attribution"]]
write_meta(out, meta)
log("done")
