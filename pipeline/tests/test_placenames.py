"""FEAT-235: place names for any US resort: the GNIS states the far ring touches, the downloads, and reading the
GNIS and Census files into summits and towns."""
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import gen_manifest  # noqa: E402
import paths  # noqa: E402
import placenames as P  # noqa: E402


def cfg(slug):
    return json.load(open(paths.config_path(slug), encoding="utf-8"))


def test_the_far_ring_takes_the_neighbouring_states_the_resorts_own_first():
    assert P.states_for(P.far_box_ll(cfg("vail")), "CO") == ["CO"]
    bm = P.states_for(P.far_box_ll(cfg("boston-mills")), "OH")
    assert bm[0] == "OH" and {"PA", "WV"} <= set(bm) and "NY" not in bm       # PA 87 km east, WV's panhandle
    bs = cfg("bigsky")
    assert P.primary_state(bs) == "MT"                                        # a hand config: by region name
    assert P.states_for(P.far_box_ll(bs), "MT") == ["MT", "ID", "WY"]


def test_the_state_comes_from_openskidata_then_the_region():
    assert P.primary_state({"openskidata": {"iso3166_2": "US-OH"}, "region": "Colorado"}) == "OH"
    assert P.primary_state({"region": "Montana"}) == "MT"
    assert P.primary_state({"region": "Ontario"}) is None


def test_no_names_outside_the_us_or_without_a_planned_box():
    c = cfg("vail")
    assert P.plan_names({**c, "country": "CA"}) is None
    assert P.plan_names({"country": "US", "lonlat_bbox": [0, 0, 1, 1]}) is None
    assert P.plan_names(c)["states"] == ["CO"]


def test_the_manifest_downloads_each_states_gnis_file_and_the_census_files():
    c = cfg("boston-mills")
    items = [i for i in gen_manifest.manifest_items(c) if i["path"].startswith("names/")]
    paths_ = [i["path"] for i in items]
    assert paths_[0] == "names/DomesticNames_OH_Text.zip"
    assert "names/DomesticNames_PA_Text.zip" in paths_
    assert paths_[-2:] == [f"names/{P.CENSUS_YEAR}_Gaz_place_national.zip", f"names/sub-est{P.CENSUS_YEAR}.csv"]
    assert all(i["url"].startswith("https://") for i in items)
    # a config that records its states keeps them
    assert [i["path"] for i in P.manifest_items({**c, "names": {"states": ["OH"]}})][0] == "names/DomesticNames_OH_Text.zip"
    assert len(P.manifest_items({**c, "names": {"states": ["OH"]}})) == 3
    assert gen_manifest.MANIFEST_VERSION >= 2


GNIS_HEAD = ("﻿feature_id|feature_name|feature_class|state_name|state_numeric|county_name|county_numeric|map_name|"
             "date_created|date_edited|bgn_type|bgn_authority|bgn_date|prim_lat_dms|prim_long_dms|prim_lat_dec|"
             "prim_long_dec|source_lat_dms|source_long_dms|source_lat_dec|source_long_dec\n")


def gnis_row(fid, name, cls, lat, lon):
    f = [str(fid), name, cls, "Ohio", "39", "Summit", "153", "Peninsula", "", "", "", "", "", "", "", str(lat), str(lon),
         "", "", "", ""]
    return "|".join(f) + "\n"


def write_zip(path, member, text):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(member, text.encode("utf-8"))


def test_gnis_summits_inside_the_far_ring_once_each(tmp_path):
    d = tmp_path / "names"; d.mkdir()
    rows = [gnis_row(1, "Hogback Hill", "Summit", 41.25, -81.55), gnis_row(2, "Boston", "Populated Place", 41.26, -81.56),
            gnis_row(3, "Far Knob", "Summit", 45.0, -81.5), gnis_row(4, "Nowhere", "Summit", "", "")]
    write_zip(d / "DomesticNames_OH_Text.zip", "Text/DomesticNames_OH.txt", GNIS_HEAD + "".join(rows))
    write_zip(d / "DomesticNames_PA_Text.zip", "Text/DomesticNames_PA.txt", GNIS_HEAD + rows[0])  # listed twice
    feats, states = P.load_gnis(str(tmp_path), (-82.0, 41.0, -81.0, 42.0))
    assert states == ["OH", "PA"]
    assert [(f["id"], f["name"]) for f in feats] == [(1, "Hogback Hill")]
    towns, _ = P.load_gnis(str(tmp_path), (-82.0, 41.0, -81.0, 42.0), classes=("Populated Place",))
    assert [f["name"] for f in towns] == ["Boston"]


def test_vails_extract_osm_gnis_json_still_counts(tmp_path):
    d = tmp_path / "names"; d.mkdir()
    json.dump({"source": "USGS GNIS DomesticNames_CO", "features": [
        {"id": 9, "name": "Mount of the Holy Cross", "class": "Summit", "lat": 39.47, "lon": -106.48, "near": False}]},
        open(d / "gnis.json", "w"))
    feats, states = P.load_gnis(str(tmp_path), (-107, 39, -106, 40))
    assert states == ["CO"] and feats[0]["name"] == "Mount of the Holy Cross"


GAZ = ("USPS\tGEOID\tANSICODE\tNAME\tLSAD\tFUNCSTAT\tALAND\tAWATER\tALAND_SQMI\tAWATER_SQMI\tINTPTLAT\tINTPTLONG   \n"
       "OH\t3901000\t01086993\tAkron city\t25\tA\t1\t1\t1\t1\t41.080456\t-81.521429   \n"
       "OH\t3907790\t01086997\tBoston Heights village\t47\tA\t1\t1\t1\t1\t41.252583\t-81.507668   \n"
       "OH\t3999999\t09999999\tSomewhere CDP\t57\tS\t1\t1\t1\t1\t41.3\t-81.6   \n"
       "OH\t3975098\t01086999\tStow city\t25\tA\t1\t1\t1\t1\t41.17\t-81.44   \n"
       "MT\t3008950\t02409889\tBozeman city\t25\tA\t1\t1\t1\t1\t45.683155\t-111.053782   \n")
POP = ("SUMLEV,STATE,COUNTY,PLACE,COUSUB,CONCIT,PRIMGEO_FLAG,FUNCSTAT,NAME,STNAME,ESTIMATESBASE2020,POPESTIMATE2020,"
       "POPESTIMATE2024\n"
       "040,39,000,00000,00000,00000,0,A,Ohio,Ohio,1,1,11800000\n"
       "162,39,000,01000,00000,00000,0,A,Akron city,Ohio,1,1,188000\n"
       "162,39,000,07790,00000,00000,0,A,Boston Heights village,Ohio,1,1,1300\n"
       "162,39,000,75098,00000,00000,0,A,Stow city,Ohio,1,1,34500\n"
       "061,39,153,00000,07790,00000,0,A,Boston Heights village,Ohio,1,1,1300\n")


def test_census_towns_are_sized_like_osm_places(tmp_path):
    d = tmp_path / "names"; d.mkdir()
    write_zip(d / "2024_Gaz_place_national.zip", "2024_Gaz_place_national.txt", GAZ)
    (d / "sub-est2024.csv").write_text(POP, encoding="latin-1")
    towns = P.load_towns(str(tmp_path), (-82.0, 41.0, -81.0, 42.0))
    assert [(t["name"], t["kind"], t["pop"]) for t in towns] == [
        ("Akron", "city", 188000), ("Boston Heights", "village", 1300), ("Somewhere", "village", None),
        ("Stow", "town", 34500)]
    assert P.load_towns(str(tmp_path / "none"), (-82.0, 41.0, -81.0, 42.0)) == []


def test_place_names_lose_their_census_suffix():
    assert P.place_name("Akron city") == "Akron"
    assert P.place_name("Big Sky CDP") == "Big Sky"
    assert P.place_name("Nashville-Davidson metropolitan government (balance)") == "Nashville-Davidson"
    assert P.place_name("Carson City") == "Carson City"     # the suffixes are lower case: a capital City stays


def test_gnis_summits_osm_already_has_are_dropped():
    osm = [{"name": "Lone Mountain", "x": 0.0, "y": 0.0, "z": 3403}]
    gnis = [{"name": "Lone Mountain", "x": 900.0, "y": 0.0, "z": 3390},      # same name, 900 m off: same peak
            {"name": "Unnamed Knob", "x": 100.0, "y": 0.0, "z": 3300},       # another name 100 m off: same summit
            {"name": "Lone Mountain", "x": 5000.0, "y": 0.0, "z": 2900},     # same name far away: another peak
            {"name": "Fan Mountain", "x": -3000.0, "y": 2500.0, "z": 3100}]
    assert [g["x"] for g in P.merge_peaks(osm, gnis)] == [5000.0, -3000.0]
