"""FEAT-298: crown width by openness (widths.py), the stand image's width byte (stands.py) and the drawn radii (cover.py)"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cover  # noqa: E402
import stands  # noqa: E402
import widths as W  # noqa: E402
import species as spc  # noqa: E402


def test_open_trees_widen_toward_the_open_grown_ratio_crowded_ones_keep_the_species_radius():
    fir, spruce, douglas, lodgepole = 3, 0, 5, 4
    assert W.openness(0.0) == 1 and W.openness(1.0) == 0
    assert W.open_factor(fir, 1.0) == pytest.approx(W.OPEN_RATIO / 0.10)
    assert W.open_factor(spruce, 1.0) == pytest.approx(W.OPEN_RATIO / 0.13)
    assert W.open_factor(fir, 0.0) == 1
    # a species already wider than the open-grown ratio, and a high-crown form, keep their radius
    assert W.open_factor(douglas, 1.0) == 1
    assert W.open_factor(lodgepole, 1.0) == 1


def test_own_draw_has_mean_one_and_its_area_in_expectation():
    x, y = np.meshgrid(np.arange(200.0), np.arange(200.0))
    d = W.own_draw(np.zeros(x.size, int), x.ravel(), y.ravel(), spc.hash01)
    assert d.min() >= 1 - W.JITTER - 1e-6 and d.max() <= 1 + W.JITTER + 1e-6
    assert d.mean() == pytest.approx(1, abs=0.01)
    assert (d ** 2).mean() == pytest.approx(W.draw_area(), abs=0.01)
    assert np.all(W.own_draw(np.full(5, 4), np.arange(5.0), np.zeros(5), spc.hash01) == 1)


def test_hold_canopy_keeps_each_blocks_crown_area():
    rng = np.random.default_rng(1)
    p = rng.uniform(0.2, 0.9, (12, 12)).astype(np.float32)
    a_stem = np.full_like(p, 12.0)
    g = np.full_like(p, 1.6)                             # the stems widened
    a0 = np.zeros_like(p); a0[2, 2] = 30; a0[8, 9] = 40   # two detected crowns
    a1 = a0 * 1.5
    q = W.hold_canopy(p, a_stem, g, a0, a1, 4.0)
    k = int(W.BLOCK / 4)
    for bi in range(0, 12, k):
        for bj in range(0, 12, k):
            sl = (slice(bi, bi + k), slice(bj, bj + k))
            before = (p[sl] * a_stem[sl]).sum() + a0[sl].sum()
            after = (q[sl] * a_stem[sl] * g[sl]).sum() + a1[sl].sum()
            assert after == pytest.approx(before, rel=1e-4)
    assert np.all(q <= p + 1e-7)


def test_a_block_with_no_stems_keeps_its_wider_crowns():
    p = np.zeros((6, 6), np.float32)
    a0 = np.zeros_like(p); a0[1, 1] = 20
    q = W.hold_canopy(p, np.full_like(p, 10.0), np.full_like(p, 2.0), a0, a0 * 2, 4.0)
    assert not q.any()


def test_stand_image_carries_the_width_factor_and_the_stems_area_counts_it(tmp_path):
    n = 4
    p = np.full((n, n), 0.5, np.float32); p[0, 0] = 0
    h = np.full((n, n), 20.0, np.float32); sp = np.full((n, n), 3, np.int16); z = np.full((n, n), 2500.0, np.float32)
    f = np.full((n, n), 1.37, np.float32)
    wb = W.encode_factor(f, p)
    assert wb[0, 0] == 0 and wb[1, 1] == 137
    img = stands.encode(p, h, sp, z, 2000.0, wb)
    assert np.allclose(stands.width_factor(img)[1:, 1:], 1.37) and stands.width_factor(img)[0, 0] == 1
    # an older image (no width byte) reads factor 1
    assert np.all(stands.width_factor(stands.encode(p, h, sp, z, 2000.0)) == 1)


def test_drawn_radii_read_the_record_within_the_clamp_and_species_radii_ignore_it():
    sp = np.array([3, 3, 0, 2]); h = np.array([20.0, 20.0, 20.0, 2.0])
    nat = cover.CROWN_RATIO[sp] * h
    rec = nat * np.array([1.6, 9.0, 0.95, 1.0])
    assert np.allclose(cover.crown_radii(sp, h, rec, True), nat * np.array([1.6, 3.0, 0.95, 1.0]))
    # the legacy reading clamps to 0.85..1.25 of the natural radius
    assert np.allclose(cover.crown_radii(sp, h, rec), nat * np.array([1.25, 1.25, 0.95, 1.0]))
    # the species radii are what the record drew at before the widths (krummholz: 0.5 h pulled to 0.85 x 1.1 h)
    assert np.allclose(cover.species_radii(sp, h), cover.crown_radii(sp, h, spc.CROWN_K[sp] * h))


def test_multipliers_from_the_resort_config():
    k = W.multipliers({"crown_widths": {"k": 1.1, "species": {"fir": 1.2}}})
    assert k[0] == pytest.approx(1.1) and k[3] == pytest.approx(1.32)
    assert np.all(W.multipliers({}) == 1)
    with pytest.raises(ValueError):
        W.multipliers({"crown_widths": {"species": {"oak": 2}}})
    assert W.enabled({}) and not W.enabled({"crown_widths": False})


def test_meta_block_is_what_the_game_reads():
    m = W.meta_block(np.ones(10), 1.234567)
    assert set(m) == {"open", "cover", "jitter", "widen", "k", "crownArea"}
    assert m["crownArea"] == 1.2346 and m["widen"] == list(W.WIDEN) and len(m["k"]) == 10


def test_cover_check_compares_discs_round_the_spots_and_skips_ones_off_the_grid():
    drawn = np.full((500, 500), 0.2, np.float32); lidar = np.full((500, 500), 0.25, np.float32)
    rows = W.cover_check({"drawn": drawn, "lidar": lidar}, 4.0, 0.0, 2000.0, {"middle": (1000.0, 1000.0), "edge": (10.0, 10.0)}, (250.0, 600.0))
    assert [(r[0], r[1]) for r in rows] == [("middle", 250.0), ("middle", 600.0)]
    assert rows[0][2]["drawn"] == pytest.approx(0.2) and rows[0][2]["lidar"] == pytest.approx(0.25)


def test_apply_holds_the_canopy_and_writes_the_drawn_radius():
    rng = np.random.default_rng(4)
    n = 60
    p4 = np.zeros((n, n), np.float32); p4[:, : n // 2] = 0.8              # a closed stand in the west, open in the east
    h4 = np.full((n, n), 20.0, np.float32); sp4 = np.full((n, n), 3, np.int16)
    m = 300
    x = rng.uniform(0, n * 4, m); y = rng.uniform(0, n * 4, m); hgt = rng.uniform(10, 25, m)
    sp = np.where(rng.uniform(0, 1, m) < 0.5, 3, 4).astype(np.float32)   # fir widens, lodgepole does not
    trees = np.stack([x, y, np.zeros(m), hgt, np.zeros(m), sp], axis=1).astype(np.float32)
    r4 = np.clip(((n * 4) - y) // 4, 0, n - 1).astype(int); c4 = np.clip(x // 4, 0, n - 1).astype(int)
    p_new, wb, (after, before), meta, line = W.apply(trees, r4, c4, p4, h4, sp4, W.multipliers({}), spc.hash01)
    k = int(W.BLOCK / 4) * (n // 2 // int(W.BLOCK / 4))                 # the whole blocks in the stand
    assert after[:, :k].sum() == pytest.approx(before[:, :k].sum(), rel=1e-3)   # held where there are stems
    assert after[:, n // 2:].sum() > before[:, n // 2:].sum()                  # the open crowns keep their width
    assert np.all(p_new <= p4 + 1e-7) and p_new.sum() < p4.sum()
    lp = sp == 4
    assert np.allclose(trees[lp, 4], cover.species_radii(sp[lp], hgt[lp]))   # lodgepole keeps its radius
    rr = trees[~lp, 4] / hgt[~lp]
    assert rr.min() >= 0.1 * (1 - W.JITTER) - 1e-6 and rr.max() <= W.OPEN_RATIO * (1 + W.JITTER) + 1e-6
    assert wb[:, : n // 2].min() >= 100 and not wb[:, n // 2:].any()
    assert meta["crownArea"] > 1 and "crown widths" in line
