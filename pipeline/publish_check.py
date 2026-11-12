"""FEAT-272: check a publish PR's draft release zip against the catalog entry the PR adds.

    python pipeline/publish_check.py --base <catalog.json> --head <catalog.json> --repo <owner/name>

For each entry in head that is new or whose pack differs from base, downloads release `<slug>-v<version>`'s
`<slug>.zip` (drafts included, with a write token), checks its size and sha256 against the entry, then lints it
(pack_lint.py). Prints the problems per slug, exit 1 if there are any. CI runs this from main's copy of pipeline/."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pack_lint import lint_zip  # noqa: E402
from publish_pack import all_entries  # noqa: E402


def _key(e):
    return (e.get("slug"), (e.get("pack") or {}).get("formatVersion"))


def changed_entries(base: dict, head: dict) -> list:
    """entries of head (resorts, then test) whose (slug, formatVersion) is new or whose pack differs from base"""
    before = {_key(e): e.get("pack") for e in all_entries(base)}
    return [e for e in all_entries(head) if _key(e) not in before or before[_key(e)] != e.get("pack")]


def zip_problems(entry: dict, zip_path: str) -> list:
    """the zip's size and sha256 against the entry's pack.bytes and pack.sha256"""
    pack = entry.get("pack") or {}
    problems = []
    size = os.path.getsize(zip_path)
    if size != pack.get("bytes"):
        problems.append(f"bytes: the zip is {size}, the catalog says {pack.get('bytes')}")
    h = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    if h.hexdigest() != pack.get("sha256"):
        problems.append(f"sha256: the zip is {h.hexdigest()}, the catalog says {pack.get('sha256')}")
    return problems


def download(entry: dict, repo: str, dest: str) -> str:
    """gh release download of the entry's zip into dest; returns its path (a draft needs a write token)"""
    slug, version = entry["slug"], entry["pack"]["version"]
    subprocess.run(["gh", "release", "download", f"{slug}-v{version}", "-p", f"{slug}.zip", "-D", dest,
                    "-R", repo, "--clobber"], check=True)
    return os.path.join(dest, f"{slug}.zip")


def check(base: dict, head: dict, repo: str, fetch=download) -> dict:
    """{slug: problems} for every changed entry; `fetch(entry, repo, dest)` downloads the zip"""
    out = {}
    for e in changed_entries(base, head):
        with tempfile.TemporaryDirectory() as tmp:
            try:
                path = fetch(e, repo, tmp)
            except (subprocess.CalledProcessError, OSError) as err:
                out[e["slug"]] = [f"download failed: {err}"]
                continue
            problems = zip_problems(e, path)
            try:
                problems += lint_zip(path)
            except zipfile.BadZipFile:
                problems.append("not a zip file")
            out[e["slug"]] = problems
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args(argv)
    with open(a.base, encoding="utf-8") as f:
        base = json.load(f)
    with open(a.head, encoding="utf-8") as f:
        head = json.load(f)
    results = check(base, head, a.repo)
    if not results:
        print("no changed catalog entry to check")
    bad = False
    for slug, problems in results.items():
        if problems:
            bad = True
            print(f"{slug}: {len(problems)} problem(s)")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"{slug}: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
