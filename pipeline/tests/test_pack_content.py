"""FEAT-243: pack_content.py copies a resort's hand content into its pack and resolves the start."""
import json
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pack_content as P  # noqa: E402

GATEWAY = {"id": "back-bowls-gateway", "kind": "gateway", "name": "The Legendary Back Bowls", "x": -718.0, "y": 495.9,
           "heading": 162, "span": 7.1, "clearance": 3.55, "text": "THE LEGENDARY BACK BOWLS", "source": "photo",
           "start": True, "note": "a code comment"}
RUN_START = {"x": 10.0, "y": 20.0, "heading": 1.0, "run": "Riva Ridge"}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _dump(p, v):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(v, f)


@pytest.fixture
def env(tmp_path):
    resorts, pack = tmp_path / "resorts", tmp_path / "packs" / "demo"
    (resorts / "demo").mkdir(parents=True)
    _dump(str(pack / "meta.json"), {"slug": "demo", "formatVersion": 1, "build": "b1", "start": dict(RUN_START)})
    return str(resorts), str(pack)


def meta(pack):
    return _load(os.path.join(pack, "meta.json"))


def test_landmark_start_beats_placed_and_run(env):
    resorts, pack = env
    _dump(os.path.join(resorts, "demo", "landmarks.json"), [GATEWAY])
    _dump(os.path.join(resorts, "demo", "start.json"), {"x": 1, "y": 2, "heading": 140, "label": "placed"})
    out = P.apply(pack, resorts=resorts, log=lambda s: None)
    m = meta(pack)
    h = math.radians(162)
    assert out["start"] == "landmark" and out["landmarks"] == 1
    assert m["start"]["x"] == pytest.approx(-718.0 - math.sin(h) * 15, abs=0.01)
    assert m["start"]["y"] == pytest.approx(495.9 - math.cos(h) * 15, abs=0.01)
    assert m["start"]["heading"] == pytest.approx(h)
    assert m["start"]["label"] == "Starts at The Legendary Back Bowls" and m["start"]["source"] == "landmark"
    assert "run" not in m["start"]
    assert m["baseStart"] == RUN_START
    assert m["landmarks"][0]["id"] == "back-bowls-gateway" and "note" not in m["landmarks"][0]
    assert m["build"] == "b1" and m["formatVersion"] == 1       # no new stamp, no format change


def test_placed_start_in_degrees(env):
    resorts, pack = env
    _dump(os.path.join(resorts, "demo", "start.json"),
          {"x": -1688, "y": -244, "heading": 140, "label": "Starts at the top of Imperial Bowl", "note": "n"})
    assert P.apply(pack, resorts=resorts, log=lambda s: None)["start"] == "placed"
    s = meta(pack)["start"]
    assert (s["x"], s["y"]) == (-1688, -244) and s["heading"] == pytest.approx(math.radians(140))
    assert s["label"] == "Starts at the top of Imperial Bowl" and s["source"] == "placed"
    assert "landmarks" not in meta(pack)


def test_run_start_kept_without_content(env):
    resorts, pack = env
    assert P.apply(pack, resorts=resorts, log=lambda s: None) == {"slug": "demo", "landmarks": 0, "start": "build", "attract": 0}
    m = meta(pack)
    assert m["start"] == RUN_START and "baseStart" not in m and "landmarks" not in m and "attract" not in m


def test_dropping_the_landmark_gives_the_build_start_back(env):
    resorts, pack = env
    lp = os.path.join(resorts, "demo", "landmarks.json")
    _dump(lp, [GATEWAY])
    P.apply(pack, resorts=resorts, log=lambda s: None)
    P.apply(pack, resorts=resorts, log=lambda s: None)          # twice: still resolved from the build's start
    assert meta(pack)["baseStart"] == RUN_START
    os.remove(lp)
    P.apply(pack, resorts=resorts, log=lambda s: None)
    m = meta(pack)
    assert m["start"] == RUN_START and "baseStart" not in m and "landmarks" not in m


def test_twice_is_the_same(env):
    resorts, pack = env
    _dump(os.path.join(resorts, "demo", "landmarks.json"), [GATEWAY])
    P.apply(pack, resorts=resorts, log=lambda s: None)
    once = open(os.path.join(pack, "meta.json")).read()
    P.apply(pack, resorts=resorts, log=lambda s: None)
    assert open(os.path.join(pack, "meta.json")).read() == once


def _hand_menu(resorts, extra=()):
    d = os.path.join(resorts, "demo", "attract")
    for f in ("take-1.json", "shots.json", "extra.json") + tuple(extra):
        _dump(os.path.join(d, f), [])
    with open(os.path.join(d, "a.jpg"), "wb") as f:
        f.write(b"\xff\xd8")
    _dump(os.path.join(d, "index.json"), {"shots": True, "stills": ["a"], "ghosts": ["take-1.json"],
                                          "looks": {"a": {"code": "c", "pack": "b1"}}})
    return d


def test_copies_only_listed_files_and_clears_a_generated_menu(env):
    resorts, pack = env
    _hand_menu(resorts)
    _dump(os.path.join(pack, "attract", "index.json"), {"shots": True, "generated": True})
    _dump(os.path.join(pack, "attract", "old.json"), [])
    assert P.apply(pack, resorts=resorts, log=lambda s: None)["attract"] == 3
    assert sorted(os.listdir(os.path.join(pack, "attract"))) == ["a.jpg", "index.json", "shots.json", "take-1.json"]
    idx = _load(os.path.join(pack, "attract", "index.json"))
    assert idx["hand"] is True and "generated" not in idx and idx["looks"]["a"]["pack"] == "b1"
    assert meta(pack)["attract"] == {"generated": False}


def test_missing_listed_file_stops(env):
    resorts, pack = env
    d = _hand_menu(resorts)
    os.remove(os.path.join(d, "take-1.json"))
    with pytest.raises(SystemExit, match="take-1.json"):
        P.apply(pack, resorts=resorts, log=lambda s: None)


def test_a_hand_menu_taken_out_of_the_resort_leaves_the_pack(env):
    resorts, pack = env
    d = _hand_menu(resorts)
    P.apply(pack, resorts=resorts, log=lambda s: None)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))
    P.apply(pack, resorts=resorts, log=lambda s: None)
    assert not os.path.exists(os.path.join(pack, "attract")) and "attract" not in meta(pack)


def test_a_generated_menu_stays_without_a_hand_one(env):
    resorts, pack = env
    _dump(os.path.join(pack, "attract", "index.json"), {"shots": True, "generated": True})
    m = meta(pack)
    m["attract"] = {"generated": True}
    _dump(os.path.join(pack, "meta.json"), m)
    P.apply(pack, resorts=resorts, log=lambda s: None)
    assert _load(os.path.join(pack, "attract", "index.json"))["generated"] is True
    assert meta(pack)["attract"] == {"generated": True}


def test_the_real_vail_and_breckenridge_content_applies(tmp_path):
    for slug in ("vail", "breckenridge"):
        pack = tmp_path / "packs" / slug
        _dump(str(pack / "meta.json"), {"slug": slug, "build": "b", "start": dict(RUN_START)})
        out = P.apply(str(pack), log=lambda s: None)
        assert out["start"] == {"vail": "landmark", "breckenridge": "placed"}[slug]
