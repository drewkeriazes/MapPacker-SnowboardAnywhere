#!/usr/bin/env python3
"""FEAT-243: a resort's hand content, from its folder here into its pack, without a new build stamp.

    python pipeline/pack_content.py <pack_dir> [--slug <slug>] [--resorts <resorts dir>]

The game knows nothing about a resort that its pack does not carry. What a person made by hand lives in
`resorts/<slug>/` (one home per file) and this step copies it into the pack:

- **landmarks** (`resorts/<slug>/landmarks.json`, a list of the game's `Landmark`, `game/src/world/Landmarks.ts`):
  into `meta.landmarks`, without each one's `note` (the home keeps it). No file: no `meta.landmarks`.
- **the start**, resolved here so the game just reads `meta.start`: a landmark with `start: true` (the rider
  `START_BACK_M` uphill of it, facing through it, label `Starts at <name>`, `source: "landmark"`), else
  `resorts/<slug>/start.json` (`{x, y, heading, label, source, note}`, heading in degrees clockwise from north;
  `source: "placed"`), else the start the build or gen_content.py wrote. That one is kept in `meta.baseStart` while
  a hand start covers it, so a rerun (or a dropped landmark) resolves from it again.
- **the main menu** (`resorts/<slug>/attract/`, the layout gen_content.py writes into a pack: `index.json` is the
  resort's entry, plus `shots.json`, the stills and the takes it lists): replaces the pack's `attract/` (a generated
  one included), only the listed files, and `meta.attract = {"generated": false}`. The copied `index.json` gets
  `"hand": true`, so gen_content.py leaves it alone and a later run with no hand folder takes it back out.
  A file listed but missing stops the step. No folder: the pack's generated `attract/`, if any, stays.

`write_meta(..., stamp=False)`: `meta.build` does not change, so a menu still rendered from this build stays valid.
The format does not change either: every key here is optional and a game that does not read it ignores it.
`build_resort.py`'s `content` stage runs it after gen_content.py; on its own it puts the content into a pack
built or published earlier.
"""
import argparse
import json
import math
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
from packwriter import write_meta  # noqa: E402

START_BACK_M = 15.0          # the rider spawns this far uphill of a start landmark (the game's old landmarkStart)
HAND_STARTS = ("landmark", "placed")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def read_landmarks(slug, resorts=None):
    """resorts/<slug>/landmarks.json, each without its `note`; [] without the file"""
    p = paths.landmarks_path(slug, resorts)
    if not os.path.isfile(p):
        return []
    out = _load(p)
    if not isinstance(out, list):
        raise SystemExit(f"{p}: a list of landmarks expected")
    for lm in out:
        for k in ("id", "name", "x", "y", "heading"):
            if k not in lm:
                raise SystemExit(f"{p}: landmark {lm.get('id', '?')} has no {k}")
    return [{k: v for k, v in lm.items() if k != "note"} for lm in out]


def read_placed(slug, resorts=None):
    p = paths.start_path(slug, resorts)
    if not os.path.isfile(p):
        return None
    s = _load(p)
    for k in ("x", "y", "heading"):
        if not isinstance(s.get(k), (int, float)):
            raise SystemExit(f"{p}: {k} is not a number")
    return s


def resolve_start(base, landmarks, placed):
    """-> (start, kind): kind "landmark", "placed" or "build" (base unchanged)"""
    lm = next((m for m in landmarks if m.get("start")), None)
    if lm:
        h = math.radians(lm["heading"])
        return {"x": round(lm["x"] - math.sin(h) * START_BACK_M, 2), "y": round(lm["y"] - math.cos(h) * START_BACK_M, 2),
                "heading": h, "label": f"Starts at {lm['name']}", "source": "landmark", "landmark": lm["id"]}, "landmark"
    if placed:
        s = {"x": placed["x"], "y": placed["y"], "heading": math.radians(placed["heading"]), "source": "placed"}
        if placed.get("label"):
            s["label"] = placed["label"]
        return s, "placed"
    return base, "build"


def attract_files(idx):
    """the files a resort's attract/index.json lists (besides itself)"""
    files = list(idx.get("ghosts") or []) + [f"{s}.jpg" for s in idx.get("stills") or []]
    if idx.get("shots"):
        files.append("shots.json")
    return list(dict.fromkeys(files))


def copy_attract(slug, pack_dir, resorts=None):
    """-> files copied, 0 when the resort has no hand-made menu, None when an earlier hand copy was taken out"""
    src = paths.attract_dir(slug, resorts)
    dst = os.path.join(pack_dir, "attract")
    ip = os.path.join(src, "index.json")
    if not os.path.isfile(ip):
        old = os.path.join(dst, "index.json")
        if os.path.isfile(old) and _load(old).get("hand"):
            shutil.rmtree(dst)
            return None
        return 0
    idx = _load(ip)
    files = attract_files(idx)
    for f in files:
        if os.path.basename(f) != f or not os.path.isfile(os.path.join(src, f)):
            raise SystemExit(f"{f} is listed in resorts/{slug}/attract/index.json but is not in that folder")
    if os.path.isdir(dst):
        shutil.rmtree(dst)        # a take dropped from the index must not linger in the pack
    os.makedirs(dst)
    for f in files:
        shutil.copyfile(os.path.join(src, f), os.path.join(dst, f))
    idx = {k: v for k, v in idx.items() if k != "generated"}
    idx["hand"] = True
    with open(os.path.join(dst, "index.json"), "w", encoding="utf-8") as f:
        json.dump(idx, f, indent=2)
        f.write("\n")
    return len(files)


def apply(pack_dir, slug=None, resorts=None, log=print):
    """copy the hand content of the pack's resort into it; -> a summary dict"""
    mp = os.path.join(pack_dir, "meta.json")
    meta = _load(mp)
    slug = slug or meta.get("slug")
    if not slug:
        raise SystemExit(f"{mp} has no slug: pass --slug")
    landmarks = read_landmarks(slug, resorts)
    if landmarks:
        meta["landmarks"] = landmarks
    else:
        meta.pop("landmarks", None)
    cur = meta.get("start")
    base = meta.get("baseStart", cur) if (cur or {}).get("source") in HAND_STARTS else cur
    start, kind = resolve_start(base, landmarks, read_placed(slug, resorts))
    meta.pop("baseStart", None)
    if kind != "build":
        meta["baseStart"] = base
    if start:
        meta["start"] = start
    copied = copy_attract(slug, pack_dir, resorts)
    if copied:
        meta["attract"] = {"generated": False}
    elif copied is None:
        meta.pop("attract", None)
        log("  the hand-made menu copied earlier is gone from the resort folder: removed from the pack too "
            "(gen_content.py makes a generated one: build_resort.py --force content)")
    write_meta(pack_dir, meta, stamp=False)      # same build: a still rendered from it stays valid
    out = {"slug": slug, "landmarks": len(landmarks), "start": kind, "attract": copied or 0}
    said = {"landmark": "a landmark", "placed": "start.json", "build": "the build"}[kind]
    log(f"{slug}: {out['landmarks']} landmarks, start from {said}"
        + (f" ({start.get('label')})" if kind != "build" and start.get("label") else "")
        + (f", hand-made menu ({copied} files)" if copied else "") + f"; build {meta.get('build')} kept")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pack_dir")
    ap.add_argument("--slug", help="the resort (default: the pack's meta.json slug)")
    ap.add_argument("--resorts", help="the folder of resort folders (default resorts/)")
    a = ap.parse_args(argv)
    if not os.path.isfile(os.path.join(a.pack_dir, "meta.json")):
        ap.error(f"no meta.json in {a.pack_dir}")
    apply(a.pack_dir, a.slug, a.resorts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
