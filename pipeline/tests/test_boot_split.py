"""FEAT-229 / FEAT-230: the coarse (4 m) height set and the boot / rest split of a pack."""
import json
import os
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import boot_split  # noqa: E402
from coarse_set import add_to_pack, box_mean  # noqa: E402
from packwriter import decode_terrarium, write_height_set, write_meta  # noqa: E402
from publish_pack import add_parts, catalog_entry, pack_files  # noqa: E402
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


def make_pack(root, start=(100.0, 100.0)):
    """a small pack: fine and mask on 512 m / 1 km tiles over 4 km, far and mid one tile, cover, instances"""
    d = root / "p"
    for rel in ["far/0_0.png", "mid/0_0.png", "coarse/0_0.png", "cover/pack.png", "features.json", "report.md"]:
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_bytes(b"x" * 10)
    for tx in range(8):
        for ty in range(8):
            (d / "fine").mkdir(exist_ok=True)
            (d / "fine" / f"{tx}_{ty}.png").write_bytes(b"f" * 100)
    for kind in ("mask", "ao", "trees", "rocks"):
        (d / kind).mkdir(exist_ok=True)
        for tx in range(4):
            for ty in range(4):
                (d / kind / f"{tx}_{ty}.{'png' if kind in ('mask', 'ao') else 'bin'}").write_bytes(b"m" * 50)
    (d / "farTrees").mkdir()
    (d / "farTrees" / "-1_0.bin").write_bytes(b"r")
    (d / "farTrees" / "-3_0.bin").write_bytes(b"r")
    grid = {"tileSize": 512, "minX": 0.0, "minY": 0.0}
    meta = {"slug": "p", "name": "P", "start": {"x": start[0], "y": start[1], "heading": 0},
            "terrain": {"fine": {**grid, "res": 1.0, "tilesX": 8, "tilesY": 8}},
            "mask": {**grid, "res": 2.0, "tilesX": 4, "tilesY": 4}, "ao": {**grid, "res": 2.0, "tilesX": 4, "tilesY": 4},
            "instances": {"cellSize": 1000, "minX": 0.0, "minY": 0.0, "cellsX": 4, "cellsY": 4}}
    (d / "meta.json").write_text(json.dumps(meta))
    (d / "features.json").write_text(json.dumps({"runs": [{"name": "Long", "points": [[150, 150, 3000], [3900, 150, 2500]]}]}))
    return d


def test_split_takes_the_area_round_the_start_and_everything_coarse(tmp_path):
    d = make_pack(tmp_path)
    files = pack_files(str(d))
    boot, rest, info = boot_split.split(str(d), files, [(100.0, 100.0)], radius=600, corridor=0)
    assert sorted(boot + rest) == files and not set(boot) & set(rest)
    for f in ("meta.json", "features.json", "far/0_0.png", "mid/0_0.png", "coarse/0_0.png", "cover/pack.png"):
        assert f in boot
    assert "report.md" in rest
    # fine tiles 512 m: those within 600 m of (100, 100) are tx, ty in 0..1
    assert info["tiles"]["fine"] == sorted(f"{x}_{y}" for x in range(2) for y in range(2))
    assert info["tiles"]["mask"] == ["0_0"] and info["tiles"]["trees"] == ["0_0"]
    # the far tree ring west of the grid: cell -1 spans x -1,000 to 0, 100 m from the start; cell -3 is far off
    assert info["tiles"]["farTrees"] == ["-1_0"] and "farTrees/-3_0.bin" in rest
    assert info["tiles"]["ao"] == ["0_0"] and info["tiles"]["rocks"] == ["0_0"]


def test_split_follows_the_first_runs(tmp_path):
    d = make_pack(tmp_path)
    _, _, info = boot_split.split(str(d), pack_files(str(d)), [(100.0, 100.0)], radius=600, corridor=300)
    assert info["runs"] == 1
    # the run heads east along y = 150 to x = 3,900: the fine tiles on the bottom row (ty 0) all the way
    assert {f"{x}_0" for x in range(8)} <= set(info["tiles"]["fine"])
    assert "0_7" not in info["tiles"]["fine"]


def test_write_split_zips_with_boot_json(tmp_path):
    d = make_pack(tmp_path)
    files = pack_files(str(d))
    r = boot_split.write_split(str(d), files, str(tmp_path), "p", [(100.0, 100.0)], radius=600, corridor=0)
    with zipfile.ZipFile(r["boot"]["path"]) as zb, zipfile.ZipFile(r["rest"]["path"]) as zr:
        nb, nr = zb.namelist(), zr.namelist()
        assert "boot.json" in nb and "meta.json" in nb and "meta.json" not in nr
        assert sorted([n for n in nb if n != "boot.json"] + nr) == files
        info = json.loads(zb.read("boot.json"))
    assert info["tiles"]["fine"] == ["0_0", "0_1", "1_0", "1_1"] and info["restBytes"] > info["bootBytes"]
    (tmp_path / "again").mkdir()
    again = boot_split.write_split(str(d), files, str(tmp_path / "again"), "p", [(100.0, 100.0)], radius=600, corridor=0)
    assert again["boot"]["sha256"] == r["boot"]["sha256"] and again["rest"]["sha256"] == r["rest"]["sha256"]


def test_catalog_entry_gets_boot_and_rest_beside_the_full_zip():
    e = catalog_entry({"slug": "vail", "name": "Vail", "formatVersion": 1}, {}, version=3, size=100, sha256="f" * 64,
                      pipeline="x", tier="gold", status="preview", report=None)
    add_parts(e, {"boot": {"bytes": 30, "sha256": "b" * 64}, "rest": {"bytes": 70, "sha256": "r" * 64}})
    pk = e["pack"]
    assert pk["url"].endswith("/vail-v3/vail.zip") and pk["bytes"] == 100
    assert pk["boot"] == {"url": pk["url"].replace("vail.zip", "vail-boot.zip"), "bytes": 30, "sha256": "b" * 64}
    assert pk["rest"]["url"].endswith("/vail-v3/vail-rest.zip") and pk["rest"]["bytes"] == 70


def test_boot_centres_add_the_games_start(tmp_path):
    lm = tmp_path / "game" / "src" / "world"
    lm.mkdir(parents=True)
    (lm / "Landmarks.ts").write_text("""export const LANDMARKS: Record<string, Landmark[]> = {
  vail: [
    {
      id: 'gate', kind: 'gateway', name: 'Gate',
      x: -718.0, y: 495.9, heading: 180, span: 7.1,
      start: true,
    },
  ],
};

const STARTS: Record<string, PlacedStart> = {
  breckenridge: {
    x: -1688, y: -244, heading: 140, label: 'Top',
  },
};
""")
    meta = {"slug": "vail", "start": {"x": -3246.0, "y": 2241.0, "heading": 0}}
    c = boot_split.boot_centres(meta, [], str(tmp_path))
    assert c[0] == (-3246.0, 2241.0)
    assert abs(c[1][0] - -718.0) < 1e-6 and abs(c[1][1] - (495.9 + 15.0)) < 1e-6   # 15 m uphill of a gate facing south
    b = boot_split.boot_centres({"slug": "breckenridge", "start": {"x": -1690.0, "y": -250.0}}, [["10", "20"]], str(tmp_path))
    assert b == [(-1690.0, -250.0), (10.0, 20.0)]          # the placed start is 6 m from meta.start: one centre
    assert boot_split.boot_centres({"slug": "bigsky", "start": {"x": 1, "y": 2}}, [], str(tmp_path)) == [(1.0, 2.0)]
