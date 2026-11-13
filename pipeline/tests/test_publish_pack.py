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
import publish_pack  # noqa: E402
from publish_pack import (catalog_entry, content_key, find_test_pack, next_version, pack_files,  # noqa: E402
                          update_catalog, zip_pack)
from pack_fixtures import tiny_pack, write_json  # noqa: E402

ENTRY = catalog_entry({"slug": "demo", "name": "Demo Mountain", "formatVersion": FORMAT_VERSION,
                       "build": "20260101T000000Z-abc123", "pipeline": "abc1234", "lonlat": [0, 0]}, {},
                      version=3, size=12_000_000, sha256="ab" * 32, pipeline="abc1234", tier="gold",
                      status="preview", report=None)


def tiny_pack_with_stamp(tmp_path, stamp="abc1234"):
    """pack_fixtures.tiny_pack as resort `demo`, built by pipeline `stamp`"""
    d = tiny_pack(tmp_path, pipeline=stamp)
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    write_json(os.path.join(d, "meta.json"), {**meta, "slug": "demo", "name": "Demo Mountain", "lonlat": [0, 0]})
    return d


def fake_gh_and_git(monkeypatch, maintainer=True, catalog=None, fail=None):
    """publish_pack.run records every argv and answers the gh and git queries; `git worktree add` makes the folder
    with origin/main's catalog.json and `git worktree remove` deletes it, so open_publish_pr runs end to end. A
    command starting with `fail` exits as run() does on a failed command."""
    calls = []
    catalog = catalog or {"formatVersion": FORMAT_VERSION, "resorts": []}
    monkeypatch.delenv("GITHUB_TRIGGERING_ACTOR", raising=False)   # set on a GitHub runner

    def run(cmd, cwd=None, capture=True):
        calls.append(list(cmd))
        line = " ".join(cmd)
        if fail and line.startswith(fail):
            raise SystemExit(f"{line} failed (1):\nboom")
        if line.startswith("gh api repos/") and "/releases?" in line:     # releases.list_releases
            return json.dumps({"tag_name": "vail/v4", "name": "Vail v4", "draft": False,
                               "published_at": "2026-11-11T00:00:00Z", "assets": [{"name": "vail.zip", "size": 9e6}]})
        if line.startswith("gh release list"):
            return json.dumps([{"tagName": "other-v1"}])
        if line.startswith("gh release create"):
            return f"https://github.com/o/r/releases/tag/untagged-{cmd[3]}"
        if line.startswith("gh api user"):
            return "drewkeriazes" if maintainer else "someone-else"
        if line.startswith("gh pr create"):
            return "https://github.com/o/r/pull/7"
        if line.startswith("git branch -r --contains"):
            return "  origin/main\n  origin/issue-1-x"
        if line.startswith("git show origin/main:catalog.json"):
            return json.dumps(catalog)
        if line.startswith("git worktree add"):
            os.makedirs(cmd[-2])
            write_json(os.path.join(cmd[-2], "catalog.json"), catalog)
        if line.startswith("git worktree remove"):
            shutil.rmtree(cmd[-1])
        return ""
    monkeypatch.setattr(publish_pack, "run", run)
    return calls


def test_stamp_problem_accepts_a_clean_stamp_on_main():
    assert publish_pack.stamp_problem({"slug": "demo", "pipeline": "abc1234"}, lambda s: True) is None


def test_stamp_problem_refuses_a_missing_stamp():
    msg = publish_pack.stamp_problem({"slug": "bigsky"}, lambda s: True)
    assert "no pipeline stamp" in msg and "build_resort.py bigsky --force build" in msg


def test_stamp_problem_refuses_dirty_and_unmerged():
    assert "+dirty" in publish_pack.stamp_problem({"slug": "d", "pipeline": "abc1234+dirty"}, lambda s: True)
    assert "not on origin/main" in publish_pack.stamp_problem({"slug": "d", "pipeline": "abc1234"}, lambda s: False)


def test_next_version_counts_draft_tags():
    assert publish_pack.next_version("vail", ["vail-v3", "vail-v4"], {"resorts": []}) == 5


def test_maintainers_ignores_comments_and_blanks(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "maintainers.txt").write_text("# who\ndrewkeriazes\n\n")
    assert publish_pack.maintainers(str(tmp_path)) == {"drewkeriazes"}


def test_pr_body_names_the_requester_and_the_build():
    body = publish_pack.pr_body(ENTRY, why="report passes", release_url="u", started_by="drewkeriazes",
                                run_url="https://github.com/o/r/actions/runs/42", requested_by="player-1-id")
    assert "Requested by: player-1-id" in body and "Run: https://github.com/o/r/actions/runs/42" in body
    assert f"Build: {ENTRY['pack']['build']}" in body and "not the merge button" in body
    local = publish_pack.pr_body(ENTRY, why="w", release_url="u", started_by="d", run_url=None, requested_by=None)
    assert "Run:" not in local and "Requested by:" not in local
    assert "rebuild_choices.py --write" not in local                       # FEAT-297: only a new resort's says it
    new = publish_pack.pr_body(ENTRY, why="w", release_url="u", started_by="d", run_url=None, requested_by=None,
                               new_resort=True)
    assert "rebuild_choices.py --write" in new and "rebuild list" in new


def test_publish_opens_a_pr_and_never_pushes_main(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch, maintainer=True)       # records every run() argv, answers gh queries
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    flat = [" ".join(c) for c in calls]
    assert any(c.startswith("gh release create demo/v1") and "--draft" in c for c in flat)
    assert any(c.startswith("git push -u origin publish/demo-v1") for c in flat)
    assert any("gh pr create" in c and "--label publish" in c and "--label automerge" in c for c in flat)
    assert not any(c.startswith("git push") and "main" in c.split()[-1] for c in flat)


def test_a_non_maintainer_publish_gets_no_automerge(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch, maintainer=False)
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    assert not any("--label automerge" in " ".join(c) for c in calls)


def test_the_pr_branch_carries_the_new_entry_on_origin_mains_catalog(tmp_path, monkeypatch):
    other = {"slug": "vail", "name": "Vail", "pack": {"version": 4, "formatVersion": FORMAT_VERSION}}
    calls = fake_gh_and_git(monkeypatch, catalog={"formatVersion": FORMAT_VERSION, "resorts": [other]})
    checkout = tmp_path / "checkout"           # the publisher's checkout: the resort's config and an older report
    (checkout / "resorts" / "demo").mkdir(parents=True)
    (checkout / "resorts" / "demo" / "demo.json").write_text("{}")
    (checkout / "reports").mkdir()
    (checkout / "reports" / "demo.md").write_text("older report")
    monkeypatch.setattr(publish_pack, "REPO", str(checkout))
    pack = tiny_pack_with_stamp(tmp_path)
    with open(os.path.join(pack, "report.md"), "w") as f:
        f.write("this build's report")
    seen = {}
    fake_run = publish_pack.run

    def run(cmd, cwd=None, capture=True):        # read the worktree at commit time
        if cmd[:2] == ["git", "add"]:
            seen["added"] = cmd[3:]
        if cmd[:2] == ["git", "commit"]:
            seen["catalog"] = json.load(open(os.path.join(cwd, "catalog.json"), encoding="utf-8"))
            seen["report"] = open(os.path.join(cwd, "reports", "demo.md")).read()
            seen["index"] = open(os.path.join(cwd, "RELEASES.md")).read()
            seen["message"] = cmd[-1]
        return fake_run(cmd, cwd, capture)
    monkeypatch.setattr(publish_pack, "run", run)
    publish_pack.main([pack, "--status", "preview", "--accept-change", "--requested-by", "player-1-id"])
    assert [r["slug"] for r in seen["catalog"]["resorts"]] == ["demo", "vail"]
    assert seen["catalog"]["resorts"][0]["pack"]["pipeline"] == "abc1234"
    assert seen["catalog"]["resorts"][0]["report"] == "reports/demo.md"
    assert sorted(seen["added"]) == ["RELEASES.md", "catalog.json", "reports/demo.md", "resorts/demo/demo.json"]
    assert seen["report"] == "this build's report"
    assert "## Demo Mountain" in seen["index"] and "releases/tag/demo/v1) (latest)" in seen["index"]  # its own draft
    assert "releases/tag/vail/v4) (latest) 9 MB, 2026-11-11" in seen["index"]
    assert (checkout / "reports" / "demo.md").read_text() == "older report"     # the checkout is left alone
    assert sorted(p.name for p in (checkout / "reports").iterdir()) == ["demo.md"]
    assert seen["message"] == "demo v1: preview, 0 MB, pipeline abc1234"
    pr = next(c for c in calls if c[:3] == ["gh", "pr", "create"])
    assert "accept-change" in pr
    assert not any(os.path.exists(c[-2]) for c in calls if c[:3] == ["git", "worktree", "add"])


def test_the_local_publish_branch_is_deleted_after_the_pr(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch)
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    assert ["git", "branch", "-D", "publish/demo-v1"] in calls


def test_a_failed_pr_names_the_draft_and_the_pushed_branch_and_cleans_up(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch, fail="gh pr create")
    with pytest.raises(SystemExit) as e:
        publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    msg = str(e.value)
    assert "draft release demo/v1" in msg and "origin/publish/demo-v1" in msg
    assert ["git", "branch", "-D", "publish/demo-v1"] in calls
    assert calls.index(["git", "branch", "-D", "publish/demo-v1"]) > \
        next(i for i, c in enumerate(calls) if c[:3] == ["git", "worktree", "remove"])


def test_a_failure_before_the_push_does_not_mention_a_pushed_branch(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch, fail="git commit")
    with pytest.raises(SystemExit) as e:
        publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    assert "draft release demo/v1" in str(e.value) and "is pushed" not in str(e.value)
    assert ["git", "branch", "-D", "publish/demo-v1"] in calls


def test_a_stamp_problem_refuses_before_any_release(tmp_path, monkeypatch):
    calls = fake_gh_and_git(monkeypatch)
    with pytest.raises(SystemExit, match=r"\+dirty"):
        publish_pack.main([str(tiny_pack_with_stamp(tmp_path, "abc1234+dirty")), "--status", "preview"])
    assert not any(c[:2] in (["gh", "release"], ["git", "push"]) for c in calls)


def test_dry_run_prints_the_branch_and_calls_no_gh_and_no_fetch(tmp_path, monkeypatch, capsys):
    calls = fake_gh_and_git(monkeypatch)
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview", "--dry-run"])
    assert "publish/demo-v" in capsys.readouterr().out
    assert not any(c[0] == "gh" or c[:2] in (["git", "fetch"], ["git", "push"], ["git", "worktree"]) for c in calls)


@pytest.mark.parametrize("dry", [False, True])
def test_a_pack_the_lint_rejects_is_refused_before_the_zip_and_any_release(tmp_path, monkeypatch, dry):
    calls = fake_gh_and_git(monkeypatch)
    pack = tiny_pack_with_stamp(tmp_path)
    os.remove(os.path.join(pack, "fine", "0_0.png"))
    zipped = []
    monkeypatch.setattr(publish_pack, "zip_pack", lambda *a: zipped.append(a) or (1, "0" * 64))
    with pytest.raises(SystemExit) as e:
        publish_pack.main([pack, "--status", "preview"] + (["--dry-run"] if dry else []))
    assert "pack_lint found 1 problem(s)" in str(e.value) and "fine/0_0.png: missing" in str(e.value)
    assert not zipped
    assert not any(c[0] == "gh" or c[:2] == ["git", "push"] for c in calls)


def test_the_lint_refusal_lists_at_most_twenty_problems(monkeypatch):
    monkeypatch.setattr(publish_pack, "lint", lambda d: [f"p{i}" for i in range(25)])
    with pytest.raises(SystemExit) as e:
        publish_pack.lint_refusal("packs/x")
    msg = str(e.value)
    assert "25 problem(s)" in msg and "  - p19" in msg and "p20" not in msg and "and 5 more" in msg


def test_the_printed_next_step_says_the_app_is_needed_and_names_the_safe_manual_path(tmp_path, monkeypatch, capsys):
    fake_gh_and_git(monkeypatch)
    publish_pack.main([str(tiny_pack_with_stamp(tmp_path)), "--status", "preview"])
    out = capsys.readouterr().out
    assert "when the publish App is set up" in out
    assert out.index("gh release edit demo/v1") < out.index("then merge the PR")


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
    assert e["pack"]["url"].endswith("/releases/download/vail/v2/vail.zip")
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


def test_content_key_leaves_out_the_report(tmp_path):
    """FEAT-245: report.json and report.md carry the build, the time and file dates; a rebuild that changed
    nothing else keeps its key"""
    pack = make_pack(tmp_path / "a")
    key = content_key(str(pack))
    (pack / "report.json").write_text('{"build": "b2", "generated": "2026-11-12T10:00:00Z"}')
    (pack / "report.md").write_text("# report, generated now")
    assert content_key(str(pack)) == key
    (pack / "fine" / "0_0.png").write_bytes(b"other tile")
    assert content_key(str(pack)) != key


def published_demo(pack, content=True):
    """origin/main's catalog with demo v2, carrying the pack's content key when `content`"""
    e = catalog_entry({"slug": "demo", "name": "Demo Mountain", "formatVersion": FORMAT_VERSION}, {}, version=2,
                      size=1, sha256="d", pipeline="p", tier="gold", status="preview", report=None)
    if content:
        e["pack"]["content"] = content_key(pack)
    return {"formatVersion": FORMAT_VERSION, "resorts": [e]}


def released(calls):
    return [c for c in calls if c[:3] == ["gh", "release", "create"]]


def test_an_identical_resort_pack_is_not_published_again(tmp_path, monkeypatch, capsys):
    pack = tiny_pack_with_stamp(tmp_path)
    calls = fake_gh_and_git(monkeypatch, catalog=published_demo(pack))
    publish_pack.main([pack, "--status", "preview"])
    assert "demo is unchanged since v2" in capsys.readouterr().out
    assert not any(c[0] == "gh" for c in calls)                   # stopped before any gh call


def test_an_entry_without_a_content_key_counts_as_changed(tmp_path, monkeypatch):
    pack = tiny_pack_with_stamp(tmp_path)
    calls = fake_gh_and_git(monkeypatch, catalog=published_demo(pack, content=False))
    publish_pack.main([pack, "--status", "preview"])
    assert [c[3] for c in released(calls)] == ["demo/v3"]


@pytest.mark.parametrize("flags", [["--tier", "silver"], ["--status", "playable"]])
def test_the_same_content_with_another_tier_or_status_is_published(tmp_path, monkeypatch, flags):
    pack = tiny_pack_with_stamp(tmp_path)
    calls = fake_gh_and_git(monkeypatch, catalog=published_demo(pack))
    monkeypatch.setattr(publish_pack, "report_status", lambda d, m, s: (s or "preview", "test"))
    publish_pack.main([pack, "--status", "preview", *flags] if "--status" not in flags else [pack, *flags])
    assert [c[3] for c in released(calls)] == ["demo/v3"]


def test_force_publishes_an_identical_pack(tmp_path, monkeypatch):
    pack = tiny_pack_with_stamp(tmp_path)
    calls = fake_gh_and_git(monkeypatch, catalog=published_demo(pack))
    publish_pack.main([pack, "--status", "preview", "--force"])
    assert [c[3] for c in released(calls)] == ["demo/v3"]


def test_the_entry_and_the_pr_body_carry_the_content_key(tmp_path, monkeypatch):
    pack = tiny_pack_with_stamp(tmp_path)
    calls = fake_gh_and_git(monkeypatch)
    fake_run = publish_pack.run
    seen = {}

    def run(cmd, cwd=None, capture=True):        # read the catalog and the body file while they exist
        if cmd[:2] == ["git", "commit"]:
            seen["catalog"] = json.load(open(os.path.join(cwd, "catalog.json"), encoding="utf-8"))
        if cmd[:3] == ["gh", "pr", "create"]:
            seen["body"] = open(cmd[cmd.index("--body-file") + 1], encoding="utf-8").read()
        return fake_run(cmd, cwd, capture)
    monkeypatch.setattr(publish_pack, "run", run)
    publish_pack.main([pack, "--status", "preview"])
    key = content_key(pack)
    assert seen["catalog"]["resorts"][0]["pack"]["content"] == key
    assert f"Content: {key}" in seen["body"].splitlines()
    assert released(calls)


def test_an_open_publish_pr_with_the_same_content_skips(tmp_path, monkeypatch, capsys):
    pack = tiny_pack_with_stamp(tmp_path)
    key = content_key(pack)
    calls = fake_gh_and_git(monkeypatch)
    fake_run = publish_pack.run
    prs = [{"number": 8, "url": "", "headRefName": "publish/demo-extra-v1", "body": f"Content: {key}\n"},  # other slug
           {"number": 9, "url": "https://github.com/o/r/pull/9", "headRefName": "publish/demo-v1",
            "body": f"Build: b\nContent: {key}\n"}]

    def run(cmd, cwd=None, capture=True):
        if cmd[:3] == ["gh", "pr", "list"]:
            calls.append(list(cmd))
            return json.dumps(prs)
        return fake_run(cmd, cwd, capture)
    monkeypatch.setattr(publish_pack, "run", run)
    publish_pack.main([pack, "--status", "preview"])
    assert "https://github.com/o/r/pull/9 is open with this content: nothing to publish" in capsys.readouterr().out
    assert not released(calls)
    prs[1]["body"] = "Content: 0000000000000000\n"                  # an open PR with other content: publish
    publish_pack.main([pack, "--status", "preview"])
    assert [c[3] for c in released(calls)] == ["demo/v1"]
    assert publish_pack.pending_same_content("demo", key, "o/r") is None


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
