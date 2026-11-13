"""FEAT-279: resort.py search --json, the ski areas a typed name finds, for the game's Find a resort box (FEAT-246).
Offline, on a small fixture index: read-only (no config written, never the runs or lifts files), the JSON shape,
and an `osm_id` that build-pack's input check accepts."""
import json
import os
import sys
import urllib.error
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "ci"))
import resort as R  # noqa: E402
import build_pack_ci  # noqa: E402


def area(i, name, lon, lat, lifts=1, runs=2, site=None, region="Ohio", cc="US", osm="way/1", status="operating"):
    d = 0.003
    return {"type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d],
                                                             [lon - d, lat + d], [lon - d, lat - d]]]},
            "properties": {
                "id": i, "name": name, "type": "skiArea", "status": status,
                "sources": ([{"type": "openstreetmap", "id": osm}] if osm else []) + [{"type": "skimap.org", "id": 7}],
                "websites": [site] if site else [],
                "places": [{"iso3166_2": f"{cc}-XX", "iso3166_1Alpha2": cc, "localized": {"en": {"region": region}}}],
                "statistics": {"lifts": {"byType": {"chair_lift": {"count": lifts}}} if lifts else {"byType": {}},
                               "runs": {"byActivity": {"downhill": {"byDifficulty": {"easy": {"count": runs}}}}}}}}


FEATS = [
    area("bm", "Boston Mills Ski Resort", -81.565, 41.264, lifts=7, runs=7, site="https://www.bmbw.com/",
         osm="way/452323654"),
    area("bw", "Brandywine Ski Resort", -81.555, 41.284, lifts=9, runs=9, site="https://bmbw.com", osm="way/391698033"),
    area("bh", "Boston Hills", -71.09, 42.64, lifts=0, runs=0, region="Massachusetts", osm=None, status="abandoned"),
    area("bn", "Boston Nordic", -81.575, 41.262, lifts=0, runs=3, osm="relation/55"),
    area("pc1", "Pine Crest", -105.0, 40.0, lifts=3, region="Colorado", osm="way/11"),
    area("pc2", "Pine Crest", -89.0, 45.0, lifts=2, region="Wisconsin", osm="relation/22"),
    area("far", "Far Away", -81.0, 41.9, lifts=2, site="https://www.bmbw.com/", osm="way/33"),   # same site, 70 km
    {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
     "properties": {"id": "run", "name": "Boston Run", "type": "run"}},
]


@pytest.fixture
def index(tmp_path, monkeypatch):
    """a cache folder holding only ski_areas.geojson, and no network: a download (of a missing runs or lifts index
    too) fails with exit 1"""
    cache = tmp_path / "_index"
    cache.mkdir()
    (cache / "ski_areas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": FEATS}),
                                             encoding="utf-8")
    resorts = tmp_path / "resorts"
    resorts.mkdir()

    def no_network(*a, **k):
        raise urllib.error.URLError("no network in this test")
    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    return cache, resorts


def run(index, capsys, *args):
    cache, resorts = index
    code = R.main(["--cache", str(cache), "--resorts-dir", str(resorts), "search", *args])
    out, err = capsys.readouterr()
    return code, out, err


def files(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs)


def test_a_hit_and_the_area_sold_with_it(index, capsys):
    code, out, err = run(index, capsys, "boston", "--json")
    assert code == 0
    r = json.loads(out)                                   # one JSON object and nothing else on stdout
    assert r["query"] == "boston"
    names = [m["name"] for m in r["matches"]]
    # lifts first (Boston Nordic has none), Brandywine listed as its own match since bmbw.com sells both
    assert names == ["Boston Mills Ski Resort", "Brandywine Ski Resort", "Boston Nordic"]
    assert [m["sold_with"] for m in r["matches"]] == [None, "Boston Mills Ski Resort", None]
    assert r["skipped"] == 1                              # Boston Hills: skimap.org only, no OSM id to build
    assert r["closest"] == []


def test_the_json_shape_and_osm_ids_build_pack_accepts(index, capsys):
    cache, resorts = index
    (resorts / "boston-mills").mkdir()                    # already configured
    r = json.loads(run(index, capsys, "boston", "--json")[1])
    assert set(r) == {"query", "matches", "skipped", "closest"}
    bm = r["matches"][0]
    assert bm == {"openskidata_id": "bm", "osm_id": "way/452323654", "name": "Boston Mills Ski Resort",
                  "region": "Ohio", "country": "US", "lat": 41.264, "lon": -81.565, "runs": 7, "lifts": 7,
                  "status": "operating", "slug": "boston-mills", "configured": True, "sold_with": None}
    assert r["matches"][1]["configured"] is False
    for m in r["matches"]:
        got = build_pack_ci.check_inputs(m["name"], m["osm_id"], m["slug"], "uid123", resorts_dir=str(cache))
        assert got["mode"] == "new" and got["osm_id"] == m["osm_id"]
        assert R.osm_pick(FEATS, m["osm_id"]) == m["openskidata_id"]     # resort.py add --osm finds the same area


def test_two_areas_of_one_name_are_both_listed_told_apart_by_region(index, capsys):
    r = json.loads(run(index, capsys, "Pine Crest", "--json")[1])
    assert [(m["openskidata_id"], m["region"], m["osm_id"]) for m in r["matches"]] == \
        [("pc1", "Colorado", "way/11"), ("pc2", "Wisconsin", "relation/22")]   # same name, same quality: by id
    assert {m["slug"] for m in r["matches"]} == {"pine-crest"}


def test_no_hit_gives_the_closest_names(index, capsys):
    code, out, _ = run(index, capsys, "Bostn Mils", "--json")
    r = json.loads(out)
    assert code == 0 and r["matches"] == [] and r["skipped"] == 0
    assert "Boston Mills Ski Resort" in r["closest"]


def test_limit_and_a_query_that_looks_like_a_flag(index, capsys):
    r = json.loads(run(index, capsys, "boston", "--json", "--limit", "1")[1])
    assert [m["name"] for m in r["matches"]] == ["Boston Mills Ski Resort"] and r["skipped"] == 1
    code, out, _ = run(index, capsys, "--json", "--", "-boston")    # the game passes the query after --
    assert code == 0 and json.loads(out)["query"] == "-boston"


def test_writes_nothing_and_reads_only_the_ski_areas(index, capsys, tmp_path):
    before = files(tmp_path)
    for q in ("boston", "pine crest", "zzz"):
        assert run(index, capsys, q, "--json")[0] == 0
    run(index, capsys, "boston")                         # the text form too
    assert files(tmp_path) == before                     # no config, no resorts/<slug>/, no lifts or runs index


def test_errors_go_to_stderr_with_a_non_zero_exit(index, capsys, tmp_path):
    code, out, err = run(index, capsys, "  ", "--json")
    assert code == 2 and out == "" and "search:" in err
    code, out, err = run(index, capsys, "boston", "--json", "--limit", "0")
    assert code == 2 and out == ""
    code = R.main(["--cache", str(tmp_path / "empty"), "search", "boston", "--json"])   # missing index: download
    out, err = capsys.readouterr()
    assert code == 1 and out == ""
    assert "downloading" in err and "cannot read the OpenSkiData ski areas index" in err


def test_the_download_message_goes_to_stderr(index, capsys, tmp_path, monkeypatch):
    body = json.dumps({"features": FEATS}).encode()

    class Resp:
        def __init__(self):
            self.left = body

        def read(self, n):
            b, self.left = self.left[:n], self.left[n:]
            return b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Resp())
    code = R.main(["--cache", str(tmp_path / "fresh"), "search", "boston", "--json"])
    out, err = capsys.readouterr()
    assert code == 0 and "downloading" in err and json.loads(out)["matches"][0]["slug"] == "boston-mills"


def test_osm_source_prefers_a_way():
    assert R.osm_source({"sources": [{"type": "openstreetmap", "id": "relation/5"},
                                     {"type": "openstreetmap", "id": "way/6"}]}) == "way/6"
    assert R.osm_source({"sources": [{"type": "openstreetmap", "id": "relation/5"}]}) == "relation/5"
    assert R.osm_source({"sources": [{"type": "openstreetmap", "id": "node/5"}, {"type": "skimap.org", "id": 3}]}) \
        is None
    assert R.osm_source({}) is None
