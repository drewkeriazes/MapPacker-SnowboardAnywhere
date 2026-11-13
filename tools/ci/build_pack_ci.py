"""The steps of the build-pack workflow (FEAT-245, .github/workflows/build-pack.yml): one resort in, one publish PR out.

    python tools/ci/build_pack_ci.py check      check the run's inputs (the probe job, before anything runs)
    python tools/ci/build_pack_ci.py inputs     the same, then write the step outputs and the summary's heading
    python tools/ci/build_pack_ci.py resolve    new slug: resort.py add --osm ... --stop-after plan; rebuild: skip
    python tools/ci/build_pack_ci.py fetch      build_resort.py data stages, for the raw data it builds on first
    python tools/ci/build_pack_ci.py build      build_resort.py build to index (attract and spots skip: no game)
    python tools/ci/build_pack_ci.py report     build_resort.py report (the DATA-022 scorecard, not a gate here)
    python tools/ci/build_pack_ci.py publish    publish_pack.py: a draft release and a publish PR, or nothing when
                                                the pack is the same as the one published (or already in a PR)

The inputs are untrusted text (anyone with write access can start a run, and later the game's Build it button
passes a typed name). The workflow hands them over as environment variables, never in a shell line, and `inputs`
refuses anything outside the shapes below before any other step runs. Every step appends a line to the run
summary ($GITHUB_STEP_SUMMARY); the steps are named after the stages, so the game can read progress from the
run's jobs (FEAT-247).
"""
import argparse, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPELINE = os.path.join(ROOT, "pipeline")
sys.path.insert(0, PIPELINE)
import paths  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rebuild_choices  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
OSM_RE = re.compile(r"^((way|relation|skimap)/)?[1-9][0-9]{0,15}$")   # skimap/497: no OSM outline (FEAT-286)
REQUESTED_BY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$")   # a game account id (Firebase uid) or a login
MAX_NAME = 100


class Refused(Exception):
    pass


def check_inputs(name, osm_id, slug, requested_by, resorts_dir=None, rebuild=None):
    """-> dict(mode, slug, name, osm_id, requested_by, tier, deps). Raises Refused on bad input. `mode` is "rebuild"
    when resorts/<slug>/<slug>.json exists (name and osm_id are then optional: the config already says which ski
    area it is), else "new" (both needed). FEAT-297: `rebuild` is the form's pick from the rebuild list; a pack
    picked there is the slug (a typed slug must then be the same one), and it must already have a config."""
    name, osm_id, slug, requested_by, rebuild = (s.strip() for s in (name or "", osm_id or "", slug or "",
                                                                      requested_by or "", rebuild or ""))
    if rebuild and rebuild != rebuild_choices.NEW:
        if not SLUG_RE.fullmatch(rebuild) or len(rebuild) > 60:
            raise Refused(f"rebuild {rebuild!r} is not a pack slug")
        if slug and slug != rebuild:
            raise Refused(f"the rebuild list picked {rebuild} but the slug typed is {slug}: pick one")
        if not os.path.isfile(paths.config_path(rebuild, resorts_dir)):
            raise Refused(f"{rebuild} has no config in resorts/: it can't be rebuilt")
        slug = rebuild
    if not slug:
        raise Refused("no pack: pick one in the rebuild list, or type a slug (with name and osm_id for a new resort)")
    if not SLUG_RE.fullmatch(slug) or len(slug) > 60:
        raise Refused(f"slug {slug!r} is not lower-case letters, digits and single hyphens (at most 60)")
    if len(name) > MAX_NAME or any(ord(c) < 32 or ord(c) == 127 for c in name) or name.startswith("-"):
        raise Refused(f"name is longer than {MAX_NAME} characters, has control characters or starts with -")
    if osm_id and not OSM_RE.fullmatch(osm_id):
        raise Refused(f"osm_id {osm_id!r} is not an OSM or Skimap.org id (123, way/123, relation/123 or skimap/123)")
    if requested_by and not REQUESTED_BY_RE.fullmatch(requested_by):
        raise Refused("requested_by is not an account id (a letter or digit, then letters, digits and _.:@-, "
                      "at most 128)")
    path = paths.config_path(slug, resorts_dir)
    if os.path.isfile(path):
        cfg = json.load(open(path, encoding="utf-8"))
        if cfg.get("source_only"):
            raise Refused(f"{slug} is a relocate source (source_only), not a pack: build the resort that uses it")
        mode = "rebuild"
        name = name or cfg.get("name") or slug
    else:
        if not name or not osm_id:
            raise Refused(f"{slug} is a new resort: give both name and osm_id (the ski area picked in the game)")
        mode, cfg = "new", {}
    return {"mode": mode, "slug": slug, "name": name, "osm_id": osm_id, "requested_by": requested_by,
            "tier": cfg.get("tier", "gold"), "deps": deps(slug, resorts_dir) if mode == "rebuild" else []}


def deps(slug, resorts_dir=None, seen=None):
    """the resorts whose raw data `slug` builds on, deepest first: its `raw_from` (FEAT-268) and its relocate
    sources, and theirs. A new resort has none (resort.py plan never writes either)."""
    seen = set() if seen is None else seen
    path = paths.config_path(slug, resorts_dir)
    if not os.path.isfile(path):
        raise Refused(f"{slug} names a resort with no config ({path})")
    cfg = json.load(open(path, encoding="utf-8"))
    names = ([cfg["raw_from"]] if cfg.get("raw_from") else []) + \
        [m["source"] for m in cfg.get("relocate") or [] if m.get("source")]
    out = []
    for d in dict.fromkeys(names):
        if d in seen or d == slug:
            continue
        seen.add(d)
        out += [x for x in deps(d, resorts_dir, seen) if x not in out] + [d]
    return list(dict.fromkeys(out))


def md(text):
    """`text` safe in a Markdown heading or table cell of the run summary (the name is untrusted text)"""
    return re.sub(r"([\\`*_{}\[\]<>|#!])", r"\\\1", text)


def summary(line):
    print(line, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def outputs(values):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def stream(cmd):
    """run cmd, passing its output through as it comes -> (exit code, the output)"""
    p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", bufsize=1, env={**os.environ, "PYTHONUNBUFFERED": "1"})
    lines = []
    for line in p.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    return p.wait(), "".join(lines)


def run(cmd, runner=stream):
    print("  $ " + " ".join(cmd), flush=True)   # the inputs are checked, and the LANDFIRE email is in the env only
    return runner(cmd)


def publish_result(text):
    """the run summary's word on what publish_pack did, from its output"""
    if m := re.search(r"(unchanged since v\d+)", text):
        return f"{m.group(1)}: nothing published"
    if m := re.search(r"(https://github\.com/\S+/pull/\d+) is open with this content", text):
        return f"already in {m.group(1)}: nothing published"
    if m := re.search(r"opened (https://github\.com/\S+/pull/\d+)", text):
        return f"opened {m.group(1)}"
    return "done"


def py(script, *args):
    return [sys.executable, os.path.join(PIPELINE, script), *args]


def stage_commands(stage, cfg):
    """the commands one stage runs, in order"""
    slug = cfg["slug"]
    if stage == "resolve":
        if cfg["mode"] == "rebuild":
            return []
        # --alone: the area picked in the game is the pack; a neighbour sold with it (Boston Mills and Brandywine)
        # is a hand config's job. --osm names it, so resolve never asks which of several areas.
        return [py("resort.py", "add", "--osm", cfg["osm_id"], "--slug", slug, "--alone", "--stop-after", "plan",
                   "--", cfg["name"])]    # after --: a name is never read as a flag
    if stage == "fetch":
        return [py("build_resort.py", d, "--stop-after", "grooming") for d in cfg["deps"]] + \
               [py("build_resort.py", slug, "--stop-after", "grooming")]
    if stage == "build":
        return [py("build_resort.py", slug, "--from", "build", "--stop-after", "index")]
    if stage == "report":
        # BUG-124: from `published` (FEAT-293), the stage before the report: the resort's figures for line 21
        return [py("build_resort.py", slug, "--from", "published", "--stop-after", "report")]
    if stage == "publish":
        cmd = py("publish_pack.py", os.path.join(paths.PACKS, slug), "--tier", cfg["tier"])
        if cfg.get("run_url"):
            cmd += ["--run-url", cfg["run_url"]]
        if cfg.get("requested_by"):
            cmd += [f"--requested-by={cfg['requested_by']}"]     # one word: never read as a flag
        return [cmd]
    raise ValueError(stage)


def from_env():
    return check_inputs(os.environ.get("NAME"), os.environ.get("OSM_ID"), os.environ.get("SLUG"),
                        os.environ.get("REQUESTED_BY"), rebuild=os.environ.get("REBUILD"))


def main(argv=None, runner=stream):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("stage", choices=["check", "inputs", "resolve", "fetch", "build", "report", "publish"])
    a = ap.parse_args(argv)
    try:
        cfg = from_env()
    except Refused as e:
        summary(f"**Refused:** {e}")
        return 1
    if a.stage == "check":
        print(f"{cfg['slug']}: {cfg['mode']}" + (f", builds on {', '.join(cfg['deps'])}" if cfg["deps"] else ""))
        return 0
    if a.stage == "inputs":
        outputs({"mode": cfg["mode"], "slug": cfg["slug"]})
        summary(f"## {md(cfg['name'])} (`{cfg['slug']}`)\n\n"
                + ("New resort, OSM " + cfg["osm_id"] if cfg["mode"] == "new" else "Rebuild of the committed config")
                + (f", builds on {', '.join(cfg['deps'])}" if cfg["deps"] else "")
                + (f". Requested by `{cfg['requested_by']}`" if cfg["requested_by"] else "") + ".\n\n"
                "| stage | result | time |\n|---|---|---|")
        return 0
    cfg["run_url"] = os.environ.get("RUN_URL")
    cmds = stage_commands(a.stage, cfg)
    if not cmds:
        summary(f"| {a.stage} | skip: the config is committed | |")
        return 0
    t0 = time.time()
    text = ""
    for cmd in cmds:
        code, out = run(cmd, runner)
        text += out
        if code:
            summary(f"| {a.stage} | **failed** (exit {code}) | {time.time() - t0:.0f} s |")
            return code
    summary(f"| {a.stage} | {publish_result(text) if a.stage == 'publish' else 'done'} | {time.time() - t0:.0f} s |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
