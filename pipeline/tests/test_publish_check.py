"""FEAT-272: publish_check.py picks the catalog entries a PR changed and checks their draft zips."""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from publish_check import changed_entries, zip_problems  # noqa: E402


def entry(slug, version, fmt=1, size=3, sha256="0" * 64):
    return {"slug": slug, "pack": {"version": version, "formatVersion": fmt, "bytes": size, "sha256": sha256,
                                   "url": f"https://example.invalid/{slug}-v{version}/{slug}.zip"}}


def test_changed_entries_finds_a_new_version_only():
    base = {"resorts": [entry("vail", 3)], "test": [entry("synth", 2)]}
    head = {"resorts": [entry("vail", 4)], "test": [entry("synth", 2)]}
    assert [(e["slug"], e["pack"]["version"]) for e in changed_entries(base, head)] == [("vail", 4)]


def test_changed_entries_finds_a_new_resort_and_a_new_format_beside_the_old():
    base = {"resorts": [], "test": [entry("synth", 2, fmt=1)]}
    head = {"resorts": [entry("demo", 1)], "test": [entry("synth", 2, fmt=1), entry("synth", 3, fmt=2)]}
    got = [(e["slug"], e["pack"]["formatVersion"]) for e in changed_entries(base, head)]
    assert got == [("demo", 1), ("synth", 2)]


def test_zip_problems_catches_size_and_hash(tmp_path):
    z = tmp_path / "demo.zip"
    z.write_bytes(b"abc")
    e = entry("demo", 1, size=3, sha256=hashlib.sha256(b"abc").hexdigest())
    assert zip_problems(e, str(z)) == []
    assert any("sha256" in p for p in zip_problems({**e, "pack": {**e["pack"], "sha256": "0" * 64}}, str(z)))
    assert any("bytes" in p for p in zip_problems({**e, "pack": {**e["pack"], "bytes": 4}}, str(z)))


def test_check_runs_size_hash_and_lint_on_the_downloaded_zip_without_gh(tmp_path):
    import publish_check
    data = b"abc"
    e = entry("demo", 1, size=3, sha256=hashlib.sha256(data).hexdigest())

    def fake_download(ent, repo, dest):
        assert repo == "o/r"
        p = os.path.join(dest, f"{ent['slug']}.zip")
        with open(p, "wb") as f:
            f.write(data)
        return p

    out = publish_check.check({"resorts": [], "test": []}, {"resorts": [e], "test": []}, "o/r", fetch=fake_download)
    assert list(out) == ["demo"]
    assert out["demo"], "b'abc' is not a zip: the check must say so"
    assert not any("bytes" in p or "sha256" in p for p in out["demo"])


def good_zip_fetch(data=b"abc"):
    def fetch(ent, repo, dest):
        p = os.path.join(dest, f"{ent['slug']}.zip")
        with open(p, "wb") as f:
            f.write(data)
        return p
    return fetch


def test_check_flags_a_url_that_is_not_this_repos_release():
    import publish_check
    from publish_pack import asset_url
    ok = {**entry("demo", 1), "pack": {**entry("demo", 1)["pack"], "url": asset_url("demo", 1, "o/r")}}
    out = publish_check.check({"resorts": []}, {"resorts": [ok]}, "o/r", fetch=good_zip_fetch())
    assert not any(p.startswith("url") for p in out["demo"])
    evil = {**ok, "pack": {**ok["pack"], "url": "https://evil.invalid/demo.zip"}}
    out = publish_check.check({"resorts": []}, {"resorts": [evil]}, "o/r", fetch=good_zip_fetch())
    assert any(p.startswith("url") and "evil.invalid" in p for p in out["demo"])
    other_tag = {**ok, "pack": {**ok["pack"], "url": asset_url("demo", 2, "o/r")}}
    out = publish_check.check({"resorts": []}, {"resorts": [other_tag]}, "o/r", fetch=good_zip_fetch())
    assert any(p.startswith("url") for p in out["demo"])


def test_check_refuses_a_bad_slug_or_version_before_any_download():
    import publish_check

    def never(ent, repo, dest):
        raise AssertionError("downloaded an entry whose slug or version is not checked")
    for slug, version in (("../x", 1), ("Demo", 1), ("-x", 1), ("a/b", 1), (None, 1), ("demo\n", 1),
                          ("demo", 0), ("demo", -1), ("demo", "1"), ("demo", 1.0), ("demo", True), ("demo", None)):
        e = {"slug": slug, "pack": {"version": version, "formatVersion": 1, "bytes": 3, "sha256": "0" * 64}}
        out = publish_check.check({"resorts": []}, {"resorts": [e]}, "o/r", fetch=never)
        assert len(out) == 1 and len(next(iter(out.values()))) == 1, (slug, version)
