"""Stand density per 4 m cell: the stems the client generates when a tree cell loads (FEAT-074).

The pack stores the detected crowns (`trees/`) and, per 1 km tree cell, `stands/<cx>_<cy>.png`: how likely a
generated stem is in each 4 m cell, the stand's height and species, and the ground height. The client draws
the stems with a seeded hash (stable between sessions) only near the camera, so millions of fill stems never
sit in the pack or in memory.

stands/<cx>_<cy>.png: RGB, SIZE wide and 2 * SIZE tall, row 0 = north.
  rows 0 .. SIZE-1, one pixel per 4 m cell:
    R  chance of one generated stem in the cell, 0..255 = 0..1
    G  stand height, H_STEP m per step
    B  species id 0..9 (species.py)
  rows SIZE .. 2*SIZE-1: the ground height at the cell centre, (z - zBase) * Z_SCALE as 16 bits, R high and G low,
    where a stem can stand and one cell round it; 0 elsewhere (no data). zBase is the pack's lowest ground, so
    a pack spans at most 2,048 m of relief. B (FEAT-298, packs with meta.instances.crownWidths): the cell's crown
    width factor x widths.WIDTH_STEP where a stem can stand, 0 elsewhere (and in older packs).
RGB only: a browser decoder that premultiplies alpha would zero the colour where alpha is 0.
"""
import math
import os
import numpy as np
from PIL import Image
from scipy import ndimage

RES = 4.0
H_STEP = 0.25
Z_SCALE = 32.0
# crown area per m2 of canopy that reads as closed forest: the stems' crowns cover the canopy once over
K_CLOSE = 1.0
# the client's crown radius / height per species id (game/src/world/trees/species.ts SPECIES[].radius;
# tests/test_contract.py checks it against the game's main)
CROWN_RATIO = np.array([0.13, 0.17, 1.1, 0.1, 0.09, 0.17, 0.35, 0.05, 0.26, 0.16])
# detected crowns count against the stand over this radius (m), so stems fill gaps instead of doubling clumps
DETECTED_SIGMA = 6.0


def stem_chance(canopy4, height4, species4, detected4, closed4=None):
    """chance (0..1) of one generated stem per 4 m cell, from the canopy mask: packs without lidar (FEAT-225) and the
    synthetic pack. A lidar pack fills to the lidar canopy share instead (`stem_chance_to_share`, BUG-131).

    canopy4: share of the cell under canopy 0..1; height4: stand height (m); species4: species id per cell;
    detected4: detected crowns per cell; closed4 (BUG-120): 0..1 weight of a closed stand per cell, or None.
    A closed stand wants K_CLOSE / (pi r^2) stems per m2 (r the drawn crown radius), scaled by the canopy share;
    the detected crowns nearby are subtracted. The canopy mask reads a sparse stand as closed canopy (BUG-069),
    so the stems are scaled by `closed4` too: a sparse stand is carried by its detected crowns alone."""
    r = CROWN_RATIO[np.clip(species4, 0, len(CROWN_RATIO) - 1).astype(np.int64)] * np.maximum(height4, 1.0)
    want = canopy4 * K_CLOSE / (np.pi * np.maximum(r, 0.5) ** 2)                 # stems per m2
    have = ndimage.gaussian_filter(detected4.astype(np.float32), DETECTED_SIGMA / RES) / RES ** 2
    p = np.clip((want - have) * RES ** 2, 0, 1)
    if closed4 is not None:
        p = p * np.clip(closed4, 0, 1)
    return p.astype(np.float32)


# BUG-131: the lidar canopy share the stems fill to is read over SHARE_SIGMA m, and what a full cell cannot hold (one
# stem per 4 m cell, at the species' crown width) is passed to the cells within about SPILL_SIGMA m, SPILL_ITERS times
SHARE_SIGMA = 8.0
SPILL_SIGMA = 40.0
SPILL_ITERS = 12
# a generated stem's mean height is this share of the stand's (the client draws 0.75 to 1 of it; expected_crowns)
STEM_H = 0.875


def lidar_share(chm2, canopy2):
    """BUG-131: the share of each 4 m cell truly under canopy, from the 2 m canopy height and canopy mask.

    Canopy 3 m or taller, eroded by one 2 m cell: build_pack closes the canopy height over 3 cells (6 m) to bridge
    the lidar's empty cells, which fattens every crown by a cell. Without the erosion the share reads 0.28 and 0.35
    within 250 m and 600 m of Vail's Back Bowls sign; with it 0.181 and 0.257, against 0.178 and 0.258 measured on
    the raw 1 m lidar there (canopy 3 m or taller)."""
    core = ndimage.binary_erosion((chm2 >= 3.0) & canopy2, np.ones((3, 3), bool))
    h4, w4 = core.shape[0] // 2, core.shape[1] // 2
    return core[:h4 * 2, :w4 * 2].reshape(h4, 2, w4, 2).mean(axis=(1, 3)).astype(np.float32)


def stem_area(height4, species4):
    """the crown share of a 4 m cell one drawn stem adds (the client's crown radius at the stems' mean height)"""
    r = CROWN_RATIO[np.clip(species4, 0, len(CROWN_RATIO) - 1).astype(np.int64)] * np.maximum(height4, 1.0) * STEM_H
    return (np.pi * np.maximum(r, 0.5 * STEM_H) ** 2 / RES ** 2).astype(np.float32)


def stem_chance_to_share(share4, canopy4, height4, species4, detected_area4):
    """BUG-131: chance (0..1) of one generated stem per 4 m cell, so that the drawn crowns cover what the lidar does.

    share4: the lidar canopy share per cell (`lidar_share`); canopy4: where a stem may stand (> 0); detected_area4:
    the detected crowns' drawn disc area per cell, as a share of the cell. The stems owe each cell the canopy share
    round it less the detected crowns' round it. A cell holds one stem at most, so a closed stand of narrow trees
    cannot hold its share; what it cannot hold goes to the stand's cells round it. (FEAT-074's rule filled the canopy
    mask's share instead, which over-reads a sparse stand by about half and was cut to closed stands in BUG-120,
    leaving Vail 30 to 40% under the lidar by the Back Bowls sign.)"""
    area = stem_area(height4, species4)
    cap = np.where(canopy4 > 0, area, 0).astype(np.float32)
    want = np.clip(ndimage.gaussian_filter(share4.astype(np.float32), SHARE_SIGMA / RES)
                   - ndimage.gaussian_filter(detected_area4.astype(np.float32), SHARE_SIGMA / RES), 0, None)
    add = np.minimum(want, cap)
    for _ in range(SPILL_ITERS):
        want = add + ndimage.gaussian_filter(want - add, SPILL_SIGMA / RES)
        add = np.minimum(want, cap)
    return np.clip(np.where(cap > 0, add / np.maximum(area, 1e-6), 0), 0, 1).astype(np.float32)


def cover_ratio(p4, share4, height4, species4, detected_area4, block=250):
    """BUG-131: drawn crown cover (detected crowns plus the stems in expectation) over the lidar canopy share: for the
    whole grid, and the 10th, 50th and 90th percentile over `block` x `block` cell blocks (1 km) with any forest"""
    drawn = detected_area4 + p4 * stem_area(height4, species4)
    rat = []
    for i in range(0, share4.shape[0] - block + 1, block):
        for j in range(0, share4.shape[1] - block + 1, block):
            s = float(share4[i:i + block, j:j + block].mean())
            if s > 0.05:
                rat.append(float(drawn[i:i + block, j:j + block].mean()) / s)
    q = [float(np.percentile(rat, k)) for k in (10, 50, 90)] if rat else [float("nan")] * 3
    return float(drawn.mean() / max(float(share4.mean()), 1e-9)), q


def encode(p, height, species, z, z_base, wb=None):
    """one cell's (SIZE x SIZE) fields to the RGB stand image (2 * SIZE x SIZE x 3, uint8); wb: the width factor
    bytes (FEAT-298, widths.encode_factor) or None"""
    top = np.stack([np.round(np.clip(p, 0, 1) * 255),
                    np.round(np.clip(height / H_STEP, 0, 255)),
                    np.clip(species, 0, 255)], axis=-1)
    # ground height where a stem can stand and one cell round it (the client interpolates it bilinearly)
    near = ndimage.binary_dilation(p > 0, structure=np.ones((3, 3), bool))
    q = np.where(near, np.round(np.clip((z - z_base) * Z_SCALE, 1, 65535)), 0).astype(np.int64)
    bot = np.stack([q >> 8, q & 255, np.zeros_like(q) if wb is None else wb.astype(np.int64)], axis=-1)
    return np.concatenate([top, bot], axis=0).astype(np.uint8)


def decode(img, z_base):
    """the inverse of `encode`: p, height (m), species, z (m) per 4 m cell"""
    n = img.shape[0] // 2
    t, b = img[:n].astype(np.float32), img[n:].astype(np.float32)
    return t[..., 0] / 255, t[..., 1] * H_STEP, t[..., 2].astype(np.int64), (b[..., 0] * 256 + b[..., 1]) / Z_SCALE + z_base


def write(out_dir, p, height, species, z, cell, min_x, min_y, cells_x, cells_y, z_base, wb=None):
    """split the pack-wide 4 m fields (row 0 = north, the south edge at min_y) into stands/<cx>_<cy>.png per tree
    cell; cells with no stem chance get no file. wb: the width factor bytes (FEAT-298) or None. Returns the meta entry."""
    size = int(round(cell / RES))
    H, W = p.shape
    d = os.path.join(out_dir, "stands"); os.makedirs(d, exist_ok=True)
    # south-aligned: pad (or crop) the north rows and the east columns to whole cells
    pad = lambda a: np.pad(a, ((max(0, cells_y * size - H), 0), (0, max(0, cells_x * size - W))))[-cells_y * size:, :cells_x * size]
    P, Hh, S, Z = pad(p), pad(height), pad(species), pad(z)
    WB = None if wb is None else pad(wb)
    names, stems = [], 0.0
    for cy in range(cells_y):
        r0 = (cells_y - 1 - cy) * size
        for cx in range(cells_x):
            sl = (slice(r0, r0 + size), slice(cx * size, (cx + 1) * size))
            if not (P[sl] > 0.5 / 255).any():
                continue
            Image.fromarray(encode(P[sl], Hh[sl], S[sl], Z[sl], z_base, None if WB is None else WB[sl]), "RGB").save(os.path.join(d, f"{cx}_{cy}.png"), optimize=True)
            names.append(f"{cx}_{cy}"); stems += float(np.round(P[sl] * 255).sum() / 255)
    return {"res": RES, "size": size, "zBase": float(z_base), "zScale": Z_SCALE, "hStep": H_STEP, "cells": sorted(names),
            "stems": int(round(stems))}


def width_factor(img):
    """FEAT-298: the width factor per 4 m cell of a stand image (lower half B / WIDTH_STEP; 0 reads as 1)"""
    from widths import WIDTH_STEP
    n = img.shape[0] // 2
    b = img[n:, :, 2].astype(np.float32)
    return np.where(b > 0, b / WIDTH_STEP, 1.0).astype(np.float32)


def read_all(pack_dir, meta, with_width=False):
    """yield (cx, cy, p, height, species, z) per stand file of a built pack, plus the width factor with `with_width`"""
    st = meta.get("stands")
    if not st:
        return
    for nm in st["cells"]:
        f = os.path.join(pack_dir, "stands", f"{nm}.png")
        if os.path.exists(f):
            cx, cy = (int(v) for v in nm.split("_"))
            img = np.asarray(Image.open(f).convert("RGB"))
            yield (cx, cy) + decode(img, st["zBase"]) + ((width_factor(img),) if with_width else ())


def expected_crowns(pack_dir, meta, res, w, h, shadow_h):
    """FEAT-074: the crown share the generated stems add per `res` m cell over the pack bounds (row 0 = north),
    in expectation (chance x crown area), plus the shadow-weighted share and height sums, for cover.py"""
    area = np.zeros((h, w), np.float64); shade = np.zeros((h, w), np.float64)
    hsum = np.zeros((h, w), np.float64); hcnt = np.zeros((h, w), np.float64)
    st, inst, b = meta.get("stands"), meta.get("instances") or {}, meta["bounds"]
    if not st:
        return area, shade, hsum, hcnt
    size, sres, cs = st["size"], st["res"], inst["cellSize"]
    cw = inst.get("crownWidths")
    for cx, cy, p, hh, sp, _z, wf in read_all(pack_dir, meta, with_width=True):
        i, j = np.nonzero(p > 0)
        x = inst["minX"] + cx * cs + (j + 0.5) * sres
        y = inst["minY"] + (cy + 1) * cs - (i + 0.5) * sres
        c = ((x - b["minX"]) / res).astype(int); r = ((b["maxY"] - y) / res).astype(int)
        ok = (c >= 0) & (c < w) & (r >= 0) & (r < h)
        pp, hv = p[i, j][ok], hh[i, j][ok]
        spp = np.clip(sp[i, j][ok], 0, len(CROWN_RATIO) - 1)
        a = pp * np.pi * (CROWN_RATIO[spp] * hv * 0.875) ** 2   # mean height 0.875 x the stand's
        if cw:   # FEAT-298: the stems' widths, their own draw in expectation
            import widths
            a = a * widths.area_factor(spp, wf[i, j][ok])
        np.add.at(area, (r[ok], c[ok]), a)
        np.add.at(shade, (r[ok], c[ok]), a * np.clip(hv * 0.875 / shadow_h, 0, 1.5))
        np.add.at(hsum, (r[ok], c[ok]), pp * hv * 0.875); np.add.at(hcnt, (r[ok], c[ok]), pp)
    k = res * res
    return area / k, shade / k, hsum, hcnt
