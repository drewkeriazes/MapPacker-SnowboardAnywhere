"""FEAT-225: the Silver and Bronze sources on the pack's grids, for build_pack.py.

- `mapterhorn_grid`: heights from Mapterhorn's Terrarium tiles (raw/<slug>/mapterhorn/<z>/<x>_<y>.webp) sampled
  bilinearly onto a UTM grid: the 1 m resort box and the 10 m mid ring outside the US, where there is no 3DEP.
- `landcover_grid`: ESA WorldCover 2021 classes and the ETH 2020 canopy height (raw/<slug>/landcover/, the same
  3 x 3 degree COGs the far cover levels read) on a UTM grid: the canopy height model where there is no lidar
  (Silver trees) and the surface classes where there is no NAIP (Bronze masks).
- `bronze_surface`: canopy, rock and scree from those classes, in the shape build_pack.py's NAIP rules give them.
"""
import glob
import math
import os

import numpy as np
from PIL import Image
from scipy import ndimage

from packwriter import decode_terrarium

TILE = 512
# WorldCover 2021 classes
WC_TREE, WC_SHRUB, WC_GRASS, WC_CROP, WC_BUILT, WC_BARE, WC_SNOW, WC_WATER, WC_WETLAND, WC_MANGROVE, WC_MOSS = \
    10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100
ETH_NODATA = 255
# Bronze stands in for NAIP's NDVI with the class's typical summer NDVI: only the shrub density (species.py
# shrub_probabilities) and the "vegetated" tests read it once the masks are made. Not an index the imagery gave.
CLASS_NDVI = {WC_TREE: 0.7, WC_SHRUB: 0.5, WC_GRASS: 0.4, WC_CROP: 0.45, WC_BUILT: 0.1, WC_BARE: 0.08, WC_SNOW: 0.0,
              WC_WATER: -0.3, WC_WETLAND: 0.45, WC_MANGROVE: 0.6, WC_MOSS: 0.25}
SHARE_SIGMA_M = 5.0     # WorldCover's 10 m blocks are smoothed over this before a class share is thresholded
HEIGHT_SIGMA_M = 5.0    # and the ETH heights over this, so neither shows its pixel grid on the 2 m mask
TREE_MIN_H = 3.0        # m: WorldCover tree cover the ETH model calls lower than this is scrub (as cover.py)
# The ETH model predicts the canopy top over 10 m (GEDI's RH98), taller than the stand the client draws: at Boston
# Mills the tallest lidar return per 4 m stand cell is 0.81 to 0.99 of it (median 22 to 26 m against 26 to 30 m in
# the four 1 km cells), and the stem chance falls with the square of the crown, so the stand height without lidar is
# the ETH height times this (FEAT-225, measured against the Gold build).
ETH_STAND_K = 0.85


# ------------------------------------------------------------------ Mapterhorn heights
# Mapterhorn rounds its heights by zoom (z16: 1/32 m, z13: 1/4 m), so on the 1 m grid a gentle slope is a stair of
# 3 cm steps (up to 2 degrees of normal noise) on the bilinear 0.8 m pixels. The resort box is smoothed over this
# much: half the 2 m mask cell, far less than a mogul (4 to 7 m).
DEQUANT_SIGMA_M = 1.0

def tile_xy(lon, lat, z):
    """global pixel coordinates (x, y) of lon/lat at zoom z on 512 px tiles (pixel i covers [i, i + 1))"""
    n = 2 ** z * TILE
    lat = np.clip(lat, -85.05, 85.05)
    x = (np.asarray(lon) + 180.0) / 360.0 * n
    y = (1.0 - np.log(np.tan(np.radians(lat)) + 1.0 / np.cos(np.radians(lat))) / np.pi) / 2.0 * n
    return x, y


def read_tiles(raw, z):
    """{(tx, ty): heights} of every Mapterhorn tile on disk at zoom z"""
    out = {}
    for p in glob.glob(os.path.join(raw, "mapterhorn", str(z), "*.webp")):
        tx, ty = os.path.basename(p)[:-5].split("_")
        out[(int(tx), int(ty))] = decode_terrarium(np.asarray(Image.open(p).convert("RGB")))
    return out


def mosaic(tiles):
    """the tiles as one array (NaN where one is missing) and the global pixel of its top-left corner"""
    if not tiles:
        return None, 0, 0
    xs = [k[0] for k in tiles]; ys = [k[1] for k in tiles]
    x0, y0 = min(xs), min(ys)
    a = np.full(((max(ys) - y0 + 1) * TILE, (max(xs) - x0 + 1) * TILE), np.nan, np.float32)
    for (tx, ty), h in tiles.items():
        a[(ty - y0) * TILE:(ty - y0 + 1) * TILE, (tx - x0) * TILE:(tx - x0 + 1) * TILE] = h
    return a, x0 * TILE, y0 * TILE


def bilinear(a, fx, fy):
    """`a` sampled at fractional (column, row) positions of its pixel centres; NaN outside or next to a void"""
    c0 = np.floor(fx).astype(np.int64); r0 = np.floor(fy).astype(np.int64)
    tx = (fx - c0).astype(np.float32); ty = (fy - r0).astype(np.float32)
    ok = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < a.shape[1]) & (r0 + 1 < a.shape[0])
    c0 = np.where(ok, c0, 0); r0 = np.where(ok, r0, 0)
    v = (a[r0, c0] * (1 - tx) * (1 - ty) + a[r0, c0 + 1] * tx * (1 - ty) +
         a[r0 + 1, c0] * (1 - tx) * ty + a[r0 + 1, c0 + 1] * tx * ty)
    return np.where(ok, v, np.nan).astype(np.float32)


def mapterhorn_grid(raw, z, to_ll, x0, y_top, res, w, h, block=2_000_000):
    """(h, w) float32 heights, row 0 = north, of the UTM grid whose north-west corner is (x0, y_top) at `res` m,
    sampled bilinearly from the zoom z tiles on disk (`to_ll`: a UTM -> lon/lat pyproj Transformer); NaN where no
    tile covers. Returns (grid, tiles read)."""
    tiles = read_tiles(raw, z)
    a, gx0, gy0 = mosaic(tiles)
    out = np.full((h, w), np.nan, np.float32)
    if a is None:
        return out, 0
    xs = x0 + (np.arange(w) + 0.5) * res
    rows = max(1, block // max(w, 1))
    for r in range(0, h, rows):
        r1 = min(h, r + rows)
        ys = y_top - (np.arange(r, r1) + 0.5) * res
        GX, GY = np.meshgrid(xs, ys)
        lon, lat = to_ll.transform(GX, GY)
        px, py = tile_xy(lon, lat, z)
        out[r:r1] = bilinear(a, px - gx0 - 0.5, py - gy0 - 0.5)
    return out, len(tiles)


# ------------------------------------------------------------------ WorldCover and ETH canopy height

def landcover_grid(raw, to_ll, x0, y_top, res, w, h, block=2_000_000):
    """(WorldCover class uint8, ETH canopy height float32 m with NaN for no data) on the UTM grid whose north-west
    corner is (x0, y_top) at `res` m, row 0 = north, each from its nearest 10 m pixel. Raises when the land cover
    is not on disk (gen_manifest.py fetches it with every resort unless the config turns it off)."""
    from cover import Mosaic
    lc = os.path.join(raw, "landcover")
    wc_p = sorted(glob.glob(os.path.join(lc, "worldcover", "*.tif")))
    eth_p = sorted(glob.glob(os.path.join(lc, "eth_canopy", "*.tif")))
    if not wc_p or not eth_p:
        raise SystemExit(f"no WorldCover or ETH canopy height in {lc}: a pack without lidar or NAIP (FEAT-225 Silver "
                         "and Bronze) builds its trees and masks from them; fetch them (landcover.enabled)")
    xs = [x0, x0 + w * res / 2, x0 + w * res]; ys = [y_top - h * res, y_top - h * res / 2, y_top]
    lo, la = to_ll.transform([x for x in xs for _ in ys], [y for _ in xs for y in ys])
    box = (min(lo) - 0.002, min(la) - 0.002, max(lo) + 0.002, max(la) + 0.002)
    wc_m, eth_m = Mosaic(wc_p, box, 0, 0), Mosaic(eth_p, box, 0, ETH_NODATA)
    wc = np.zeros((h, w), np.uint8); eth = np.full((h, w), np.nan, np.float32)
    gx = x0 + (np.arange(w) + 0.5) * res
    rows = max(1, block // max(w, 1))
    for r in range(0, h, rows):
        r1 = min(h, r + rows)
        GX, GY = np.meshgrid(gx, y_top - (np.arange(r, r1) + 0.5) * res)
        lon, lat = to_ll.transform(GX, GY)
        wc[r:r1] = wc_m.lookup(lon, lat)
        e = eth_m.lookup(lon, lat)
        eth[r:r1] = np.where(e == ETH_NODATA, np.nan, e.astype(np.float32))
    return wc, eth


def smooth(a, sigma_cells, valid=None):
    """normalised gaussian: NaN (or ~valid) cells do not pull the average down; NaN where nothing valid is near"""
    v = np.isfinite(a) if valid is None else valid & np.isfinite(a)
    num = ndimage.gaussian_filter(np.where(v, a, 0).astype(np.float32), sigma_cells)
    den = ndimage.gaussian_filter(v.astype(np.float32), sigma_cells)
    return np.where(den > 1e-3, num / np.maximum(den, 1e-3), np.nan).astype(np.float32)


def share(wc, classes, sigma_cells):
    """the smoothed share (0..1) of cells in any of `classes`"""
    return ndimage.gaussian_filter(np.isin(wc, classes).astype(np.float32), sigma_cells)


def canopy_height(eth, wc, res):
    """the canopy height model where there is no lidar: the ETH height smoothed over HEIGHT_SIGMA_M, 0 off
    WorldCover tree cover and where the ETH model has no data"""
    h = smooth(eth, HEIGHT_SIGMA_M / res)
    trees = share(wc, [WC_TREE, WC_MANGROVE], SHARE_SIGMA_M / res) > 0.5
    return np.where(trees & np.isfinite(h), h, 0).astype(np.float32)


def pseudo_ndvi(wc, res):
    """CLASS_NDVI per cell, smoothed like the class shares (Bronze has no imagery)"""
    lut = np.zeros(256, np.float32)
    for c, v in CLASS_NDVI.items():
        lut[c] = v
    return ndimage.gaussian_filter(lut[wc], SHARE_SIGMA_M / res).astype(np.float32)


def bronze_surface(wc, chm, slope, res):
    """canopy, rock (as the imagery would see it), steep rock and scree from WorldCover without NAIP: canopy is tree
    cover the ETH model has at TREE_MIN_H or more; rock is bare / sparse ground or moss and lichen, steep where the
    slope passes 28 degrees, and any open ground over 42 degrees; scree is bare ground between 12 and 28 degrees.
    Snow and ice stay snow. -> dict of bool arrays plus `have` (cells WorldCover classed)"""
    sig = SHARE_SIGMA_M / res
    have = wc > 0
    canopy = (share(wc, [WC_TREE, WC_MANGROVE], sig) > 0.5) & (chm >= TREE_MIN_H) & have
    bare = (share(wc, [WC_BARE, WC_MOSS], sig) > 0.5) & ~canopy & have
    snow = share(wc, [WC_SNOW], sig) > 0.5
    rock_steep = (bare & (slope > 28)) | ((slope > 42) & ~canopy & ~snow & have)
    scree = bare & (slope <= 28) & (slope > 12)
    return {"have": have, "canopy": canopy, "rock": bare | rock_steep, "rock_steep": rock_steep, "scree": scree}
