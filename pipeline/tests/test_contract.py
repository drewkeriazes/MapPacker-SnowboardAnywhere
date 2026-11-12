"""FEAT-239: the pack format contract (docs/pack-format.md > Contract) against the game's main.

The live checks read the game's main on GitHub (SBA_GAME_REPO: a checkout's working files instead) and skip with
a warning offline. The rest test the comparisons on made-up sources, so the bump rule is checked without a network.
"""
import os
import sys
import warnings

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import contract as C  # noqa: E402
from packwriter import FORMAT_VERSION  # noqa: E402


@pytest.fixture
def game():
    """game(rel) -> the game file's text from its main (or SBA_GAME_REPO); skips with a warning when offline"""
    def get(rel):
        try:
            return C.game_source(rel)[0]
        except C.GameUnreachable as e:
            warnings.warn(f"pack format contract not checked: {e}")
            pytest.skip(f"offline: {e}")
    return get


# ------------------------------------------------------------------ live: this pipeline against the game's main
def test_the_game_reads_the_format_the_pipeline_writes(game):
    bad = C.format_mismatch(FORMAT_VERSION, C.pack_format(game(C.FORMAT_TS)))
    assert bad is None, bad


def test_crown_ratio_matches_the_game_species(game):
    """cover.py and stands.py CROWN_RATIO are hand copies of SPECIES[].radius in species.ts: same ids, same values"""
    from cover import CROWN_RATIO as cover_ratio
    from stands import CROWN_RATIO as stands_ratio
    radii = C.species_radii(game(C.SPECIES_TS))
    assert C.radii_mismatch(cover_ratio, radii) is None, C.radii_mismatch(cover_ratio, radii)
    assert C.radii_mismatch(stands_ratio, radii) is None, C.radii_mismatch(stands_ratio, radii)


def test_default_treeline_matches_the_game(game):
    from species import COLORADO_TREELINE
    bad = C.treeline_mismatch(COLORADO_TREELINE, C.default_treeline(game(C.TREELINE_TS)))
    assert bad is None, bad


# ------------------------------------------------------------------ the comparisons and parsers, offline
def test_format_equal_passes_ahead_says_land_the_game_first_behind_says_land_ours():
    assert C.format_mismatch(1, 1) is None
    ahead = C.format_mismatch(2, 1)
    assert "land the game's format PR first" in ahead and "--game-repo" in ahead
    behind = C.format_mismatch(1, 2)
    assert "needs rebuild" in behind and "FORMAT_VERSION" in behind


def test_parsers_read_the_game_sources():
    assert C.pack_format("/** doc PACK_FORMAT = 9 */\nexport const PACK_FORMAT = 3;\n") == 3
    assert C.default_treeline("export const DEFAULT_TREELINE = 3480;") == 3480.0
    ts = ("export const SPECIES: Species[] = [\n"
          "  { id: 0, name: 'a', form: 'spruce', radius: 0.13, needles: [1, 2] },\n"
          "  { id: 1, name: 'b', form: 'aspen', radius: 0.17, needles: [1, 2] },\n];\n")
    assert C.species_radii(ts) == [0.13, 0.17]
    with pytest.raises(ValueError):
        C.species_radii(ts.replace("id: 1", "id: 2"))
    with pytest.raises(ValueError):
        C.pack_format("export const OTHER = 1;")


def test_radii_mismatch_names_the_species():
    assert C.radii_mismatch(np.array([0.13, 0.17]), [0.13, 0.17]) is None
    assert "id 1" in C.radii_mismatch([0.13, 0.2], [0.13, 0.17])
    assert "3 species" in C.radii_mismatch([0.13, 0.17], [0.13, 0.17, 1.1])


def test_game_repo_reads_a_checkout_and_check_reports_each_value(tmp_path):
    """--game-repo: the pair can be checked before either PR lands; a one-off format mismatch fails"""
    from cover import CROWN_RATIO
    from species import COLORADO_TREELINE

    def write(rel, text):
        p = tmp_path.joinpath(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    rows = ",\n".join(f"  {{ id: {i}, name: 's', radius: {r} }}" for i, r in enumerate(CROWN_RATIO))
    write(C.SPECIES_TS, f"export const SPECIES: Species[] = [\n{rows},\n];\n")
    write(C.TREELINE_TS, f"export const DEFAULT_TREELINE = {COLORADO_TREELINE:g};\n")
    write(C.FORMAT_TS, f"export const PACK_FORMAT = {FORMAT_VERSION};\n")
    assert all(bad is None for _, bad, _ in C.check(str(tmp_path)))
    assert C.main(["--game-repo", str(tmp_path)]) == 0
    write(C.FORMAT_TS, f"export const PACK_FORMAT = {FORMAT_VERSION - 1};\n")
    res = {name: bad for name, bad, _ in C.check(str(tmp_path))}
    assert "land the game's format PR first" in res["formatVersion"]
    assert C.main(["--game-repo", str(tmp_path)]) == 1


def test_offline_is_game_unreachable_not_a_failure(monkeypatch):
    monkeypatch.delenv("SBA_GAME_REPO", raising=False)
    def no_network(*a, **k):
        raise C.urllib.error.URLError("getaddrinfo failed")
    monkeypatch.setattr(C.urllib.request, "urlopen", no_network)
    C._fetch_main.cache_clear()
    try:
        with pytest.raises(C.GameUnreachable):
            C.game_source(C.FORMAT_TS, timeout=1)
        assert C.main([]) == 2
    finally:
        C._fetch_main.cache_clear()
