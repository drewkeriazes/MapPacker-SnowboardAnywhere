"""Crown width by openness (FEAT-298): wide trees in the open, narrow in a crowd, at the same canopy cover.

Every drawn tree of a species used to have the same crown radius for its height (spruce 0.13, fir 0.10 x height).
Real trees vary: a tree with open ground round it keeps its low branches and grows wide, one in a closed stand
grows tall and narrow. Measured from the raw 3DEP lidar (docs/research/crown-widths.md): open-grown conifers have a
crown radius of 0.15 to 0.17 x their height at Vail (round the Back Bowls sign) and Park City, isolated ones 0.16 to
0.18, with a spread of about +-40 %; inside closed stands the width cannot be resolved at about 1 point per m2.

The model, per tree:
  openness = 1 - smoothstep(COVER_OPEN, COVER_CLOSED, the neighbours' crown cover within 10 m at the species radii)
  factor   = 1 + (max(OPEN_RATIO, r) - r) / r * openness     (r = the species' crown ratio; species in WIDEN only)
  radius   = the species' radius x factor x the resort's and species' hand multipliers x the tree's own draw
             (1 - JITTER .. 1 + JITTER, mean 1)
The pack's drawn canopy was already right before the widening (crowns plus stems at the species radii cover
0.170 / 0.233 of the ground within 250 / 600 m of the sign against the lidar's 0.178 / 0.258), so widening alone
would overfill: per BLOCK the generated stems are thinned so the block's crown area stays what it was.

The game (SnowboardAnywhere game/src/world/trees/widths.ts) applies what the pack carries: record field 4 is the
radius to draw, B of a stand image's lower half the cell's factor x WIDTH_STEP, and the stem's own draw is a hash of
its position there (so the stem chance here counts it in expectation, `draw_area`). It runs the model itself only
for its clump impostors' stand patches, from the `crownWidths` block in the meta (`meta_block`).
"""
import numpy as np
from scipy import ndimage

import stands

OPEN_RATIO = 0.16
COVER_OPEN, COVER_CLOSED = 0.1, 0.5
JITTER = 0.35
# spruce, subalpine fir, Douglas-fir, eastern hemlock: low crown bases. Lodgepole (crown base 0.64 h), aspen and the
# other high-crown forms stay at the species radius: widened, they read as a wide cap on a bare pole.
WIDEN = (0, 3, 5, 9)
WIDTH_STEP = 100
NEIGHBOUR_R = 10.0
# m: the stems are thinned per block of this side so its crown area stays what it was at the species radii
BLOCK = 24.0
# salt of the detected crowns' own draw (the game draws its stems' with its own hash)
S_DRAW = 29


def smoothstep(lo, hi, x):
    t = np.clip((np.asarray(x, np.float64) - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


def openness(cover10):
    """0 (crowded) .. 1 (open) from the neighbours' crown cover within NEIGHBOUR_R"""
    return 1 - smoothstep(COVER_OPEN, COVER_CLOSED, cover10)


def widens(species):
    return np.isin(np.asarray(species, np.int64), WIDEN)


def open_factor(species, open_):
    """the width factor on the species' radius openness gives, before the hand multipliers and the tree's own draw"""
    s = np.clip(np.asarray(species, np.int64), 0, len(stands.CROWN_RATIO) - 1)
    rr = stands.CROWN_RATIO[s]
    f = 1 + (np.maximum(OPEN_RATIO, rr) - rr) / rr * np.asarray(open_, np.float64)
    return np.where(widens(s), f, 1.0)


def draw_area():
    """E[draw^2]: what a widened tree's own draw does to the mean crown area"""
    return 1 + JITTER * JITTER / 3


def own_draw(species, x, y, hash01):
    """the detected crowns' own width draw: 1 - JITTER .. 1 + JITTER where the species widens, else 1"""
    return np.where(widens(species), 1 - JITTER + 2 * JITTER * hash01(np.asarray(x), np.asarray(y), S_DRAW), 1.0)


def multipliers(cfg):
    """the hand multipliers per species id from the resort config's `crown_widths` block:
    {"k": all species, "species": {"fir": k, ...}} (names as species.SPECIES_NAMES); 1 where not given"""
    import species as spc
    c = cfg.get("crown_widths") or {}
    k = np.full(len(stands.CROWN_RATIO), float(c.get("k", 1.0)))
    for name, v in (c.get("species") or {}).items():
        if name not in spc.SPECIES_NAMES:
            raise ValueError(f"crown_widths.species: unknown species {name!r} (one of {spc.SPECIES_NAMES})")
        k[spc.SPECIES_NAMES.index(name)] *= float(v)
    return k


def enabled(cfg):
    """the resort config turns the widths off with "crown_widths": false"""
    return cfg.get("crown_widths", True) is not False


def cover10(area4, res):
    """the crown cover within NEIGHBOUR_R of each res cell from the crown area per m2 per cell (a disc mean, <= 1)"""
    r = int(round(NEIGHBOUR_R / res))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    disc = ((xx * xx + yy * yy) * res * res <= NEIGHBOUR_R ** 2).astype(np.float32)
    disc /= disc.sum()
    return np.clip(ndimage.convolve(area4.astype(np.float32), disc, mode="nearest"), 0, 1)


def stem_area(p4, h4, sp4):
    """the stems' expected crown area per 4 m cell at the species radii (stands.expected_crowns' mean height)"""
    s = np.clip(sp4, 0, len(stands.CROWN_RATIO) - 1).astype(np.int64)
    return p4 * np.pi * (stands.CROWN_RATIO[s] * h4 * 0.875) ** 2


def hold_canopy(p4, a_stem, g4, crown_a0, crown_a1, res):
    """thin the stems so each BLOCK keeps the crown area it had at the species radii.

    p4: stem chance per res cell; a_stem: a stem's expected crown area there at the species radius (m2, at chance 1);
    g4: what the widths do to a stem's mean area there (`area_factor`); crown_a0 / crown_a1: the detected crowns' area per cell at the species
    radii and as widened. Returns the new chance. A block whose widened crowns already hold its area loses its stems;
    one with no stems keeps its wider crowns (an open stand, where the lidar's canopy is wider than the species radii)."""
    k = int(round(BLOCK / res))
    H, W = p4.shape
    Hb, Wb = -(-H // k), -(-W // k)
    pad = lambda a: np.pad(a, ((0, Hb * k - H), (0, Wb * k - W))).reshape(Hb, k, Wb, k).sum(axis=(1, 3))
    s0 = p4 * a_stem
    s1 = s0 * g4
    target = pad(s0) + pad(crown_a0)
    need = target - pad(crown_a1)
    have = pad(s1)
    kb = np.where(have > 0, np.clip(need / np.maximum(have, 1e-9), 0, 1), 1.0)
    return (p4 * np.repeat(np.repeat(kb, k, 0), k, 1)[:H, :W]).astype(np.float32)


def area_factor(species, f):
    """a tree's mean drawn crown area over its area at the species radius, for width factor f (its own draw in
    expectation where the species widens)"""
    return np.asarray(f, np.float64) ** 2 * np.where(widens(species), draw_area(), 1.0)


def encode_factor(f4, p4):
    """B of a stand image's lower half: the factor x WIDTH_STEP where a stem can stand, 0 elsewhere"""
    return np.where(p4 > 0, np.clip(np.round(f4 * WIDTH_STEP), 1, 255), 0).astype(np.uint8)


def meta_block(k, crown_area):
    """meta.instances.crownWidths: the model the game's clumps widen by, and the detected crowns' drawn / species area"""
    return {"open": OPEN_RATIO, "cover": [COVER_OPEN, COVER_CLOSED], "jitter": JITTER, "widen": list(WIDEN),
            "k": [round(float(v), 4) for v in k], "crownArea": round(float(crown_area), 4)}


def cover_check(fields, res, min_x, max_y, spots, radii=(250.0, 600.0, 1500.0)):
    """the mean of each field in discs round named spots (local metres): [(spot, radius, {name: mean})] for the discs
    inside the grid. build_pack.py compares the drawn crown cover after the widening with before it (FEAT-298's guard:
    widening redistributes the canopy, it does not add to it) and shows the lidar's canopy share beside them."""
    first = next(iter(fields.values()))
    H, W = first.shape
    cx = min_x + (np.arange(W) + 0.5) * res; cy = max_y - (np.arange(H) + 0.5) * res
    out = []
    for name, (x, y) in spots.items():
        for rad in radii:
            j0, j1 = np.searchsorted(cx, [x - rad, x + rad]); i0, i1 = np.searchsorted(-cy, [-(y + rad), -(y - rad)])
            if j1 <= j0 or i1 <= i0:
                continue
            dx = cx[j0:j1][None, :] - x; dy = cy[i0:i1][:, None] - y
            disc = dx * dx + dy * dy <= rad * rad
            if disc.sum() * res * res < 0.9 * np.pi * rad * rad:   # the disc runs off the grid
                continue
            out.append((name, rad, {k: float(v[i0:i1, j0:j1][disc].mean()) for k, v in fields.items()}))
    return out


def apply(trees, r4, c4, p4, h4, sp4, k, hash01, res=4.0):
    """widen a pack's detected crowns and stems and thin the stems to hold the canopy (build_pack.py, synth_pack.py).

    trees: the tree records (x, y, z, height, crown, species), field 4 rewritten in place as the radius to draw;
    r4, c4: each tree's res cell in the stand grid; p4, h4, sp4: the stem chance, stand height and species per cell;
    k: multipliers(cfg). Returns (the new stem chance, the stand images' width bytes, the drawn crown share per cell
    after and before the widening (crowns plus the stems in expectation, for cover_check), meta_block, a log line)."""
    import cover
    sp_t = trees[:, 5].astype(np.int64); hgt = trees[:, 3]
    a0_t = np.pi * cover.species_radii(sp_t, hgt) ** 2
    H4, W4 = p4.shape
    crown_a0 = np.zeros((H4, W4), np.float64); np.add.at(crown_a0, (r4, c4), a0_t)
    a_stem = stem_area(np.ones_like(p4), h4, sp4)
    c10 = cover10(((crown_a0 + p4 * a_stem) / (res * res)).astype(np.float32), res)
    nb = np.pi * NEIGHBOUR_R ** 2
    f_t = (open_factor(sp_t, openness(np.clip(c10[r4, c4] - a0_t / nb, 0, 1))) * k[np.clip(sp_t, 0, len(k) - 1)]
           * own_draw(sp_t, trees[:, 0], trees[:, 1], hash01))
    crown_a1 = np.zeros((H4, W4), np.float64); np.add.at(crown_a1, (r4, c4), a0_t * f_t ** 2)
    f4 = (open_factor(sp4, openness(np.clip(c10 - p4 * a_stem / nb, 0, 1))) * k[np.clip(sp4, 0, len(k) - 1)]).astype(np.float32)
    stems0, area0 = float(p4.sum()), float((crown_a0 + p4 * a_stem).sum())
    g4 = area_factor(sp4, f4)
    p_new = hold_canopy(p4, a_stem, g4, crown_a0, crown_a1, res)
    drawn4 = ((crown_a1 + p_new * a_stem * g4) / (res * res)).astype(np.float32)
    before4 = ((crown_a0 + p4 * a_stem) / (res * res)).astype(np.float32)
    trees[:, 4] = (np.sqrt(a0_t / np.pi) * f_t).astype(np.float32)
    crown_area = float(crown_a1.sum() / max(crown_a0.sum(), 1e-9))
    wd = widens(sp_t)
    rh = trees[wd, 4] / np.maximum(hgt[wd], 1e-3)
    pc = (lambda q: float(np.percentile(rh, q))) if wd.any() else (lambda q: 0.0)
    line = (f"crown widths (FEAT-298): widened crowns r/h p10 {pc(10):.3f} p50 {pc(50):.3f} p90 {pc(90):.3f}; detected crown "
            f"area x{crown_area:.3f}; stems {stems0 / 1e6:.2f} M -> {p_new.sum() / 1e6:.2f} M to hold the canopy (crowns + stems "
            f"{area0 / 1e6:.2f} -> {float(drawn4.sum()) * res * res / 1e6:.2f} km2 of crown)")
    return p_new, encode_factor(f4, p_new), (drawn4, before4), meta_block(k, crown_area), line
