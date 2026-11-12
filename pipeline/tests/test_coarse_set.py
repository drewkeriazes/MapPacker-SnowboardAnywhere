"""FEAT-229: the coarse (4 m) height set."""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from coarse_set import add_to_pack, box_mean  # noqa: E402
from packwriter import decode_terrarium, write_height_set, write_meta  # noqa: E402
from PIL import Image  # noqa: E402


def test_box_mean_keeps_the_south_west_anchor_and_skips_voids():
    g = np.arange(6 * 9, dtype=np.float32).reshape(6, 9)   # row 0 = north
    g[5, 0] = np.nan
    m = box_mean(g, 4)
    assert m.shape == (2, 3)
    # the south row of blocks is rows 2..5 of the grid (the padding goes north), the west column cols 0..3
    sw = g[2:6, 0:4]
    assert np.isclose(m[1, 0], np.nanmean(sw))
    assert np.isclose(m[0, 2], np.nanmean(g[0:2, 8:9]))     # a padded corner block: its two real samples
    assert np.isnan(box_mean(np.full((4, 4), np.nan, np.float32), 4)).all()


def test_coarse_set_from_a_built_pack_matches_the_fine_heights(tmp_path):
    pack = tmp_path / "demo"
    yy, xx = np.mgrid[0:1024, 0:1536]
    fine = (3000 + xx * 0.25 + yy * 0.5).astype(np.float32)      # a plane, row 0 = north
    meta = {"version": 1, "slug": "demo", "name": "Demo", "terrain": {"fine": write_height_set(str(pack), "fine", fine, 1.0, -768.0, -512.0)}}
    write_meta(str(pack), meta)
    c = add_to_pack(str(pack))
    assert (c["res"], c["minX"], c["minY"], c["tilesX"], c["tilesY"]) == (4.0, -768.0, -512.0, 1, 1)
    assert json.load(open(pack / "meta.json"))["terrain"]["coarse"] == c
    h = decode_terrarium(np.asarray(Image.open(pack / "coarse" / "0_0.png").convert("RGB")))
    # coarse sample (row from the south j, col i) is centred on minX + (i + 0.5) * 4: the mean of the plane there
    n = h.shape[0]
    for i, j in ((0, 0), (100, 50), (383, 255)):
        x, y = (i + 0.5) * 4, (j + 0.5) * 4       # from the set's lower-left corner
        want = 3000 + (x - 0.5) * 0.25 + (1024 - y - 0.5) * 0.5
        assert abs(h[n - 1 - j, i] - want) < 0.01
    assert np.isnan(h[n - 1 - 300, 0])            # past the fine data (1024 m north = 256 samples): void
