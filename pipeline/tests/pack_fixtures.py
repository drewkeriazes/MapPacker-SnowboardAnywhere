"""A tiny pack on disk for tests of what reads a pack's files (pack_lint.py and what publishes through it)."""
import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from packwriter import FORMAT_VERSION  # noqa: E402

BUILD = "20260101T000000Z-abc123"


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _png(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("L", (4, 4)).save(path)


def tiny_pack(tmp_path, format_version=FORMAT_VERSION, pipeline=None) -> str:
    """A 1 x 1 tile pack, 1000 x 1000 m, one tree cell of two records, one stand cell; returns its folder."""
    d = str(tmp_path / "tiny")
    one = {"tilesX": 1, "tilesY": 1}
    for folder in ("fine", "coarse", "mid", "far", "mask", "ao", "dir", "moguls", "stands"):
        _png(os.path.join(d, folder, "0_0.png"))
    os.makedirs(os.path.join(d, "trees"), exist_ok=True)
    with open(os.path.join(d, "trees", "0_0.bin"), "wb") as f:
        f.write(b"\0" * 48)
    meta = {
        "formatVersion": format_version, "slug": "tiny", "build": BUILD,
        "bounds": {"minX": 0, "minY": 0, "maxX": 1000, "maxY": 1000},
        "terrain": {k: dict(one) for k in ("fine", "coarse", "mid", "far")},
        "mask": dict(one), "ao": dict(one), "dir": dict(one), "moguls": dict(one),
        "instances": {"treeCount": 2, "treeCells": ["0_0"]},
        "stands": {"cells": ["0_0"], "stems": 0},
    }
    if pipeline is not None:
        meta["pipeline"] = pipeline
    write_json(os.path.join(d, "meta.json"), meta)
    write_json(os.path.join(d, "features.json"), {"runs": [{}], "lifts": [{}]})
    write_json(os.path.join(d, "report.json"), {"build": BUILD})
    return d
