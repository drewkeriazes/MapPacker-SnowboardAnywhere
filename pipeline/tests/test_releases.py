"""FEAT-271: release tags `<slug>/v<N>`, RELEASES.md and the one-off migration of the old `<slug>-v<N>` releases."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import releases  # noqa: E402
from publish_pack import asset_url, next_version  # noqa: E402
from releases import index_md, migrate_catalog, migration_plan, parse_tag, release_tag  # noqa: E402

REPO = "o/r"


def rel(tag, size=None, day="2026-11-12", draft=False, name=None):
    slug = (parse_tag(tag) or (tag,))[0]
    return {"tag_name": tag, "name": name or tag, "draft": draft, "published_at": None if draft else f"{day}T10:00:00Z",
            "created_at": f"{day}T09:00:00Z", "assets": [{"name": "meta.json", "size": 10}] +
            ([{"name": f"{slug}.zip", "size": size}] if size else [])}


def entry(slug, name, version, fmt=1):
    return {"slug": slug, "name": name, "pack": {"version": version, "formatVersion": fmt}}


def test_tags_are_slug_slash_version_and_the_old_ones_still_parse():
    assert release_tag("vail", 3) == "vail/v3"
    assert parse_tag("vail/v3") == ("vail", 3)
    assert parse_tag("boston-mills-v2") == ("boston-mills", 2)
    assert parse_tag("vail-east/v9") == ("vail-east", 9)
    for bad in ("vail", "vail/v0", "vail/3", "Vail/v3", "vail/v3/x", "../v1", ""):
        assert parse_tag(bad) is None, bad


def test_the_download_url_uses_the_new_tag():
    assert asset_url("vail", 4, REPO) == "https://github.com/o/r/releases/download/vail/v4/vail.zip"


def test_next_version_counts_old_and_new_tags_of_this_slug_only():
    tags = ["vail-v3", "vail/v4", "vail-east/v9", "vail-east-v8", "bigsky/v2"]
    assert next_version("vail", tags, {"resorts": []}) == 5
    assert next_version("vail-east", tags, {"resorts": []}) == 10
    assert next_version("bigsky", tags, {"resorts": []}) == 3


def test_the_index_groups_by_resort_latest_first_and_marks_the_catalogs_version():
    cat = {"resorts": [entry("vail", "Vail", 3), entry("breckenridge", "Breckenridge", 1)],
           "test": [entry("synth", "Synthetic test mountain", 2)]}
    md = index_md([rel("vail-v1", 250_000_000, "2026-11-10"), rel("vail/v3", 272_400_000), rel("vail/v2", 271_000_000),
                   rel("breckenridge/v1", 179_000_000, "2026-11-11"), rel("synth/v2", 46_000_000),
                   rel("synth/v1", 45_000_000), rel("not-a-pack-tag-x")], cat, REPO)
    lines = md.splitlines()
    assert lines[0] == "# Releases"
    heads = [line for line in lines if line.startswith("#")]
    assert heads == ["# Releases", "## Breckenridge", "## Vail", "## Test packs", "### Synthetic test mountain"]
    vail = lines[lines.index("## Vail") + 2:lines.index("## Vail") + 5]
    assert vail == ["- [v3](https://github.com/o/r/releases/tag/vail/v3) (latest) 272 MB, 2026-11-12",
                    "- [v2](https://github.com/o/r/releases/tag/vail/v2) 271 MB, 2026-11-12",
                    "- [v1](https://github.com/o/r/releases/tag/vail/v1) 250 MB, 2026-11-10"]   # an old tag, new link
    assert "- [v2](https://github.com/o/r/releases/tag/synth/v2) (latest for pack format 1) 46 MB, 2026-11-12" in lines
    assert "not-a-pack" not in md
    assert md.endswith("\n") and not md.endswith("\n\n")


def test_the_index_leaves_out_drafts_but_the_publish_prs_own():
    cat = {"resorts": [entry("vail", "Vail", 4)]}
    rels = [rel("vail/v3", 1_000_000), rel("vail/v4", 2_000_000, draft=True), rel("bigsky/v1", 3_000_000, draft=True)]
    assert "vail/v4" not in index_md(rels, cat, REPO) and "Big Sky" not in index_md(rels, cat, REPO)
    md = index_md(rels, cat, REPO, own="vail/v4")
    assert "- [v4](https://github.com/o/r/releases/tag/vail/v4) (latest) 2 MB, 2026-11-12" in md
    assert "bigsky" not in md


def test_a_resort_no_longer_in_the_catalog_is_named_from_its_release_title():
    md = index_md([rel("gone/v2", 5_000_000, name="Gone Peak v2")], {"resorts": []}, REPO)
    assert "## Gone Peak" in md and "(latest)" not in md


def test_an_empty_index_says_so():
    assert "No packs published yet." in index_md([], {"resorts": []}, REPO)


def test_own_release_is_a_draft_record_with_the_zip_size():
    r = releases.own_release("vail", 5, "Vail v5", 123, day="2026-11-13")
    assert r["tag_name"] == "vail/v5" and r["draft"] and r["assets"] == [{"name": "vail.zip", "size": 123}]
    assert "2026-11-13" in index_md([r], {"resorts": [entry("vail", "Vail", 5)]}, REPO, own="vail/v5")


def test_list_releases_reads_one_json_object_per_line():
    seen = []

    def run(cmd):
        seen.append(cmd)
        return '{"tag_name": "a/v1"}\n\n{"tag_name": "b-v2"}\n'
    assert [r["tag_name"] for r in releases.list_releases(REPO, run)] == ["a/v1", "b-v2"]
    assert seen[0][:3] == ["gh", "api", "repos/o/r/releases?per_page=100"] and "--paginate" in seen[0]


# --- the migration -------------------------------------------------------------------------------------------------

def test_the_migration_plan_moves_only_old_tags():
    plan = migration_plan([rel("vail-v1"), rel("vail/v2"), rel("boston-mills-v2"), rel("synth-v3"), rel("misc")])
    assert plan == [("boston-mills-v2", "boston-mills/v2"), ("synth-v3", "synth/v3"), ("vail-v1", "vail/v1")]


def test_the_migrated_catalog_names_the_new_urls_and_keeps_everything_else():
    old = {"formatVersion": 1, "resorts": [{**entry("vail", "Vail", 4), "tier": "gold"}],
           "test": [entry("synth", "Synthetic test mountain", 3)]}
    old["resorts"][0]["pack"]["url"] = "https://github.com/o/r/releases/download/vail-v4/vail.zip"
    new = migrate_catalog(old, REPO)
    assert new["resorts"][0]["pack"]["url"] == "https://github.com/o/r/releases/download/vail/v4/vail.zip"
    assert new["test"][0]["pack"]["url"] == "https://github.com/o/r/releases/download/synth/v3/synth.zip"
    assert new["resorts"][0]["tier"] == "gold" and "url" not in old["test"][0]["pack"]   # a copy, input untouched


def fake_gh(tags):
    """run() over a repo whose git tags are `tags` ({name: sha}); records every call"""
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[:2] == ["gh", "api"] and "/git/ref/tags/" in cmd[2]:
            name = cmd[2].split("/git/ref/tags/", 1)[1]
            if name not in tags:
                raise SystemExit("HTTP 404")
            return tags[name]
        if cmd[:4] == ["gh", "api", "-X", "POST"]:
            tags[cmd[-3].split("refs/tags/", 1)[1]] = cmd[-1].split("=", 1)[1]
        if cmd[:4] == ["gh", "api", "-X", "DELETE"]:
            tags.pop(cmd[-1].split("/git/refs/tags/", 1)[1])
        return ""
    return run, calls


def test_moving_a_release_tags_the_same_commit_then_moves_it_then_deletes_the_old_tag():
    tags = {"vail-v1": "abc"}
    run, calls = fake_gh(tags)
    releases.move_release("vail-v1", "vail/v1", REPO, run, draft=False)
    assert tags == {"vail/v1": "abc"}
    kinds = [c[:4] for c in calls]
    post = kinds.index(["gh", "api", "-X", "POST"])
    edit = calls.index(["gh", "release", "edit", "vail-v1", "-R", REPO, "--tag", "vail/v1"])
    assert post < edit < kinds.index(["gh", "api", "-X", "DELETE"])


def test_moving_refuses_when_the_new_tag_is_at_another_commit():
    run, calls = fake_gh({"vail-v1": "abc", "vail/v1": "def"})
    with pytest.raises(SystemExit, match="exists at def"):
        releases.move_release("vail-v1", "vail/v1", REPO, run, draft=False)
    assert not any(c[:3] == ["gh", "release", "edit"] for c in calls)


def test_moving_a_draft_only_renames_the_release():
    run, calls = fake_gh({})
    releases.move_release("vail-v5", "vail/v5", REPO, run, draft=True)
    assert calls == [["gh", "release", "edit", "vail-v5", "-R", REPO, "--tag", "vail/v5"]]


def test_migrate_without_apply_changes_nothing_on_github_but_writes_the_pr_files(tmp_path, capsys):
    cat = {"formatVersion": 1, "resorts": [{**entry("vail", "Vail", 2),
                                            "lonlat": [0, 0]}]}
    cat["resorts"][0]["pack"]["url"] = "https://github.com/o/r/releases/download/vail-v2/vail.zip"
    (tmp_path / "catalog.json").write_text(json.dumps(cat))
    listing = "\n".join(json.dumps(r) for r in (rel("vail-v1", 1_000_000), rel("vail-v2", 2_000_000)))
    calls = []

    def run(cmd):
        calls.append(cmd)
        return listing if cmd[:2] == ["gh", "api"] and "/releases?" in cmd[2] else ""
    plan = releases.migrate(REPO, run, apply=False, repo_dir=str(tmp_path))
    assert plan == [("vail-v1", "vail/v1"), ("vail-v2", "vail/v2")]
    assert len(calls) == 1, "only the release list is read"
    new = json.loads((tmp_path / "catalog.json").read_text())
    assert new["resorts"][0]["pack"]["url"] == "https://github.com/o/r/releases/download/vail/v2/vail.zip"
    md = (tmp_path / "RELEASES.md").read_text()
    assert "[v2](https://github.com/o/r/releases/tag/vail/v2) (latest) 2 MB" in md and "would move vail-v1" in \
        capsys.readouterr().out
