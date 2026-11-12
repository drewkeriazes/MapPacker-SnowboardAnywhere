"""FEAT-222: publish_pack.py's zip and catalog, and a round trip through game/tools/get_pack.mjs (skipped when node
is not installed). The format constant shared with the game is checked against the game's main in test_contract.py."""
import json
import os
import shutil
import subprocess
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from packwriter import FORMAT_VERSION, write_meta  # noqa: E402
from publish_pack import (catalog_entry, content_key, find_test_pack, next_version, pack_files,  # noqa: E402
                          update_catalog, zip_pack)



def make_pack(root, slug="demo", fmt=FORMAT_VERSION):
    d = root / slug
    (d / "fine").mkdir(parents=True)
    (d / "debug").mkdir()
    (d / "fine" / "0_0.png").write_bytes(b"\x89PNG" + bytes(range(256)) * 40)
    (d / "debug" / "species.png").write_bytes(b"debug")
    (d / ".catalog.json").write_text("{}")
    write_meta(str(d), {"version": 1, "formatVersion": fmt, "slug": slug, "name": "Demo Mountain", "lonlat": [-106, 39]})
    return d


def test_zip_is_stored_repeatable_and_leaves_out_debug(tmp_path):
    pack = make_pack(tmp_path / "packs")
    assert pack_files(str(pack)) == ["fine/0_0.png", "meta.json"]
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    size, sha = zip_pack(str(pack), str(a))
    assert (size, sha) == zip_pack(str(pack), str(b))
    with zipfile.ZipFile(a) as z:
        assert z.namelist() == ["fine/0_0.png", "meta.json"]
        assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())


def test_next_version_skips_deleted_releases_and_other_resorts():
    cat = {"resorts": [{"slug": "vail", "pack": {"version": 2}}]}
    assert next_version("vail", ["vail-v1", "vail-v3", "vail-east-v9", "bigsky-v4"], cat) == 4
    assert next_version("bigsky", [], cat) == 1


def test_catalog_replaces_the_resort_and_sorts_by_name():
    meta = {"slug": "vail", "name": "Vail", "formatVersion": FORMAT_VERSION, "build": "b1", "lonlat": [-106.35, 39.6]}
    e = catalog_entry(meta, {"region": "Colorado", "country": "US"}, version=2, size=10, sha256="ab", pipeline="abc1234",
                      tier="gold", status="preview", report=None)
    assert e["pack"]["url"].endswith("/releases/download/vail-v2/vail.zip")
    cat = {"resorts": [{"slug": "vail", "name": "Vail", "pack": {"version": 1, "formatVersion": 0}},
                       {"slug": "bigsky", "name": "Big Sky", "pack": {"version": 1, "formatVersion": FORMAT_VERSION}}]}
    out = update_catalog(cat, e)
    assert [r["slug"] for r in out["resorts"]] == ["bigsky", "vail"]
    assert out["resorts"][1]["pack"]["version"] == 2 and out["formatVersion"] == FORMAT_VERSION


def test_content_key_ignores_the_build_stamps_but_not_the_content(tmp_path):
    pack = make_pack(tmp_path / "a")
    key = content_key(str(pack))
    write_meta(str(pack), json.load(open(pack / "meta.json")))      # a fresh build and pipeline stamp
    assert content_key(str(pack)) == key
    (pack / "debug" / "species.png").write_bytes(b"other debug")    # not in the zip, not in the key
    assert content_key(str(pack)) == key
    (pack / "fine" / "0_0.png").write_bytes(b"\x89PNG changed")
    assert content_key(str(pack)) != key


def synth_entry(version, fmt, content="c1"):
    meta = {"slug": "synth", "name": "Synthetic test mountain", "formatVersion": fmt, "build": "b", "lonlat": [0, 0]}
    e = catalog_entry(meta, {}, version=version, size=1, sha256=f"s{version}", pipeline="p", tier=None,
                      status="test", report=None)
    e["pack"]["content"] = content
    return e


def test_test_packs_stay_out_of_the_picker_one_per_format():
    resorts = {"formatVersion": FORMAT_VERSION,
               "resorts": [{"slug": "vail", "name": "Vail", "pack": {"version": 1, "formatVersion": FORMAT_VERSION}}]}
    cat = update_catalog(resorts, synth_entry(1, FORMAT_VERSION), test=True)
    assert [r["slug"] for r in cat["resorts"]] == ["vail"] and [t["pack"]["version"] for t in cat["test"]] == [1]
    # a newer pack format goes beside the old one (the game's main keeps its own); the same format replaces it
    cat = update_catalog(cat, synth_entry(2, FORMAT_VERSION + 1), test=True)
    cat = update_catalog(cat, synth_entry(3, FORMAT_VERSION, "c2"), test=True)
    assert [(t["pack"]["formatVersion"], t["pack"]["version"]) for t in cat["test"]] == \
        [(FORMAT_VERSION, 3), (FORMAT_VERSION + 1, 2)]
    assert find_test_pack(cat, "synth", FORMAT_VERSION)["pack"]["content"] == "c2"
    assert find_test_pack(cat, "synth", FORMAT_VERSION + 2) is None
    # the catalog's formatVersion is the resorts', a test pack does not move it; a resort publish keeps the tests
    assert cat["formatVersion"] == FORMAT_VERSION
    vail = catalog_entry({"slug": "vail", "name": "Vail", "formatVersion": FORMAT_VERSION}, {}, version=2, size=1,
                         sha256="v", pipeline="p", tier="gold", status="preview", report=None)
    assert update_catalog(cat, vail)["test"] == cat["test"]
    assert next_version("synth", ["synth-v1"], cat) == 4


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_get_pack_installs_the_test_pack_at_its_own_format(tmp_path, game_file):
    tool = game_file("game", "tools", "get_pack.mjs")
    if "catalog.test" not in open(tool, encoding="utf-8").read():
        pytest.skip("the game's get_pack.mjs predates test packs (FEAT-241)")
    pack = make_pack(tmp_path / "src", slug="synth")
    zpath = tmp_path / "synth.zip"
    size, sha = zip_pack(str(pack), str(zpath))
    cat = {"resorts": []}
    for version, fmt, s in [(1, FORMAT_VERSION, sha), (2, FORMAT_VERSION + 1, "0" * 64)]:
        e = synth_entry(version, fmt)
        e["pack"].update(sha256=s, bytes=size, url=str(zpath))
        cat = update_catalog(cat, e, test=True)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(cat))
    run = lambda *a: subprocess.run(["node", tool, "synth", "--catalog", str(catalog), *a], capture_output=True, text=True)
    r = run("--sha256")
    assert (r.returncode, r.stdout.strip()) == (0, sha), r.stderr
    packs = tmp_path / "packs"
    r = run("--packs", str(packs))
    assert r.returncode == 0, r.stderr
    assert json.load(open(packs / "synth" / ".catalog.json"))["version"] == 1


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_get_pack_installs_a_published_zip(tmp_path, game_file):
    pack = make_pack(tmp_path / "src")
    zpath = tmp_path / "demo.zip"
    size, sha = zip_pack(str(pack), str(zpath))
    entry = catalog_entry(json.load(open(pack / "meta.json")), {}, version=1, size=size, sha256=sha, pipeline="x",
                          tier="gold", status="preview", report=None)
    entry["pack"]["url"] = str(zpath)            # get_pack reads a local path the same as a URL
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(update_catalog({}, entry)))
    packs = tmp_path / "packs"
    tool = game_file("game", "tools", "get_pack.mjs")
    run = lambda *a: subprocess.run(["node", tool, "demo", "--catalog", str(catalog), "--packs", str(packs), *a],
                                    capture_output=True, text=True)
    r = run()
    assert r.returncode == 0, r.stderr
    assert (packs / "demo" / "fine" / "0_0.png").read_bytes() == (pack / "fine" / "0_0.png").read_bytes()
    assert not (packs / "demo" / "debug").exists()
    assert json.load(open(packs / "demo" / ".catalog.json"))["sha256"] == sha
    assert json.load(open(packs / "index.json")) == {"packs": ["demo"], "names": {"demo": "Demo Mountain"}}
    assert "already" in run().stdout
    # a bad checksum is refused and leaves the installed pack alone
    entry["pack"]["sha256"] = "0" * 64
    entry["pack"]["version"] = 2
    catalog.write_text(json.dumps(update_catalog({}, entry)))
    r = run()
    assert r.returncode == 1 and "sha256" in r.stderr
    assert (packs / "demo" / "meta.json").exists() and not any(p.name.startswith(".demo") for p in packs.iterdir())
    # a pack built on this PC (no catalog marker) is only replaced with --force
    os.remove(packs / "demo" / ".catalog.json")
    entry["pack"]["sha256"] = sha
    catalog.write_text(json.dumps(update_catalog({}, entry)))
    assert "--force" in run().stderr
    assert run("--force").returncode == 0
