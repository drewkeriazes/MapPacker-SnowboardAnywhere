"""DATA-021: the treeline comes from the resort's own canopy, not Colorado's 3,480 m."""
import os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import treeline as tl


def mountain(line, seed=0):
    """Elevations 2000..4000 m, forest share 0.7 below `line`, fading to 0 over 100 m above it, plus noise."""
    rng = np.random.default_rng(seed)
    elev = rng.uniform(2000, 4000, 400_000)
    p = np.clip(0.7 * (1 - (elev - line) / 100), 0, 0.7)
    return elev, rng.random(elev.size) < p


def test_finds_a_low_and_a_high_treeline():
    for line in (2950, 3480):
        elev, forest = mountain(line)
        got = tl.derive_treeline(elev, forest)
        assert got is not None and abs(got - (line + 50)) <= 30, (line, got)


def test_isolated_trees_above_do_not_lift_it():
    elev, forest = mountain(2950, seed=1)
    stray = (elev > 3200) & (np.random.default_rng(2).random(elev.size) < 0.03)   # krummholz specks, 3 %
    got = tl.derive_treeline(elev, forest | stray)
    assert got is not None and got < 3100


def test_no_forest_or_tiny_area_gives_none():
    elev = np.linspace(2000, 3400, 100_000)
    assert tl.derive_treeline(elev, np.zeros(elev.size, bool)) is None
    assert tl.derive_treeline(elev[:500], np.ones(500, bool)) is None


def test_valid_mask_and_nan_are_ignored():
    elev, forest = mountain(3000, seed=3)
    elev = elev.copy(); elev[:1000] = np.nan
    valid = np.ones(elev.size, bool); valid[1000:2000] = False
    assert tl.derive_treeline(elev, forest, valid) is not None


def test_forest_to_the_top_is_a_measured_none():
    """FEAT-234: Boston Mills is forest from the valley to the top; that is no treeline, not Colorado's"""
    rng = np.random.default_rng(4)
    elev = rng.uniform(190, 312, 400_000)
    forest = rng.random(elev.size) < np.clip(0.6 + 0.25 * np.sin((elev - 190) / 40), 0, 1)
    assert tl.derive_treeline(elev, forest) is None
    assert tl.forested_to_top(elev, forest)


def test_a_treeline_or_no_forest_is_not_forested_to_the_top():
    for line in (2950, 3480):
        elev, forest = mountain(line)
        assert not tl.forested_to_top(elev, forest)
    elev = np.linspace(2000, 3400, 100_000)
    assert not tl.forested_to_top(elev, np.zeros(elev.size, bool))   # no forest: unknown, the client keeps its default
    assert not tl.forested_to_top(elev[:500], np.ones(500, bool))      # too small to say


def test_forested_to_top_is_exactly_where_derive_finds_none():
    """the two never disagree: a box with forest either has a treeline or is forested to the top"""
    rng = np.random.default_rng(5)
    for _ in range(40):
        lo = rng.uniform(100, 3000); hi = lo + rng.uniform(150, 1500); line = rng.uniform(lo, hi + 300)
        elev = rng.uniform(lo, hi, 60_000)
        forest = rng.random(elev.size) < np.clip(0.7 * (1 - (elev - line) / 100), 0.0, 0.7)
        got = tl.derive_treeline(elev, forest, min_cells=500)
        top = tl.forested_to_top(elev, forest, min_cells=500)
        assert not (got is not None and top), (lo, hi, line, got)
