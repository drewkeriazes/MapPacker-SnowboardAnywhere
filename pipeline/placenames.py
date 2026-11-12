"""FEAT-235: place names for any US resort, not only Colorado's.

Peaks: USGS GNIS domestic names, one file per state (`DomesticNames_<ST>_Text.zip`, public domain). The far ring is
200 km across, so a resort near a state line takes the neighbours' files too: `states_for` picks every state whose
box meets the far ring's (the boxes come from the Census 2023 cartographic boundary file, cb_2023_us_state_20m, a
little wider than the states themselves, so a neighbour is never missed; an extra file costs a megabyte or two).
`resort.py plan` records the list in the config (`names.states`), `gen_manifest.py` adds the downloads to
`names/`, and `build_pack.py` reads them: GNIS summits join the OSM peaks in features.json.

Towns: the Census Gazetteer's places (every incorporated place and census designated place, with its GNIS id and
centre point; `<year>_Gaz_place_national.zip`) sized by the Census population estimates (`sub-est<year>.csv`,
incorporated places only). They replace the Overpass `places_far` query, which queued for minutes on every host
and was dropped. Sized as OSM sizes `place`: a city from 100,000 people, a town from 10,000, else a village (a CDP
has no estimate and counts as a village).

Pure helpers; tested offline in tests/test_placenames.py.
"""
import csv, glob, io, json, math, os, re, zipfile

GNIS_URL = "https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/DomesticNames/DomesticNames_{st}_Text.zip"
CENSUS_YEAR = 2024
GAZ_URL = (f"https://www2.census.gov/geo/docs/maps-data/data/gazetteer/{CENSUS_YEAR}_Gazetteer/"
           f"{CENSUS_YEAR}_Gaz_place_national.zip")
POP_URL = (f"https://www2.census.gov/programs-surveys/popest/datasets/2020-{CENSUS_YEAR}/cities/totals/"
           f"sub-est{CENSUS_YEAR}.csv")
DIR = "names"
CITY_POP, TOWN_POP = 100_000, 10_000
PAD_DEG = 0.02              # the 1:20,000,000 state outlines are generalised; grow each box a little

# state: (FIPS, name, lon0, lat0, lon1, lat1), from cb_2023_us_state_20m (Alaska west of the antimeridian only)
STATES = {
    "AK": ("02", "Alaska", -179.17, 51.22, -129.98, 71.35),
    "AL": ("01", "Alabama", -88.47, 30.23, -84.89, 35.01),
    "AR": ("05", "Arkansas", -94.62, 33.00, -89.65, 36.50),
    "AZ": ("04", "Arizona", -114.81, 31.33, -109.05, 37.00),
    "CA": ("06", "California", -124.41, 32.53, -114.14, 42.01),
    "CO": ("08", "Colorado", -109.06, 36.99, -102.04, 41.00),
    "CT": ("09", "Connecticut", -73.73, 40.99, -71.79, 42.05),
    "DC": ("11", "District of Columbia", -77.12, 38.79, -76.91, 39.00),
    "DE": ("10", "Delaware", -75.79, 38.45, -75.05, 39.84),
    "FL": ("12", "Florida", -87.63, 24.50, -80.03, 31.00),
    "GA": ("13", "Georgia", -85.61, 30.36, -80.84, 35.00),
    "HI": ("15", "Hawaii", -160.25, 18.92, -154.81, 22.23),
    "IA": ("19", "Iowa", -96.62, 40.38, -90.14, 43.50),
    "ID": ("16", "Idaho", -117.24, 41.99, -111.04, 49.00),
    "IL": ("17", "Illinois", -91.51, 36.98, -87.50, 42.51),
    "IN": ("18", "Indiana", -88.07, 37.77, -84.79, 41.76),
    "KS": ("20", "Kansas", -102.05, 36.99, -94.59, 40.00),
    "KY": ("21", "Kentucky", -89.57, 36.50, -81.97, 39.15),
    "LA": ("22", "Louisiana", -94.04, 28.93, -89.01, 33.02),
    "MA": ("25", "Massachusetts", -73.51, 41.24, -69.93, 42.88),
    "MD": ("24", "Maryland", -79.49, 37.92, -75.05, 39.72),
    "ME": ("23", "Maine", -71.08, 43.06, -66.95, 47.46),
    "MI": ("26", "Michigan", -90.42, 41.70, -82.42, 48.21),
    "MN": ("27", "Minnesota", -97.23, 43.50, -89.49, 49.38),
    "MO": ("29", "Missouri", -95.77, 36.00, -89.10, 40.61),
    "MS": ("28", "Mississippi", -91.64, 30.18, -88.10, 35.00),
    "MT": ("30", "Montana", -116.05, 44.38, -104.04, 49.00),
    "NC": ("37", "North Carolina", -84.32, 33.85, -75.46, 36.59),
    "ND": ("38", "North Dakota", -104.05, 45.94, -96.55, 49.00),
    "NE": ("31", "Nebraska", -104.05, 40.00, -95.31, 43.00),
    "NH": ("33", "New Hampshire", -72.56, 42.70, -70.70, 45.31),
    "NJ": ("34", "New Jersey", -75.56, 38.93, -73.89, 41.36),
    "NM": ("35", "New Mexico", -109.05, 31.33, -103.00, 37.00),
    "NV": ("32", "Nevada", -120.01, 35.00, -114.04, 42.00),
    "NY": ("36", "New York", -79.76, 40.50, -71.86, 45.01),
    "OH": ("39", "Ohio", -84.82, 38.40, -80.52, 41.98),
    "OK": ("40", "Oklahoma", -103.00, 33.62, -94.43, 37.00),
    "OR": ("41", "Oregon", -124.55, 41.99, -116.46, 46.27),
    "PA": ("42", "Pennsylvania", -80.52, 39.72, -74.69, 42.27),
    "PR": ("72", "Puerto Rico", -67.96, 17.91, -65.22, 18.51),
    "RI": ("44", "Rhode Island", -71.86, 41.15, -71.12, 42.02),
    "SC": ("45", "South Carolina", -83.35, 32.03, -78.54, 35.20),
    "SD": ("46", "South Dakota", -104.06, 42.48, -96.44, 45.95),
    "TN": ("47", "Tennessee", -90.31, 34.98, -81.65, 36.68),
    "TX": ("48", "Texas", -106.64, 25.84, -93.53, 36.50),
    "UT": ("49", "Utah", -114.05, 37.00, -109.04, 42.00),
    "VA": ("51", "Virginia", -83.68, 36.54, -75.24, 39.47),
    "VT": ("50", "Vermont", -73.44, 42.73, -71.49, 45.01),
    "WA": ("53", "Washington", -124.73, 45.54, -116.92, 49.00),
    "WI": ("55", "Wisconsin", -92.89, 42.49, -86.81, 47.05),
    "WV": ("54", "West Virginia", -82.63, 37.20, -77.72, 40.64),
    "WY": ("56", "Wyoming", -111.06, 41.00, -104.05, 45.01),
}


def far_box_ll(cfg):
    """(lon0, lat0, lon1, lat1) of the far ring: the config's origin +- far_ring.size_m / 2, in its crs"""
    from pyproj import Transformer
    to_ll = Transformer.from_crs(cfg["crs"], "EPSG:4326", always_xy=True)
    ox, oy = cfg["origin"]; h = cfg["far_ring"]["size_m"] / 2
    cs = [to_ll.transform(ox + sx * h, oy + sy * h) for sx in (-1, 1) for sy in (-1, 1)]
    return min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs)


def primary_state(cfg):
    """the resort's own state code: OpenSkiData's ISO 3166-2 (US-OH), else the config's region by name"""
    iso = (cfg.get("openskidata") or {}).get("iso3166_2") or ""
    if iso.startswith("US-") and iso[3:] in STATES:
        return iso[3:]
    region = (cfg.get("region") or "").strip().lower()
    for st, (_, name, *_b) in STATES.items():
        if name.lower() == region:
            return st
    return None


def states_for(box_ll, primary=None):
    """the states whose box meets `box_ll` (lon0, lat0, lon1, lat1), the resort's own first"""
    lo0, la0, lo1, la1 = box_ll
    hit = sorted(st for st, (_, _, a0, b0, a1, b1) in STATES.items()
                 if a0 - PAD_DEG < lo1 and a1 + PAD_DEG > lo0 and b0 - PAD_DEG < la1 and b1 + PAD_DEG > la0)
    if primary in hit:
        hit.remove(primary); hit.insert(0, primary)
    return hit


def plan_names(cfg):
    """the config's `names` block (resort.py plan): the GNIS states to fetch, or None outside the US"""
    if cfg.get("country", "US") != "US" or not all(k in cfg for k in ("crs", "origin", "far_ring")):
        return None
    sts = states_for(far_box_ll(cfg), primary_state(cfg))
    return {"states": sts, "source": "USGS GNIS", "towns": f"US Census {CENSUS_YEAR} Gazetteer and population estimates"} if sts else None


def states_of(cfg):
    """the GNIS states for a config: its `names.states`, else worked out from the far ring (configs planned before
    FEAT-235)"""
    n = cfg.get("names")
    if n and n.get("states"):
        return list(n["states"])
    p = plan_names(cfg)
    return p["states"] if p else []


def manifest_items(cfg):
    """the downloads: one GNIS file per state, the national Gazetteer and population files -> [{url, path}]"""
    sts = states_of(cfg)
    if not sts:
        return []
    items = [{"url": GNIS_URL.format(st=st), "path": f"{DIR}/DomesticNames_{st}_Text.zip"} for st in sts]
    items.append({"url": GAZ_URL, "path": f"{DIR}/{os.path.basename(GAZ_URL)}"})
    items.append({"url": POP_URL, "path": f"{DIR}/{os.path.basename(POP_URL)}"})
    return items


def inside(box_ll, lon, lat):
    return box_ll[0] <= lon <= box_ll[2] and box_ll[1] <= lat <= box_ll[3]


def read_gnis_rows(f):
    """GNIS DomesticNames rows (pipe separated, a BOM on the header) from a text stream"""
    for row in csv.DictReader(f, delimiter="|"):
        try:
            lat, lon = float(row["prim_lat_dec"]), float(row["prim_long_dec"])
        except (KeyError, TypeError, ValueError):
            continue
        if lat == 0.0 and lon == 0.0:
            continue
        yield {"id": int(row["feature_id"]), "name": row["feature_name"], "class": row["feature_class"],
               "lat": lat, "lon": lon, "state": row.get("state_name")}


def load_gnis(raw, box_ll, classes=("Summit",)):
    """GNIS features of `classes` inside `box_ll` from <raw>/names/: every DomesticNames_<ST>_Text.zip, and
    gnis.json (extract_osm.py's cut, Vail). A feature listed by two states' files is kept once. -> ([features],
    [states read])"""
    d = os.path.join(raw, DIR)
    seen, out, states = set(), [], []
    for z in sorted(glob.glob(os.path.join(d, "DomesticNames_*_Text.zip"))):
        states.append(os.path.basename(z).split("_")[1])
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                if not (member.lower().endswith(".txt") and "domesticnames" in member.lower()):
                    continue
                with zf.open(member) as fb:
                    for f in read_gnis_rows(io.TextIOWrapper(fb, encoding="utf-8-sig", errors="replace")):
                        if f["class"] in classes and f["id"] not in seen and inside(box_ll, f["lon"], f["lat"]):
                            seen.add(f["id"]); out.append(f)
    j = os.path.join(d, "gnis.json")
    if os.path.isfile(j):
        with open(j, encoding="utf-8") as fh:
            doc = json.load(fh)
        states.append(doc.get("source", "gnis.json").split("_")[-1])
        for f in doc.get("features", []):
            if f.get("class") in classes and f["id"] not in seen and inside(box_ll, f["lon"], f["lat"]):
                seen.add(f["id"]); out.append(f)
    return out, states


LSAD = re.compile(r"\s+(city and borough|consolidated government \(balance\)|metropolitan government \(balance\)|"
                  r"unified government \(balance\)|metro government \(balance\)|urban county|city|town|village|"
                  r"borough|CDP|municipality|plantation|corporation|comunidad|zona urbana)$")


def place_name(name):
    """"Akron city" -> "Akron", "Big Sky CDP" -> "Big Sky" """
    return LSAD.sub("", name.strip()).strip()


def kind_for(pop):
    if pop is None:
        return "village"
    return "city" if pop >= CITY_POP else "town" if pop >= TOWN_POP else "village"


def read_population(f):
    """{GEOID (state + place FIPS): (name, population)} for incorporated places (summary level 162) from the Census
    population estimates CSV; the latest POPESTIMATE<year> column"""
    rd = csv.DictReader(f)
    col = sorted(c for c in rd.fieldnames if re.fullmatch(r"POPESTIMATE\d{4}", c))[-1]
    out = {}
    for row in rd:
        if row.get("SUMLEV") != "162":
            continue
        try:
            out[row["STATE"] + row["PLACE"]] = (row["NAME"], int(row[col]))
        except (KeyError, ValueError):
            continue
    return out


def read_gazetteer(f):
    """Census Gazetteer place rows (tab separated, padded header) -> [{geoid, gnis, name, lat, lon}]"""
    rd = csv.reader(f, delimiter="\t")
    head = [h.strip() for h in next(rd)]
    ix = {h: i for i, h in enumerate(head)}
    out = []
    for row in rd:
        try:
            out.append({"geoid": row[ix["GEOID"]].strip(), "gnis": int(row[ix["ANSICODE"]]),
                        "name": row[ix["NAME"]].strip(), "lat": float(row[ix["INTPTLAT"]]),
                        "lon": float(row[ix["INTPTLONG"]])})
        except (IndexError, KeyError, ValueError):
            continue
    return out


def load_towns(raw, box_ll):
    """towns inside `box_ll` from <raw>/names/: the Gazetteer's places, sized by the population estimates ->
    [{name, kind, lat, lon, pop}] (pop None for a CDP); [] when the files are missing"""
    d = os.path.join(raw, DIR)
    gz = sorted(glob.glob(os.path.join(d, "*_Gaz_place_national.zip")))
    pp = sorted(glob.glob(os.path.join(d, "sub-est*.csv")))
    if not gz:
        return []
    with zipfile.ZipFile(gz[-1]) as zf:
        member = next(m for m in zf.namelist() if m.lower().endswith(".txt"))
        with zf.open(member) as fb:
            places = read_gazetteer(io.TextIOWrapper(fb, encoding="utf-8", errors="replace"))
    pop = {}
    if pp:
        with open(pp[-1], encoding="latin-1", newline="") as fh:
            pop = read_population(fh)
    out = []
    for p in places:
        if not inside(box_ll, p["lon"], p["lat"]):
            continue
        name, n = pop.get(p["geoid"], (p["name"], None))
        out.append({"name": place_name(name), "kind": kind_for(n), "lat": p["lat"], "lon": p["lon"], "pop": n})
    return out


def merge_peaks(osm_peaks, gnis_peaks, same_name_m=1500.0, any_m=150.0):
    """the GNIS summits OSM lacks: a GNIS peak is dropped when an OSM peak of the same name is within
    `same_name_m`, or any OSM peak within `any_m`. Both lists hold {name, x, y, ...} in local metres."""
    def key(s): return re.sub(r"[^a-z0-9]", "", s.lower())
    cell = 2000.0
    grid = {}
    for p in osm_peaks:
        grid.setdefault((int(p["x"] // cell), int(p["y"] // cell)), []).append(p)
    out = []
    for g in gnis_peaks:
        cx, cy = int(g["x"] // cell), int(g["y"] // cell)
        dup = False
        for i in (-1, 0, 1):
            for j in (-1, 0, 1):
                for p in grid.get((cx + i, cy + j), []):
                    dd = math.hypot(p["x"] - g["x"], p["y"] - g["y"])
                    if dd < any_m or (dd < same_name_m and key(p["name"]) == key(g["name"])):
                        dup = True
        if not dup:
            out.append(g)
    return out
