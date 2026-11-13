#!/usr/bin/env python3
"""FEAT-175 step 3: one command builds a resort, from its config to a scored pack.

    python pipeline/build_resort.py <slug> [<raw_dir>] [<out_dir>] [--from <stage>] [--stop-after <stage>]
                                    [--force <stage>]... [--email <address>] [--dry-run]

`raw_dir` is the resort's raw folder (default <raw root>/<slug>, the raw root being SBA_RAW_ROOT or raw/ in the main
checkout; its last folder must be the slug, as fetch.ps1 writes <RawDir>/<slug>), `out_dir` the pack (default
packs/<slug>). The config is resorts/<slug>/<slug>.json, the manifest manifests/<slug>.json (pipeline/paths.py). Stages:

  nodes     ept_select.py: the EPT node lists (resort.py plan writes them too)
  manifest  gen_manifest.py: the download list
  fetch     fetch.ps1: everything in the manifest (resumable; stops when an item failed)
  landfire  fetch_landfire.mjs EVT, EVC, EVH (US only; the LFPS service wants an email: --email or LANDFIRE_EMAIL)
  grooming  fetch_grooming.py, when the config has a terrain_status_url
  build     build_pack.py (DEM, lidar, NAIP, masks, moguls, piste directions, AO, trees, far trees, cover)
  content   gen_content.py (FEAT-175 step 4): the default start and the main menu shots, from the pack
  attract   the game's tools/auto_attract.mjs: the menu still and ghost takes down the start run (on the GPU; skipped
            without a SnowboardAnywhere checkout that has the tool, paths.game_repo)
  spots     the game's tools/propose_spots.py: 10 proposed compare spots with game stills in the game checkout's
            docs/compare/<slug>/, for Drew to add Street View links (once, while the resort has no spots there)
  index     packs/index.json lists the pack
  published published.py (FEAT-293): the resort's published figures and trail list, resorts/<slug>/<slug>-published.json,
            for the report's line 21 (Wikidata and Wikipedia; when they can't be reached the line skips, the build
            goes on, and the next run tries again)
  report    pack_report.py: the DATA-022 scorecard (report.json, report.md in the pack)

A stage is skipped when its inputs have not changed since it last ran: each stage's input fingerprint is kept in
<raw_dir>/build_resort.json. The first run trusts outputs already on disk (node lists, manifest, LANDFIRE clips,
grooming reports, a pack built by a pipeline whose code matches this one) and records them, so an existing resort
is not walked, fetched or built again. A fetch from an older manifest (a new layer, a bigger box, MANIFEST_VERSION)
changes the manifest's fingerprint, so the fetch runs again and downloads only what is missing (DATA-022 item 3).
After the fetch and the build come the pack-build skill's checks: every raw layer present, the OSM files real
JSON and not an Overpass error page, the pack's meta.json in this pipeline's format.

FEAT-268: a config with `"raw_from": "<slug>"` builds on that resort's raw data and manifest (Ohio Hills on Boston
Mills'): its data stages are that resort's to run, and only its state file is in <raw root>/<slug>/. A
`"source_only": true` config (a relocate source such as Mad River Mountain) runs the data stages and stops there; a
pack whose relocate moves name a `source` checks that source's raw data before it builds, and rebuilds when it changes.

`--from` and `--stop-after` limit the run to a range of stages, `--force` runs a stage even when it looks done
(`--force all` runs every one), `--dry-run` prints what would run and why. Exit status: 0 done, 1 a stage failed
(the message says which and what to do), 2 bad arguments. `build_resort.cmd` is the launcher on Drew's PC.
"""
import argparse, glob, hashlib, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import paths  # noqa: E402

STAGES = ["nodes", "manifest", "fetch", "landfire", "grooming", "build", "content", "attract", "spots", "index", "published", "report"]
STATE = "build_resort.json"
LANDFIRE = (("EVT", "landfire"), ("EVC", os.path.join("landfire", "evc")), ("EVH", os.path.join("landfire", "evh")))
# raw layers build_pack.py needs (pack_report.py line 2): folder, and a file that must be in it
RAW_NEED = {"1 m DEM": ("dem1m", None), "10 m DEM": ("dem10m", None), "lidar (EPT)": ("ept", "ept.json"),
            "NAIP": ("naip1m", None), "Mapterhorn": ("mapterhorn", None)}
OSM_NEED = ("ski", "built", "natural", "peaks_far")


def raw_need(cfg):
    """RAW_NEED for this config's sources (FEAT-225): Mapterhorn tiles at the plan's zooms in place of the 3DEP
    DEMs, no lidar or NAIP when the config has none (the trees and masks then come from the land cover)"""
    import tiers
    need = dict(RAW_NEED)
    for key, name, block in (("dem", "1 m DEM", cfg.get("dem")), ("mid_ring", "10 m DEM", cfg.get("mid_ring"))):
        if tiers.uses_mapterhorn(block):
            del need[name]
            need[f"Mapterhorn z{block['zoom']} ({'resort box' if key == 'dem' else 'mid ring'})"] = (
                os.path.join("mapterhorn", str(block["zoom"])), None)
    if not cfg.get("lidar"):
        del need["lidar (EPT)"]
    if not cfg.get("naip"):
        del need["NAIP"]
    return need


class Failed(Exception):
    """a stage failed; the message says what to do"""


def sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True).encode())
    return h.hexdigest()[:16]


def file_sha(path) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return sha(f.read())


# pipeline/ paths that do not shape the pack: inputs of their own, or tools around the build (pipeline/resorts and
# pipeline/manifests are where the configs lived in SnowboardAnywhere: MOVED below fingerprints that tree)
# BUG-092: contract.py checks the format against the game (FEAT-239); prep_textures.py wrote the game's own textures
# and went back to the game (FEAT-242), so neither shapes a pack
NOT_BUILD = ("pipeline/tests", "pipeline/resorts", "pipeline/manifests", "pipeline/build_resort.py",
             "pipeline/resort.py", "pipeline/publish_pack.py", "pipeline/pack_report.py", "pipeline/contract.py",
             "pipeline/prep_textures.py", "pipeline/gen_content.py", "pipeline/published.py")
# FEAT-175 step 4: gen_content.py is its own stage (content) after the build, with its own fingerprint
NOT_BUILD_SPEC = [f":!{p}" for p in NOT_BUILD]


def pipeline_code(repo=REPO) -> str | None:
    """a fingerprint of the code that builds the pack: the git tree of pipeline/ without NOT_BUILD, plus the
    contents of any uncommitted change to it (an edited build script builds again); None outside git"""
    try:
        tree = subprocess.run(["git", "ls-tree", "-r", "HEAD", "pipeline/"], cwd=repo, capture_output=True,
                              text=True, check=True).stdout
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", "pipeline"]
                               + NOT_BUILD_SPEC, cwd=repo, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    keep = [l for l in tree.splitlines() if not l.split("\t")[-1].startswith(NOT_BUILD)]
    changed = sorted(l[3:].strip().strip('"') for l in dirty.splitlines() if l.strip())
    blobs = [(p, file_sha(os.path.join(repo, p))) for p in changed]
    return sha("\n".join(keep), blobs) + ("+dirty" if changed else "")


def same_code(commit, repo=REPO) -> bool:
    """True when the pipeline code at `commit` (a pack's meta.json `pipeline`) is this checkout's"""
    if not commit or commit.endswith("+dirty"):
        return False
    r = subprocess.run(["git", "diff", "--quiet", commit, "HEAD", "--", "pipeline"] + NOT_BUILD_SPEC, cwd=repo,
                       capture_output=True)
    return r.returncode == 0 and not (pipeline_code(repo) or "").endswith("+dirty")


def default_raw_root(repo=REPO) -> str:
    """where raw data lives: SBA_RAW_ROOT, else raw/ in the main checkout (paths.raw_root)"""
    return paths.raw_root(repo)


# FEAT-238: the pipeline moved here from SnowboardAnywhere at its commit 2a0b12f. A build recorded there (its
# fingerprint has the game's pipeline code and the game checkout's packs/<slug>) still counts here, so the packs
# built before the move are not built again: only while this checkout's build code is still the moved code
# (`code`, pipeline_code() right after the move; any later change to the build code builds again, as it should).
# `same`: later build code that differs from the moved code only in where it reads files, so it builds the same
# packs (FEAT-244, a folder per resort; BUG-092, FEAT-239's comment changes with contract.py and prep_textures.py
# out of the build code). build_resort.py is not build code, so listing one here does not change it.
MOVED = {"from": "SnowboardAnywhere 2a0b12f",
         "game_code": "80d9391a499fed00",
         "code": "1df239f500ce0922",
         "same": ("1cdddd3bff92c566", "16675d25ca2bb68f")}
MOVED_WHY = "built before the move to MapPacker (FEAT-238), inputs unchanged"


def run(cmd, cwd=REPO, env=None):
    """run a stage's command with its output on the console; -> exit code. `env` is added to the child's
    environment and never echoed (BUG-111: the LANDFIRE email goes this way, not as an argument)"""
    print("  $ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, env={**os.environ, **env} if env else None).returncode


class Resort:
    """the paths and config one run works on. `raw_dir` is the folder the data is in: with `raw_from` in the config
    (FEAT-268), that resort's, and the state file goes in <raw_dir>/../<slug>/ instead"""

    def __init__(self, slug, raw_dir, out_dir, resorts_dir=None, manifests_dir=None):
        self.slug, self.raw, self.out = slug, os.path.abspath(raw_dir), os.path.abspath(out_dir)
        self.resorts = resorts_dir or paths.RESORTS
        self.manifests = manifests_dir or paths.MANIFESTS
        self.cfg_path = paths.config_path(slug, self.resorts)
        with open(self.cfg_path, encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.data = self.cfg.get("raw_from") or slug
        self.man_path = os.path.join(self.manifests, f"{self.data}.json")
        self.state_path = os.path.join(self.raw if self.data == slug else
                                       os.path.join(os.path.dirname(self.raw), slug), STATE)
        try:
            with open(self.state_path, encoding="utf-8") as f:
                self.state = json.load(f)
        except (OSError, ValueError):
            self.state = {}

    def save(self):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.state, f, indent=1, sort_keys=True)
            f.write("\n")

    def node_files(self):
        L = self.cfg.get("lidar") or {}
        files = [s["nodes_file"] for s in [L] + list(L.get("extra", [])) if s.get("nodes_file")]
        if L.get("far"):
            files.append(L["far"]["nodes_file"])
        return [os.path.join(paths.resort_dir(self.data, self.resorts), f) for f in files]

    def sources(self):
        """FEAT-268: Resorts for the relocate sources the config's moves cut from (their raw folders beside this
        one's)"""
        slugs = list(dict.fromkeys(m["source"] for m in self.cfg.get("relocate") or [] if m.get("source")))
        for s in slugs:
            if not os.path.isfile(paths.config_path(s, self.resorts)):
                raise Failed(f"relocate source {s} has no config ({paths.config_path(s, self.resorts)})")
        return [Resort(s, os.path.join(os.path.dirname(self.raw), s), self.out, self.resorts, self.manifests)
                for s in slugs]


# ------------------------------------------------------------------------------------------------ stages
# Each stage: inputs(r) -> fingerprint, present(r) -> outputs on disk, run(r, ctx) -> None or raises Failed.

def nodes_inputs(r):
    L = {k: v for k, v in (r.cfg.get("lidar") or {}).items()}
    return sha(r.cfg.get("crs"), r.cfg.get("utm_bbox"), r.cfg.get("lonlat_bbox"), L)


def nodes_present(r):
    return all(os.path.isfile(p) for p in r.node_files())


def nodes_run(r, ctx):
    if not r.cfg.get("lidar"):
        print("  no lidar in the config: nothing to select")
        return
    if ctx.run([sys.executable, os.path.join(HERE, "ept_select.py"), r.slug]):
        raise Failed("ept_select.py failed (the EPT hierarchy is on the usgs-lidar-public bucket: Drew's PC only)")


def manifest_inputs(r):
    import gen_manifest
    return sha(file_sha(r.cfg_path), [file_sha(p) for p in r.node_files()], gen_manifest.MANIFEST_VERSION)


def manifest_items_sha(r):
    """the manifest's download list (not its bytes: a new manifestVersion key alone fetches nothing)"""
    try:
        with open(r.man_path, encoding="utf-8") as f:
            return sha(json.load(f).get("items"))
    except (OSError, ValueError):
        return None


def manifest_present(r):
    """the manifest is there and from this MANIFEST_VERSION: an older one (Breckenridge's, from before land cover)
    is made again, and the fetch then gets the layers it lacked (DATA-022 item 3)"""
    import gen_manifest
    try:
        with open(r.man_path, encoding="utf-8") as f:
            return json.load(f).get("manifestVersion") == gen_manifest.MANIFEST_VERSION
    except (OSError, ValueError):
        return False


def manifest_run(r, ctx):
    if ctx.run([sys.executable, os.path.join(HERE, "gen_manifest.py"), r.slug]):
        raise Failed("gen_manifest.py failed")


def fetch_inputs(r):
    return manifest_items_sha(r)


def fetch_present(r):
    return os.path.isfile(os.path.join(r.raw, "FETCH_COMPLETE.txt"))


def powershell():
    """Windows PowerShell where there is one (Drew's PC), else PowerShell 7 (`pwsh`: the Linux build runner,
    FEAT-245); fetch.ps1 runs on both"""
    for exe in ("powershell", "pwsh"):
        if shutil.which(exe):
            return exe
    raise Failed("fetch.ps1 needs PowerShell: neither powershell nor pwsh is on PATH (install PowerShell 7)")


def fetch_run(r, ctx):
    if os.path.basename(os.path.normpath(r.raw)) != r.slug:
        raise Failed(f"fetch.ps1 writes <RawDir>\\{r.slug}; the raw folder {r.raw} is not named {r.slug}")
    code = ctx.run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HERE, "fetch.ps1"),
                    "-Slug", r.slug, "-RawDir", os.path.dirname(os.path.normpath(r.raw))])
    if code == 2:
        raise Failed(f"some downloads failed ({os.path.join(r.raw, 'fetch_log.txt')} lists them): run again, "
                     "it resumes")
    if code:
        raise Failed(f"fetch.ps1 exited {code}")
    check_raw(r)


def check_raw(r):
    """the pack-build skill's raw checks: every layer there, the OSM files real JSON (an Overpass error page is
    HTML or a JSON "remark" with no elements). Land cover and pistes_wide are required unless the config turns
    land cover off (DATA-022 item 8: cover.py skips the far levels without them, and the far terrain reads as camo),
    the far ring's lidar when the config has lidar.far (item 8b), and place names in the US (FEAT-235)"""
    miss = []
    need = raw_need(r.cfg)
    osm_need = list(OSM_NEED)
    if not (r.cfg.get("lidar") and r.cfg.get("naip")) and not (r.cfg.get("landcover") or {}).get("enabled", True):
        raise Failed("the config has no lidar or no NAIP, so its trees or masks come from the land cover (FEAT-225), "
                     "but landcover.enabled is false: turn it on and run again with --force manifest")
    if (r.cfg.get("landcover") or {}).get("enabled", True):
        need["WorldCover land cover"] = (os.path.join("landcover", "worldcover"), None)
        need["ETH canopy height"] = (os.path.join("landcover", "eth_canopy"), None)
        osm_need.append("pistes_wide")
    if (r.cfg.get("lidar") or {}).get("far"):
        need["far ring lidar (ept_far)"] = ("ept_far", None)
    import placenames
    if placenames.states_of(r.cfg) and not r.cfg.get("source_only"):   # FEAT-235: GNIS and Census towns (US only;
        # FEAT-268: a relocate source's names are never read)
        need["place names (GNIS)"] = ("names", None)
    for name, (d, f) in need.items():
        p = os.path.join(r.raw, d)
        if not os.path.isdir(p) or not os.listdir(p) or (f and not os.path.isfile(os.path.join(p, f))):
            miss.append(name)
    for q in osm_need:
        p = os.path.join(r.raw, "osm", f"{q}.json")
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            if not d.get("elements"):
                miss.append(f"OSM {q} (no elements{': ' + d['remark'][:80] if d.get('remark') else ''})")
        except (OSError, ValueError):
            miss.append(f"OSM {q} (missing or not JSON)")
    if miss:
        raise Failed(f"raw data incomplete in {r.raw}: {', '.join(miss)}. Delete any bad files and run again with "
                     "--force fetch (it downloads only what is missing)")


def landfire_needed(r):
    return r.cfg.get("country", "US") == "US"


def landfire_inputs(r):
    return sha(r.cfg.get("lonlat_bbox"), r.cfg.get("crs"))


def landfire_present(r):
    return all(glob.glob(os.path.join(r.raw, d, "*.tif")) for _, d in LANDFIRE)


def landfire_run(r, ctx):
    if not landfire_needed(r):
        print("  outside the US: no LANDFIRE")
        return
    email = ctx.email or os.environ.get("LANDFIRE_EMAIL")
    if not email and ctx.interactive:
        try:
            email = input("Email address for the LANDFIRE service (LFPS asks for one for its statistics): ").strip()
        except EOFError:          # no console after all (a background run)
            email = None
    if not email:
        raise Failed("LANDFIRE needs an email address for the LFPS service: --email <address> or set LANDFIRE_EMAIL")
    force = ctx.forced("landfire") or (r.state.get("landfire") not in (None, landfire_inputs(r)))
    for prod, _ in LANDFIRE:
        cmd = ["node", os.path.join(HERE, "fetch_landfire.mjs"), r.slug, prod,
               "--raw", os.path.dirname(os.path.normpath(r.raw))] + (["--force"] if force else [])
        if ctx.run(cmd, env={"LANDFIRE_EMAIL": email}):
            raise Failed(f"fetch_landfire.mjs {prod} failed (LFPS jobs queue; run again later)")


def grooming_inputs(r):
    return sha(r.cfg.get("terrain_status_url"))


def grooming_present(r):
    return not r.cfg.get("terrain_status_url") or bool(glob.glob(os.path.join(r.raw, "grooming", "*.json")))


def grooming_run(r, ctx):
    if not r.cfg.get("terrain_status_url"):
        print("  no terrain_status_url: groomed runs come from OSM tags only")
        return
    if ctx.run([sys.executable, os.path.join(HERE, "fetch_grooming.py"), r.slug, r.raw]):
        raise Failed("fetch_grooming.py failed (the Internet Archive is slow at times; run again, it resumes)")


def build_inputs(r, code=None, out=None):
    groom = sorted(os.path.basename(p) for p in glob.glob(os.path.join(r.raw, "grooming", "*.json")))
    parts = [file_sha(r.cfg_path), manifest_items_sha(r), r.state.get("fetch"), r.state.get("landfire"), groom,
             code or pipeline_code(), out or r.out]
    for s in r.sources():      # FEAT-268: a relocate source's data is an input too (none: the formula as before)
        parts.append([s.slug, file_sha(s.cfg_path), manifest_items_sha(s), s.state.get("fetch"), s.state.get("landfire")])
    return sha(*parts)


def built_before_move(r, seen):
    """FEAT-238: True when the recorded build fingerprint `seen` is this build's inputs as SnowboardAnywhere saw
    them (the game's pipeline code at the move, the pack in the game checkout's packs/), this checkout's build code
    is still the moved code, and the pack here is that build (the same build id as the game checkout's copy)"""
    if pipeline_code() not in (MOVED["code"], *MOVED.get("same", ())):
        return False
    old_out = os.path.join(paths.game_repo(), "packs", r.slug)
    if seen != build_inputs(r, MOVED["game_code"], old_out):
        return False
    try:
        with open(os.path.join(old_out, "meta.json"), encoding="utf-8") as f:
            old_build = json.load(f).get("build")
    except (OSError, ValueError):
        old_build = None
    return old_build is None or old_build == (meta(r) or {}).get("build")


def meta(r):
    try:
        with open(os.path.join(r.out, "meta.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def build_present(r):
    """the pack is there, in this pipeline's format"""
    from packwriter import FORMAT_VERSION
    m = meta(r)
    return bool(m) and m.get("formatVersion") == FORMAT_VERSION


def build_adoptable(r):
    """a pack with no recorded build counts as built only when its pipeline commit has this pipeline's code"""
    return build_present(r) and same_code(meta(r).get("pipeline"))


def check_sources(r):
    """FEAT-268: every relocate source fetched (raw layers, LANDFIRE) before the pack that pastes it builds"""
    for s in r.sources():
        if not s.cfg.get("source_only"):
            raise Failed(f"relocate source {s.slug} is not marked \"source_only\": true in {s.cfg_path}")
        if not fetch_present(s) or not os.path.isfile(s.man_path):
            raise Failed(f"relocate source {s.slug} is not fetched ({s.raw}): python pipeline/build_resort.py "
                         f"{s.slug} --stop-after landfire")
        check_raw(s)
        if landfire_needed(s) and not landfire_present(s):
            raise Failed(f"relocate source {s.slug} has no LANDFIRE clips: python pipeline/build_resort.py "
                         f"{s.slug} --stop-after landfire")


def build_run(r, ctx):
    from packwriter import FORMAT_VERSION
    check_sources(r)
    t = time.time()
    if ctx.run([sys.executable, os.path.join(HERE, "build_pack.py"), r.slug, r.raw, r.out]):
        raise Failed("build_pack.py failed: the log above names the stage (pack-build skill, Common failures)")
    m = meta(r)
    if not m:
        raise Failed(f"build_pack.py wrote no {os.path.join(r.out, 'meta.json')}")
    if m.get("formatVersion") != FORMAT_VERSION:
        raise Failed(f"meta.json is format {m.get('formatVersion')}, this pipeline writes {FORMAT_VERSION}")
    print(f"  built in {time.time() - t:.0f} s, build {m.get('build')}")


# FEAT-175 step 4: the generated start, menu shots, still, ghosts and compare spots (gen_content.py, the game's tools)
def content_inputs(r):
    m = meta(r) or {}
    return sha(m.get("build"), file_sha(os.path.join(HERE, "gen_content.py")), file_sha(r.cfg_path))


def content_present(r):
    """gen_content.py ran on this build (meta.generated, also when it found no start or shots; a build drops it)"""
    m = meta(r) or {}
    return "generated" in m or (m.get("start") or {}).get("source") == "generated"


def content_run(r, ctx):
    if ctx.run([sys.executable, os.path.join(HERE, "gen_content.py"), r.out, "--config", r.cfg_path]):
        raise Failed("gen_content.py failed: the log above says where")


def game_tool(rel):
    """the game checkout's file `rel` (game/tools/...), or None without one (paths.game_repo: SBA_GAME_REPO)"""
    p = os.path.join(paths.game_repo(), *rel.split("/"))
    return p if os.path.isfile(p) else None


def attract_index(r):
    try:
        with open(os.path.join(r.out, "attract", "index.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def attract_inputs(r):
    return sha((meta(r) or {}).get("build"), file_sha(os.path.join(r.out, "attract", "shots.json")))


def attract_present(r):
    idx = attract_index(r)
    if idx is None:                     # done when gen_content.py found no camera spot: nothing to render
        return ((meta(r) or {}).get("generated") or {}).get("shots") == 0
    return bool(idx) and (not idx.get("generated") or (bool(idx.get("stills")) and bool(idx.get("ghosts"))))


def with_packs(r, fn):
    """run fn() with SHOT_PACKS at the folder that holds the pack (the game's tools serve /packs/<slug>/ from it)"""
    if os.path.basename(os.path.normpath(r.out)) != r.slug:
        raise Failed(f"the game serves packs by slug: {r.out} must be named {r.slug}")
    old = os.environ.get("SHOT_PACKS")
    os.environ["SHOT_PACKS"] = os.path.dirname(os.path.normpath(r.out))
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("SHOT_PACKS", None)
        else:
            os.environ["SHOT_PACKS"] = old


def attract_run(r, ctx):
    idx = attract_index(r)
    if idx is not None and not idx.get("generated"):
        print("  the pack's attract/ is hand-made: left alone")
        return
    if not os.path.isfile(os.path.join(r.out, "attract", "shots.json")):
        print("  no generated shots (gen_content.py found no camera spot): no menu still or ghosts")
        return
    game = os.path.dirname(os.path.dirname(game_tool("game/tools/auto_attract.mjs")))
    if ctx.run([shutil.which("npx") or "npx", "vite", "build"], game):
        raise Failed("the game did not build (cd game && npx vite build)")
    code = with_packs(r, lambda: ctx.run(["node", os.path.join("tools", "auto_attract.mjs"), r.slug], game))
    if code == 1:
        print("  warning: auto_attract.mjs has things to look at (above); the still and takes are written")
    elif code:
        raise Failed(f"auto_attract.mjs exited {code} (above)")


def compare_dir(r):
    return os.path.join(paths.game_repo(), "docs", "compare", r.slug)


def spots_inputs(r):
    return sha(r.slug)            # once: the proposals are a start; Drew's own spots then live there


def spots_present(r):
    return bool(glob.glob(os.path.join(compare_dir(r), "*", "spot.json")))


def spots_run(r, ctx):
    tool = game_tool("tools/propose_spots.py")
    code = with_packs(r, lambda: ctx.run([sys.executable, tool, r.slug, "--shoot"], paths.game_repo()))
    if code:
        raise Failed(f"propose_spots.py exited {code} (above)")


def index_inputs(r):
    return None      # always: cheap, and another pack may have changed the index


def index_present(r):
    return False


def index_run(r, ctx):
    from packwriter import index_packs
    packs = os.path.dirname(os.path.normpath(r.out))
    index_packs(packs)
    with open(os.path.join(packs, "index.json"), encoding="utf-8") as f:
        if r.slug not in json.load(f)["packs"]:
            raise Failed(f"{r.slug} is not in {os.path.join(packs, 'index.json')}: is {r.out} named {r.slug}?")


def published_inputs(r):
    import published
    groom = sorted(os.path.basename(p) for p in glob.glob(os.path.join(r.raw, "grooming", "*.json")))
    ident = {k: r.cfg.get(k) for k in ("name", "openskidata", "osm_ski_area_way", "relocate", "terrain_status_url")}
    return sha(published.VERSION, ident, groom[-1:])


def published_present(r):
    import published
    return os.path.isfile(published.published_path(r.slug, r.resorts))


def published_run(r, ctx):
    cmd = [sys.executable, os.path.join(HERE, "published.py"), r.slug, "--raw", r.raw, "--resorts", r.resorts]
    if ctx.run(cmd):
        print("  published.py failed (Wikidata or Wikipedia not reached?): line 21 uses the figures already in the "
              "resort's folder, or skips without them; the next run tries again")
        return False      # not recorded: a new fingerprint must not sit on figures gathered for older inputs


def report_inputs(r):
    return None      # always: 15 s, and the summary is what the run is for


def report_present(r):
    return False


def report_run(r, ctx):
    cmd = [sys.executable, os.path.join(HERE, "pack_report.py"), r.out, "--raw", r.raw, "--config", r.cfg_path]
    code = ctx.run(cmd + (["--gate"] if ctx.gate else []))
    if code and ctx.gate:
        raise Failed("the DATA-022 report has MVP lines that do not pass (report.md in the pack): the pack is preview")
    if code:
        raise Failed(f"pack_report.py exited {code}")


STAGE_FN = {s: (globals()[f"{s}_inputs"], globals()[f"{s}_present"], globals()[f"{s}_run"]) for s in STAGES}
ADOPT = {"build": build_adoptable}     # stricter than "present" for outputs this tool did not record
GAME_TOOL = {"attract": "game/tools/auto_attract.mjs", "spots": "tools/propose_spots.py"}   # stages that need the game


# ------------------------------------------------------------------------------------------------ runner

class Context:
    def __init__(self, force=(), email=None, interactive=False, gate=False, runner=run):
        self.force, self.email, self.interactive, self.gate, self.run = set(force), email, interactive, gate, runner

    def forced(self, stage):
        return "all" in self.force or stage in self.force


DATA_STAGES = ("nodes", "manifest", "fetch", "landfire", "grooming")
SOURCE_WHY = "source only (a relocate source for another pack, not a pack)"


def raw_from_why(r):
    return f"the raw data is from {r.data} (python pipeline/build_resort.py {r.data} fetches it)"


def decide(r, stage, ctx):
    """(run?, why) for one stage"""
    inputs, present, _ = STAGE_FN[stage]
    if r.cfg.get("source_only") and stage not in DATA_STAGES:
        return False, SOURCE_WHY
    if r.data != r.slug and stage in DATA_STAGES:
        return False, raw_from_why(r)
    if stage in GAME_TOOL and not game_tool(GAME_TOOL[stage]):
        return False, f"no {GAME_TOOL[stage]} in a game checkout at {paths.game_repo()} (SBA_GAME_REPO)"
    if ctx.forced(stage):
        return True, "forced"
    fp = inputs(r)
    if fp is None:
        return True, "always runs"
    if stage == "landfire" and not landfire_needed(r):
        return False, "outside the US"
    if stage == "grooming" and not r.cfg.get("terrain_status_url"):
        return False, "no terrain_status_url"
    seen = r.state.get(stage)
    if seen == fp and present(r):
        return False, "inputs unchanged"
    if stage == "build" and seen is not None and present(r) and built_before_move(r, seen):
        return False, MOVED_WHY
    if seen is None and ADOPT.get(stage, present)(r):
        return False, "already on disk (adopted)"
    if seen is None:
        return True, "not done yet"
    return True, "inputs changed" if present(r) else "output missing"


def build(r, ctx, first=None, last=None, dry=False, out=print):
    """run the stages from `first` to `last`; -> 0, or raises Failed"""
    a = STAGES.index(first) if first else 0
    b = STAGES.index(last) if last else len(STAGES) - 1
    for stage in STAGES[a:b + 1]:
        go, why = decide(r, stage, ctx)
        out(f"[{stage}] {'run' if go else 'skip'}: {why}")
        if dry:
            continue
        inputs, present, fn = STAGE_FN[stage]
        if go:
            t = time.time()
            if fn(r, ctx) is False:  # a soft failure (published): not recorded, so the next run tries again
                out(f"[{stage}] not done, the build goes on")
                continue
            out(f"[{stage}] done in {time.time() - t:.0f} s")
        elif stage == "fetch":
            check_raw(r)             # data fetched earlier gets the same checks before it is built
        if stage in ("nodes", "manifest", "fetch", "build"):
            r.cfg = json.load(open(r.cfg_path, encoding="utf-8"))
        if why == SOURCE_WHY:
            continue
        fp = inputs(r)
        if fp is not None and (go or r.state.get(stage) is None or why == MOVED_WHY):
            r.state[stage] = fp
            r.save()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("slug")
    ap.add_argument("raw_dir", nargs="?", help="the resort's raw folder (default raw/<slug> in the main checkout, "
                                               "or SBA_RAW_ROOT/<slug>)")
    ap.add_argument("out_dir", nargs="?", help="the pack folder (default packs/<slug>)")
    ap.add_argument("--from", dest="first", choices=STAGES, help="start at this stage")
    ap.add_argument("--stop-after", dest="last", choices=STAGES, help="stop after this stage")
    ap.add_argument("--force", action="append", default=[], choices=STAGES + ["all"], help="run a stage even if done")
    ap.add_argument("--email", help="email for the LANDFIRE service (or LANDFIRE_EMAIL)")
    ap.add_argument("--gate", action="store_true", help="fail unless every DATA-022 MVP line passes")
    ap.add_argument("--dry-run", action="store_true", help="print what would run and why")
    a = ap.parse_args(argv)
    if not os.path.isfile(paths.config_path(a.slug)):
        print(f"no resorts/{a.slug}/{a.slug}.json: `python pipeline/resort.py resolve \"<name>\"` and `plan` make one")
        return 2
    if a.first and a.last and STAGES.index(a.first) > STAGES.index(a.last):
        print("--from comes after --stop-after")
        return 2
    with open(paths.config_path(a.slug), encoding="utf-8") as f:
        data = json.load(f).get("raw_from") or a.slug       # FEAT-268: the resort whose raw data this builds on
    raw = a.raw_dir or os.path.join(default_raw_root(), data)
    out = a.out_dir or os.path.join(paths.PACKS, a.slug)
    r = Resort(a.slug, raw, out)
    print(f"{r.cfg.get('name', a.slug)}: raw {r.raw}, pack {r.out}")
    ctx = Context(a.force, a.email, sys.stdin.isatty(), a.gate)
    t = time.time()
    try:
        build(r, ctx, a.first, a.last, a.dry_run)
    except Failed as e:
        print(f"\nstopped: {e}")
        return 1
    print(f"\n{a.slug}: {'checked' if a.dry_run else 'done'} in {time.time() - t:.0f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
