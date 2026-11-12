"""FEAT-271: release tags `<slug>/v<N>`, and RELEASES.md, this repo's releases grouped by resort.

    python pipeline/releases.py index [--repo R]              write RELEASES.md from the releases and catalog.json
    python pipeline/releases.py migrate [--repo R] [--apply]  move the old `<slug>-v<N>` releases to `<slug>/v<N>`

GitHub Releases has no folders: a tag `vail/v3` groups Vail's versions in the Releases page's "Find a release"
(type `vail/`), and RELEASES.md (linked from the README) lists every resort with its versions, latest first.
publish_pack.py writes RELEASES.md into each publish PR and publish_merge.py rewrites it in the refresh onto main,
so it is never pushed on its own. It lists published releases only, plus the publish PR's own draft.

`migrate` (one off, FEAT-271): for each release whose tag is the old `<slug>-v<N>`, makes the git tag `<slug>/v<N>`
at the same commit, moves the release to it and deletes the old tag; then rewrites this checkout's catalog.json
urls to the new tags and writes RELEASES.md, for the migration PR. Without --apply it prints the plan and changes
nothing on GitHub. The old download urls stop working when a release moves: merge the migration PR right after.
"""
import argparse, json, os, re, sys, time
from typing import Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

SLUG = r"[a-z0-9][a-z0-9-]*"
TAG = re.compile(rf"^({SLUG})/v([1-9][0-9]*)$")
OLD_TAG = re.compile(rf"^({SLUG})-v([1-9][0-9]*)$")      # before FEAT-271
INDEX = "RELEASES.md"
FIELDS = "{tag_name, name, draft, published_at, created_at, assets: [.assets[] | {name, size}]}"


def release_tag(slug: str, version: int) -> str:
    return f"{slug}/v{version}"


def parse_tag(tag: str) -> tuple[str, int] | None:
    """(slug, version) of a `<slug>/v<N>` tag, or of an old `<slug>-v<N>` one; None for anything else"""
    m = TAG.match(tag or "") or OLD_TAG.match(tag or "")
    return (m.group(1), int(m.group(2))) if m else None


def list_releases(repo: str, run: Callable) -> list[dict]:
    """every release of `repo`, drafts included when gh's token can push (`run` is publish_pack.run)"""
    out = run(["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate", "--jq", f".[] | {FIELDS}"])
    return [json.loads(line) for line in (out or "").splitlines() if line.strip()]


def own_release(slug: str, version: int, title: str, size: int, day: str | None = None) -> dict:
    """the record list_releases would give for a publish's own draft, for a publisher whose token can't list it"""
    return {"tag_name": release_tag(slug, version), "name": title, "draft": True,
            "published_at": None, "created_at": (day or time.strftime("%Y-%m-%d", time.gmtime())) + "T00:00:00Z",
            "assets": [{"name": f"{slug}.zip", "size": size}]}


def _title_name(title: str) -> str:
    return re.sub(r"\s+v\d+$", "", title or "").strip()


def index_md(releases: list[dict], catalog: dict, repo: str, own: str | None = None) -> str:
    """RELEASES.md: the published releases (and the draft tagged `own`, the publish PR's), grouped by resort, newest
    version first, resorts by name, then the test packs. A version the catalog names is marked latest."""
    named = {}                                        # slug -> {"name", "test", "latest": {version: format}}
    for test, entries in ((False, catalog.get("resorts", [])), (True, catalog.get("test", []))):
        for e in entries:
            g = named.setdefault(e["slug"], {"name": e.get("name") or e["slug"], "test": test, "latest": {}})
            if e.get("pack"):
                g["latest"][e["pack"]["version"]] = e["pack"].get("formatVersion")
    groups = {}
    for r in releases:
        parsed = parse_tag(r.get("tag_name", ""))
        if not parsed or (r.get("draft") and r.get("tag_name") != own):
            continue
        slug, version = parsed
        zip_size = next((a.get("size") for a in r.get("assets") or [] if a.get("name") == f"{slug}.zip"), None)
        day = (r.get("published_at") or r.get("created_at") or "")[:10]
        groups.setdefault(slug, {})[version] = (zip_size, day, r.get("name") or "")
    lines = ["# Releases", "",
             "Every published pack, grouped by resort, newest version first. The game downloads the version marked "
             "latest, the one `catalog.json` names. Release tags are `<slug>/v<N>`: type `vail/` in the Releases "
             "page's search to see one resort. Written by `pipeline/releases.py` in each publish PR (FEAT-271); "
             "do not edit it by hand.", ""]

    def name_of(slug):
        if slug in named:
            return named[slug]["name"]
        titles = [t for _, _, t in groups[slug].values() if t]
        return _title_name(titles[0]) if titles else slug

    def section(slugs, level):
        for slug in sorted(slugs, key=lambda s: (name_of(s).lower(), s)):
            info = named.get(slug, {"latest": {}, "test": False})
            lines.extend([f"{level} {name_of(slug)}", ""])
            for v in sorted(groups[slug], reverse=True):
                size, day, _ = groups[slug][v]
                tag = release_tag(slug, v)
                notes = []
                if v in info["latest"]:
                    notes.append(f"latest for pack format {info['latest'][v]}" if info["test"] else "latest")
                bits = [f"[v{v}](https://github.com/{repo}/releases/tag/{tag})"]
                bits += [f"({', '.join(notes)})"] if notes else []
                tail = ", ".join(x for x in ([f"{size / 1e6:.0f} MB"] if size else []) + ([day] if day else []))
                lines.append(f"- {' '.join(bits)}" + (f" {tail}" if tail else ""))
            lines.append("")
    resorts = [s for s in groups if not named.get(s, {}).get("test")]
    tests = [s for s in groups if named.get(s, {}).get("test")]
    if not groups:
        lines.extend(["No packs published yet.", ""])
    section(resorts, "##")
    if tests:
        lines.extend(["## Test packs", "", "Not in the resort picker: the game's CI downloads them (FEAT-241).", ""])
        section(tests, "###")
    return "\n".join(lines).rstrip("\n") + "\n"


def write_index(path: str, releases: list[dict], catalog: dict, repo: str, own: str | None = None) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(index_md(releases, catalog, repo, own))


# --- migrate (one off) ---------------------------------------------------------------------------------------------

def migration_plan(releases: list[dict]) -> list[tuple[str, str]]:
    """(old tag, new tag) for each release still on an old `<slug>-v<N>` tag, oldest name first"""
    out = []
    for r in releases:
        tag = r.get("tag_name", "")
        m = OLD_TAG.match(tag)
        if m and not TAG.match(tag):
            out.append((tag, release_tag(m.group(1), int(m.group(2)))))
    return sorted(out)


def migrate_catalog(catalog: dict, repo: str) -> dict:
    """the catalog with every pack url at its release's `<slug>/v<N>` url (publish_pack.asset_url)"""
    from publish_pack import asset_url          # publish_pack imports this module
    out = json.loads(json.dumps(catalog))
    for key in ("resorts", "test"):
        for e in out.get(key, []):
            if e.get("pack"):
                e["pack"]["url"] = asset_url(e["slug"], e["pack"]["version"], repo)
    return out


def move_release(old: str, new: str, repo: str, run: Callable, draft: bool) -> None:
    """the git tag `new` at `old`'s commit, the release moved onto it, then `old` deleted (a draft has no git tag
    yet: only the release's tag name changes)"""
    if not draft:
        sha = run(["gh", "api", f"repos/{repo}/git/ref/tags/{old}", "--jq", ".object.sha"])
        try:
            have = run(["gh", "api", f"repos/{repo}/git/ref/tags/{new}", "--jq", ".object.sha"])
        except SystemExit:
            have = None
        if have and have != sha:
            raise SystemExit(f"tag {new} exists at {have}, not at {old}'s {sha}: not moving {old}")
        if not have:
            run(["gh", "api", "-X", "POST", f"repos/{repo}/git/refs", "-f", f"ref=refs/tags/{new}", "-f", f"sha={sha}"])
    run(["gh", "release", "edit", old, "-R", repo, "--tag", new])
    if not draft:
        run(["gh", "api", "-X", "DELETE", f"repos/{repo}/git/refs/tags/{old}"])


def migrate(repo: str, run: Callable, apply: bool, repo_dir: str = paths.REPO) -> list[tuple[str, str]]:
    releases = list_releases(repo, run)
    plan = migration_plan(releases)
    drafts = {r["tag_name"] for r in releases if r.get("draft")}
    for old, new in plan:
        print(f"{'moving' if apply else 'would move'} {old} -> {new}" + (" (draft)" if old in drafts else ""))
        if apply:
            move_release(old, new, repo, run, old in drafts)
    cat_path = os.path.join(repo_dir, "catalog.json")
    with open(cat_path, encoding="utf-8") as f:
        catalog = migrate_catalog(json.load(f), repo)
    with open(cat_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(catalog, f, indent=1)
        f.write("\n")
    write_index(os.path.join(repo_dir, INDEX), releases, catalog, repo)
    print(f"rewrote {cat_path} and {INDEX}" + ("" if apply else ": nothing on GitHub changed (--apply moves them)"))
    return plan


def main(argv=None) -> int:
    from publish_pack import RESORTS_REPO, run
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["index", "migrate"])
    ap.add_argument("--repo", default=RESORTS_REPO)
    ap.add_argument("--apply", action="store_true", help="with migrate: move the releases on GitHub")
    a = ap.parse_args(argv)
    if a.action == "migrate":
        migrate(a.repo, run, a.apply)
        return 0
    with open(os.path.join(paths.REPO, "catalog.json"), encoding="utf-8") as f:
        catalog = json.load(f)
    write_index(os.path.join(paths.REPO, INDEX), list_releases(a.repo, run), catalog, a.repo)
    print(f"wrote {INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
