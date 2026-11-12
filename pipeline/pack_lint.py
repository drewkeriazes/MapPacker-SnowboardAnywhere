"""FEAT-272: check a pack's files against its meta.json and the size ceilings, before it is published.

    python pipeline/pack_lint.py <pack folder or .zip>     prints each problem, exit 1 if there are any

A set or key that meta.json does not name is not checked. `debug/` is not counted (publish_pack.py leaves it out)."""
import json
import os
import sys
import tempfile
import zipfile

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from packwriter import FORMAT_VERSION  # noqa: E402

MAX_PACK_BYTES = 600_000_000   # about twice today's largest: Vail 287 MB, 2,135 files, 39,201 per km2
MAX_FILES = 5_000                # about twice today's largest (Vail, 2,135 files)
MAX_TREES_PER_KM2 = 80_000       # about twice today's densest (39,201 per km2)
TILE_SETS = ("terrain.fine", "terrain.coarse", "terrain.mid", "terrain.far", "mask", "ao", "dir", "moguls")
RECORD_BYTES = 24               # one instance: six float32
INSTANCE_DIRS = (("trees", "treeCells"), ("shrubs", "shrubCells"), ("rocks", "rockCells"), ("farTrees", "farTreeCells"))


def _load_json(pack_dir, name, problems):
    try:
        with open(os.path.join(pack_dir, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        problems.append(f"{name}: cannot be read ({e})")
        return None


def _decode(path):
    with Image.open(path) as im:
        im.load()
        return im.size


def _lint_tile_set(pack_dir, key, meta, problems):
    node = meta
    for part in key.split("."):
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, dict) or "tilesX" not in node or "tilesY" not in node:
        return
    folder = key.split(".")[-1]
    sizes = set()
    for tx in range(node["tilesX"]):
        for ty in range(node["tilesY"]):
            rel = f"{folder}/{tx}_{ty}.png"
            path = os.path.join(pack_dir, rel)
            if not os.path.isfile(path):
                problems.append(f"{rel}: missing ({key} has {node['tilesX']} x {node['tilesY']} tiles)")
                continue
            try:
                sizes.add(_decode(path))
            except Exception as e:
                problems.append(f"{rel}: does not decode ({e})")
    if len(sizes) > 1:
        problems.append(f"{folder}/: tiles differ in size ({sorted(sizes)})")


def _lint_instances(pack_dir, meta, problems):
    inst = meta.get("instances") or {}
    for folder, key in INSTANCE_DIRS:
        for cell in inst.get(key) or []:
            rel = f"{folder}/{cell}.bin"
            path = os.path.join(pack_dir, rel)
            if not os.path.isfile(path):
                problems.append(f"{rel}: missing (named in instances.{key})")
            elif os.path.getsize(path) % RECORD_BYTES:
                problems.append(f"{rel}: {os.path.getsize(path)} bytes is not a multiple of {RECORD_BYTES}")


def _lint_stands(pack_dir, meta, problems):
    for cell in (meta.get("stands") or {}).get("cells") or []:
        rel = f"stands/{cell}.png"
        path = os.path.join(pack_dir, rel)
        if not os.path.isfile(path):
            problems.append(f"{rel}: missing (named in stands.cells)")
            continue
        try:
            _decode(path)
        except Exception as e:
            problems.append(f"{rel}: does not decode ({e})")


def _lint_ceilings(pack_dir, meta, problems):
    total = files = 0
    for root, dirs, names in os.walk(pack_dir):
        if os.path.abspath(root) == os.path.abspath(pack_dir):
            dirs[:] = [d for d in dirs if d != "debug"]
        for n in names:
            files += 1
            total += os.path.getsize(os.path.join(root, n))
    if total > MAX_PACK_BYTES:
        problems.append(f"pack is {total} bytes, over the {MAX_PACK_BYTES} ceiling")
    if files > MAX_FILES:
        problems.append(f"pack has {files} files, over the {MAX_FILES} ceiling")
    b = meta.get("bounds")
    if b:
        area = (b["maxX"] - b["minX"]) * (b["maxY"] - b["minY"]) / 1e6
        trees = (meta.get("instances") or {}).get("treeCount", 0) + (meta.get("stands") or {}).get("stems", 0)
        if area > 0 and trees / area > MAX_TREES_PER_KM2:
            problems.append(f"{trees / area:.0f} trees per km2 ({trees} on {area:.1f} km2), over the {MAX_TREES_PER_KM2} ceiling")


def lint(pack_dir: str) -> list:
    """Problems found in the pack folder, as strings; empty when it is clean."""
    problems = []
    meta = _load_json(pack_dir, "meta.json", problems)
    if meta is None:
        return problems
    if meta.get("formatVersion") != FORMAT_VERSION:
        problems.append(f"meta.json formatVersion is {meta.get('formatVersion')}, this pipeline writes {FORMAT_VERSION}")
    for key in TILE_SETS:
        _lint_tile_set(pack_dir, key, meta, problems)
    _lint_instances(pack_dir, meta, problems)
    _lint_stands(pack_dir, meta, problems)
    features = _load_json(pack_dir, "features.json", problems)
    if features is not None:
        for k in ("runs", "lifts"):
            if not isinstance(features.get(k), list):
                problems.append(f"features.json: {k} is not a list")
    if os.path.isfile(os.path.join(pack_dir, "report.json")):
        report = _load_json(pack_dir, "report.json", problems)
        if report is not None and report.get("build") != meta.get("build"):
            problems.append(f"report.json is for build {report.get('build')}, meta.json is build {meta.get('build')}")
    _lint_ceilings(pack_dir, meta, problems)
    return problems


def lint_zip(zip_path: str) -> list:
    """Extract a published pack zip to a temp folder and lint it."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)
        return lint(tmp)


def main(argv):
    if len(argv) != 2:
        print("usage: pack_lint.py <pack folder or .zip>")
        return 2
    target = argv[1]
    problems = lint_zip(target) if target.lower().endswith(".zip") else lint(target)
    for p in problems:
        print(p)
    if not problems:
        print(f"{target}: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
