"""FEAT-272: pack_lint.py finds what is wrong with a pack's files before it is published."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import pack_lint  # noqa: E402
import publish_pack  # noqa: E402
from pack_fixtures import tiny_pack, write_json  # noqa: E402
from pack_lint import lint, lint_zip  # noqa: E402
from packwriter import FORMAT_VERSION  # noqa: E402


def test_a_clean_pack_has_no_problems(tmp_path):
    assert lint(tiny_pack(tmp_path)) == []


def test_a_missing_tile_is_named(tmp_path):
    p = tiny_pack(tmp_path)
    os.remove(os.path.join(p, "mask", "0_0.png"))
    assert any("mask/0_0.png" in x for x in lint(p))


def test_a_truncated_instance_file_is_named(tmp_path):
    p = tiny_pack(tmp_path)
    with open(os.path.join(p, "trees", "0_0.bin"), "ab") as f:
        f.write(b"\0" * 5)
    assert any("trees/0_0.bin" in x and "24" in x for x in lint(p))


def test_a_report_for_another_build_is_named(tmp_path):
    p = tiny_pack(tmp_path)
    write_json(os.path.join(p, "report.json"), {"build": "other"})
    assert any("report.json" in x for x in lint(p))


def test_wrong_format_version_is_named(tmp_path):
    p = tiny_pack(tmp_path, format_version=FORMAT_VERSION + 1)
    assert any("formatVersion" in x for x in lint(p))


def test_tree_density_over_the_ceiling_is_named(tmp_path, monkeypatch):
    monkeypatch.setattr(pack_lint, "MAX_TREES_PER_KM2", 1)
    assert any("per km2" in x for x in lint(tiny_pack(tmp_path)))


def test_lint_zip_reads_a_published_zip(tmp_path):
    p = tiny_pack(tmp_path)
    z = str(tmp_path / "p.zip")
    publish_pack.zip_pack(p, z)
    assert lint_zip(z) == []
