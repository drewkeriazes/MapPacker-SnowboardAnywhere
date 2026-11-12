"""FEAT-175 step 4: gen_content.py's start and menu shots on the tiny pack test_pack_report.py builds."""
import json
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))
import gen_content as gc  # noqa: E402
import pack_report as pr  # noqa: E402
from packwriter import write_instances  # noqa: E402
from test_pack_report import HALF, ground, make_pack  # noqa: E402


def meta_of(pack):
    return json.load(open(os.path.join(pack, "meta.json"), encoding="utf-8"))


def test_start_and_shots(tmp_path):
    pack = make_pack(tmp_path / "packs")
    build = meta_of(pack)["build"]
    start, shots = gc.generate(str(pack), log=lambda s: None)
    # the run below Chair 1's top station (150, 290), START_FROM_TOP_M down from the point of the run nearest it
    assert start["source"] == "generated" and start["run"] == "Main" and start["lift"] == "Chair 1"
    assert start["x"] == pytest.approx(100, abs=0.5) and start["y"] == pytest.approx(HALF - 10 - gc.START_FROM_TOP_M, abs=1)
    assert math.degrees(start["heading"]) % 360 == pytest.approx(180, abs=1)     # down the run, south
    assert start["label"] == "Starts at the top of Chair 1"
    m = meta_of(pack)
    assert m["start"] == start and m["attract"] == {"generated": True}
    assert m["build"] == build                                                  # no new stamp: stills stay valid
    assert 1 <= len(shots) <= gc.SHOTS and len({s["id"] for s in shots}) == len(shots)
    for s in shots:
        assert {"id", "x", "y", "h", "pitch", "fov", "eye", "place", "region", "dolly", "pan", "period", "conditions"} <= set(s)
        assert s["region"] == "Demo Mountain" and s["conditions"] == gc.DEFAULT_CONDITIONS
    assert json.load(open(pack / "attract" / "shots.json", encoding="utf-8")) == shots
    idx = json.load(open(pack / "attract" / "index.json", encoding="utf-8"))
    assert idx["shots"] is True and idx["generated"] is True and idx["ghosts"] == []
    # the report's start line passes on the generated start
    rep = pr.build_report(str(pack), repo=str(tmp_path))
    assert next(ln for ln in rep.lines if ln["id"] == "10")["status"] == pr.PASS


def test_start_steps_past_a_tree(tmp_path):
    pack = make_pack(tmp_path / "packs")
    y0 = HALF - 10 - gc.START_FROM_TOP_M
    tree = np.array([[100.5, y0, ground(100.5, y0), 10, 1.5, 0]], np.float32)
    write_instances(str(pack), "trees", tree, 1000.0, -HALF, -HALF, 1, 1)
    start, _ = gc.generate(str(pack), dry=True, log=lambda s: None)
    assert start["y"] < y0 - 3                                                  # on down the run, clear of the crown
    assert np.hypot(start["x"] - 100.5, start["y"] - y0) - 1.5 >= pr.START_CLEAR_M


def test_named_start_run(tmp_path):
    pack = make_pack(tmp_path / "packs")
    cfg = tmp_path / "demo.json"
    cfg.write_text(json.dumps({"start_run": "MAIN"}))
    start, _ = gc.generate(str(pack), str(cfg), dry=True, log=lambda s: None)
    assert start["run"] == "Main"
    assert gc.run_key("Four O’Clock") == gc.run_key("4 O'Clock")


def test_attract_folder_rules(tmp_path):
    d = tmp_path / "pack"
    (d / "attract").mkdir(parents=True)
    shots = [{"id": "a", "x": 0}]
    # hand-made: left alone
    (d / "attract" / "index.json").write_text(json.dumps({"shots": True}))
    assert not gc.write_attract(str(d), shots, log=lambda s: None)
    # generated, then rendered (a still and a take), then the same shots again: kept
    (d / "attract" / "index.json").write_text(json.dumps({"generated": True}))
    assert gc.write_attract(str(d), shots, log=lambda s: None)
    idx = {"shots": True, "generated": True, "stills": ["a"], "ghosts": ["a-start-run-1.json"], "looks": {}, "shotGhosts": {}}
    (d / "attract" / "index.json").write_text(json.dumps(idx))
    (d / "attract" / "a.jpg").write_bytes(b"jpg")
    (d / "attract" / "a-start-run-1.json").write_text("{}")
    assert gc.write_attract(str(d), shots, log=lambda s: None)
    assert (d / "attract" / "a.jpg").exists() and json.load(open(d / "attract" / "index.json"))["stills"] == ["a"]
    # new shots: the old still and takes go
    assert gc.write_attract(str(d), [{"id": "b", "x": 1}], log=lambda s: None)
    assert not (d / "attract" / "a.jpg").exists() and not (d / "attract" / "a-start-run-1.json").exists()
    assert json.load(open(d / "attract" / "index.json"))["stills"] == []


def test_in_frame():
    cam = (0.0, 0.0, 10.0)
    assert gc.in_frame(cam, 0, 0, 0, 100, 10)            # straight ahead, north
    assert not gc.in_frame(cam, 0, 0, 0, -100, 10)       # behind
    assert gc.in_frame(cam, 90, 0, 100, 0, 10)           # east
    assert not gc.in_frame(cam, 0, 0, 0, 10, -30)        # far below a level frame
    assert gc.in_frame(cam, 0, -45, 0, 10, 0)            # but in one pitched down


def test_rolls_on_needs_the_run_to_fall_on():
    class G:                                   # flat for 30 m, then a 10 % fall (a cat track rolling over)
        def z(self, x, y):
            x = np.asarray(x, float)
            return np.where(x < 30, 100.0, 100.0 - 0.1 * (x - 30))

        def at(self, x, y):
            return float(self.z(np.array([x]), np.array([y]))[0])
    pts = np.stack([np.arange(0, 200, 3.0), np.zeros(67)], 1)
    d = pts[:, 0].copy()
    assert "falls only" in gc.rolls_on(G(), pts, d, 0)          # 3 m in the first 60 m
    assert gc.rolls_on(G(), pts, d, 10) is None                  # from 30 m on: 6 m
    bump = lambda x: np.where((x > 40) & (x < 50), 101.0, 100.0 - 0.2 * x)
    class B(G):
        def z(self, x, y):
            return bump(np.asarray(x, float))
    assert "rises" in gc.rolls_on(B(), pts, d, 0)
