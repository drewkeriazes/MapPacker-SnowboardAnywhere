"""FEAT-245: tools/ci/build_pack_ci.py, the build-pack workflow's steps."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "ci"))
import build_pack_ci as ci  # noqa: E402


def config(resorts, slug, **cfg):
    d = os.path.join(resorts, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{slug}.json"), "w", encoding="utf-8") as f:
        json.dump({"name": slug.title(), **cfg}, f)


def test_a_new_slug_needs_a_name_and_an_osm_id(tmp_path):
    with pytest.raises(ci.Refused, match="new resort"):
        ci.check_inputs("Boston Mills", "", "boston-mills", "", tmp_path)
    got = ci.check_inputs(" Boston Mills ", "way/123", "boston-mills", "uid-1", tmp_path)
    assert got["mode"] == "new" and got["name"] == "Boston Mills" and got["osm_id"] == "way/123"
    assert got["deps"] == [] and got["tier"] == "gold"
    assert ci.check_inputs("Beaver Creek", "skimap/497", "beaver-creek", "", tmp_path)["osm_id"] == "skimap/497"
    for bad in ("skimap/0", "skimap.org/497", "node/5", "skimap/497; rm -rf /"):        # FEAT-286 shapes only
        with pytest.raises(ci.Refused, match="not an OSM or Skimap.org id"):
            ci.check_inputs("Beaver Creek", bad, "beaver-creek", "", tmp_path)


def test_an_existing_slug_is_a_rebuild_from_its_config(tmp_path):
    config(tmp_path, "vail", tier="gold", name="Vail")
    got = ci.check_inputs("", "", "vail", "", tmp_path)
    assert got["mode"] == "rebuild" and got["name"] == "Vail"


def test_the_workflow_call_reads_the_repo_resorts_folder(monkeypatch):
    """BUG-116: the workflow calls from_env(), no folder given; None must mean resorts/, not crash"""
    monkeypatch.setenv("SLUG", "vail")
    for k in ("NAME", "OSM_ID", "REQUESTED_BY"):
        monkeypatch.delenv(k, raising=False)
    assert ci.from_env()["mode"] == "rebuild"
    got = ci.check_inputs("Heavenly Mountain Resort", "relation/12152028", "no-such-resort-bug-116", "")
    assert got["mode"] == "new"
    assert sorted(ci.deps("ohio-hills")) == ["boston-mills", "mad-river-mountain"]


@pytest.mark.parametrize("slug,osm,who", [
    ("Vail", "", ""), ("vail;rm -rf /", "", ""), ("-vail", "", ""), ("a" * 61, "", ""),
    ("new", "way/12 $(id)", ""), ("new", "node/12", ""), ("new", "0", ""),
    ("new", "12", "uid with spaces"), ("new", "12", "x" * 129),
])
def test_inputs_outside_their_shapes_are_refused(tmp_path, slug, osm, who):
    with pytest.raises(ci.Refused):
        ci.check_inputs("Name", osm, slug, who, tmp_path)


@pytest.mark.parametrize("name", ["Vail\nrm", "--force", "-x"])
def test_a_name_with_control_characters_or_a_leading_dash_is_refused(tmp_path, name):
    with pytest.raises(ci.Refused):
        ci.check_inputs(name, "12", "new", "", tmp_path)


def test_a_relocate_source_is_not_built_on_its_own(tmp_path):
    config(tmp_path, "mad-river-mountain", source_only=True)
    with pytest.raises(ci.Refused, match="relocate source"):
        ci.check_inputs("", "", "mad-river-mountain", "", tmp_path)


def test_deps_fetch_raw_from_and_relocate_sources_first(tmp_path):
    config(tmp_path, "mad-river-mountain", source_only=True)
    config(tmp_path, "boston-mills", relocate=[{"source": "mad-river-mountain"}, {"offset": [1, 2]}])
    config(tmp_path, "ohio-hills", raw_from="boston-mills", relocate=[{"source": "mad-river-mountain"}])
    assert ci.deps("boston-mills", tmp_path) == ["mad-river-mountain"]
    assert ci.deps("ohio-hills", tmp_path) == ["mad-river-mountain", "boston-mills"]
    cfg = ci.check_inputs("", "", "ohio-hills", "", tmp_path)
    fetch = ci.stage_commands("fetch", cfg)
    assert [c[2] for c in fetch] == ["mad-river-mountain", "boston-mills", "ohio-hills"]
    assert all(c[-2:] == ["--stop-after", "grooming"] for c in fetch)


def test_resolve_uses_the_osm_id_alone_and_stops_after_the_plan(tmp_path):
    cfg = ci.check_inputs("Boston Mills", "way/42", "boston-mills", "", tmp_path)
    (cmd,) = ci.stage_commands("resolve", cfg)
    assert cmd[1].endswith("resort.py") and cmd[2] == "add" and cmd[-2:] == ["--", "Boston Mills"]
    assert cmd[cmd.index("--osm") + 1] == "way/42" and cmd[cmd.index("--slug") + 1] == "boston-mills"
    assert "--alone" in cmd and cmd[cmd.index("--stop-after") + 1] == "plan"
    config(tmp_path, "vail")
    assert ci.stage_commands("resolve", ci.check_inputs("", "", "vail", "", tmp_path)) == []


def test_publish_passes_the_run_and_the_requester(tmp_path):
    config(tmp_path, "vail", tier="silver")
    cfg = {**ci.check_inputs("", "", "vail", "uid-1", tmp_path), "run_url": "https://github.com/o/r/actions/runs/9"}
    (cmd,) = ci.stage_commands("publish", cfg)
    assert cmd[1].endswith("publish_pack.py") and cmd[2].endswith(os.path.join("packs", "vail"))
    assert cmd[cmd.index("--tier") + 1] == "silver"
    assert cmd[cmd.index("--run-url") + 1] == "https://github.com/o/r/actions/runs/9"
    assert "--requested-by=uid-1" in cmd


def test_a_requester_starting_with_a_dash_is_refused(tmp_path):
    with pytest.raises(ci.Refused):
        ci.check_inputs("Name", "12", "new", "-abc", tmp_path)


def test_the_name_is_escaped_in_the_summary():
    assert ci.md("A|B <b>*x*</b> [l](u)") == r"A\|B \<b\>\*x\*\</b\> \[l\](u)"


@pytest.mark.parametrize("text,want", [
    ("vail is unchanged since v4 (content ab): nothing to publish", "unchanged since v4: nothing published"),
    ("https://github.com/o/r/pull/7 is open with this content: nothing to publish",
     "already in https://github.com/o/r/pull/7: nothing published"),
    ("opened https://github.com/o/r/pull/8 (draft release vail/v5): ...", "opened https://github.com/o/r/pull/8"),
])
def test_the_summary_says_what_publish_did(text, want):
    assert ci.publish_result(text) == want


def test_a_stage_writes_a_summary_line_and_stops_on_failure(tmp_path, monkeypatch):
    config(tmp_path, "vail")
    summ = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    monkeypatch.setenv("SLUG", "vail")
    monkeypatch.setattr(ci, "from_env", lambda: ci.check_inputs("", "", "vail", "", tmp_path))
    calls = []
    assert ci.main(["build"], runner=lambda cmd: (calls.append(cmd), (0, "ok"))[1]) == 0
    assert ci.main(["report"], runner=lambda cmd: (3, "boom")) == 3
    lines = summ.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("| build | done |") and lines[1].startswith("| report | **failed** (exit 3) |")
    assert len(calls) == 1


def test_refused_inputs_fail_every_stage(tmp_path, monkeypatch):
    summ = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summ))
    for k, v in {"SLUG": "Bad Slug", "NAME": "", "OSM_ID": "", "REQUESTED_BY": ""}.items():
        monkeypatch.setenv(k, v)
    assert ci.main(["check"], runner=lambda cmd: pytest.fail("ran a command")) == 1
    assert "Refused" in summ.read_text(encoding="utf-8")


def test_inputs_writes_the_mode_for_the_cache_step(tmp_path, monkeypatch):
    out = tmp_path / "out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(ci, "from_env", lambda: ci.check_inputs("Boston Mills", "42", "boston-mills", "", tmp_path))
    assert ci.main(["inputs"]) == 0
    assert out.read_text(encoding="utf-8").splitlines() == ["mode=new", "slug=boston-mills"]
