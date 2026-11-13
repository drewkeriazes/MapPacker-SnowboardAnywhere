"""FEAT-293: the resort's published figures (published.py) and the pack checked against them. Offline: the
Wikidata and Wikipedia calls are a fake."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import published as P  # noqa: E402

VAIL = """{{Short description|Ski resort in Colorado}}
{{Infobox ski area
| name                   = Vail Ski Resort
| image                  = [[File:Vail.jpg|250px]]
| location               = [[Vail, Colorado|Vail]]
| vertical               = {{spaces|2}}{{convert|3450|ft|0|abbr=on}}
| top_elevation          = {{convert|11570|ft|0|abbr=on}}
| base_elevation         = {{spaces|2}}{{convert|8120|ft|0|abbr=on}}
| skiable_area           = {{convert|5317|acre|mi2 km2|1}}
| number_trails          = 195 total<br>[[File:Ski trail rating symbol-green circle.svg|13px]] 18% beginner<br>[[File:x.svg|13px]] 29% intermediate
| lift_system            = 31 total (2 [[Gondola lift|gondolas]] (12 and 10 person), 4 [[Detachable chairlift|high speed]] six's)
| lift_capacity          = <!-- passengers/hr -->
}}
'''Vail Ski Resort''' is a ski resort.{{cite web|url=x}}
"""

CRYSTAL = """{{Infobox ski area
| top_elevation = {{convert|7012|ft|abbr=on}}<br />{{convert|6992|ft|abbr=on}} - ''lifts''
| number_trails = 80 (57 designated trails)<br />- 11% easiest
| lift_system = 1 [[Gondola lift|gondola]]<br /> 9 [[chairlift|chairs]]<br />1 [[Magic carpet (ski lift)|magic carpet]]
| skiable_area = 1,050 ha
}}"""


def test_infobox_figures_vail():
    box = P.infobox(VAIL)
    assert box["name"] == "Vail Ski Resort" and box["lift_capacity"] == "<!-- passengers/hr -->"
    f = P.figures_from_infobox(box, "Wikipedia: Vail Ski Resort")
    assert {k: v["value"] for k, v in f.items()} == {"summit": 3527, "base": 2475, "vertical": 1052, "lifts": 31,
                                                     "runs": 195, "area": 21.52}
    assert f["summit"]["text"] == "11570 ft" and f["runs"]["source"] == "Wikipedia: Vail Ski Resort"


def test_infobox_figures_with_several_values_and_a_breakdown():
    f = P.figures_from_infobox(P.infobox(CRYSTAL), "w")
    assert f["summit"]["value"] == 2131            # the lifts' top (6992 ft), as the pack measures lifts
    assert f["runs"]["value"] == 80
    assert f["lifts"]["value"] == 11               # 1 gondola + 9 chairs + 1 carpet
    assert f["area"]["value"] == 10.5
    assert P.infobox("no box here") is None


@pytest.mark.parametrize("text,n", [("195 total\n18% beginner", 195), ("41\nGondolas: 4\nChairs: 32", 41),
                                    ("25 total: 1 high speed gondola", 25), ("20 lifts (1 Gondola, 5 six)", 20),
                                    ("140+ total", 140), ("15", 15), ("1 gondola\n9 chairs\n1 magic carpet", 11),
                                    ("none", None)])
def test_count(text, n):
    assert P.count(text) == n


# ------------------------------------------------------------------------------------------------ finding the article

AREA = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-106.35, 39.60]},
        "properties": {"id": "a1", "type": "skiArea", "name": "Vail", "status": "operating",
                       "sources": [{"type": "openstreetmap", "id": "way/531009607"}]}}


class FakeWeb:
    def __init__(self, entities, articles, statements=None, names=None):
        self.ents, self.articles, self.statements, self.names = entities, articles, statements or {}, names or {}
        self.calls = []

    def entities(self, qids):
        self.calls.append(("entities", tuple(qids)))
        return {q: self.ents[q] for q in qids if q in self.ents}

    def by_statement(self, prop, value):
        self.calls.append(("statement", prop, value))
        return self.statements.get((prop, value), [])

    def by_name(self, name):
        self.calls.append(("name", name))
        return self.names.get(name, [])

    def wikitext(self, title):
        self.calls.append(("wikitext", title))
        return title, self.articles.get(title, "")


def ent(title=None, lonlat=None):
    e = {"claims": {}, "sitelinks": {}}
    if title:
        e["sitelinks"]["enwiki"] = {"title": title}
    if lonlat:
        e["claims"]["P625"] = [{"mainsnak": {"datavalue": {"value": {"longitude": lonlat[0], "latitude": lonlat[1]}}}}]
    return e


def test_article_by_osm_way_then_stops():
    web = FakeWeb({"Q1": ent("Vail Ski Resort")}, {"Vail Ski Resort": VAIL}, statements={("P10689", "531009607"): ["Q1"]})
    q, how, title, box = P.article(AREA, {"name": "Vail"}, web)
    assert (q, how, title) == ("Q1", "Wikidata P10689=531009607", "Vail Ski Resort") and box
    assert not any(c[0] == "name" for c in web.calls)          # found: no name search (Wikidata rate limits)


def test_article_by_name_must_be_near():
    far = ent("Vail, Arizona", (-110.7, 32.0))
    near = ent("Vail Ski Resort", (-106.37, 39.63))
    web = FakeWeb({"Q9": far, "Q1": near}, {"Vail, Arizona": VAIL, "Vail Ski Resort": VAIL}, names={"Vail": ["Q9", "Q1"]})
    q, how, title, _ = P.article(AREA, {"name": "Vail"}, web)
    assert (q, title) == ("Q1", "Vail Ski Resort") and how == "Wikidata search 'Vail'"


def test_article_bracket_dropped_from_the_name():
    area = json.loads(json.dumps(AREA))
    area["properties"].update(name="Beaver Creek Resort (Arrowhead Mountain)", sources=[])
    web = FakeWeb({"Q8": ent("Beaver Creek Resort", (-106.52, 39.60))}, {"Beaver Creek Resort": VAIL},
                  names={"Beaver Creek Resort": ["Q8"]})
    assert P.article(area, {}, web)[2] == "Beaver Creek Resort"


def test_article_none_keeps_the_tied_item():
    area = json.loads(json.dumps(AREA))
    area["properties"]["wikidataID"] = "Q5"
    web = FakeWeb({"Q5": ent()}, {})
    assert P.article(area, {}, web) == ("Q5", "OpenSkiData wikidataID", None, None)


# ------------------------------------------------------------------------------------------------ the record

def feed(raw, name, trails):
    os.makedirs(os.path.join(raw, "grooming"), exist_ok=True)
    json.dump({"date": "x", "trails": [{"name": t} for t in trails]}, open(os.path.join(raw, "grooming", name), "w"))


def test_gather_figures_hand_and_trails(tmp_path):
    raw = str(tmp_path / "raw")
    feed(raw, "20250101000000.json", ["Old Run"])
    feed(raw, "20260401090356.json", ["Born Free", "Riva Ridge", "Born Free"])
    feed(raw, "20260402000000.json", [])                         # a night with no trails: not the list
    web = FakeWeb({"Q1": ent("Vail Ski Resort")}, {"Vail Ski Resort": VAIL}, statements={("P10689", "531009607"): ["Q1"]})
    cfg = {"slug": "vail", "name": "Vail", "osm_ski_area_way": 531009607,
           "terrain_status_url": "https://www.vail.com/the-mountain/x.aspx"}
    old = {"figures": {"runs": {"value": 278, "source": "hand: vail.com mountain stats", "unit": ""},
                       "lifts": {"value": 1, "source": "Wikipedia: old"}}}
    rec = P.gather(cfg, [AREA], web, raw=raw, old=old)
    assert rec["areas"][0]["wikipedia"] == "Vail Ski Resort"
    assert rec["figures"]["runs"]["value"] == 278                 # a hand figure wins and is kept
    assert rec["figures"]["lifts"]["value"] == 31                 # a gathered one is replaced
    assert rec["trails"] == {"source": "vail.com terrain status, 2026-04-01", "names": ["Born Free", "Riva Ridge"]}
    again = P.gather(cfg, [AREA], web, raw=str(tmp_path / "gone"), old=rec)
    assert again["trails"] == rec["trails"]                       # raw moved away: the list read before stays


def test_gather_skips_a_mashup_and_an_unknown_area():
    web = FakeWeb({}, {})
    rec = P.gather({"slug": "ohio-hills", "relocate": [{"name": "Brandywine"}, {"name": "Mad River", "source": "mad"}]},
                   [AREA], web)
    assert rec["figures"] == {} and "Mad River" in rec["why"] and web.calls == []
    rec = P.gather({"slug": "x", "name": "Nowhere"}, [AREA], web)
    assert "no OpenSkiData ski area" in rec["why"]


def test_write_and_load(tmp_path):
    rec = {"version": 1, "slug": "demo", "figures": {}}
    p = P.write(rec, "demo", str(tmp_path))
    assert p == os.path.join(str(tmp_path), "demo", "demo-published.json") and P.load("demo", str(tmp_path)) == rec
    assert P.load("other", str(tmp_path)) is None


# ------------------------------------------------------------------------------------------------ against the pack

def test_match_trails():
    osm = ["Born Free", "Four O'Clock", "Power line", "Assesment", "Brisk Walk", "Lonely Run"]
    m = P.match_trails(["born free", "Upper 4 O'Clock", "Powerline", "Assessment", "Brisk Walk - Lower",
                        "Inner Mongolia"], osm)
    assert dict(m["matched"]) == {"born free": "Born Free", "Upper 4 O'Clock": "Four O'Clock", "Powerline": "Power line",
                                  "Assessment": "Assesment", "Brisk Walk - Lower": "Brisk Walk"}
    assert m["unmatched"] == ["Inner Mongolia"] and m["osm_only"] == ["Lonely Run"]


def lift(name, z0, z1, kind="chair_lift", x=0.0):
    return {"name": name, "type": kind, "stations": [[x, 0, z0], [x, 1000, z1]]}


def runs(names, x=0.0):
    return [{"name": n, "difficulty": "easy", "area": False, "points": [[x + 60 * i, 0, 3000], [x + 60 * i, 1000, 2500]]}
            for i, n in enumerate(names)]


def resort_features(cut=False):
    """a resort of 10 lifts (8 chairs, 2 carpets) from 2450 m to 3500 m and 20 named runs; `cut` leaves out the
    west part: its 4 lifts, its 10 runs and the lowest base"""
    east = [lift(f"E{i}", 2600, 3500 - 10 * i) for i in range(4)] + \
        [lift("Carpet", 2600, 2610, "magic_carpet"), lift("Carpet 2", 2600, 2605, "magic_carpet")]
    west = [lift(f"W{i}", 2450, 3200, x=-5000) for i in range(4)]
    f = {"lifts": east + ([] if cut else west), "runs": runs([f"East {i}" for i in range(10)]) +
         ([] if cut else runs([f"West {i}" for i in range(10)], x=-5000))}
    return f


def fig(v, unit=""):
    return {"value": v, "unit": unit, "source": "Wikipedia: Demo", "text": str(v)}


REC = {"figures": {"summit": fig(3510, "m"), "base": fig(2440, "m"), "vertical": fig(1070, "m"), "lifts": fig(10),
                   "runs": fig(20), "area": fig(1.4, "km2")},
       "trails": {"source": "demo.example terrain status, 2026-04-01",
                  "names": [f"East {i}" for i in range(10)] + [f"West {i}" for i in range(10)]}}


def statuses(rows):
    return {r["figure"]: r["status"] for r in rows}


def test_a_whole_resort_passes():
    rows, trails = P.compare(REC, resort_features())
    assert statuses(rows) == {f: "pass" for f in P.FIGURES}, [r["note"] for r in rows]
    assert len(trails["matched"]) == 20 and not trails["unmatched"]


def test_a_resort_missing_its_west_part_warns():
    rows, trails = P.compare(REC, resort_features(cut=True))
    st = statuses(rows)
    assert st["base"] == "warn" and st["lifts"] == "warn" and st["runs"] == "warn" and st["area"] == "warn"
    assert st["vertical"] == "warn" and st["summit"] == "pass"
    assert trails["unmatched"] == [f"West {i}" for i in range(10)]
    assert "base lift missing" in next(r for r in rows if r["figure"] == "base")["note"]


def test_lifts_counted_either_way_and_a_low_town_gondola():
    f = resort_features()
    f["lifts"] += [lift("Town gondola", 2200, 2600, "gondola")] + [lift("C", 2600, 2610, "magic_carpet")] * 2
    rec = json.loads(json.dumps(REC))
    rec["figures"]["lifts"] = fig(9)                 # chairs and gondolas only: 9 of the 13
    rows, _ = P.compare(rec, f)
    st = statuses(rows)
    assert st["lifts"] == "pass" and "leaves out surface lifts" in next(r for r in rows if r["figure"] == "lifts")["note"]
    assert st["base"] == "pass" and st["vertical"] == "pass"   # below the published base: a town gondola, not a gap


def test_little_area_with_every_lift_says_glades_not_a_gap():
    rec = json.loads(json.dumps(REC))
    rec["figures"]["area"] = fig(5.0, "km2")         # Heavenly: 4,800 acres, its woods mapped as lines
    row = next(r for r in P.compare(rec, resort_features())[0] if r["figure"] == "area")
    assert row["status"] == "warn" and "likely no part missing" in row["note"]
    row = next(r for r in P.compare(rec, resort_features(cut=True))[0] if r["figure"] == "area")
    assert row["note"].endswith("part of the resort missing")


def test_a_summit_off_either_way_warns_and_no_figures_no_rows():
    rec = json.loads(json.dumps(REC))
    rec["figures"]["summit"] = fig(3800, "m")
    assert statuses(P.compare(rec, resort_features())[0])["summit"] == "warn"
    rec["figures"]["summit"] = fig(3300, "m")
    assert statuses(P.compare(rec, resort_features())[0])["summit"] == "warn"
    assert P.compare({"figures": {}, "trails": None}, resort_features()) == ([], None)
