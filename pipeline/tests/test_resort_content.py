"""FEAT-243: the hand content that moved from the game into resorts/<slug>/ is in shape."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paths  # noqa: E402


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def test_vail_has_its_gateway_as_start():
    lm = _load(paths.landmarks_path("vail"))
    assert len(lm) == 1
    g = lm[0]
    assert g["id"] == "back-bowls-gateway" and g["start"] is True
    assert (g["x"], g["y"], g["heading"]) == (-718.0, 495.9, 162)
    assert g["note"]


def test_breckenridge_start():
    s = _load(paths.start_path("breckenridge"))
    assert (s["x"], s["y"], s["heading"]) == (-1688, -244, 140)
    assert s["label"] == "Starts at the top of Imperial Bowl" and s["source"] and s["note"]
