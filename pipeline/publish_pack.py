"""FEAT-222: publish a built pack as a release of this repo, so the game's `npm run get <slug>` can download it.

    python pipeline/publish_pack.py packs/vail [--status preview|playable] [--tier gold] [--report report.md]
                                               [--accept-change] [--requested-by <id>] [--run-url <url>] [--dry-run]
    python pipeline/publish_pack.py --synth [--force] [--dry-run]

`--synth` (FEAT-241) builds the synthetic pack (synth_pack.py, about 2 minutes) into packs/synth and publishes it
as a test pack, release `synth/v<N>`, for the game's CI (`node game/tools/get_pack.mjs synth`). It publishes only
when the pack's content differs from the catalog's synth for this format (`--force` publishes anyway). Run it from
a clean checkout of main after merging a change to the pipeline or the pack format.

Runs from any checkout or worktree (needs `gh` signed in with push access to this repo); nothing here pushes to
main (FEAT-272). Steps:
  1. refuse a pack whose meta.json `formatVersion` is not this pipeline's FORMAT_VERSION (rebuild it on main), and
     one whose build stamp (meta.json `pipeline`) is missing, `+dirty` or not on origin/main (stamp_problem)
  2. refuse a pack pack_lint.py finds problems in (the publish-check job would reject its zip), dry run included;
     zip the pack, stored (PNG tiles do not compress), fixed timestamps so the same pack gives the same sha256;
     refuse a zip over 1.9 GiB (GitHub's limit per release asset is 2 GiB)
  3. `gh release create <slug>/v<N> --draft` in this repo with the zip, meta.json and the report if there is one
     (FEAT-271 tags; the old `<slug>-v<N>` ones still count); the version counts draft tags, so two publishes in
     flight never pick the same number. Players and the catalog don't see a draft.
  4. open a publish PR (open_publish_pr): in a throwaway worktree off a fresh origin/main, branch
     `publish/<slug>-v<N>` with catalog.json plus the new entry, RELEASES.md rewritten with this release in it
     (releases.py, FEAT-271), the pack's report as reports/<slug>.md and the
     resort's config, EPT node lists, data plan (resorts/<slug>/) and manifest (manifests/), copied from this
     checkout (which is left as it was; the worktree and the local branch are deleted afterwards); labels `publish`,
     `automerge` when the publisher is in .github/maintainers.txt, `accept-change` with --accept-change. The merge
     workflow releases the draft, then merges. The command prints the PR link and does not wait.

Test packs (`--test`, and `--synth`) go in the catalog's `test` list, not `resorts`, so the resort picker never
shows them; the list keeps one entry per slug and pack format, so a format bump publishes the new synth beside the
old one and the game's main keeps its own until it moves to the new format.
The catalog's `pipeline` is the pack's build stamp, the commit here that built it (FEAT-272; before it, the
publisher's HEAD, and before FEAT-238 a SnowboardAnywhere commit). Catalog schema: SnowboardAnywhere docs/research/resort-auto-pipeline.md section 2; download side: the
game's game/tools/get_pack.mjs.
A pack is `playable` only when every DATA-022 MVP line passes in its report (EPIC-15 rule 2): the status comes
from `<pack_dir>/report.json` (`pack_report.py`, FEAT-175) when it was made for this build, `preview` without one,
and `--status playable` is refused unless the report passes.
"""
import argparse, glob, hashlib, json, os, shutil, subprocess, sys, tempfile, time, zipfile
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from packwriter import FORMAT_VERSION, pipeline_commit  # noqa: E402
from pack_lint import lint  # noqa: E402
from releases import INDEX, list_releases, own_release, parse_tag, release_tag, write_index  # noqa: E402
import paths  # noqa: E402

RESORTS_REPO = "drewkeriazes/MapPacker-SnowboardAnywhere"
REPO = paths.REPO
MAX_ZIP = int(1.9 * 1024 ** 3)
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
SKIP_DIRS = {"debug"}        # pipeline diagnostics (debug/species.png), not read by the game
STAMPS = ("build", "pipeline")  # meta.json fields every build writes afresh (packwriter.stamp_build)
REPORT_FILES = ("report.json", "report.md")   # pack_report.py's output: build stamps, a time, file dates
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
    """sha256 (16 hex) of what the pack holds, leaving out meta.json's build stamps and the report (derived from
    the pack, and stamped with the build and the time it ran): two builds of the same pack from the same code give
    the same key, so a rebuild that changed nothing is not published again (FEAT-241, FEAT-245)."""
    h = hashlib.sha256()
    for rel in pack_files(pack_dir):
        if rel in REPORT_FILES:
            continue
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


def find_resort(catalog: dict, slug: str) -> dict | None:
    """the catalog's resort entry for `slug`, or None"""
    return next((r for r in catalog.get("resorts", []) if r.get("slug") == slug), None)


CONTENT_LINE = "Content: "


def pending_same_content(slug: str, content: str, repo: str) -> str | None:
    """FEAT-245: the URL of an open publish PR for `slug` whose body names this `content` (a rerun while the first
    publish is still waiting for its checks), or None"""
    prs = json.loads(run(["gh", "pr", "list", "-R", repo, "--label", "publish", "--state", "open",
                          "--json", "number,url,headRefName,body"]) or "[]")
    for pr in prs:
        head = pr.get("headRefName", "")
        if not (head.startswith(f"publish/{slug}-v") and head[len(f"publish/{slug}-v"):].isdigit()):
            continue
        if f"{CONTENT_LINE}{content}" in [line.strip() for line in (pr.get("body") or "").splitlines()]:
            return pr.get("url") or f"https://github.com/{repo}/pull/{pr.get('number')}"
    return None


def next_version(slug: str, tags: list, catalog: dict) -> int:
    """One past the highest <slug>/v<N> (or old <slug>-v<N>) release or catalog version, so a deleted release's
    number is not reused."""
    nums = [p[1] for t in tags if (p := parse_tag(t)) and p[0] == slug]
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
    return f"https://github.com/{repo}/releases/download/{release_tag(slug, version)}/{slug}.zip"


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
    """the resort's own files, relative to the repo: config, EPT node lists, data plan, published figures (FEAT-293),
    manifest, report"""
    own = os.path.join("resorts", slug)
    rel = [os.path.join(own, f"{slug}.json"), os.path.join(own, f"{slug}-plan.md"), os.path.join(own, f"{slug}-published.json"),
           os.path.join("manifests", f"{slug}.json"), os.path.join("reports", f"{slug}.md")]
    rel += [os.path.relpath(p, repo_dir) for p in sorted(glob.glob(os.path.join(repo_dir, own, f"{slug}_*nodes*.txt")))]
    return [p.replace(os.sep, "/") for p in rel if os.path.isfile(os.path.join(repo_dir, p))]


def stamp_why(meta: dict, on_origin_main: Callable[[str], bool]) -> str | None:
    """why the pipeline commit that built the pack (meta.json `pipeline`) can't be rebuilt from main, or None"""
    slug, stamp = meta.get("slug"), meta.get("pipeline")
    if not stamp:
        return f"{slug} has no pipeline stamp in meta.json (built before the stamp existed)"
    if "+dirty" in stamp:
        return f"{slug} was built from uncommitted pipeline code (pipeline {stamp})"
    if not on_origin_main(stamp):
        return f"{slug} was built by pipeline {stamp}, which is not on origin/main (a branch build)"
    return None


def stamp_problem(meta: dict, on_origin_main: Callable[[str], bool]) -> str | None:
    """FEAT-272: None when the pack's build stamp is a clean commit on origin/main; else why not, ending with the
    rebuild command"""
    why = stamp_why(meta, on_origin_main)
    return why and f"{why}: rebuild it on main, python pipeline/build_resort.py {meta.get('slug')} --force build"


def on_origin_main(sha: str, repo_dir: str = REPO, fetch: bool = True) -> bool:
    """`sha` is on origin/main (`git branch -r --contains`), after fetching main unless `fetch` is False"""
    if fetch:
        run(["git", "fetch", "origin", "main"], cwd=repo_dir)
    try:
        out = run(["git", "branch", "-r", "--contains", sha], cwd=repo_dir)
    except SystemExit:                # not a commit this clone has
        return False
    return "origin/main" in [line.strip() for line in out.splitlines()]


def maintainers(repo_dir: str = REPO) -> set[str]:
    """the GitHub logins whose publishes merge themselves: .github/maintainers.txt, one per line, # comments"""
    path = os.path.join(repo_dir, ".github", "maintainers.txt")
    if not os.path.isfile(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {line.split("#")[0].strip() for line in f} - {""}


def publisher_login() -> str:
    """who started this publish: the workflow's triggering actor, else gh's signed-in user"""
    return os.environ.get("GITHUB_TRIGGERING_ACTOR") or run(["gh", "api", "user", "--jq", ".login"])


def publish_branch(slug: str, version: int) -> str:
    return f"publish/{slug}-v{version}"


REBUILD_LIST = ("New resort: after this merges, `python tools/ci/rebuild_choices.py --write` in a PR of its own adds "
                "it to Build pack's rebuild list (FEAT-297; a publish PR can't change a workflow file)")


def pr_body(entry: dict, *, why: str, release_url: str, started_by: str, run_url: str | None,
            requested_by: str | None, new_resort: bool = False) -> str:
    """the publish PR's description; `Build:` and `Run:` are read back by resort.py and the merge workflow"""
    p = entry["pack"]
    lines = [f"Publishes **{entry['name']}** v{p['version']}: {entry['status']} ({why}).", "",
             f"Draft release: {release_url}",
             f"Size: {p['bytes'] / 1e6:.0f} MB ({p['bytes']} bytes), sha256 `{p['sha256']}`", "",
             f"Started by: {started_by}"]
    lines += [f"Run: {run_url}"] if run_url else []
    lines += [f"Requested by: {requested_by}"] if requested_by else []
    lines += [f"Build: {p['build']}", f"Pipeline: {p['pipeline']}"]
    lines += [f"{CONTENT_LINE}{p['content']}"] if p.get("content") else []   # read back by pending_same_content
    lines += ["", REBUILD_LIST] if new_resort else []
    lines += ["",
              "Approve with the `automerge` label, not the merge button: the merge workflow publishes the draft "
              "release before it merges, so the catalog never names a download that is not live (FEAT-272)."]
    return "\n".join(lines) + "\n"


def warn_on_failure(cmd: list, cwd: str) -> None:
    """run(cmd) for cleanup: a failure only warns, so it can't hide the error being cleaned up after"""
    try:
        run(cmd, cwd=cwd)
    except SystemExit as e:
        print(f"warning: {e}")


def open_publish_pr(*, slug: str, version: int, entry: dict, test: bool, src_repo: str, labels: list[str],
                    body: str, repo: str, report: str | None = None, releases: list | None = None) -> str:
    """Commit the catalog entry, RELEASES.md from `releases` when given (list_releases records, this publish's
    draft among them), the resort's own files (copied from `src_repo`) and `report` (as reports/<slug>.md) on
    publish/<slug>-v<N>, in a throwaway worktree off a fresh origin/main (never the publisher's
    checkout), push that branch, open the PR against main. Returns the PR URL. The worktree and the local branch
    are deleted afterwards, so a rerun can make the branch again."""
    branch = publish_branch(slug, version)
    tmp = tempfile.mkdtemp(prefix=f"publish-pr-{slug}-")
    wt = os.path.join(tmp, "wt")
    created = pushed = False
    try:
        run(["git", "fetch", "origin", "main"], cwd=src_repo)
        run(["git", "worktree", "add", "--detach", wt, "origin/main"], cwd=src_repo)
        cat_path = os.path.join(wt, "catalog.json")
        with open(cat_path, encoding="utf-8") as f:
            catalog = json.load(f)
        catalog = update_catalog(catalog, entry, test=test)
        with open(cat_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(catalog, f, indent=1)
            f.write("\n")
        index = [] if releases is None else [INDEX]
        if releases is not None:
            write_index(os.path.join(wt, INDEX), releases, catalog, repo, own=release_tag(slug, version))
        report_rel = f"reports/{slug}.md"   # this publish's report only, never an older one left in src_repo
        own = [] if test else [rel for rel in resort_files(slug, src_repo) if rel != report_rel]
        copies = [(os.path.join(src_repo, rel), rel) for rel in own] + ([(report, report_rel)] if report else [])
        for src, rel in copies:
            os.makedirs(os.path.dirname(os.path.join(wt, rel)), exist_ok=True)
            shutil.copy2(src, os.path.join(wt, rel))
        p = entry["pack"]
        run(["git", "switch", "-c", branch], cwd=wt)
        created = True
        run(["git", "add", "--", "catalog.json", *index, *[rel for _, rel in copies]], cwd=wt)
        run(["git", "commit", "-q", "-m",
             f"{slug} v{version}: {entry['status']}, {p['bytes'] / 1e6:.0f} MB, pipeline {p['pipeline']}"], cwd=wt)
        run(["git", "push", "-u", "origin", branch], cwd=wt)
        pushed = True
        body_path = os.path.join(tmp, "body.md")
        with open(body_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(body)
        return run(["gh", "pr", "create", "-R", repo, "--base", "main", "--head", branch,
                    "--title", f"{slug} v{version}: publish", "--body-file", body_path,
                    *[arg for label in ["publish", *labels] for arg in ("--label", label)]], cwd=wt)
    except SystemExit as e:
        if pushed:
            raise SystemExit(f"{e}\nThe branch {branch} is pushed: delete origin/{branch} too "
                             f"(git push origin --delete {branch})")
        raise
    finally:
        if os.path.isdir(wt):
            warn_on_failure(["git", "worktree", "remove", "--force", wt], src_repo)
        if created:
            warn_on_failure(["git", "branch", "-D", branch], src_repo)
        shutil.rmtree(tmp, ignore_errors=True)


LINT_SHOWN = 20


def lint_refusal(pack_dir: str) -> None:
    """refuse a pack the publish-check job's pack lint would reject, before anything is zipped or uploaded"""
    problems = lint(pack_dir)
    if problems:
        shown = [f"  - {p}" for p in problems[:LINT_SHOWN]]
        if len(problems) > LINT_SHOWN:
            shown.append(f"  ... and {len(problems) - LINT_SHOWN} more (python pipeline/pack_lint.py {pack_dir})")
        raise SystemExit("\n".join([f"refusing to publish: pack_lint found {len(problems)} problem(s) in {pack_dir}",
                                    *shown]))


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
    ap.add_argument("--force", action="store_true",
                    help="publish even when the content is unchanged since the catalog's version or an open publish PR")
    ap.add_argument("--repo", default=RESORTS_REPO)
    ap.add_argument("--accept-change", action="store_true",
                    help="label the PR accept-change: a big change from the previous version is intended (FEAT-264)")
    ap.add_argument("--requested-by", help="the game account that asked for this build (Build it, FEAT-245)")
    ap.add_argument("--run-url", help="the workflow run that built and publishes the pack (FEAT-245)")
    ap.add_argument("--dry-run", action="store_true",
                    help="zip and print the catalog entry and the PR branch; no fetch, no release, no PR")
    a = ap.parse_args(argv)
    if a.synth == bool(a.pack_dir):
        ap.error("give a pack_dir, or --synth")
    test = a.test or a.synth
    origin_main = lambda sha: on_origin_main(sha, fetch=not a.dry_run)   # noqa: E731 (a dry run reads the local ref)

    if a.synth:   # the synth is stamped with this checkout's pipeline: refuse before the two-minute build, not after
        why = stamp_why({"slug": SYNTH, "pipeline": pipeline_commit()}, origin_main)
        if why:
            raise SystemExit(f"refusing --synth: {why}; run it from a clean checkout of main")
    pack_dir = build_synth(os.path.join(paths.PACKS, SYNTH)) if a.synth else os.path.abspath(a.pack_dir)
    with open(os.path.join(pack_dir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    slug = meta["slug"]
    fmt = meta.get("formatVersion", 0)
    if fmt != FORMAT_VERSION:
        raise SystemExit(f"{pack_dir} is pack format {fmt}, this pipeline writes {FORMAT_VERSION}: rebuild it on main "
                         f"(python pipeline/build_pack.py {slug} <raw_dir> <out_dir>) before publishing")
    problem = stamp_problem(meta, origin_main)
    if problem:
        raise SystemExit(f"refusing to publish: {problem}")
    lint_refusal(pack_dir)          # local, so a dry run lints too; before any gh call, zip or upload
    pipeline = meta["pipeline"]
    if test:
        a.status, why, a.tier, report, cfg = "test", "test pack, not in the picker", None, None, {}
    else:
        a.status, why = report_status(pack_dir, meta, a.status)
        cfg_path = paths.config_path(slug)
        cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.isfile(cfg_path) else {}
        if cfg.get("source_only"):
            raise SystemExit(f"{slug} is a relocate source (source_only, FEAT-268), not a pack: it is not published")
        report = a.report or (os.path.join(pack_dir, "report.md") if os.path.isfile(os.path.join(pack_dir, "report.md")) else None)
    print(f"status {a.status} ({why})")

    # origin/main's catalog (fetched by on_origin_main), not this checkout's, which may be stale; a dry run reads
    # this checkout's as it is, so --synth can still say whether it changed
    if a.dry_run:
        cat_path = os.path.join(REPO, "catalog.json")
        catalog = json.load(open(cat_path, encoding="utf-8")) if os.path.isfile(cat_path) else {"resorts": []}
    else:
        catalog = json.loads(run(["git", "show", "origin/main:catalog.json"], cwd=REPO))
    # FEAT-241, FEAT-245: a rebuild that changed nothing is not published again (no release, no version). An entry
    # published before content keys existed has none, so the first rebuild after that publishes. A resort whose tier
    # or status changed (a re-plan, a report that now passes) is published again even with the same content.
    content = content_key(pack_dir)
    old = find_test_pack(catalog, slug, fmt) if test else find_resort(catalog, slug)
    where = f"{slug} at pack format {fmt}" if test else slug
    same_listing = test or (old and (old.get("tier"), old.get("status")) == (a.tier, a.status))
    if old and old["pack"].get("content") == content and same_listing and not a.force:
        print(f"{where} is unchanged since v{old['pack']['version']} (content {content}): "
              f"nothing to publish (--force publishes anyway)")
        return
    print(f"content {content}" + (f", v{old['pack']['version']} has {old['pack'].get('content') or 'no content key'}"
                                  if old else f", no {where} in the catalog yet"))
    if not a.dry_run and not a.force and (url := pending_same_content(slug, content, a.repo)):
        print(f"{url} is open with this content: nothing to publish")
        print(f"(content {content}; --force publishes anyway)")
        return
    tags = [] if a.dry_run else [r["tagName"] for r in json.loads(run(
        ["gh", "release", "list", "-R", a.repo, "--limit", "1000", "--json", "tagName"]) or "[]")]
    version = next_version(slug, tags, catalog)
    tag = release_tag(slug, version)

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
        entry["pack"]["content"] = content
        if a.dry_run:
            print(json.dumps(entry, indent=1))
            print(f"would upload draft release {tag} and open a PR from {publish_branch(slug, version)}")
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
        login = publisher_login()        # before the upload, so a gh that is not signed in leaves no draft behind
        trusted = login in maintainers()
        labels = (["automerge"] if trusted else []) + (["accept-change"] if a.accept_change else [])
        assets = [zip_path, os.path.join(pack_dir, "meta.json")] + ([report] if report else [])
        print(f"uploading draft release {tag} to {a.repo}")
        release_url = run(["gh", "release", "create", tag, *assets, "-R", a.repo, "--draft",
                           "--title", f"{meta['name']} v{version}", "--notes", notes])

        # the recipe that built it goes in the PR beside the catalog: config, node lists, plan, manifest, report;
        # RELEASES.md lists this publish's draft as out (the merge workflow publishes it before it merges)
        body = pr_body(entry, why=why, release_url=release_url, started_by=login, run_url=a.run_url,
                       requested_by=a.requested_by, new_resort=not test and old is None)
        try:
            releases = [r for r in list_releases(a.repo, run) if r.get("tag_name") != tag]
            releases.append(own_release(slug, version, f"{meta['name']} v{version}", size))
            pr = open_publish_pr(slug=slug, version=version, entry=entry, test=test, src_repo=REPO, labels=labels,
                                 body=body, repo=a.repo, report=report, releases=releases)
        except SystemExit as e:
            raise SystemExit(f"{e}\nThe draft release {tag} exists with nothing pointing at it: open the PR by hand, "
                             f"or delete the draft (gh release delete {tag} -R {a.repo} --yes)")
        print(f"opened {pr} (draft release {tag}): " + (
            "once checks pass it releases and merges itself, when the publish App is set up (publish-merge.yml)"
            if trusted else
            f"{login} is not in .github/maintainers.txt, so a maintainer approves it with the automerge label"))
        if not test and old is None:
            print(REBUILD_LIST)
        print(f"Without the App nothing merges itself: once checks pass, run gh release edit {tag} -R {a.repo} "
              f"--draft=false first, then merge the PR (never the merge button while the release is a draft)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
