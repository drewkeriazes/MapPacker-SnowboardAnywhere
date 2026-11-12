"""FEAT-229: the `coarse` height set, 4 m between `fine` (1 m) and `mid` (16 m), over the fine set's area.

The game's 4 and 8 m terrain chunks (about 350 m to 1.7 km from the camera) read it instead of the 1 m tiles, so a
boot download (FEAT-230, boot_split.py) can hold the whole of it and only the fine tiles round the start, and the
ring still looks finished. Each sample is the mean of the 4 x 4 fine samples it covers (void samples left out; all
void stays void), so its centre falls where the height set's own rule puts it (minX + (i + 0.5) * 4). Same tiling
and anchor as fine (lower-left corner at fine's minX, minY), 512 samples per tile: 2 km tiles, 1/16 of the fine set.

build_pack.py writes it from the 1 m mosaic right after the fine set. CLI, to add it to a built pack from its fine
tiles without a rebuild:
  python pipeline/coarse_set.py packs/vail [packs/synth ...]
"""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from packwriter import TILE, decode_terrarium, write_height_set, write_meta  # noqa: E402

K = 4                      # fine samples per coarse sample side
RES = 4.0                  # m


def box_mean(grid: np.ndarray, k: int = K) -> np.ndarray:
    """(H, W) heights, row 0 = north, anchored south-west -> (ceil(H / k), ceil(W / k)) means of k x k blocks,
    padded on the north and east like packwriter.write_height_set; NaN samples are left out of each mean."""
    H, W = grid.shape
    nH, nW = -(-H // k), -(-W // k)
    top = nH * k - H                         # rows of padding on the north
    out = np.full((nH, nW), np.nan, np.float32)
    band = 256                               # output rows per pass, to bound the temporaries on a 12 km mosaic
    for o0 in range(0, nH, band):
        o1 = min(nH, o0 + band)
        r0, r1 = o0 * k - top, o1 * k - top
        blk = np.full(((o1 - o0) * k, nW * k), np.nan, np.float32)
        s0 = max(0, r0)
        blk[s0 - r0:r1 - r0, :W] = grid[s0:r1]
        blk = blk.reshape(o1 - o0, k, nW, k)
        ok = np.isfinite(blk)
        n = ok.sum(axis=(1, 3))
        s = np.where(ok, blk, 0).sum(axis=(1, 3), dtype=np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            out[o0:o1] = np.where(n > 0, s / np.maximum(n, 1), np.nan)
    return out


def write_coarse(out_dir: str, fine_grid: np.ndarray, min_x: float, min_y: float) -> dict:
    """the coarse set from the fine set's 1 m grid (as write_height_set got it); returns its meta block"""
    return write_height_set(out_dir, "coarse", box_mean(fine_grid), RES, min_x, min_y)


def coarse_from_tiles(pack_dir: str, fine: dict) -> np.ndarray:
    """the coarse grid from a built pack's fine tiles, one tile at a time (a whole 1 m mosaic is 0.5 GB for Vail)"""
    n = fine["tileSize"]
    if n % K:
        raise SystemExit(f"fine tiles of {n} samples do not split into {K} x {K} blocks")
    m = n // K
    grid = np.full((fine["tilesY"] * m, fine["tilesX"] * m), np.nan, np.float32)
    for ty in range(fine["tilesY"]):
        for tx in range(fine["tilesX"]):
            p = os.path.join(pack_dir, "fine", f"{tx}_{ty}.png")
            if not os.path.isfile(p):
                continue                          # an all-void tile is not written
            h = decode_terrarium(np.asarray(Image.open(p).convert("RGB")))
            r0 = (fine["tilesY"] - 1 - ty) * m
            grid[r0:r0 + m, tx * m:(tx + 1) * m] = box_mean(h)
    return grid


def add_to_pack(pack_dir: str) -> dict:
    """write coarse/ into a built pack from its fine tiles and add `terrain.coarse` to its meta.json"""
    with open(os.path.join(pack_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    fine = meta["terrain"].get("fine")
    if not fine:
        raise SystemExit(f"{pack_dir} has no fine height set")
    grid = coarse_from_tiles(pack_dir, fine)
    # the fine set is padded to whole tiles; drop the padding rows and columns that hold no data at all, so the
    # coarse set is no larger than the mosaic would give
    rows = np.flatnonzero(np.isfinite(grid).any(axis=1))
    cols = np.flatnonzero(np.isfinite(grid).any(axis=0))
    if not len(rows):
        raise SystemExit(f"{pack_dir}: the fine tiles hold no heights")
    grid = grid[rows[0]:, :cols[-1] + 1]          # keep the south-west anchor: trim only the north and east
    shutil.rmtree(os.path.join(pack_dir, "coarse"), ignore_errors=True)
    meta["terrain"]["coarse"] = write_height_set(pack_dir, "coarse", grid, RES, fine["minX"], fine["minY"])
    write_meta(pack_dir, meta)
    return meta["terrain"]["coarse"]


if __name__ == "__main__":
    for pack in sys.argv[1:]:
        c = add_to_pack(pack)
        print(f"{pack}: coarse set {c['tilesX']} x {c['tilesY']} tiles of {TILE * RES / 1000:.0f} km written, meta.json updated")
