"""FEAT-225: Silver and Bronze tiers. The tier rules (tiers.py), the Silver and Bronze sources on the pack grid
(tier_sources.py: Mapterhorn heights, WorldCover classes, the ETH canopy height), the plan outside the US
(resort.py with fake hosts), its manifest, the raw checks and the report."""
import json
import math
import os
import sys

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tiers  # noqa: E402
import tier_sources as ts  # noqa: E402
from packwriter import encode_terrarium  # noqa: E402


# ------------------------------------------------------------------ tiers.py

def test_tier_is_the_weakest_layer():
    assert tiers.tier_of({"terrain": "gold", "trees": "gold", "surface": "gold"}) == ("gold", [])
    assert tiers.tier_of({"terrain": "silver", "trees": "silver", "surface": "bronze"}) == ("bronze", ["surface"])
    assert tiers.tier_of({"terrain": "silver", "trees": "silver", "surface": "gold"}) == ("silver", ["terrain", "trees"])


def test_mapterhorn_pixel_sizes_and_zooms():
    assert tiers.tile_px_m(16, 0) == pytest.approx(1.194, abs=1e-3)
    assert tiers.tile_px_m(16, 47.28) == pytest.approx(0.81, abs=0.01)
    assert tiers.zoom_for(1.0, 47.28) == 16          # z15 is 1.6 m there
    assert tiers.zoom_for(10.0, 47.28) == 13
    assert tiers.zoom_for(1.0, 0.0) == 17
    assert tiers.zoom_for(1.0, 47.28, native=14) == 14   # never past what Mapterhorn has


def test_layer_sources_from_the_config():
    gold = tiers.layer_sources({"lidar": {"ept": "x"}, "naip": {"items": []}, "dem": {"source": "3DEP ImageServer"}})
    assert {k: v["tier"] for k, v in gold.items()} == {"terrain": "gold", "trees": "gold", "surface": "gold"}
    bronze = tiers.layer_sources({"dem": {"source": "Mapterhorn", "zoom": 16, "native_zoom": 17},
                                  "lonlat_bbox": [8.99, 47.27, 9.01, 47.29]})
    assert bronze["terrain"] == {"source": "Mapterhorn z16, 0.8 m", "tier": "silver"}
    assert bronze["trees"]["tier"] == "silver" and "ETH" in bronze["trees"]["source"]
    assert bronze["surface"] == {"source": "WorldCover 10 m", "tier": "bronze"}
    coarse = tiers.layer_sources({"dem": {"source": "Mapterhorn", "zoom": 12, "native_zoom": 12}})
    assert coarse["terrain"]["tier"] == "bronze"     # only the 30 m Copernicus DEM there
    # the plan may lower a tier (a 1 m DEM over part of the box), never raise one
    part = tiers.layer_sources({"lidar": {}, "naip": {}, "dem": {}, "sources": {"terrain": {"tier": "silver"},
                                                                              "surface": {"tier": "gold"}}})
    assert part["terrain"]["tier"] == "silver"
    nonaip = tiers.layer_sources({"lidar": {"ept": "x"}, "dem": {}, "sources": {"surface": {"tier": "gold"}}})
    assert nonaip["surface"]["tier"] == "bronze"
    assert tiers.summary(bronze).startswith("terrain Mapterhorn z16, 0.8 m (silver), trees ")


# ------------------------------------------------------------------ tier_sources.py

def write_tile(raw, z, tx, ty, h):
    d = os.path.join(raw, "mapterhorn", str(z))
    os.makedirs(d, exist_ok=True)
    Image.fromarray(encode_terrarium(h), "RGB").save(os.path.join(d, f"{tx}_{ty}.webp"), lossless=True)


def test_mapterhorn_grid_samples_across_tile_edges(tmp_path):
    """two tiles of a plane that rises 1 m per tile pixel to the east: a grid sampled through both reads the plane"""
    z, ty = 16, 22972
    for tx in (34406, 34407):
        cols = (tx - 34406) * 512 + np.arange(512) + 0.5
        write_tile(str(tmp_path), z, tx, ty, np.broadcast_to(1000.0 + cols / 8.0, (512, 512)).astype(np.float32))

    class LonLat:          # the "UTM" grid is lon/lat itself, to test the sampling alone
        def transform(self, x, y):
            return x, y
    n = 2 ** z * 512
    lon0 = 34406 * 512 / n * 360 - 180
    lat_of = lambda py: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * py / n))))
    px = 360 / n                 # one tile pixel in degrees of longitude
    grid, k = ts.mapterhorn_grid(str(tmp_path), z, LonLat(), lon0 + 400 * 360 / n, lat_of(ty * 512 + 100), px, 600, 3)
    assert k == 2
    xs = lon0 + 400 * 360 / n + (np.arange(600) + 0.5) * px
    col = (xs + 180) / 360 * n - 34406 * 512          # global pixel from the west edge of the first tile
    want = 1000.0 + col / 8.0
    ok = np.isfinite(grid[1])
    assert ok.mean() > 0.95
    assert np.abs(grid[1][ok] - want[ok]).max() < 0.02      # bilinear on a plane is exact, to the 1/256 m encoding


def test_canopy_height_and_bronze_surface():
    res = 2.0
    wc = np.full((60, 60), ts.WC_GRASS, np.uint8)
    wc[:, :30] = ts.WC_TREE                                   # forest in the west half
    wc[:20, 40:] = ts.WC_BARE                                 # bare ground in the north-east
    wc[40:, 40:] = ts.WC_SNOW
    eth = np.where(wc == ts.WC_TREE, 20.0, 0.0).astype(np.float32)
    eth[50:54, :4] = np.nan                                   # a small gap in the ETH data
    chm = ts.canopy_height(eth, wc, res)
    assert chm[30, 5] == pytest.approx(20.0, abs=0.1) and chm[30, 50] == 0
    assert chm[52, 2] == pytest.approx(20.0, abs=0.1)        # filled from the stand round it
    slope = np.zeros_like(chm)
    slope[:, 45:] = 35.0                                      # steep in the east
    s = ts.bronze_surface(wc, chm, slope, res)
    assert s["canopy"][30, 5] and not s["canopy"][30, 50]
    assert s["rock_steep"][10, 50] and not s["rock_steep"][10, 42]       # bare: steep is rock, gentle is not
    assert not s["rock"][50, 50]                               # snow and ice stay snow, however steep
    assert not s["rock"][30, 50]                              # grass at 35 degrees: snow (open ground is rock from 42)
    slope[:] = 45.0
    assert ts.bronze_surface(wc, chm, slope, res)["rock_steep"][30, 50]
    v = ts.pseudo_ndvi(wc, res)
    assert v[30, 5] > 0.6 and v[30, 35] == pytest.approx(0.4, abs=0.05)


# ------------------------------------------------------------------ the plan outside the US (resort.py)

def pb_varint(v):
    out = b""
    while True:
        b = v & 0x7F
        v >>= 7
        out += bytes([b | (0x80 if v else 0)])
        if not v:
            return out


def pb_bytes(field, data):
    return pb_varint(field << 3 | 2) + pb_varint(len(data)) + data


def coverage_tile(*ids):
    """a vector tile with one `coverage` layer whose value table holds `ids` (as Mapterhorn's coverage tiles)"""
    values = b"".join(pb_bytes(4, pb_bytes(1, i.encode())) for i in ids)
    layer = pb_bytes(1, b"coverage") + pb_bytes(3, b"source") + values + pb_varint(15 << 3) + pb_varint(2)
    return pb_bytes(3, layer)


def test_mvt_strings_and_credits():
    import resort as R
    assert R.mvt_strings(coverage_tile("glo30", "swissalti3d")) == ["glo30", "swissalti3d"]
    import gzip
    assert R.mvt_strings(gzip.compress(coverage_tile("at1"))) == ["at1"]
    cat = [{"source": "glo30", "name": "COPERNICUS GLO-30", "producer": "DLR", "license": "Copernicus", "resolution": 30},
           {"source": "swissalti3d", "name": "swissALTI3D", "producer": "swisstopo", "license": "OGD", "resolution": 0.5}]
    c = R.mapterhorn_credits(["glo30", "swissalti3d", "glo30", "xx"], cat)
    assert [x["source"] for x in c] == ["swissalti3d", "glo30", "xx"]
    a = R.attribution([], [], [], {"zoom": 16, "sources": c[:1]})
    assert a[0] == "Elevation: Mapterhorn (mapterhorn.com) terrain tiles at z16, from swissALTI3D, swisstopo (OGD)"
    assert not any(x.startswith(("Canopy:", "Imagery:")) for x in a)


@pytest.fixture
def swiss_hosts(tmp_path):
    sys.path.insert(0, os.path.dirname(__file__))
    from test_resort_plan import FakeHosts

    class Swiss(FakeHosts):
        def dem_1m(self, box_ll):
            raise AssertionError("no TNM outside the US")

        def naip(self, box_ll):
            raise AssertionError("no NAIP outside the US")

        def mapterhorn_zoom(self, box_ll):
            return 17

        def mapterhorn_sources(self, box_ll):
            return [{"source": "swissalti3d", "name": "swissALTI3D", "producer": "swisstopo", "license": "OGD",
                     "resolution": 0.5}, {"source": "glo30", "name": "GLO-30", "producer": "DLR", "license": "C",
                                          "resolution": 30}]
    h = Swiss(str(tmp_path))
    h.files["geofabrik_index.json"]["features"].append(
        {"properties": {"id": "europe/switzerland", "iso3166-1:alpha2": ["CH"], "urls": {"pbf": "https://g/ch.pbf"}}})
    return h


def test_plan_outside_the_us_is_bronze(swiss_hosts):
    import resort as R
    stub = {"slug": "atz", "name": "Atzmannig", "country": "CH", "region": "Saint Gallen",
            "lonlat_bbox": [8.9904, 47.2774, 9.0138, 47.2876], "openskidata": {"iso3166_2": "CH-SG", "websites": []}}
    cfg, facts, nodes = R.plan(stub, swiss_hosts, log=lambda *a: None)
    assert cfg["crs"] == "EPSG:32632"
    assert cfg["dem"] == {"source": "Mapterhorn", "res_m": 1, "zoom": 16, "native_zoom": 17}
    assert cfg["mid_ring"]["source"] == "Mapterhorn" and cfg["mid_ring"]["zoom"] == 13
    assert "naip" not in cfg and "lidar" not in cfg and nodes == {}
    assert cfg["tier"] == "bronze" and facts["tier_why"] == ["surface"]
    assert {k: v["tier"] for k, v in cfg["sources"].items()} == {"terrain": "silver", "trees": "silver", "surface": "bronze"}
    assert "swissALTI3D" in cfg["attribution"][0] and "GLO-30" not in cfg["attribution"][0]
    m = facts["manifest"]
    assert m["mapterhorn_fine"][0] > 20 and m["mapterhorn_mid"][0] > 100 and m["landcover"][0] >= 2
    assert not {"dem1m", "dem10m", "naip1m", "ept", "ept_far"} & set(m)
    md = R.plan_md(cfg, facts)
    assert "**Tier: bronze**" in md and "| Terrain, resort | Mapterhorn z16 (finest there z17: swissALTI3D)" in md
    assert "| Surface masks | ESA WorldCover 2021 classes (no NAIP)" in md and "LANDFIRE" not in md.split("## Notes")[0]


def test_manifest_and_raw_checks_follow_the_sources(swiss_hosts, tmp_path):
    import resort as R
    import gen_manifest
    import build_resort as B
    stub = {"slug": "atz", "name": "Atzmannig", "country": "CH", "lonlat_bbox": [8.9904, 47.2774, 9.0138, 47.2876],
            "openskidata": {"iso3166_2": "CH-SG", "websites": []}}
    cfg, _, _ = R.plan(stub, swiss_hosts, log=lambda *a: None)
    items = gen_manifest.manifest_items(cfg, str(tmp_path))
    fine = [i for i in items if (i.get("meta") or {}).get("for") == "fine"]
    assert fine and all(i["path"].startswith("mapterhorn/16/") for i in fine)
    # the tiles cover the box: every corner of utm_bbox falls in one of them
    from pyproj import Transformer
    to_ll = Transformer.from_crs(cfg["crs"], "EPSG:4326", always_xy=True)
    have = {(i["meta"]["x"], i["meta"]["y"]) for i in fine}
    x0, y0, x1, y1 = cfg["utm_bbox"]
    for x, y in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        tx, ty = gen_manifest.lonlat_to_tile(*to_ll.transform(x, y), 16)
        assert (int(tx), int(ty)) in have
    assert not any(i["path"].split("/")[0] in ("dem1m", "dem10m", "naip1m", "ept") for i in items)
    need = B.raw_need(cfg)
    assert set(need) == {"Mapterhorn", "Mapterhorn z16 (resort box)", "Mapterhorn z13 (mid ring)"}
    gold = B.raw_need({"lidar": {"ept": "x"}, "naip": {"res_m": 1}, "dem": {"source": "3DEP ImageServer"}, "mid_ring": {}})
    assert set(gold) == set(B.RAW_NEED)


def test_report_shows_the_tier_and_judges_by_it(tmp_path):
    import pack_report as pr
    sys.path.insert(0, os.path.dirname(__file__))
    from test_pack_report import make_pack, line
    pack = make_pack(tmp_path / "packs", cover=True)
    meta = json.load(open(pack / "meta.json", encoding="utf-8"))
    src = tiers.layer_sources({"dem": {"source": "Mapterhorn", "zoom": 16}, "lonlat_bbox": [9, 47, 9, 47]})
    meta.update({"sources": src, "tier": "bronze", "attribution": [
        "Elevation: Mapterhorn (mapterhorn.com) terrain tiles at z16", "Background terrain: Mapterhorn",
        "OpenStreetMap contributors (ODbL)", "Land cover: ESA WorldCover", "Canopy height: ETH"]})
    meta["instances"]["treeCount"] = 0
    meta["stands"] = {"res": 4, "size": 250, "zBase": 0, "zScale": 32, "hStep": 0.25, "cells": [], "stems": 5000}
    json.dump(meta, open(pack / "meta.json", "w", encoding="utf-8"))
    for f in os.listdir(pack / "trees"):
        os.remove(pack / "trees" / f)
    cfg = {"country": "CH", "crs": meta["crs"], "origin": meta["origin"]}
    rep = pr.Report(str(pack), cfg, repo=str(tmp_path))
    rep.measure()
    rep.check()
    assert "no tree instances" not in line(rep, "7")["detail"] and "no lidar" in line(rep, "7")["detail"]
    assert line(rep, "4")["status"] == pr.WARN and "outside the US" in line(rep, "4")["detail"]
    assert line(rep, "8b")["status"] == pr.FAIL and "no lidar" in line(rep, "8b")["detail"]
    assert line(rep, "13")["status"] == pr.PASS, line(rep, "13")["detail"]
    j = rep.to_json()
    assert j["tier"] == "bronze" and j["sources"]["surface"]["source"] == "WorldCover 10 m"
    md = rep.to_markdown()
    assert "**Tier: bronze**" in md and "| surface | WorldCover 10 m | bronze |" in md
