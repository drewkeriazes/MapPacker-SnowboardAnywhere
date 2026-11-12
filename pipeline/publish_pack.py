"""FEAT-222: publish a built pack as a release of this repo, so the game's `npm run get <slug>` can download it.

    python pipeline/publish_pack.py packs/vail [--status preview|playable] [--tier gold] [--report report.md]
                                               [--dry-run]
    python pipeline/publish_pack.py --synth [--force] [--dry-run]

`--synth` (FEAT-241) builds the synthetic pack (synth_pack.py, about 2 minutes) into packs/synth and publishes it
as a test pack, release `synth-v<N>`, for the game's CI (`node game/tools/get_pack.mjs synth`). It publishes only
when the pack's content differs from the catalog's synth for this format (`--force` publishes anyway). Run it on
main after merging a change to the pipeline or the pack format.

Runs on Drew's PC, in the main checkout on `main` (needs `gh` signed in with push access to this repo). Steps:
  1. refuse a pack whose meta.json `formatVersion` is not this pipeline's FORMAT_VERSION (rebuild it on main)
  2. zip the pack, stored (PNG tiles do not compress), fixed timestamps so the same pack gives the same sha256;
     refuse a zip over 1.9 GiB (GitHub's limit per release asset is 2 GiB)
  3. `gh release create <slug>-v<N>` in this repo with the zip, meta.json and the report if there is one
  4. update catalog.json, copy the report to reports/<slug>.md, and commit them in place with the resort's
     config, EPT node lists, data plan (resorts/<slug>/) and manifest (manifests/), then push. Only those files go in
     the commit; anything else uncommitted in the checkout is left alone.

Test packs (`--test`, and `--synth`) go in the catalog's `test` list, not `resorts`, so the resort picker never
shows them; the list keeps one entry per slug and pack format, so a format bump publishes the new synth beside the
old one and the game's main keeps its own until it moves to the new format.
The catalog's `pipeline` is this repo's commit (FEAT-238; packs published before the move name a SnowboardAnywhere
commit). Catalog schema: SnowboardAnywhere docs/research/resort-auto-pipeline.md section 2; download side: the
game's game/tools/get_pack.mjs.
A pack is `playable` only when every DATA-022 MVP line passes in its report (EPIC-15 rule 2): the status comes
from `<pack_dir>/report.json` (`pack_report.py`, FEAT-175) when it was made for this build, `preview` without one,
and `--status playable` is refused unless the report passes.
"""
import argparse, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from packwriter import FORMAT_VERSION  # noqa: E402
import paths  # noqa: E402

RESORTS_REPO = "drewkeriazes/MapPacker-SnowboardAnywhere"
REPO = paths.REPO
MAX_ZIP = int(1.9 * 1024 ** 3)
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SKIP_DIRS = {"debug"}        # pipeline diagnostics (debug/species.png), not read by the game
STAMPS = ("build", "pipeline")  # meta.json fields every build writes afresh (packwriter.stamp_build)
SYNTH = "synth"


def pack_files(pack_dir: str) -> list:
    """Every file the zip carries, as forward-slash paths relative to the pack, sorted. Leaves out debug/ and
    dot files (get_pack's .catalog.json marker)."""
    out = []
    for root, dirs, files in os.walk(pack_dir):
        rel_root = os.path.relpath(root, pack_dir)
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and not (rel_root == "." and d in SKIP_DIRS))
        for f in files:
            if f.startswith("."):
                continue
            out.append(os.path.normpath(os.path.join(rel_root, f)).replace(os.sep, "/"))
    return sorted(out)


def zip_pack(pack_dir: str, zip_path: str) -> tuple:
    """Stored zip of the pack (entries relative to the pack folder). Returns (bytes, sha256 hex)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
        for rel in pack_files(pack_dir):
            info = zipfile.ZipInfo(rel, ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            with open(os.path.join(pack_dir, rel), "rb") as src, z.open(info, "w") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return os.path.getsize(zip_path), h.hexdigest()


def content_key(pack_dir: str) -> str:
    """sha256 (16 hex) of what the pack holds, leaving out meta.json's build stamps: two builds of the same pack
    from the same code give the same key, so `--synth` can tell whether a rebuild changed anything."""
    h = hashlib.sha256()
    for rel in pack_files(pack_dir):
        h.update(rel.encode() + b"\0")
        path = os.path.join(pack_dir, rel)
        if rel == "meta.json":
            meta = json.load(open(path, encoding="utf-8"))
            h.update(json.dumps({k: v for k, v in meta.items() if k not in STAMPS}, sort_keys=True).encode())
        else:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
        h.update(b"\0")
    return h.hexdigest()[:16]


def all_entries(catalog: dict) -> list:
    return catalog.get("resorts", []) + catalog.get("test", [])


def find_test_pack(catalog: dict, slug: str, fmt: int) -> dict | None:
    """the catalog's test pack `slug` at pack format `fmt`, or None"""
    return next((t for t in catalog.get("test", []) if t.get("slug") == slug
                 and (t.get("pack") or {}).get("formatVersion") == fmt), None)


def next_version(slug: str, tags: list, catalog: dict) -> int:
    """One past the highest <slug>-v<N> release or catalog version, so a deleted release's number is not reused."""
    pat = re.compile(rf"^{re.escape(slug)}-v(\d+)$")
    nums = [int(m.group(1)) for t in tags if (m := pat.match(t))]
    nums += [r["pack"]["version"] for r in all_entries(catalog) if r.get("slug") == slug and r.get("pack")]
    return max(nums, default=0) + 1


def report_status(pack_dir: str, meta: dict, requested: str | None) -> tuple:
    """(status, why) from the pack's report.json (EPIC-15 rule 2). A report made for another build counts as none.
    Raises SystemExit when `playable` is asked for and the report does not pass."""
    path = os.path.join(pack_dir, "report.json")
    rep = json.load(open(path, encoding="utf-8")) if os.path.isfile(path) else None
    if rep and rep.get("build") != meta.get("build"):
        why, rep = f"report.json is for build {rep.get('build')}, the pack is {meta.get('build')}: re-run pack_report.py", None
    elif rep:
        why = "report passes" if rep.get("playable") else f"report: MVP lines {', '.join(rep.get('failing', []))} hold it back"
    else:
        why = "no report.json (python pipeline/pack_report.py <pack_dir>)"
    passes = bool(rep and rep.get("playable"))
    if requested == "playable" and not passes:
        raise SystemExit(f"refusing --status playable: {why}")
    return requested or ("playable" if passes else "preview"), why


def asset_url(slug: str, version: int, repo: str = RESORTS_REPO) -> str:
    return f"https://github.com/{repo}/releases/download/{slug}-v{version}/{slug}.zip"


def catalog_entry(meta: dict, cfg: dict, *, version: int, size: int, sha256: str, pipeline: str, tier: str,
                  status: str, report: str | None, repo: str = RESORTS_REPO) -> dict:
    slug = meta["slug"]
    return {
        "slug": slug, "name": meta["name"],
        "region": cfg.get("region", ""), "country": cfg.get("country", ""),
        "lonlat": meta.get("lonlat"),
        "tier": tier, "status": status,
        "pack": {"version": version, "formatVersion": meta.get("formatVersion", 0), "build": meta.get("build"),
                 "built": time.strftime("%Y-%m-%d"), "pipeline": pipeline,
                 "bytes": size, "sha256": sha256, "url": asset_url(slug, version, repo)},
        "report": report,
    }


def update_catalog(catalog: dict, entry: dict, test: bool = False) -> dict:
    """Replace the resort's entry (or add it), resorts sorted by name; `formatVersion` is the newest format any
    resort in the catalog uses. With `test` the entry goes in the `test` list instead, replacing only the entry
    with the same slug and pack format (FEAT-241), sorted by slug then format."""
    resorts = list(catalog.get("resorts", []))
    tests = list(catalog.get("test", []))
    if test:
        fmt = entry["pack"]["formatVersion"]
        tests = [t for t in tests if not (t.get("slug") == entry["slug"] and t["pack"].get("formatVersion") == fmt)]
        tests = sorted(tests + [entry], key=lambda t: (t["slug"], t["pack"].get("formatVersion", 0)))
    else:
        resorts = [r for r in resorts if r.get("slug") != entry["slug"]] + [entry]
        resorts.sort(key=lambda r: (r.get("name") or r["slug"]).lower())
    fmt = max([r["pack"].get("formatVersion", 0) for r in resorts if r.get("pack")], default=FORMAT_VERSION)
    out = {**catalog, "formatVersion": fmt, "resorts": resorts}
    if tests:
        out["test"] = tests
    return out


def run(cmd: list, cwd: str | None = None, capture: bool = True) -> str:
    r = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True, encoding="utf-8")
    if r.returncode:
        raise SystemExit(f"{' '.join(cmd)} failed ({r.returncode}):\n{(r.stderr or '') + (r.stdout or '')}".rstrip())
    return (r.stdout or "").strip()


def resort_files(slug: str, repo_dir: str = REPO) -> list:
    """the resort's own files, relative to the repo: config, EPT node lists, data plan, manifest, report"""
    own = os.path.join("resorts", slug)
    rel = [os.path.join(own, f"{slug}.json"), os.path.join(own, f"{slug}-plan.md"),
           os.path.join("manifests", f"{slug}.json"), os.path.join("reports", f"{slug}.md")]
    rel += [os.path.relpath(p, repo_dir) for p in sorted(glob.glob(os.path.join(repo_dir, own, f"{slug}_*nodes*.txt")))]
    return [p.replace(os.sep, "/") for p in rel if os.path.isfile(os.path.join(repo_dir, p))]


def ready_to_commit(repo_dir: str = REPO) -> str:
    """the checkout publish commits in: on main, catalog.json unchanged, up to date with origin"""
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir)
    if branch != "main":
        raise SystemExit(f"{repo_dir} is on {branch}: publish from the main checkout on main (the catalog commit "
                         "goes straight to main)")
    if run(["git", "status", "--porcelain", "--", "catalog.json"], cwd=repo_dir):
        raise SystemExit(f"{os.path.join(repo_dir, 'catalog.json')} has uncommitted changes; commit or discard them first")
    run(["git", "pull", "--ff-only", "--quiet"], cwd=repo_dir)
    return repo_dir


def build_synth(out_dir: str) -> str:
    """synth_pack.py into a clean out_dir (a file left from an older build would go in the zip)"""
    shutil.rmtree(out_dir, ignore_errors=True)
    print(f"building the synthetic pack into {out_dir} (about 2 minutes)")
    run([sys.executable, os.path.join(paths.HERE, "synth_pack.py"), out_dir], capture=False)
    return out_dir


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("pack_dir", nargs="?", help="the built pack (not with --synth)")
    ap.add_argument("--status", choices=["preview", "playable"],
                    help="default from report.json; playable only when the DATA-022 report passes (EPIC-15 rule 2)")
    ap.add_argument("--tier", choices=["gold", "silver", "bronze"], default="gold")
    ap.add_argument("--report", help="report markdown to attach and commit (default <pack_dir>/report.md if present)")
    ap.add_argument("--test", action="store_true", help="a test pack: the catalog's `test` list, not the picker")
    ap.add_argument("--synth", action="store_true",
                    help="build the synthetic pack into packs/synth and publish it as a test pack if it changed")
    ap.add_argument("--force", action="store_true", help="with --synth: publish even when the content is unchanged")
    ap.add_argument("--repo", default=RESORTS_REPO)
    ap.add_argument("--dry-run", action="store_true", help="zip and print the catalog entry; no release, no commit")
    a = ap.parse_args(argv)
    if a.synth == bool(a.pack_dir):
        ap.error("give a pack_dir, or --synth")
    test = a.test or a.synth

    # on main and up to date before the two-minute synth build, not after it
    repo_dir = None if a.dry_run else ready_to_commit()
    pack_dir = build_synth(os.path.join(paths.PACKS, SYNTH)) if a.synth else os.path.abspath(a.pack_dir)
    with open(os.path.join(pack_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    slug = meta["slug"]
    fmt = meta.get("formatVersion", 0)
    if fmt != FORMAT_VERSION:
        raise SystemExit(f"{pack_dir} is pack format {fmt}, this pipeline writes {FORMAT_VERSION}: rebuild it on main "
                         f"(python pipeline/build_pack.py {slug} <raw_dir> <out_dir>) before publishing")
    if test:
        a.status, why, a.tier, report, cfg = "test", "test pack, not in the picker", None, None, {}
    else:
        a.status, why = report_status(pack_dir, meta, a.status)
        cfg_path = paths.config_path(slug)
        cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.isfile(cfg_path) else {}
        report = a.report or (os.path.join(pack_dir, "report.md") if os.path.isfile(os.path.join(pack_dir, "report.md")) else None)
    print(f"status {a.status} ({why})")
    pipeline = run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO)
    if run(["git", "status", "--porcelain", "--", "pipeline"], cwd=REPO):
        print("warning: pipeline/ has uncommitted changes; the catalog records the commit, not them")

    # a dry run reads this checkout's catalog as it is (no pull), so --synth can still say whether it changed
    cat_path = os.path.join(repo_dir or REPO, "catalog.json")
    catalog = json.load(open(cat_path, encoding="utf-8")) if os.path.isfile(cat_path) else {"resorts": []}
    content = content_key(pack_dir) if test else None
    if test:
        old = find_test_pack(catalog, slug, fmt)
        if old and old["pack"].get("content") == content and not a.force:
            print(f"{slug} at pack format {fmt} is unchanged since v{old['pack']['version']} (content {content}): "
                  f"nothing to publish (--force publishes anyway)")
            return
        print(f"content {content}" + (f", v{old['pack']['version']} has {old['pack'].get('content')}" if old else
                                      f", no {slug} at pack format {fmt} in the catalog yet"))
    tags = [] if a.dry_run else [r["tagName"] for r in json.loads(run(
        ["gh", "release", "list", "-R", a.repo, "--limit", "1000", "--json", "tagName"]) or "[]")]
    version = next_version(slug, tags, catalog)
    tag = f"{slug}-v{version}"

    tmp = tempfile.mkdtemp(prefix=f"publish-{slug}-")
    try:
        zip_path = os.path.join(tmp, f"{slug}.zip")
        t0 = time.time()
        size, sha = zip_pack(pack_dir, zip_path)
        print(f"{slug}.zip: {size / 1e6:.0f} MB, sha256 {sha} ({time.time() - t0:.0f} s)")
        if size > MAX_ZIP:
            raise SystemExit(f"{slug}.zip is {size / 1024 ** 3:.2f} GiB, over the 1.9 GiB limit for a release asset")
        report_rel = f"reports/{slug}.md" if report else None
        entry = catalog_entry(meta, cfg, version=version, size=size, sha256=sha, pipeline=pipeline,
                              tier=a.tier, status=a.status, report=report_rel, repo=a.repo)
        if content:
            entry["pack"]["content"] = content
        if a.dry_run:
            print(json.dumps(entry, indent=1))
            return

        if test:
            notes = (f"{meta['name']} v{version}: a test pack for the game's CI, not in the resort picker (FEAT-241). "
                     f"Pack format {fmt}, build {meta.get('build')}, pipeline {pipeline}, content {content}. "
                     f"{size / 1e6:.0f} MB, sha256 `{sha}`.\n\n"
                     f"Get it: `cd game && npm run get {slug}` in SnowboardAnywhere.")
        else:
            notes = (f"{meta['name']} pack v{version} ({a.status}, {a.tier} tier). Pack format {fmt}, build {meta.get('build')}, "
                     f"pipeline {pipeline}. {size / 1e6:.0f} MB, sha256 `{sha}`.\n\n"
                     f"Get it: `cd game && npm run get {slug}` in SnowboardAnywhere.")
        assets = [zip_path, os.path.join(pack_dir, "meta.json")] + ([report] if report else [])
        print(f"creating release {tag} in {a.repo}")
        run(["gh", "release", "create", tag, *assets, "-R", a.repo, "--title", f"{meta['name']} v{version}",
             "--notes", notes], capture=False)

        with open(cat_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(update_catalog(catalog, entry, test=test), f, indent=1)
            f.write("\n")
        # the recipe that built it is committed beside the catalog: config, node lists, plan, manifest, report
        os.makedirs(os.path.join(repo_dir, "reports"), exist_ok=True)
        if report and os.path.abspath(report) != os.path.abspath(os.path.join(repo_dir, report_rel)):
            shutil.copy2(report, os.path.join(repo_dir, report_rel))
        files = ["catalog.json"] + ([] if test else resort_files(slug, repo_dir))
        run(["git", "add", "--", *files], cwd=repo_dir)
        run(["git", "commit", "-q", "-m", f"{slug} v{version}: {a.status}, {size / 1e6:.0f} MB, pipeline {pipeline}",
             "--", *files], cwd=repo_dir)
        try:
            run(["git", "push", "-q"], cwd=repo_dir)
        except SystemExit as e:
            raise SystemExit(f"{e}\nThe release {tag} exists; push the catalog commit by hand from {repo_dir}")
        print(f"published {tag}: {entry['pack']['url']}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
