#!/usr/bin/env python3
"""FEAT-240 public repo guards: mistakes that cannot be undone once pushed to a public repo. Ported from
SnowboardAnywhere's tools/ci/public_guards.py (FEAT-172); the game's Spotify rule is replaced by this repo's own:
packs and raw data stay out of git.

python tools/ci/public_guards.py --base <ref> [--head <ref>]

Fails (exit 1) on:
  - a tracked .env file (other than .env.example), anywhere in the tree at <head>;
  - a file the PR adds or changes under packs/ (other than packs/.gitkeep) or raw/: packs go out as release assets
    (publish_pack.py) and raw downloads stay at SBA_RAW_ROOT;
  - a raster, point cloud, archive or other data file the PR adds or changes (.gitignore lists most of them, and
    `git add -f` gets past it);
  - any file the PR adds or changes that is over 2 MB (the biggest manifest is under 0.5 MB);
  - an image the PR adds or changes that is over 1 MB, or outside docs/ and reports/.
Secrets in general are gitleaks' job (a separate step in .github/workflows/checks.yml).
Standard library only.
"""
import argparse
import re
import subprocess
import sys

IMAGE = re.compile(r"\.(png|jpe?g|webp|gif|bmp|avif)$", re.I)
DATA = re.compile(r"\.(tiff?|laz|las|copc|pbf|osm|zip|7z|gz|tar|bin|npy|npz|gpkg|shp|dbf|shx|vrt|nc|h5|hdf|parquet)$", re.I)
MAX_IMAGE = 1024 * 1024
MAX_FILE = 2 * 1024 * 1024
IMAGE_DIRS = ("docs/", "reports/")


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def annotate(kind, msg, path=None, line=None):
    loc = f" file={path}" + (f",line={line}" if line else "") if path else ""
    print(f"::{kind}{loc}::{msg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    fails = 0

    # 1. .env files, across the tree at head
    for path in git("ls-tree", "-r", "--name-only", a.head).splitlines():
        name = path.rsplit("/", 1)[-1]
        if name.startswith(".env") and name != ".env.example":
            fails += 1
            annotate("error", "A .env file is tracked. Remove it from git (it may hold keys) and rotate anything in it.", path)

    # 2. what the PR adds or changes
    for path in git("diff", "--name-only", "--diff-filter=AM", f"{a.base}...{a.head}").splitlines():
        size = int(git("cat-file", "-s", f"{a.head}:{path}").strip())
        if (path.startswith("packs/") and path != "packs/.gitkeep") or path.startswith("raw/"):
            fails += 1
            annotate("error", "Packs and raw data never go in git: packs go out as release assets (publish_pack.py), "
                     "raw downloads stay at SBA_RAW_ROOT. Drop this file from the branch.", path)
            continue
        if DATA.search(path):
            fails += 1
            annotate("error", "A data file (raster, point cloud, archive or array) in git. It belongs in a release asset "
                     "or under SBA_RAW_ROOT; drop it from the branch.", path)
            continue
        if IMAGE.search(path):
            if size > MAX_IMAGE:
                fails += 1
                annotate("error", f"Image is {size / 1048576:.1f} MB, over the 1 MB limit. Save it as a JPEG or crop it.", path)
            if not path.startswith(IMAGE_DIRS):
                fails += 1
                annotate("error", f"Images go under {', '.join(IMAGE_DIRS)}; this one is elsewhere.", path)
        elif size > MAX_FILE:
            fails += 1
            annotate("error", f"File is {size / 1048576:.1f} MB, over the 2 MB limit for anything in git. Big outputs "
                     "go in a release asset.", path)

    print(f"public repo guards: {fails} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
