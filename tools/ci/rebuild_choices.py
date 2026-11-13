"""FEAT-297: the Build pack form's rebuild list (.github/workflows/build-pack.yml, input `rebuild`).

    python tools/ci/rebuild_choices.py           print the list the catalog gives, and whether the workflow has it
    python tools/ci/rebuild_choices.py --write   write it into build-pack.yml

GitHub's workflow_dispatch choice lists are static, so the list lives in the workflow file: first NEW (build a new
resort from the typed slug, name and osm_id), then every resort in catalog.json that can be rebuilt (a config in
resorts/, not a relocate source). A publish PR can't update it: the publisher App has no Workflows permission and
publish-merge.yml merges only PRs that change the publish file set. So after a new resort's publish PR merges,
run this with --write in a PR of its own (publish_pack.py says so); until then the new resort is rebuilt by typing
its slug. pipeline/tests/test_workflows.py checks that every entry on the list can be rebuilt.
"""
import argparse, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "build-pack.yml")
CATALOG = os.path.join(ROOT, "catalog.json")
NEW = "(new resort: type the slug below)"
MARKER = "# rebuild_choices.py writes this list from catalog.json"


def rebuildable(slug, resorts):
    path = os.path.join(resorts, slug, f"{slug}.json")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        return not json.load(f).get("source_only")


def choices(catalog=CATALOG, resorts=None):
    """[NEW, slug, ...]: the catalog's resorts (not its test packs) that have a config, sorted"""
    resorts = resorts or os.path.join(ROOT, "resorts")
    with open(catalog, encoding="utf-8") as f:
        cat = json.load(f)
    return [NEW] + sorted({r["slug"] for r in cat.get("resorts") or [] if rebuildable(r["slug"], resorts)})


def read_list(text):
    """the options under MARKER in the workflow text"""
    lines = text.split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.strip() == MARKER)
    out = []
    for ln in lines[i + 1:]:
        m = re.match(r"^\s*-\s+(.*)$", ln)
        if not m:
            break
        out.append(m.group(1).strip().strip("'\""))
    return out


def write_list(text, items):
    """the workflow text with the options under MARKER replaced by `items`, at the marker's indent"""
    lines = text.split("\n")
    i = next(k for k, ln in enumerate(lines) if ln.strip() == MARKER)
    indent = lines[i][:len(lines[i]) - len(lines[i].lstrip())]
    j = i + 1
    while j < len(lines) and re.match(r"^\s*-\s+", lines[j]):
        j += 1
    return "\n".join(lines[:i + 1] + [f"{indent}- '{s}'" if s == NEW else f"{indent}- {s}" for s in items] + lines[j:])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true", help="write the list into build-pack.yml")
    a = ap.parse_args(argv)
    want = choices()
    with open(WORKFLOW, encoding="utf-8") as f:
        text = f.read()
    have = read_list(text)
    print("\n".join(want))
    if have == want:
        print("build-pack.yml has this list")
        return 0
    if a.write:
        with open(WORKFLOW, "w", encoding="utf-8", newline="\n") as f:
            f.write(write_list(text, want))
        print("wrote it into build-pack.yml: commit it in a PR")
        return 0
    missing, extra = sorted(set(want) - set(have)), sorted(set(have) - set(want))
    print("build-pack.yml differs" + (f"; missing {', '.join(missing)}" if missing else "") +
          (f"; not in the catalog {', '.join(extra)}" if extra else "") + ": run with --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
