"""FEAT-175 step 3: build_resort.py runs each stage once, skips it while its inputs are unchanged, trusts what is
already on disk the first time, and stops with a message on a failed check. The scripts are replaced by a fake
runner that writes their outputs into a temp folder."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build_resort as B  # noqa: E402
from packwriter import FORMAT_VERSION  # noqa: E402
from gen_manifest import MANIFEST_VERSION  # noqa: E402

CFG = {"slug": "demo", "name": "Demo", "country": "US", "crs": "EPSG:26913", "utm_bbox": [0, 0, 1000, 1000],
       "lonlat_bbox": [-106.1, 39.4, -106.0, 39.5], "terrain_status_url": "https://www.demo.example/x.aspx",
       "naip": {"res_m": 1, "items": []},
       "lidar": {"ept": "https://x/", "dataset": "D", "nodes_file": "demo_ept_nodes.txt",
                 "far": {"pad_m": 5000, "max_depth": 9, "nodes_file": "demo_ept_far_nodes.txt"}}}


class Fake:
    """stands in for the scripts: records each command and writes what the script would"""

    def __init__(self, r, fail=None, fetch_code=0, osm=None, finds=True):
        self.r, self.fail, self.fetch_code, self.osm, self.finds = r, fail, fetch_code, osm, finds
        self.calls = []
        self.envs = []

    def __call__(self, cmd, cwd=None, env=None):
        self.envs.append(env)
        script = os.path.basename(cmd[1] if cmd[0] != "powershell" else cmd[cmd.index("-File") + 1])
        self.calls.append(script if "fetch_landfire" not in script else f"{script} {cmd[3]}")
        if self.fail and self.fail in script:
            return 1
        r = self.r
        if script == "ept_select.py":
            for p in r.node_files():
                open(p, "w").write("0-0-0-0 1-0-0-0")
        elif script == "gen_manifest.py":
            box = json.load(open(r.cfg_path))["utm_bbox"]      # the real manifest follows the box
            json.dump({"slug": "demo", "manifestVersion": MANIFEST_VERSION, "items": [{"url": f"u{box}", "path": "dem1m/a.tif"}]},
                      open(r.man_path, "w"))
        elif script == "fetch.ps1":
            if self.fetch_code:
                return self.fetch_code
            for d in ("dem1m", "dem10m", "naip1m", "mapterhorn", "ept", "ept_far", "landcover/worldcover",
                      "landcover/eth_canopy"):
                os.makedirs(os.path.join(r.raw, d), exist_ok=True)
                open(os.path.join(r.raw, d, "ept.json" if d == "ept" else "a"), "w").write("x")
            os.makedirs(os.path.join(r.raw, "osm"), exist_ok=True)
            for q in B.OSM_NEED + ("pistes_wide",):
                json.dump(self.osm if self.osm is not None else {"elements": [{"id": 1}]},
                          open(os.path.join(r.raw, "osm", f"{q}.json"), "w"))
            open(os.path.join(r.raw, "FETCH_COMPLETE.txt"), "w").write("complete")
        elif script == "fetch_landfire.mjs":
            d = dict(B.LANDFIRE)[cmd[3]]
            os.makedirs(os.path.join(r.raw, d), exist_ok=True)
            open(os.path.join(r.raw, d, "c.tif"), "w").write("x")
        elif script == "fetch_grooming.py":
            os.makedirs(os.path.join(r.raw, "grooming"), exist_ok=True)
            open(os.path.join(r.raw, "grooming", "20240101.json"), "w").write("{}")
        elif script == "build_pack.py":
            os.makedirs(r.out, exist_ok=True)
            json.dump({"slug": "demo", "name": "Demo", "formatVersion": FORMAT_VERSION, "pipeline": "abc1234",
                       "build": "b1"}, open(os.path.join(r.out, "meta.json"), "w"))
        elif script == "gen_content.py":
            m = json.load(open(os.path.join(r.out, "meta.json")))
            m["generated"] = {"start": self.finds, "shots": int(self.finds)}
            if not self.finds:                                  # no start, no camera spot
                json.dump(m, open(os.path.join(r.out, "meta.json"), "w"))
                return 0
            m["start"] = {"x": 0, "y": 0, "heading": 0, "source": "generated"}
            json.dump(m, open(os.path.join(r.out, "meta.json"), "w"))
            os.makedirs(os.path.join(r.out, "attract"), exist_ok=True)
            json.dump([{"id": "a"}], open(os.path.join(r.out, "attract", "shots.json"), "w"))
            json.dump({"shots": True, "generated": True}, open(os.path.join(r.out, "attract", "index.json"), "w"))
        elif script == "auto_attract.mjs":
            self.packs = os.environ.get("SHOT_PACKS")
            json.dump({"shots": True, "generated": True, "stills": ["a"], "ghosts": ["a-start-run-1.json"]},
                      open(os.path.join(r.out, "attract", "index.json"), "w"))
        elif script == "propose_spots.py":
            self.packs = os.environ.get("SHOT_PACKS")
        return 0


@pytest.fixture
def resort(tmp_path, monkeypatch):
    res, man = tmp_path / "resorts", tmp_path / "manifests"
    (res / "demo").mkdir(parents=True); man.mkdir()
    json.dump(CFG, open(res / "demo" / "demo.json", "w"))   # FEAT-244: a folder per resort
    monkeypatch.setattr(B, "pipeline_code", lambda repo=B.REPO: "code1")
    monkeypatch.setattr(B, "same_code", lambda commit, repo=B.REPO: commit == "abc1234")
    monkeypatch.setattr(B, "game_tool", lambda rel: None)     # no game checkout: attract and spots skip
    r = B.Resort("demo", str(tmp_path / "raw" / "demo"), str(tmp_path / "packs" / "demo"), str(res), str(man))
    return r


def go(r, fake, **kw):
    lines = []
    B.build(r, B.Context(runner=fake, email="me@example.com", **{k: v for k, v in kw.items() if k in ("force", "gate")}),
            kw.get("first"), kw.get("last"), kw.get("dry", False), out=lines.append)
    return lines


def test_first_run_runs_every_stage_then_nothing_but_index_and_report(resort):
    f = Fake(resort)
    go(resort, f)
    assert f.calls == ["ept_select.py", "gen_manifest.py", "fetch.ps1", "fetch_landfire.mjs EVT",
                       "fetch_landfire.mjs EVC", "fetch_landfire.mjs EVH", "fetch_grooming.py", "build_pack.py",
                       "gen_content.py", "pack_report.py"]
    assert json.load(open(os.path.join(resort.out, "..", "index.json")))["packs"] == ["demo"]
    f2 = Fake(resort)
    lines = go(B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests), f2)
    assert f2.calls == ["pack_report.py"]
    assert "[fetch] skip: inputs unchanged" in lines and "[build] skip: inputs unchanged" in lines


def test_a_build_by_uncommitted_code_is_skipped_once_recorded(resort, monkeypatch):
    # build_pack.py stamps "<sha>+dirty" while pipeline/ has changes; the recorded fingerprint still matches
    monkeypatch.setattr(B, "same_code", lambda commit, repo=B.REPO: False)
    go(resort, Fake(resort))
    f = Fake(resort)
    go(B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests), f)
    assert f.calls == ["pack_report.py"]


def test_a_config_change_runs_the_stages_after_it(resort):
    go(resort, Fake(resort))
    cfg = dict(CFG, utm_bbox=[0, 0, 2000, 1000], lonlat_bbox=[-106.1, 39.4, -105.98, 39.5])
    json.dump(cfg, open(resort.cfg_path, "w"))
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    f = Fake(r)
    go(r, f)
    # new box: new node lists, manifest, fetch (resumes), LANDFIRE clip again (forced: the box moved), build
    assert f.calls[:3] == ["ept_select.py", "gen_manifest.py", "fetch.ps1"]
    assert "fetch_landfire.mjs EVT" in f.calls and "build_pack.py" in f.calls
    assert "fetch_grooming.py" not in f.calls       # same feed URL


def test_existing_outputs_are_adopted_on_the_first_run(resort):
    # a resort fetched and built before build_resort.py: node lists, manifest, raw data, clips, reports, pack
    go(resort, Fake(resort))
    os.remove(resort.state_path)
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    f = Fake(r)
    lines = go(r, f)
    assert f.calls == ["pack_report.py"]
    assert "[nodes] skip: already on disk (adopted)" in lines and "[build] skip: already on disk (adopted)" in lines
    # a pack from other pipeline code is built again
    os.remove(resort.state_path)
    m = json.load(open(os.path.join(resort.out, "meta.json")))
    json.dump(dict(m, pipeline="old9999"), open(os.path.join(resort.out, "meta.json"), "w"))
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    f = Fake(r)
    go(r, f)
    assert f.calls == ["build_pack.py", "gen_content.py", "pack_report.py"]


def test_a_new_manifest_fetches_again(resort):
    go(resort, Fake(resort))
    json.dump({"slug": "demo", "manifestVersion": MANIFEST_VERSION, "items": [{"url": "u2", "path": "landcover/x.tif"}]},
              open(resort.man_path, "w"))                 # a layer added to the download list
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    f = Fake(r)
    lines = go(r, f)
    assert "[manifest] run: inputs changed" not in lines        # the manifest's own inputs did not change
    assert f.calls == ["fetch.ps1", "build_pack.py", "gen_content.py", "pack_report.py"]


def test_failed_downloads_stop_with_a_message(resort):
    with pytest.raises(B.Failed, match="some downloads failed"):
        go(resort, Fake(resort, fetch_code=2))
    assert "fetch" not in resort.state                          # not recorded: the next run fetches again
    assert resort.state["manifest"]


def test_an_overpass_error_page_is_caught_after_the_fetch(resort):
    with pytest.raises(B.Failed, match=r"OSM ski \(no elements: runtime error"):
        go(resort, Fake(resort, osm={"remark": "runtime error: Query timed out", "elements": []}))


def test_raw_data_fetched_earlier_is_checked_too(resort):
    go(resort, Fake(resort))
    os.remove(os.path.join(resort.raw, "osm", "ski.json"))
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    with pytest.raises(B.Failed, match=r"OSM ski \(missing or not JSON\)"):
        go(r, Fake(r))


def test_land_cover_and_the_far_ring_are_required(resort):
    go(resort, Fake(resort))
    import shutil
    shutil.rmtree(os.path.join(resort.raw, "landcover", "eth_canopy"))
    os.remove(os.path.join(resort.raw, "osm", "pistes_wide.json"))
    shutil.rmtree(os.path.join(resort.raw, "ept_far"))
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    with pytest.raises(B.Failed) as e:
        go(r, Fake(r))
    assert "ETH canopy height" in str(e.value) and "far ring lidar" in str(e.value) and "OSM pistes_wide" in str(e.value)
    assert "--force fetch" in str(e.value)
    # a config with land cover off and no far ring needs neither
    json.dump(dict(CFG, landcover={"enabled": False}, lidar={k: v for k, v in CFG["lidar"].items() if k != "far"}),
              open(resort.cfg_path, "w"))
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    B.check_raw(r)


def test_an_old_manifest_is_made_again_but_the_same_items_fetch_nothing(resort):
    go(resort, Fake(resort))
    m = json.load(open(resort.man_path))
    del m["manifestVersion"]                            # a manifest from before FEAT-223
    json.dump(m, open(resort.man_path, "w"))
    os.remove(resort.state_path)                        # and never seen by build_resort.py
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    f = Fake(r)
    lines = go(r, f)
    assert "[manifest] run: not done yet" in lines
    assert f.calls == ["gen_manifest.py", "pack_report.py"]    # same items: the fetch and the build are adopted


def test_landfire_without_an_email_stops(resort):
    f = Fake(resort)
    with pytest.raises(B.Failed, match="LANDFIRE needs an email"):
        B.build(resort, B.Context(runner=f), out=lambda *a: None)
    assert f.calls[-1] == "fetch.ps1"


def test_outside_the_us_and_without_a_feed_those_stages_skip(resort):
    json.dump(dict(CFG, country="CA", terrain_status_url=None), open(resort.cfg_path, "w"))
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    f = Fake(r)
    lines = go(r, f)
    assert not any("landfire" in c or "grooming" in c for c in f.calls)
    assert "[landfire] skip: outside the US" in lines and "[grooming] skip: no terrain_status_url" in lines


def test_from_stop_after_force_and_dry_run(resort):
    f = Fake(resort)
    go(resort, f, last="manifest")
    assert f.calls == ["ept_select.py", "gen_manifest.py"]
    f = Fake(resort)
    lines = go(resort, f, dry=True)
    assert f.calls == [] and "[fetch] run: not done yet" in lines
    go(resort, Fake(resort))
    f = Fake(resort)
    go(resort, f, first="build", force=["build"])
    assert f.calls == ["build_pack.py", "gen_content.py", "pack_report.py"]   # a new meta.json: the content again
    f = Fake(resort)
    go(resort, f, force=["all"])
    assert len(f.calls) == 10                      # attract and spots skip without the game, forced or not


def test_a_failed_build_and_the_gate(resort):
    with pytest.raises(B.Failed, match="build_pack.py failed"):
        go(resort, Fake(resort, fail="build_pack"))
    with pytest.raises(B.Failed, match="MVP lines"):
        go(resort, Fake(resort, fail="pack_report"), gate=True)


def test_the_raw_folder_must_be_named_for_the_slug(resort, tmp_path):
    r = B.Resort("demo", str(tmp_path / "raw" / "other"), resort.out, resort.resorts, resort.manifests)
    with pytest.raises(B.Failed, match="not named demo"):
        go(r, Fake(r))


def test_raw_lives_in_the_main_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv("SBA_RAW_ROOT", raising=False)
    root = B.default_raw_root()
    assert os.path.basename(root) == "raw" and os.path.isdir(os.path.join(os.path.dirname(root), ".git"))
    monkeypatch.setenv("SBA_RAW_ROOT", str(tmp_path))
    assert B.default_raw_root() == str(tmp_path)


def moved_state(resort, tmp_path, monkeypatch, old_build="b1"):
    """FEAT-238: the resort as SnowboardAnywhere left it: built there (its packs/demo, the game's pipeline code),
    with the same pack copied here"""
    go(resort, Fake(resort))
    game = tmp_path / "SnowboardAnywhere"
    (game / "packs" / "demo").mkdir(parents=True)
    json.dump({"build": old_build}, open(game / "packs" / "demo" / "meta.json", "w"))
    monkeypatch.setenv("SBA_GAME_REPO", str(game))
    monkeypatch.setattr(B, "MOVED", {"from": "test", "game_code": "gamecode", "code": "code1"})
    r = B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)
    r.state["build"] = B.build_inputs(r, "gamecode", str(game / "packs" / "demo"))
    r.save()
    return B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests)



def test_a_build_from_before_the_move_still_counts_after_a_path_only_change(resort, tmp_path, monkeypatch):
    """FEAT-244: build code listed in MOVED["same"] (it only reads files from new places) keeps the moved packs"""
    r = moved_state(resort, tmp_path, monkeypatch)
    monkeypatch.setattr(B, "MOVED", {**B.MOVED, "code": "older", "same": ()})
    assert not B.built_before_move(r, r.state["build"])            # other build code: built again
    monkeypatch.setattr(B, "MOVED", {**B.MOVED, "code": "older", "same": ("code1",)})
    assert B.built_before_move(r, r.state["build"])
    f = Fake(r)
    assert f"[build] skip: {B.MOVED_WHY}" in go(r, f) and "build_pack.py" not in f.calls


def test_a_build_recorded_before_the_move_is_not_built_again(resort, tmp_path, monkeypatch):
    r = moved_state(resort, tmp_path, monkeypatch)
    f = Fake(r)
    lines = go(r, f)
    assert f.calls == ["pack_report.py"] and f"[build] skip: {B.MOVED_WHY}" in lines
    assert B.Resort("demo", r.raw, r.out, r.resorts, r.manifests).state["build"] == B.build_inputs(r)   # recorded
    lines = go(B.Resort("demo", r.raw, r.out, r.resorts, r.manifests), Fake(r))
    assert "[build] skip: inputs unchanged" in lines


def test_a_build_from_before_the_move_builds_again_once_the_code_changes(resort, tmp_path, monkeypatch):
    r = moved_state(resort, tmp_path, monkeypatch)
    monkeypatch.setattr(B, "pipeline_code", lambda repo=B.REPO: "code2")
    f = Fake(r)
    go(r, f)
    assert "build_pack.py" in f.calls


def test_a_different_pack_here_than_the_game_had_builds_again(resort, tmp_path, monkeypatch):
    r = moved_state(resort, tmp_path, monkeypatch, old_build="b0")
    f = Fake(r)
    go(r, f)
    assert "build_pack.py" in f.calls


def test_no_console_for_the_landfire_prompt_stops_cleanly(resort, monkeypatch):
    def eof(prompt=""):
        raise EOFError
    monkeypatch.setattr("builtins.input", eof)
    monkeypatch.delenv("LANDFIRE_EMAIL", raising=False)
    with pytest.raises(B.Failed, match="LANDFIRE needs an email"):
        B.build(resort, B.Context(runner=Fake(resort), interactive=True), out=lambda *a: None)


def test_pipeline_code_ignores_tests_and_configs():
    code = B.pipeline_code()
    if code is None:
        pytest.skip("not a git checkout")
    assert len(code.split("+")[0]) == 16


def test_content_attract_and_spots_with_the_game(resort, monkeypatch, tmp_path):
    game = tmp_path / "game"
    monkeypatch.setattr(B, "game_tool", lambda rel: str(game / rel))
    monkeypatch.setattr(B.paths, "game_repo", lambda *a, **k: str(game))
    f = Fake(resort)
    lines = go(resort, f)
    assert f.calls[-6:] == ["build_pack.py", "gen_content.py", "vite", "auto_attract.mjs", "propose_spots.py",
                            "pack_report.py"]
    assert f.packs == os.path.dirname(resort.out)          # the game's tools serve the pack from where it was built
    assert "SHOT_PACKS" not in os.environ
    # done: the still and ghosts are there; spots run again only while the game has none for the resort
    (game / "docs" / "compare" / "demo" / "top").mkdir(parents=True)
    (game / "docs" / "compare" / "demo" / "top" / "spot.json").write_text("{}")
    f = Fake(resort)
    lines = go(B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests), f)
    assert f.calls == ["pack_report.py"]
    assert "[content] skip: inputs unchanged" in lines and "[attract] skip: inputs unchanged" in lines


def test_content_that_finds_nothing_is_still_done(resort, monkeypatch, tmp_path):
    game = tmp_path / "game"
    monkeypatch.setattr(B, "game_tool", lambda rel: str(game / rel))
    monkeypatch.setattr(B.paths, "game_repo", lambda *a, **k: str(game))
    (game / "docs" / "compare" / "demo" / "top").mkdir(parents=True)     # the game has spots: spots skip
    (game / "docs" / "compare" / "demo" / "top" / "spot.json").write_text("{}")
    f = Fake(resort, finds=False)
    go(resort, f)
    assert f.calls[-2:] == ["gen_content.py", "pack_report.py"]          # no shots: no still, no vite build
    f = Fake(resort, finds=False)
    lines = go(B.Resort("demo", resort.raw, resort.out, resort.resorts, resort.manifests), f)
    assert f.calls == ["pack_report.py"]                                 # not the ray-march again
    assert "[content] skip: inputs unchanged" in lines and "[attract] skip: inputs unchanged" in lines


# ------------------------------------------------------------------------------------------------ FEAT-268

def other(resort, slug, **cfg):
    """another config beside the demo one, as a Resort (its raw folder beside demo's unless raw_from says)"""
    res = os.path.dirname(os.path.dirname(resort.cfg_path))
    os.makedirs(os.path.join(res, slug), exist_ok=True)
    c = dict(CFG, slug=slug, **cfg)
    json.dump(c, open(os.path.join(res, slug, f"{slug}.json"), "w"))
    raw_root = os.path.dirname(resort.raw)
    return B.Resort(slug, os.path.join(raw_root, c.get("raw_from") or slug), os.path.join(os.path.dirname(resort.out), slug),
                    res, resort.manifests)


def test_a_source_only_config_fetches_and_stops(resort):
    src = other(resort, "src", source_only=True)
    f = Fake(src)
    lines = go(src, f)
    assert "build_pack.py" not in f.calls and "pack_report.py" not in f.calls
    assert f.calls[:3] == ["ept_select.py", "gen_manifest.py", "fetch.ps1"]
    assert any(B.SOURCE_WHY in s for s in lines) and not os.path.exists(os.path.join(src.out, "..", "index.json"))
    assert "build" not in src.state and "report" not in src.state


def test_raw_from_builds_on_the_other_resorts_data_with_its_own_state(resort):
    go(resort, Fake(resort))
    before = open(resort.state_path).read()
    mash = other(resort, "mash", raw_from="demo")
    assert mash.raw == resort.raw and mash.man_path == resort.man_path
    assert mash.state_path == os.path.join(os.path.dirname(resort.raw), "mash", B.STATE)
    assert mash.node_files() == resort.node_files()          # the lists are demo's
    f = Fake(mash)
    lines = go(mash, f)
    assert f.calls == ["build_pack.py", "gen_content.py", "pack_report.py"]
    assert any("the raw data is from demo" in s for s in lines if s.startswith("[fetch]"))
    assert os.path.isfile(mash.state_path) and open(resort.state_path).read() == before
    assert any(s.startswith("[fetch] skip") for s in lines)
    f2 = Fake(mash)
    go(mash, f2, force=["fetch"])                             # never fetches into demo's folder, even forced
    assert "fetch.ps1" not in f2.calls and "build_pack.py" not in f2.calls


def test_a_pack_with_a_sourced_move_checks_and_fingerprints_the_source(resort):
    go(resort, Fake(resort))
    move = {"name": "Hill", "source": "src", "from": [0, 0, 400, 400], "to": [500, 500]}
    mash = other(resort, "mash", raw_from="demo", relocate=[move])
    with pytest.raises(B.Failed, match="has no config"):
        go(mash, Fake(mash))
    other(resort, "src", source_only=True)
    with pytest.raises(B.Failed, match="not fetched"):
        go(mash, Fake(mash))
    src = other(resort, "src")
    go(src, Fake(src), last="landfire")
    with pytest.raises(B.Failed, match='not marked "source_only"'):
        go(mash, Fake(mash))
    src = other(resort, "src", source_only=True)
    go(src, Fake(src))
    f = Fake(mash)
    go(mash, f)
    assert f.calls == ["build_pack.py", "gen_content.py", "pack_report.py"]
    f = Fake(mash)
    go(mash, f)
    assert "build_pack.py" not in f.calls                     # nothing changed
    json.dump(dict(json.load(open(src.cfg_path)), name="Moved"), open(src.cfg_path, "w"))
    f = Fake(mash)
    go(mash, f)
    assert "build_pack.py" in f.calls                         # the source's config is an input of the pack


def test_build_inputs_without_sources_are_the_formula_from_before(resort):
    go(resort, Fake(resort))
    r = resort
    groom = sorted(os.path.basename(p) for p in B.glob.glob(os.path.join(r.raw, "grooming", "*.json")))
    assert B.build_inputs(r) == B.sha(B.file_sha(r.cfg_path), B.manifest_items_sha(r), r.state.get("fetch"),
                                      r.state.get("landfire"), groom, B.pipeline_code(), r.out)


def test_landfire_gets_the_email_in_its_environment_not_its_arguments(resort):
    f = Fake(resort)
    go(resort, f)
    lf = [(c, e) for c, e in zip(f.calls, f.envs) if c.startswith("fetch_landfire")]
    assert len(lf) == 3
    assert all(e and e["LANDFIRE_EMAIL"] == "me@example.com" for _, e in lf)
    assert not any("@" in c for c, _ in lf)


def test_the_command_echo_never_holds_the_email(capsys):
    env = {"LANDFIRE_EMAIL": "rider@example.com"}
    B.run([sys.executable, "-c", "pass"], env=env)
    out = capsys.readouterr().out
    assert "$ " in out and "@" not in out


def test_run_hands_the_child_the_extra_environment(tmp_path):
    out = tmp_path / "o.txt"
    code = "import os;open(r'%s','w').write(os.environ['LANDFIRE_EMAIL'])" % out
    assert B.run([sys.executable, "-c", code], env={"LANDFIRE_EMAIL": "rider@example.com"}) == 0
    assert out.read_text() == "rider@example.com"


def _lf_args(*argv, env=None):
    import subprocess
    e = {k: v for k, v in os.environ.items() if k != "LANDFIRE_EMAIL"}
    e.update(env or {})
    src = ("import {parseArgs} from './pipeline/landfire_args.mjs';"
           "console.log(JSON.stringify(parseArgs(process.argv.slice(1), process.env)))")
    r = subprocess.run(["node", "--input-type=module", "-e", src, *argv], cwd=os.path.join(B.HERE, ".."),
                       capture_output=True, text=True, env=e)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="no node")
def test_fetch_landfire_reads_the_email_from_the_environment_or_the_argument():
    env = {"LANDFIRE_EMAIL": "rider@example.com"}
    assert _lf_args("vail", env=env) == {"slug": "vail", "email": "rider@example.com", "layerArg": "EVT"}
    assert _lf_args("vail", "EVC", env=env)["layerArg"] == "EVC"
    assert _lf_args("vail", "rider@example.com", "EVH")["layerArg"] == "EVH"
    assert _lf_args("vail", "rider@example.com")["email"] == "rider@example.com"
    assert _lf_args("vail")["email"] is None
