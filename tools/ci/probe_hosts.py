"""Probe every data host a pack build calls (FEAT-245): one small request each, before the build job spends hours.

    python tools/ci/probe_hosts.py [--only NAME] [--timeout SECONDS]

Each probe fetches one small item from a host the pipeline uses, with the URL the pipeline itself builds where it
can (constants imported from pipeline/, Vail's dataset and NAIP item for the per-resort ones), and checks what came
back (a TIFF, a WebP tile, JSON with the fields the pipeline reads, a 200 or 206 on a byte range of a big file).
Every probe is tried twice. A host with mirrors (Overpass) passes when any mirror passes, tried in order: the next mirror
only when the ones before it failed (each gets its own row). web.archive.org is only for grooming (fetch_grooming.py), so it warns instead of failing.

Prints a table, appends it to $GITHUB_STEP_SUMMARY as Markdown when that is set, and exits 1 when a required host
failed. Uses curl (on ubuntu-latest and Windows 10+): Python's ssl rejects web.archive.org's chain (resort.py
curl_json).
"""
import argparse, json, os, subprocess, sys, tempfile, time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote, urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "pipeline"))
import paths  # noqa: E402
import placenames  # noqa: E402
import resort  # noqa: E402

UA = resort.UA
MAX_BODY = 64 * 1024           # bytes of the reply kept for the check
RANGE = "0-1023"               # big files (WorldCover, ETH canopy, GNIS, Census): the first KB only

# ---------------------------------------------------------------- checks: (http code, body bytes) -> (ok, detail)
# Pure, so the tests run them without the network.


def _json(body: bytes):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None


def snippet(body: bytes, n: int = 80) -> str:
    return " ".join(body[:n].decode("utf-8", "replace").split())


def http_ok(code: int, body: bytes):
    return (code == 200, f"HTTP {code}")


def range_ok(code: int, body: bytes):
    """a byte range of a big file: 206 (or 200 from a server that ignores ranges) with something in it"""
    if code not in (200, 206):
        return False, f"HTTP {code}"
    return (len(body) > 0, f"HTTP {code}, {len(body)} bytes" if body else f"HTTP {code}, empty")


def json_with(*keys: str) -> Callable:
    """HTTP 200 and a JSON object holding every one of `keys`"""
    def check(code: int, body: bytes):
        if code != 200:
            return False, f"HTTP {code}: {snippet(body)}"
        d = _json(body)
        if not isinstance(d, dict):
            return False, f"not JSON: {snippet(body)}"
        missing = [k for k in keys if k not in d]
        if missing:
            return False, f"JSON without {', '.join(missing)}: {snippet(body)}"
        return True, f"HTTP 200, JSON with {', '.join(keys)}" if keys else "HTTP 200, JSON"
    return check


def any_json(code: int, body: bytes):
    """LFPS: any JSON reply, an error about the job id included, means the service is up; HTML means it is down
    (maintenance, fetch_landfire.mjs getJson). An unknown job id is HTTP 500 with {"message": "JobId not found.",
    "success": false}, so the code alone says nothing: the reply is JSON from the API, or it is not."""
    d = _json(body)
    if isinstance(d, dict) and ("success" in d or "message" in d):
        return True, f"HTTP {code}, LFPS JSON"
    if d is None or code >= 500:
        return False, f"HTTP {code}, not LFPS JSON: {snippet(body)}"
    return True, f"HTTP {code}, JSON"


def tiff(code: int, body: bytes):
    if code != 200:
        return False, f"HTTP {code}: {snippet(body)}"
    if body[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        return True, f"HTTP 200, TIFF {len(body)} bytes"
    return False, f"not a TIFF: {snippet(body)}"


def webp(code: int, body: bytes):
    if code != 200:
        return False, f"HTTP {code}"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return True, f"HTTP 200, WebP {len(body)} bytes"
    return False, f"not a WebP: {snippet(body)}"


def overpass(code: int, body: bytes):
    """Overpass answers 200 with an HTML or remark body when it fails (fetch.ps1 checks the same two words)"""
    if code != 200:
        return False, f"HTTP {code}: {snippet(body)}"
    if b'"elements"' in body or b'"version"' in body:
        return True, "HTTP 200, Overpass JSON"
    return False, f"error body: {snippet(body)}"


def cdx(code: int, body: bytes):
    """the Internet Archive CDX API: a JSON list (header row first)"""
    if code != 200:
        return False, f"HTTP {code}: {snippet(body)}"
    return (isinstance(_json(body), list), "HTTP 200, CDX JSON" if isinstance(_json(body), list)
            else f"not JSON: {snippet(body)}")


# ---------------------------------------------------------------- the probes


@dataclass
class Probe:
    name: str                  # row name
    host: str                  # the host group: a host passes when any of its probes passes (mirrors)
    url: str
    check: Callable
    range: bool = False        # ask for the first KB only
    required: bool = True      # False: warn, do not fail


def vail():
    """Vail's config: the per-resort probes (EPT dataset, NAIP item) use a resort every build of the pipeline has
    fetched"""
    with open(paths.config_path("vail"), encoding="utf-8") as f:
        return json.load(f)


def probes() -> list:
    cfg = vail()
    epsg = cfg["crs"].split(":")[1]
    x0, y0 = cfg["utm_bbox"][:2]
    naip_item = next(iter(cfg["naip"]["item_bboxes_ll"]))
    # gen_manifest.py builds these inline (EXPORT, CROP, WC, ETH, the Overpass URLs); kept here in the same form
    export = ("https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?" +
              urlencode({"bbox": f"{x0},{y0},{x0 + 16},{y0 + 16}", "bboxSR": epsg, "imageSR": epsg, "size": "16,16",
                         "format": "tiff", "pixelType": "F32", "noData": "-9999",
                         "interpolation": "RSP_BilinearInterpolation", "f": "image"}))
    # a 64 m corner of the first NAIP crop Vail's manifest fetches, 100 m in from its edge
    with open(os.path.join(paths.MANIFESTS, "vail.json"), encoding="utf-8") as f:
        first = next(it for it in json.load(f)["items"] if it["path"].startswith("naip1m/"))
    naip_item = first["meta"]["item"]
    cx, cy = first["meta"]["bbox"][0] + 100, first["meta"]["bbox"][1] + 100
    crop = (f"https://planetarycomputer.microsoft.com/api/data/v1/item/crop/{cx},{cy},{cx + 64},{cy + 64}/64x64.tif?" +
            urlencode({"collection": "naip", "item": naip_item, "assets": "image", "asset_bidx": "image|1,2,3,4",
                       "coord_crs": cfg["crs"], "dst_crs": cfg["crs"], "resampling": "average", "max_size": "4000"}))
    tile = "N39W108"           # the WorldCover / ETH 3 degree tile over Vail
    q = quote("[out:json][timeout:25];node(1);out;", safe="")
    box_ll = "-106.40,39.60,-106.39,39.61"
    tnm = "https://tnmaccess.nationalmap.gov/api/v1/products?" + urlencode(
        {"datasets": "Digital Elevation Model (DEM) 1 meter", "bbox": box_ll, "max": 1})
    cdx_url = "https://web.archive.org/cdx/search/cdx?" + urlencode(
        {"url": "vail.com", "output": "json", "filter": "statuscode:200", "limit": 1})
    return [
        Probe("3DEP ImageServer exportImage", "elevation.nationalmap.gov", export, tiff),
        Probe("TNM Access products", "tnmaccess.nationalmap.gov", tnm, json_with("items")),
        Probe("3DEP work units (WESM.csv)", "prd-tnm.s3.amazonaws.com", resort.INDEXES["wesm.csv"], range_ok,
              range=True),
        Probe("usgs-lidar-public EPT", "s3-us-west-2.amazonaws.com", cfg["lidar"]["ept"] + "ept.json",
              json_with("bounds", "schema")),
        Probe("Entwine boundaries", "usgs.entwine.io", resort.INDEXES["entwine_resources.geojson"], range_ok, range=True),
        Probe("Planetary Computer STAC naip", "planetarycomputer.microsoft.com",
              "https://planetarycomputer.microsoft.com/api/stac/v1/collections/naip", json_with("id", "extent")),
        Probe("Planetary Computer NAIP crop", "planetarycomputer.microsoft.com", crop, tiff),
        Probe("Mapterhorn tile", "tiles.mapterhorn.com", resort.MAPTERHORN_TILE.format(z=0, x=0, y=0), webp),
        Probe("Mapterhorn attribution", "download.mapterhorn.com", resort.INDEXES["mapterhorn_attribution.json"], http_ok),
        Probe("Overpass", "Overpass", "https://overpass-api.de/api/interpreter?data=" + q, overpass),
        Probe("Overpass mirror private.coffee", "Overpass", "https://overpass.private.coffee/api/interpreter?data=" + q,
              overpass),
        Probe("Overpass mirror lz4", "Overpass", "https://lz4.overpass-api.de/api/interpreter?data=" + q, overpass),
        Probe("LANDFIRE LFPS", "lfps.usgs.gov", "https://lfps.usgs.gov/api/job/status?JobId=probe", any_json),
        Probe("ESA WorldCover", "esa-worldcover.s3.eu-central-1.amazonaws.com",
              f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif",
              range_ok, range=True),
        Probe("ETH canopy height", "libdrive.ethz.ch",
              "https://libdrive.ethz.ch/index.php/s/cO8or7iOe5dT2Rt/download?path=%2F3deg_cogs&files="
              f"ETH_GlobalCanopyHeight_10m_2020_{tile}_Map.tif", range_ok, range=True),
        Probe("USGS GNIS names", "prd-tnm.s3.amazonaws.com", placenames.GNIS_URL.format(st="CO"), range_ok, range=True),
        Probe("Census gazetteer", "www2.census.gov", placenames.GAZ_URL, range_ok, range=True),
        Probe("Census population", "www2.census.gov", placenames.POP_URL, range_ok, range=True),
        Probe("OpenSkiData ski areas", "tiles.openskimap.org", resort.INDEXES["ski_areas.geojson"], range_ok, range=True),
        Probe("Geofabrik index", "download.geofabrik.de", resort.INDEXES["geofabrik_index.json"], range_ok, range=True),
        Probe("Internet Archive CDX (grooming)", "web.archive.org", cdx_url, cdx, required=False),
    ]


# ---------------------------------------------------------------- running


def curl(url: str, timeout: int, byte_range: bool) -> tuple:
    """(http code, first MAX_BODY bytes) by curl; code 0 when curl itself failed (DNS, TLS, timeout)"""
    fd, tmp = tempfile.mkstemp(prefix="probe-")
    os.close(fd)
    try:
        cmd = ["curl", "-sS", "-L", "-m", str(timeout), "-A", UA, "-o", tmp, "-w", "%{http_code}"]
        if byte_range:
            # a server that ignores the range would send the whole file (hundreds of MB): stop at 1 MB
            cmd += ["-r", RANGE, "--max-filesize", str(1 << 20)]
        p = subprocess.run(cmd + [url], capture_output=True, text=True)
        code = int(p.stdout.strip() or 0) if p.stdout.strip().isdigit() else 0
        with open(tmp, "rb") as f:
            body = f.read(MAX_BODY)
        if p.returncode and not code:
            return 0, (p.stderr.strip() or f"curl exited {p.returncode}").encode()
        if p.returncode == 63:   # --max-filesize: the server ignored the range, but it answered
            return code or 200, body or b"(range ignored)"
        return code, body
    finally:
        os.remove(tmp)


def run_probe(p: Probe, fetch: Callable, tries: int = 2) -> tuple:
    """(ok, detail, seconds) of one probe, tried up to `tries` times"""
    detail = ""
    t0 = time.time()
    for k in range(tries):
        code, body = fetch(p.url, p.range)
        ok, detail = p.check(code, body) if code else (False, snippet(body, 160))
        if ok:
            break
        if k + 1 < tries:
            time.sleep(20)     # Overpass "at capacity" and the like often pass in seconds
    return ok, detail, time.time() - t0


def verdicts(results: list) -> dict:
    """{host: ok} from [(probe, ok, detail, s)]: a host passes when any of its probes does (mirrors)"""
    out = {}
    for p, ok, _, _ in results:
        out[p.host] = out.get(p.host, False) or bool(ok)
    return out


def failed_hosts(results: list) -> tuple:
    """(required hosts that failed, warn-only hosts that failed)"""
    v = verdicts(results)
    req = {p.host: p.required for p, *_ in results}
    bad = sorted(h for h, ok in v.items() if not ok and req[h])
    warn = sorted(h for h, ok in v.items() if not ok and not req[h])
    return bad, warn


def status(p: Probe, ok, host_ok: bool) -> str:
    if ok is None:
        return "not tried (host ok)"
    if ok:
        return "ok"
    if host_ok:
        return "down (mirror ok)"
    return "FAIL" if p.required else "warn"


def table(results: list, markdown: bool = False) -> str:
    v = verdicts(results)
    rows = [(p.name, status(p, ok, v[p.host]), f"{s:.1f} s", detail) for p, ok, detail, s in results]
    if markdown:
        lines = ["| host | result | time | detail |", "|---|---|---|---|"]
        lines += ["| " + " | ".join(c.replace("|", "\\|") for c in r) + " |" for r in rows]
        return "\n".join(lines)
    w = [max(len(r[i]) for r in rows) for i in range(3)]
    return "\n".join(f"{r[0]:<{w[0]}}  {r[1]:<{w[1]}}  {r[2]:>{w[2]}}  {r[3]}" for r in rows)


def main(argv=None, fetch: Callable | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", action="append", help="probe only rows or hosts whose name contains this (repeatable)")
    ap.add_argument("--timeout", type=int, default=60, help="seconds per request (default 60)")
    a = ap.parse_args(argv)
    fetch = fetch or (lambda url, rng: curl(url, a.timeout, rng))
    todo = probes()
    if a.only:
        keys = [o.lower() for o in a.only]
        todo = [p for p in todo if any(k in p.name.lower() or k in p.host.lower() for k in keys)]
        if not todo:
            print(f"no probe matches {a.only}")
            return 2
    results = []
    for p in todo:
        if verdicts(results).get(p.host):     # a mirror of a host that already answered: not needed
            results.append((p, None, "", 0.0))
            continue
        ok, detail, s = run_probe(p, fetch)
        results.append((p, ok, detail, s))
        print(f"{'ok  ' if ok else 'FAIL'} {p.name}: {detail}", flush=True)
    bad, warn = failed_hosts(results)
    print("\n" + table(results))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Data hosts\n\n" + table(results, markdown=True) + "\n\n")
            if bad:
                f.write(f"**Unreachable:** {', '.join(bad)}. The build needs every one of them.\n\n")
            if warn:
                f.write(f"Warning: {', '.join(warn)} unreachable (grooming only).\n\n")
    if warn:
        print(f"\nwarning: {', '.join(warn)} unreachable (only grooming uses it)")
    if bad:
        print(f"\nunreachable: {', '.join(bad)}")
        return 1
    print(f"\nevery host answered ({len(results)} probes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
