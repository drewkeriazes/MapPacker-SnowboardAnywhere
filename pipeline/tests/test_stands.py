"""FEAT-074: stand density per 4 m cell (stands.py)."""
import json, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import stands


def test_encode_decode_round_trip():
    rng = np.random.default_rng(0)
    n = 250
    p = rng.uniform(0, 1, (n, n)).astype(np.float32); p[p < 0.3] = 0
    h = rng.uniform(3, 40, (n, n)).astype(np.float32)
    sp = rng.integers(0, 8, (n, n))
    z = rng.uniform(2400, 3600, (n, n)).astype(np.float32)
    img = stands.encode(p, h, sp, z, 2300.0)
    assert img.shape == (2 * n, n, 3) and img.dtype == np.uint8
    p2, h2, sp2, z2 = stands.decode(img, 2300.0)
    assert np.abs(p2 - p).max() <= 0.5 / 255 + 1e-6
    assert np.abs(h2 - h).max() <= stands.H_STEP / 2 + 1e-4
    assert np.array_equal(sp2, sp)
    on = p > 0
    assert np.abs(z2 - z)[on].max() <= 0.5 / stands.Z_SCALE + 1e-3     # 3 cm ground height where stems can stand
    from scipy import ndimage
    near = ndimage.binary_dilation(on, structure=np.ones((3, 3), bool))
    assert np.abs(z2 - z)[near].max() <= 0.5 / stands.Z_SCALE + 1e-3    # and one cell round, for the bilinear lookup
    assert (z2[~near] == 2300.0).all()                                 # no ground height kept where nothing stands


def test_stem_chance():
    n = 40
    canopy = np.ones((n, n), np.float32)
    h = np.full((n, n), 17.0, np.float32)
    spruce = np.zeros((n, n), np.int64)
    none = np.zeros((n, n), np.float32)
    p = stands.stem_chance(canopy, h, spruce, none)
    # closed spruce, 17 m: a crown of 2.2 m covers 15.3 m2, so one stem per 15 m2 -> about one per 4 m cell
    assert np.allclose(p, min(1.0, 16 / (np.pi * (0.13 * 17) ** 2)), atol=1e-4)
    # half the canopy, half the stems (25 m spruce: 33 m2 crowns, under one stem per cell, so nothing clips)
    tall = np.full((n, n), 25.0, np.float32)
    pt = stands.stem_chance(canopy, tall, spruce, none)
    assert pt.max() < 1 and np.allclose(stands.stem_chance(canopy * 0.5, tall, spruce, none), pt * 0.5, atol=1e-4)
    # no canopy, no stems
    assert (stands.stem_chance(none, h, spruce, none) == 0).all()
    # detected crowns nearby count against the stand
    det = np.zeros((n, n), np.float32); det[::2, ::2] = 1           # a crown every 8 m
    pd = stands.stem_chance(canopy * 0.5, h, spruce, det)
    assert pd[n // 2, n // 2] < p[n // 2, n // 2] * 0.5
    # BUG-120: the closed-stand weight scales the chance, none outside closed stands
    closed = np.zeros((n, n), np.float32); closed[:, n // 2:] = 1; closed[:, n // 4:n // 2] = 0.5
    pc = stands.stem_chance(canopy * 0.5, tall, spruce, none, closed)
    pt5 = stands.stem_chance(canopy * 0.5, tall, spruce, none)
    assert (pc[:, :n // 4] == 0).all() and np.allclose(pc[:, n // 2:], pt5[:, n // 2:]) and np.allclose(pc[:, n // 4:n // 2], pt5[:, n // 4:n // 2] * 0.5)


def test_lidar_share_undoes_the_gap_closing():
    # BUG-131: a 6 m square of canopy on the 2 m grid, fattened by one cell each way by the build's closing, reads
    # as its true 3 x 3 cells; canopy under 3 m and cells off the canopy mask do not count
    chm = np.zeros((40, 40), np.float32); can = np.ones((40, 40), bool)
    chm[10:15, 10:15] = 12.0                                           # 5 x 5 cells after the closing
    chm[30:35, 30:35] = 2.0
    s = stands.lidar_share(chm, can)
    assert s.shape == (20, 20) and abs(s.sum() * 4 - 9) < 1e-5         # 9 of the 2 m cells are left
    can[:, :] = False
    assert stands.lidar_share(chm, can).sum() == 0


def test_stem_chance_to_share_fills_the_lidar_canopy():
    n = 120
    tall = np.full((n, n), 25.0, np.float32); spruce = np.zeros((n, n), np.int64)
    none = np.zeros((n, n), np.float32); canopy = np.ones((n, n), np.float32)
    share = np.full((n, n), 0.25, np.float32)
    # 25 m spruce: one stem covers 1.59 of a cell, so no cell is full and the drawn crowns are the share exactly
    p = stands.stem_chance_to_share(share, canopy, tall, spruce, none)
    assert p.max() < 1
    ratio, q = stands.cover_ratio(p, share, tall, spruce, none, block=40)
    assert abs(ratio - 1) < 0.01 and abs(q[1] - 1) < 0.02
    # the detected crowns count against it, as drawn: half the share already there, half the stems
    det = np.full((n, n), 0.125, np.float32)
    pd = stands.stem_chance_to_share(share, canopy, tall, spruce, det)
    assert np.allclose(pd, p * 0.5, atol=2e-3)
    assert abs(stands.cover_ratio(pd, share, tall, spruce, det, block=40)[0] - 1) < 0.01
    # no stems where none may stand, and none where the lidar sees no canopy
    off = canopy.copy(); off[:, :20] = 0
    assert (stands.stem_chance_to_share(share, off, tall, spruce, none)[:, :20] == 0).all()
    assert stands.stem_chance_to_share(none, canopy, tall, spruce, none).max() == 0
    # short fir (9 m: one stem covers 0.12 of a cell) cannot hold a 0.5 share: its cells fill, and the taller stand
    # beside it takes what they cannot, so the whole block still draws more than the cells' own cap allows
    h = tall.copy(); h[:, :60] = 9.0; sp = spruce.copy(); sp[:, :60] = 3
    dense = np.full((n, n), 0.25, np.float32); dense[:, :60] = 0.5
    pc = stands.stem_chance_to_share(dense, canopy, h, sp, none)
    assert (pc[:, :50] > 0.999).all()
    assert pc[:, 62:70].mean() > p[:, 62:70].mean() * 1.2             # the neighbours carry the overflow
    capped = np.minimum(dense, stands.stem_area(h, sp)).mean() / dense.mean()
    assert stands.cover_ratio(pc, dense, h, sp, none, block=40)[0] > capped + 0.03


def test_write_splits_cells_south_up(tmp_path):
    # two 1 km cells across, one up: 4 m grid 250 x 500, the south edge at min_y
    H, W = 250, 500
    p = np.zeros((H, W), np.float32); p[10, 260] = 0.8               # in the east cell, 42 m below its north edge
    h = np.full((H, W), 12.0, np.float32); sp = np.full((H, W), 3); z = np.full((H, W), 3000.0, np.float32)
    m = stands.write(str(tmp_path), p, h, sp, z, 1000.0, -1000.0, 0.0, 2, 1, 2300.0)
    assert m["cells"] == ["1_0"] and m["size"] == 250 and m["stems"] == 1
    img = np.asarray(Image.open(tmp_path / "stands" / "1_0.png"))
    assert img.shape == (500, 250, 3) and img[10, 10, 0] == round(0.8 * 255) and img[10, 10, 2] == 3
    # read back through the pack reader, as cover.py does
    meta = {"stands": m, "instances": {"cellSize": 1000.0, "minX": -1000.0, "minY": 0.0}, "bounds": {"minX": -1000.0, "maxY": 1000.0}}
    area, shade, hs, hc = stands.expected_crowns(str(tmp_path), meta, 4.0, W, H, 12.0)
    assert hc[10, 260] > 0.79 and area.sum() > 0 and hc.sum() == hc[10, 260]
