#!/usr/bin/env python3
"""FEAT-293: what a resort publishes about itself, for pack_report.py to check a pack against.

    python pipeline/published.py <slug> [--raw <raw_dir>] [--refresh] [--cache <index dir>]

Writes `resorts/<slug>/<slug>-published.json` (committed with the resort's other files by publish_pack.py) and
prints it. pack_report.py reads that file; when it is missing it gathers it once (network) and writes it.

Figures (each with its source and the text it was read from): summit, base and vertical in metres, lift count,
run count, skiable area in km2. Sources, in the order tried:
- hand: a figure whose `source` starts with "hand" (typed from the resort's own site) is kept on every refresh
  and wins over the others;
- the English Wikipedia article's `Infobox ski area` (top_elevation, base_elevation, vertical, lift_system,
  number_trails, skiable_area). The article is found through Wikidata: the OpenSkiData area's `wikidataID`, else
  the Wikidata item naming the area's OSM way (P10689) or relation (P402), else a Wikidata name search kept only
  when the item is within 20 km of the resort and its article has the infobox (Big Sky, which OpenSkiData gives no
  Wikidata id). Wikidata itself rarely holds the figures (Vail's item has none), Skimap.org's records hold maps
  only, and resort websites have no common machine-readable form, so the infobox is the one source that covers
  most resorts. Figures are facts; the article is named as the source.
- the trail list: the newest night of the resort's terrain status feed in `<raw>/grooming/` (fetch_grooming.py,
  Vail Resorts' resorts), every trail the resort lists by name. pack_report.py matches it with the OSM run names.

Published figures are marketing numbers (acreage and run counts are counted in different ways), so the report
only ever warns on them. Network: Wikidata and Wikipedia (any machine with web access, CI included).
"""
import argparse, datetime, glob, json, math, os, re, sys, time, urllib.error, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

UA = "SnowboardAnywhere-pipeline/1.0 (resort pack report)"
WIKIDATA = "https://www.wikidata.org/w/api.php"
WIKIPEDIA = "https://en.wikipedia.org/w/api.php"
NEAR_KM = 20.0               # a Wikidata item found by name must be this close to the resort
FT, ACRE = 0.3048, 4046.8564224
VERSION = 1
FIGURES = ("summit", "base", "vertical", "lifts", "runs", "area")
UNITS = {"summit": "m", "base": "m", "vertical": "m", "lifts": "", "runs": "", "area": "km2"}
INFOBOX_KEYS = {"summit": ("top_elevation",), "base": ("base_elevation",), "vertical": ("vertical",),
                "lifts": ("lift_system", "number_lifts"), "runs": ("number_trails",), "area": ("skiable_area",)}


def published_path(slug, resorts=None):
    """resorts/<slug>/<slug>-published.json (`resorts`: the folder holding every resort's, as in paths.py)"""
    return os.path.join(paths.resort_dir(slug, resorts), f"{slug}-published.json")


# ------------------------------------------------------------------------------------------------ the infobox

def infobox(wikitext):
    """{param: raw value} of the first `Infobox ski area` in an article's wikitext, or None"""
    m = re.search(r"\{\{\s*Infobox[ _]ski[ _]area", wikitext or "", re.I)
    if not m:
        return None
    i, depth, start = m.start(), 0, m.start()
    while i < len(wikitext):           # the template's end: braces balanced again
        if wikitext.startswith("{{", i):
            depth += 1; i += 2; continue
        if wikitext.startswith("}}", i):
            depth -= 1; i += 2
            if depth == 0:
                break
            continue
        i += 1
    body = wikitext[start + 2:i - 2]
    parts, depth, cur = [], 0, ""
    j = 0
    while j < len(body):               # split on the top level's pipes only
        two = body[j:j + 2]
        if two in ("{{", "[["):
            depth += 1; cur += two; j += 2; continue
        if two in ("}}", "]]"):
            depth -= 1; cur += two; j += 2; continue
        if body[j] == "|" and depth == 0:
            parts.append(cur); cur = ""; j += 1; continue
        cur += body[j]; j += 1
    parts.append(cur)
    out = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


def plain(text):
    """wikitext to plain text: {{convert|11570|ft|...}} -> "11570 ft", links to their label, tags and comments out"""
    t = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    t = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", "", t, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"\{\{\s*(?:convert|cvt)\s*\|\s*([\d.,]+)\s*\|\s*([a-zA-Z0-9]+)[^{}]*\}\}",
               lambda m: f"{m.group(1)} {m.group(2)}", t, flags=re.I)
    t = re.sub(r"\{\{[^{}]*\}\}", "", t)                       # {{spaces|2}}, {{nowrap|..}} and the rest
    t = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", t, flags=re.I)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"'{2,}", "", t)                                # ''italic'' and '''bold'''
    t = t.replace("&nbsp;", " ").replace("\u00a0", " ")
    return "\n".join(" ".join(ln.split()) for ln in t.split("\n") if ln.strip())


def number(s):
    s = s.replace(",", "")
    return float(s) if re.fullmatch(r"\d+(?:\.\d+)?", s) else None


def length_m(text):
    """the first length in the text, in metres ("11570 ft", "3,527 m"), or None"""
    m = re.search(r"([\d][\d,]*(?:\.\d+)?)\s*(ft|feet|foot|m|metres|meters|metre|meter)\b", text)
    if not m:
        return None
    v = number(m.group(1))
    return None if v is None else v * (FT if m.group(2).startswith("f") else 1.0)


def area_km2(text):
    m = re.search(r"([\d][\d,]*(?:\.\d+)?)\s*(acres?|ha|hectares?|km2|km\u00b2|sq\s*km)\b", text, re.I)
    if not m:
        return None
    v, u = number(m.group(1)), m.group(2).lower()
    if v is None:
        return None
    return v * ACRE / 1e6 if u.startswith("acre") else v / 100 if u.startswith("h") else v


def count(text):
    """a count: the first line's number when it stands alone or before "total", "lifts", "trails" or a bracket
    ("195 total", "41", "80 (57 designated trails)", "20 lifts (1 Gondola, ..."), else the sum of each line's
    leading number (Crystal's "1 gondola / 9 chairs / 1 magic carpet")"""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if not lines:
        return None
    m = re.match(r"\s*(\d[\d,]*)\+?\s*(?:total|lifts|trails|runs|named trails)?\s*(?:[(:;,]|$)", lines[0], re.I)
    if m:
        return int(number(m.group(1)))
    nums = [int(number(x.group(1))) for x in (re.match(r"\s*-?\s*(\d[\d,]*)\b(?!\s*%)", ln) for ln in lines) if x]
    return sum(nums) if nums else None


def figures_from_infobox(box, source):
    """{figure: {value, unit, source, text}} from the infobox's params"""
    out = {}
    for fig, keys in INFOBOX_KEYS.items():
        raw = next((box[k] for k in keys if box.get(k)), None)
        if not raw:
            continue
        text = plain(raw)
        lines = text.split("\n") if text else [""]
        first = lines[0]
        if fig in ("summit", "base", "vertical"):
            # Crystal gives the terrain's and the lifts' ("4400 ft - lifts"): the pack measures the lifts
            first = next((ln for ln in lines if re.search(r"\blifts?\b", ln, re.I) and length_m(ln)), first)
        v = (length_m(first) if fig in ("summit", "base", "vertical") else
             area_km2(first) if fig == "area" else count(text))
        if v is None:
            continue
        value = round(v, 2) if fig == "area" else int(round(v))
        out[fig] = {"value": value, "unit": UNITS[fig], "source": source, "text": text.replace("\n", "; ")[:200]}
    return out


# ------------------------------------------------------------------------------------------------ the trail list

def trail_list(raw):
    """(names, night) from the newest terrain status feed in <raw>/grooming/ that lists trails, or (None, None)"""
    if not raw:
        return None, None
    for p in sorted(glob.glob(os.path.join(raw, "grooming", "*.json")), reverse=True):
        try:
            with open(p, encoding="utf-8") as f:
                feed = json.load(f)
        except (OSError, ValueError):
            continue
        names = sorted({(t.get("name") or "").strip() for t in feed.get("trails") or []} - {""})
        if names:
            return names, os.path.splitext(os.path.basename(p))[0][:8]
    return None, None


# ------------------------------------------------------------------------------------------------ finding the area

def ski_areas(cfg, features):
    """the OpenSkiData ski area properties a config is built from: its `openskidata.ids`, else the area built from
    its `osm_ski_area_way`, else the one name match (the hand configs of Vail, Breckenridge and Big Sky)"""
    import resort
    areas = [f for f in features if (f.get("properties") or {}).get("type") == "skiArea"]
    by_id = {f["properties"]["id"]: f for f in areas}
    ids = (cfg.get("openskidata") or {}).get("ids") or []
    if not ids and cfg.get("osm_ski_area_way"):
        i = resort.osm_pick(areas, f"way/{cfg['osm_ski_area_way']}")
        ids = [i] if i else []
    if not ids and cfg.get("name"):
        hits = resort.search(areas, cfg["name"])
        box = cfg.get("lonlat_bbox")
        if box:
            hits = [f for f in hits if resort.gap_m(box, resort.bounds(resort.geom_points(f["geometry"]))) < 1000]
        hits = [f for f in hits if f["properties"].get("status") in (None, "operating")] or hits
        ids = [hits[0]["properties"]["id"]] if len(hits) == 1 else []
    return [by_id[i] for i in dict.fromkeys(ids) if i in by_id]


class Web:
    """the network calls; tests replace it"""

    def get(self, url, params, tries=4):
        """GET a MediaWiki API; a 429 or 503 waits (Retry-After, else 5 s, 10 s, 20 s) and tries again"""
        import resort
        q = url + "?" + urllib.parse.urlencode({**params, "format": "json", "maxlag": 5})
        for i in range(tries):
            try:
                return json.loads(resort.fetch(q, headers={"User-Agent": UA}, timeout=60))
            except urllib.error.HTTPError as e:
                if e.code not in (429, 503) or i == tries - 1:
                    raise
                wait = e.headers.get("Retry-After")
                time.sleep(min(60.0, float(wait)) if wait and wait.isdigit() else 5.0 * 2 ** i)

    def entities(self, qids):
        if not qids:
            return {}
        return self.get(WIKIDATA, {"action": "wbgetentities", "ids": "|".join(qids), "props": "claims|sitelinks|labels",
                                   "languages": "en"}).get("entities", {})

    def by_statement(self, prop, value):
        r = self.get(WIKIDATA, {"action": "query", "list": "search", "srsearch": f"haswbstatement:{prop}={value}"})
        return [h["title"] for h in r.get("query", {}).get("search", [])]

    def by_name(self, name):
        r = self.get(WIKIDATA, {"action": "wbsearchentities", "search": name, "language": "en", "type": "item", "limit": 10})
        return [h["id"] for h in r.get("search", [])]

    def wikitext(self, title):
        r = self.get(WIKIPEDIA, {"action": "parse", "page": title, "prop": "wikitext", "formatversion": 2, "redirects": 1})
        p = r.get("parse") or {}
        return p.get("title", title), p.get("wikitext") or ""


def coord(entity):
    for c in (entity.get("claims") or {}).get("P625", []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if v:
            return v["longitude"], v["latitude"]
    return None


def km_between(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot((a[0] - b[0]) * 111.32 * math.cos(lat), (a[1] - b[1]) * 110.54)


def article(area, cfg, web):
    """(qid, how, title, infobox) of the English Wikipedia article with the area's infobox; without one the first
    Wikidata item tied to the area by id, with None for the rest. Candidates in order, each looked up only when the
    ones before it had no infobox (Wikidata answers a burst with 429)."""
    import resort
    p = area["properties"]
    pts = resort.geom_points(area["geometry"])
    b = resort.bounds(pts) if pts else cfg.get("lonlat_bbox")
    centre = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) if b else None

    def candidates():
        if p.get("wikidataID"):
            yield [p["wikidataID"]], "OpenSkiData wikidataID", False
        for s in p.get("sources") or []:
            kind, _, num = (resort.source_key(s) or "").partition("/")
            prop = {"way": "P10689", "relation": "P402"}.get(kind)
            if prop:
                yield web.by_statement(prop, num), f"Wikidata {prop}={num}", False
        names = [p.get("name"), cfg.get("name"), resort.short_name(p.get("name") or "")]
        names += [re.sub(r"\s*\([^)]*\)", "", n or "").strip() for n in names]   # "Beaver Creek Resort (Arrowhead Mountain)"
        for name in dict.fromkeys(n for n in names if n):
            yield web.by_name(name), f"Wikidata search {name!r}", True

    first, seen = None, set()
    for qids, how, by_name in candidates():
        qids = [q for q in qids if q not in seen]
        seen |= set(qids)
        ents = web.entities(qids[:50])
        for q in qids:
            e = ents.get(q) or {}
            if by_name:
                c = coord(e)
                if not (c and centre and km_between(c, centre) <= NEAR_KM):
                    continue
            elif first is None:
                first = (q, how)
            title = ((e.get("sitelinks") or {}).get("enwiki") or {}).get("title")
            if not title:
                continue
            title, text = web.wikitext(title)
            box = infobox(text)
            if box is not None:
                return q, how, title, box
    return (*(first or (None, None)), None, None)


# ------------------------------------------------------------------------------------------------ the record

def gather(cfg, features, web, raw=None, old=None):
    """the published figures record for a config"""
    rec = {"version": VERSION, "slug": cfg.get("slug"), "fetched": datetime.date.today().isoformat(),
           "areas": [], "figures": {}, "trails": None}
    hand = {k: v for k, v in ((old or {}).get("figures") or {}).items() if str(v.get("source", "")).startswith("hand")}
    pasted = [m.get("name") for m in cfg.get("relocate") or [] if m.get("source")]
    if pasted:     # FEAT-268: Ohio Hills, Boston Mills plus Mad River: no resort publishes figures for the pair
        rec["why"] = f"a mashup: {', '.join(pasted)} is pasted in from another resort's data, so no one resort's figures fit"
        return rec
    areas = ski_areas(cfg, features)
    if not areas:
        rec["why"] = f"no OpenSkiData ski area for {cfg.get('name')!r} (no openskidata ids, OSM way or single name match)"
    found = []
    for a in areas:
        q, how, title, box = article(a, cfg, web)
        rec["areas"].append({"openskidata_id": a["properties"]["id"], "name": a["properties"].get("name"),
                             "wikidata": q, "found_by": how, "wikipedia": title, "infobox": box is not None})
        if box is not None:
            found.append((title, box))
    titles = list(dict.fromkeys(t for t, _ in found))
    if len(titles) == 1:
        rec["figures"] = figures_from_infobox(found[0][1], f"Wikipedia: {titles[0]}")
    elif len(titles) > 1:
        rec["why"] = f"the pack covers {len(titles)} articles ({', '.join(titles)}): their figures do not add up to one resort"
    elif areas and "why" not in rec:
        rec["why"] = "no English Wikipedia article with an Infobox ski area for " + \
                     ", ".join(a["properties"].get("name") or a["properties"]["id"] for a in areas)
    rec["figures"].update(hand)
    names, night = trail_list(raw)
    if names:
        host = re.sub(r"^www\.", "", urllib.parse.urlparse(cfg.get("terrain_status_url") or "").netloc) or "the resort"
        rec["trails"] = {"source": f"{host} terrain status, {night[:4]}-{night[4:6]}-{night[6:]}", "names": names}
    elif (old or {}).get("trails"):
        rec["trails"] = old["trails"]          # raw gone (Vail's was moved): keep what was read before
    return rec


# ------------------------------------------------------------------------------------------------ against the pack

CHAIRS = {"chair_lift", "gondola", "cable_car", "mixed_lift", "funicular"}   # the lifts a chairs-only count names
FOOTPRINT_M = 50.0        # a run line widened this far each side, plus the area runs, is the pack's skiable area
Z_WARN_M = 75.0           # summit or base further than this from the published one
VERTICAL_WARN = (75.0, 0.10)   # vertical off by more than both of these (metres, share)
LIFTS_WARN = (2, 0.15)         # lift count off by more than both of these, against every lift and against chairs
RUNS_RATIO = (0.75, 2.0)       # distinct run names over the published count outside this (OSM names "Upper" and
                               # "Lower" apart, so 1.3 is usual: Breckenridge, Park City)
AREA_RATIO = (0.6, 1.6)        # footprint over published acreage outside this (0.8 to 1.5 on five resorts)
TRAILS_MATCHED = 0.75          # a share of the published trail list under this with an OSM run
LONG_NAME = 12                 # a misspelt name ("Assesment", "Canis Lupis") is one letter off, two from this long
                               # (not difflib's ratio: it pairs "West 3" with "East 3")
NUM_WORDS = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight",
             "9": "nine", "10": "ten"}
LOOSE_DROP = {"upper", "lower", "middle", "mid", "the", "run", "trail", "road", "rd", "catwalk", "ski", "way", "s"}


def pack_figures(features):
    """the pack's own summit, base, vertical (lift stations; run points when there are no lifts), lifts (every one
    and chairs only), distinct run names and footprint km2, from features.json"""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    lifts, runs = features.get("lifts") or [], features.get("runs") or []
    z = [p[2] for l in lifts for p in l.get("stations") or [] if len(p) > 2]
    zfrom = "lift stations"
    if not z:
        z, zfrom = [p[2] for r in runs for p in r.get("points") or [] if len(p) > 2], "run points"
    out = {}
    if z:
        out["summit"] = {"value": round(max(z)), "how": f"highest of the {zfrom}"}
        out["base"] = {"value": round(min(z)), "how": f"lowest of the {zfrom}"}
        out["vertical"] = {"value": round(max(z) - min(z)), "how": f"between them"}
    out["lifts"] = {"value": len(lifts), "chairs": sum(1 for l in lifts if l.get("type") in CHAIRS)}
    named = {r["name"].strip() for r in runs if (r.get("name") or "").strip()}
    out["runs"] = {"value": len(named), "segments": len(runs), "unnamed": sum(1 for r in runs if not (r.get("name") or "").strip()),
                   "names": sorted(named)}
    parts = []
    for r in runs:
        pts = [(p[0], p[1]) for p in r.get("points") or []]
        if r.get("area") and len(pts) >= 3:
            parts.append(Polygon(pts).buffer(0))
        elif len(pts) > 1:
            parts.append(LineString(pts).buffer(FOOTPRINT_M))
    if parts:
        out["area"] = {"value": round(unary_union(parts).area / 1e6, 2),
                       "how": f"run lines widened {FOOTPRINT_M:.0f} m each side, plus the area runs"}
    return out


def name_key(n):
    w = re.sub(r"[^a-z0-9]+", " ", _fold(n.replace("'", "").replace("\u2019", "").replace("&", " and "))).split()
    return " ".join(NUM_WORDS.get(x, x) for x in w)


def _fold(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def loose_key(n):
    return "".join(x for x in name_key(n).split() if x not in LOOSE_DROP)


def edits(a, b):
    """Levenshtein distance"""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_trails(published_names, osm_names):
    """{"matched": [(published, osm)], "unmatched": [published], "osm_only": [osm]}: the same name (case, accents,
    apostrophes and "4"/"four" aside), else the same without Upper, Lower, The, Run and spaces ("Power line"), else
    the part before " - " (a resort listing parts of one run), else one letter off (two on a long name)"""
    exact = {}
    for n in osm_names:
        exact.setdefault(name_key(n), n)
    loose = {}
    for n in osm_names:
        loose.setdefault(loose_key(n), n)
    matched, unmatched = [], []
    for p in published_names:
        o = exact.get(name_key(p)) or loose.get(loose_key(p))
        part = re.split(r"\s+-\s+", p)[0]            # Vail's "Brisk Walk - Lower", "Bwana - Expert Face"
        if not o and part != p:
            o = exact.get(name_key(part)) or loose.get(loose_key(part))
        if not o and loose_key(p):
            k = loose_key(p)
            near = [n for n in loose if abs(len(n) - len(k)) <= 2 and edits(n, k) <= (2 if len(k) >= LONG_NAME else 1)]
            o = loose[near[0]] if near else None
        (matched.append((p, o)) if o else unmatched.append(p))
    used = {o for _, o in matched}
    return {"matched": matched, "unmatched": unmatched, "osm_only": [n for n in osm_names if n not in used]}


def _row(fig, label, pub, packv, status, note, unit=""):
    return {"figure": fig, "label": label, "published": pub.get("value") if pub else None, "unit": unit,
            "source": pub.get("source") if pub else None, "text": pub.get("text") if pub else None,
            "pack": packv, "status": status, "note": note}


def compare(rec, features):
    """rows {figure, label, published, unit, source, text, pack, status ("pass", "warn", "skip"), note} and the trail
    match (or None), the pack against the published record. Never "fail": published figures are marketing numbers."""
    figs = (rec or {}).get("figures") or {}
    mine = pack_figures(features)
    rows = []
    for fig, label in (("summit", "Summit"), ("base", "Base")):
        pub, m = figs.get(fig), mine.get(fig)
        if not pub or not m:
            continue
        d = m["value"] - pub["value"]
        # a base below the published one is a lift down to a town (Beaver Creek's Riverfront gondola in Avon,
        # 200 m under the village base it publishes): only a base above it says something is missing
        bad = abs(d) > Z_WARN_M if fig == "summit" else d > Z_WARN_M
        note = f"{m['how']}, {d:+.0f} m"
        if bad:
            note += (": a top lift or peak missing, or a hike-to summit" if fig == "summit" and d < 0 else
                     ": a lower area or base lift missing (an area split in OpenSkiData, a neighbour left out)"
                     if fig == "base" else ": the wrong area, or a datum or unit error")
        elif fig == "base" and d < -Z_WARN_M:
            note += ": lifts below the published base (a town gondola)"
        rows.append(_row(fig, label, pub, m["value"], "warn" if bad else "pass", note, "m"))
    pub, m = figs.get("vertical"), mine.get("vertical")
    if pub and m:
        d = m["value"] - pub["value"]
        off = abs(d) > VERTICAL_WARN[0] and abs(d) > VERTICAL_WARN[1] * pub["value"]
        note = f"{d:+.0f} m ({d / pub['value']:+.0%})"
        if off and d < 0:
            note += ": part of the resort missing, or the wrong area"
        elif off:
            note += ": the pack's lifts reach below the published base or above its summit"
        rows.append(_row("vertical", "Vertical", pub, m["value"], "warn" if off and d < 0 else "pass", note, "m"))
    pub, m = figs.get("lifts"), mine["lifts"]
    if pub:
        near = lambda v: abs(v - pub["value"]) <= max(LIFTS_WARN[0], LIFTS_WARN[1] * pub["value"])
        if near(m["value"]):
            st, note = "pass", f"every lift ({m['chairs']} chairs and gondolas)"
        elif near(m["chairs"]):
            st, note = "pass", f"{m['chairs']} chairs and gondolas match: the published count leaves out surface lifts ({m['value']} in all)"
        else:
            st, note = "warn", (f"{m['value']} lifts, {m['chairs']} of them chairs and gondolas: " +
                                ("lifts missing from OSM or part of the resort left out" if m["value"] < pub["value"]
                                 else "a neighbour's lifts in the pack, or the wrong area"))
        rows.append(_row("lifts", "Lifts", pub, m["value"], st, note))
    pub, m = figs.get("runs"), mine["runs"]
    trails = None
    if (rec or {}).get("trails"):
        t = match_trails(rec["trails"]["names"], m["names"])
        t["source"], t["published"] = rec["trails"]["source"], len(rec["trails"]["names"])
        trails = t
    if pub or trails:
        detail = f"{m['value']} run names over {m['segments']} segments, {m['unnamed']} unnamed"
        st = "pass"
        if pub:
            ratio = m["value"] / pub["value"] if pub["value"] else 0
            if not RUNS_RATIO[0] <= ratio <= RUNS_RATIO[1]:
                st = "warn"
            detail += f"; {ratio:.0%} of the published count"
        if trails:
            share = len(trails["matched"]) / trails["published"] if trails["published"] else 1.0
            if share < TRAILS_MATCHED:
                st = "warn"
            detail += (f"; of the {trails['published']} trails on {trails['source']}, {len(trails['matched'])} have an OSM "
                       f"run and {len(trails['unmatched'])} have none (listed below: not mapped in OSM, or named "
                       f"differently); {len(trails['osm_only'])} OSM names are not on the list")
        elif pub and st == "warn" and ratio < 1:
            detail += ": runs not mapped in OSM, mapped with no name, or part of the resort left out"
        rows.append(_row("runs", "Runs", pub or {"value": trails["published"], "source": trails["source"]},
                         m["value"], st, detail))
    pub, m = figs.get("area"), mine.get("area")
    if pub and m:
        ratio = m["value"] / pub["value"] if pub["value"] else 0
        bad = not AREA_RATIO[0] <= ratio <= AREA_RATIO[1]
        lifts_ok = any(r["figure"] == "lifts" and r["status"] == "pass" for r in rows)
        why = ""
        if bad and ratio < 1:
            # Heavenly: every lift there, its 4,800 acres mostly woods and canyons OSM maps as single lines
            why = (": the resort counts more ground than its runs cover (glades, bowls and trees mapped as lines, or "
                   "not at all); with the lifts all there, likely no part missing" if lifts_ok else
                   ": part of the resort missing")
        elif bad:
            why = ": a neighbour in the pack"
        rows.append(_row("area", "Skiable area", pub, m["value"], "warn" if bad else "pass",
                         f"{m['how']}, {ratio:.2f} times the published{why}", "km2"))
    return rows, trails


def load(slug, resorts=None):
    p = published_path(slug, resorts)
    if not os.path.isfile(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write(rec, slug, resorts=None):
    p = published_path(slug, resorts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rec, f, indent=1, ensure_ascii=False)
        f.write("\n")
    return p


def ski_area_features(cache=None):
    import resort
    cache = cache or os.environ.get("SBA_INDEX_DIR") or os.path.join(paths.raw_root(), "_index")
    return resort.load_json(resort.index_file(cache, "ski_areas.geojson"))["features"]


def refresh(cfg, raw=None, resorts=None, web=None, features=None, cache=None):
    """gather and write the record, keeping hand figures and an earlier trail list; returns it"""
    rec = gather(cfg, features if features is not None else ski_area_features(cache), web or Web(),
                 raw=raw, old=load(cfg["slug"], resorts))
    write(rec, cfg["slug"], resorts)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("slug")
    ap.add_argument("--raw", help="the resort's raw folder, for the trail list in grooming/ (default <raw root>/<slug>)")
    ap.add_argument("--cache", help="folder of the cached OpenSkiData index (default _index/ in the raw root)")
    ap.add_argument("--resorts", help="the folder holding every resort's folder (default resorts/)")
    a = ap.parse_args(argv)
    with open(paths.config_path(a.slug, a.resorts), encoding="utf-8") as f:
        cfg = json.load(f)
    raw = a.raw or os.path.join(paths.raw_root(), a.slug)
    rec = refresh(cfg, raw=raw, resorts=a.resorts, cache=a.cache)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps({k: v for k, v in rec.items() if k != "trails"}, indent=1, ensure_ascii=False))
    if rec.get("trails"):
        print(f"trails: {len(rec['trails']['names'])} from {rec['trails']['source']}")
    print(f"wrote {published_path(a.slug, a.resorts)}")


if __name__ == "__main__":
    main()
