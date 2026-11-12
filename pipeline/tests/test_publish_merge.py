"""FEAT-272: publish_merge.py decides whether a publish PR releases its draft and merges itself. Every gh call is
faked (FakeGitHub); the refresh test runs real git against a local bare repo, no network."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_merge  # noqa: E402
from publish_merge import (catalog_problem, commits_after_label_ok, decide, files_ok, label_ok,  # noqa: E402
                           parse_branch, publish_file_patterns, rebase_catalog)
from publish_pack import asset_url  # noqa: E402

REPO = "o/r"
APP = "pub[bot]"
T_LABEL = "2026-11-12T10:00:00Z"


def labeled(label, login, at=T_LABEL):
    return {"event": "labeled", "label": {"name": label}, "actor": {"login": login}, "created_at": at}


def commit(date, login, committer=None):
    """the REST shape of a PR commit: GitHub's login for the author and committer, and the git dates"""
    return {"sha": "c", "author": {"login": login}, "committer": {"login": committer or login},
            "commit": {"author": {"date": date}, "committer": {"date": date}}}


def entry(slug, version, repo=REPO):
    return {"slug": slug, "name": slug, "pack": {"version": version, "formatVersion": 1, "bytes": 3, "sha256": "0" * 64,
                                                 "url": asset_url(slug, version, repo)}}


def test_parse_branch():
    assert parse_branch("publish/park-city-mountain-v2") == ("park-city-mountain", 2)
    assert parse_branch("issue-69-publish-pr") is None
    assert parse_branch("publish/../main-v1") is None
    assert parse_branch("publish/a-v0") is None


def test_publish_file_patterns():
    assert publish_file_patterns("vail") == ["catalog.json", "RELEASES.md", "reports/vail.md", "resorts/vail/**",
                                             "manifests/vail.json"]


def test_files_outside_the_publish_set_are_refused():
    ok = ["catalog.json", "reports/vail.md", "resorts/vail/vail.json", "manifests/vail.json"]
    assert files_ok(ok, "vail")
    assert files_ok(["RELEASES.md", "resorts/vail/sub/x.txt"], "vail")
    assert not files_ok(ok + ["pipeline/build_pack.py"], "vail")
    assert not files_ok(["resorts/bigsky/bigsky.json"], "vail")
    assert not files_ok(["resorts/vail-x/a.json"], "vail")
    assert not files_ok(["resorts/vail/../../pipeline/x.py"], "vail")
    assert not files_ok(["resorts/vail/"], "vail")
    assert not files_ok([], "vail")


def test_label_from_a_maintainer_counts():
    assert label_ok([labeled("automerge", "drewkeriazes")], "automerge", {"drewkeriazes"}, "pub[bot]", "", lambda i: None)


def test_label_from_a_non_maintainer_is_refused():
    assert not label_ok([labeled("automerge", "someone")], "automerge", {"drewkeriazes"}, "pub[bot]", "", lambda i: None)


def test_label_from_the_app_counts_only_for_a_maintainer_run():
    body = "Run: https://github.com/o/r/actions/runs/42"
    ev = [labeled("automerge", "pub[bot]")]
    assert label_ok(ev, "automerge", {"drewkeriazes"}, "pub[bot]", body, lambda i: "drewkeriazes" if i == 42 else None)
    assert not label_ok(ev, "automerge", {"drewkeriazes"}, "pub[bot]", body, lambda i: "someone")


def test_app_label_fails_closed():
    m, run = {"drewkeriazes"}, (lambda i: "drewkeriazes")
    ev = [labeled("automerge", APP)]
    body = "Run: https://github.com/o/r/actions/runs/42"
    assert not label_ok(ev, "automerge", m, "", body, run), "no App login configured: no App label counts"
    assert not label_ok(ev, "automerge", m, APP, "", run), "no Run: line"
    assert not label_ok(ev, "automerge", m, APP, body + "\nRun: https://github.com/o/r/actions/runs/43", run)
    assert not label_ok(ev, "automerge", m, APP, body.replace("o/r", "x/y"), run, repo=REPO), "a run in another repo"

    def boom(i):
        raise SystemExit("gh failed")
    assert not label_ok(ev, "automerge", m, APP, body, boom)


def test_only_the_latest_label_event_counts():
    ev = [labeled("automerge", "drewkeriazes", "2026-11-12T09:00:00Z"), labeled("automerge", "someone"),
          labeled("publish", "drewkeriazes", "2026-11-12T11:00:00Z")]
    assert not label_ok(ev, "automerge", {"drewkeriazes"}, APP, "", lambda i: None)
    assert not label_ok([], "automerge", {"drewkeriazes"}, APP, "", lambda i: None)


def test_a_commit_after_the_label_blocks_unless_it_is_the_refresh():
    t = "2026-11-12T10:00:00Z"
    assert not commits_after_label_ok([commit("2026-11-12T11:00:00Z", "someone")], t, "pub[bot]")
    assert commits_after_label_ok([commit("2026-11-12T11:00:00Z", "pub[bot]")], t, "pub[bot]")
    assert commits_after_label_ok([commit("2026-11-12T09:00:00Z", "someone")], t, "pub[bot]")
    assert not commits_after_label_ok([commit("2026-11-12T11:00:00Z", "pub[bot]", committer="someone")], t, APP)
    assert not commits_after_label_ok([commit("2026-11-12T11:00:00Z", None)], t, ""), "no App login: nothing after"
    assert not commits_after_label_ok([{"author": {"login": "x"}, "commit": {}}], t, APP), "no dates: fail closed"


def test_rebase_catalog_keeps_both_resorts():
    base = {"resorts": []}; pr = {"resorts": [entry("a", 1)]}; main = {"resorts": [entry("b", 1)]}
    assert sorted(r["slug"] for r in rebase_catalog(base, pr, main)["resorts"]) == ["a", "b"]


def test_rebase_catalog_keeps_a_test_pack_in_the_test_list():
    out = rebase_catalog({"resorts": []}, {"resorts": [], "test": [entry("synth", 2)]}, {"resorts": [entry("b", 1)]})
    assert [r["slug"] for r in out["resorts"]] == ["b"] and [t["slug"] for t in out["test"]] == ["synth"]


def test_catalog_problem():
    base = {"resorts": [entry("b", 1)]}
    assert catalog_problem(base, {"resorts": [entry("b", 1), entry("a", 2)]}, "a", 2, REPO) is None
    assert "no change" in catalog_problem(base, base, "a", 2, REPO)
    assert "b" in catalog_problem(base, {"resorts": [entry("b", 2), entry("a", 2)]}, "a", 2, REPO)
    assert "drops" in catalog_problem(base, {"resorts": [entry("a", 2)]}, "a", 2, REPO)
    assert catalog_problem(base, {"resorts": [entry("b", 1), entry("a", 3)]}, "a", 2, REPO)
    evil = entry("a", 2)
    evil["pack"]["url"] = "https://evil.invalid/a.zip"
    assert "url" in catalog_problem(base, {"resorts": [entry("b", 1), evil]}, "a", 2, REPO)


def test_decide():
    green = [{"name": "publish-check", "conclusion": "success"}, {"name": "pipeline-tests", "conclusion": "skipped"}]
    args = dict(labels=["publish", "automerge"], files=["catalog.json"], branch="publish/a-v1", checks=green,
                automerge_ok=True, behind_main=False)
    assert decide(**args) == "merge"
    assert decide(**{**args, "behind_main": True}) == "refresh"
    assert decide(**{**args, "labels": ["publish"]}) == "wait"
    assert decide(**{**args, "checks": [{"name": "publish-check", "conclusion": "failure"}]}) == "wait"
    assert decide(**{**args, "automerge_ok": False}).startswith("refuse")
    assert decide(**{**args, "files": ["catalog.json", "pipeline/x.py"]}).startswith("refuse")


def test_decide_fails_closed_on_checks_and_branch():
    green = [{"name": "publish-check", "conclusion": "success"}]
    args = dict(labels=["publish", "automerge"], files=["catalog.json"], branch="publish/a-v1", checks=green,
                automerge_ok=True, behind_main=False)
    assert decide(**{**args, "checks": []}) == "wait"
    assert decide(**{**args, "checks": [{"name": "pipeline-tests", "conclusion": "success"}]}) == "wait"
    assert decide(**{**args, "checks": [{"name": "publish-check", "conclusion": "skipped"}]}) == "wait"
    assert decide(**{**args, "checks": green + [{"name": "x", "conclusion": None}]}) == "wait"
    assert decide(**{**args, "checks": green + [{"name": "x", "conclusion": "neutral"}]}) == "wait"
    assert decide(**{**args, "branch": "issue-1-x"}).startswith("refuse")
    assert decide(**{**args, "labels": ["automerge"]}).startswith("refuse")


# --- the gh layer, against a fake GitHub ---------------------------------------------------------------------------

class Calls(list):
    """the recorded commands; `.state` is the fake's state, for a test to change after setup"""


class FakeGitHub:
    """answers publish_merge's gh calls from `state`, records every command; `fail` holds command prefixes that fail"""

    def __init__(self, pr, release_draft, **over):
        p = {"merged": False, "state": "open", "headRefName": "publish/a-v1", "labels": ["publish", "automerge"],
             "body": "", "fork": False, **pr}
        files = over.pop("files", [{"filename": "catalog.json"}])
        commits = over.pop("commits", [commit("2026-11-12T09:00:00Z", "drewkeriazes")])
        self.state = {
            "pr": {"number": 7, "state": p["state"], "merged": p["merged"], "body": p["body"],
                   "labels": [{"name": n} for n in p["labels"]], "base": {"ref": "main"},
                   "head": {"ref": p["headRefName"], "sha": "h1", "repo": {"full_name": "x/fork" if p["fork"] else REPO}},
                   "merge_commit_sha": "m1", "changed_files": len(files), "commits": len(commits)},
            "files": files, "commits": commits,
            "timeline": [labeled("automerge", "drewkeriazes"), {"event": "committed"}],
            "compare": {"behind_by": 0, "base": "b0"},
            "checks": [{"name": "publish-check", "status": "completed", "conclusion": "success", "details_url": ""},
                       {"name": "pipeline-tests", "status": "completed", "conclusion": "skipped", "details_url": ""}],
            "catalogs": {"b0": {"resorts": []}, "h1": {"resorts": [entry("a", 1)]}, "m1": {"resorts": [entry("a", 1)]}},
            "release_draft": release_draft, "comments": [], "open_prs": [], "run_actor": "drewkeriazes",
            "fail": [],
        }
        self.state.update(over)
        self.calls = Calls()

    def __call__(self, cmd, cwd=None, capture=True):
        self.calls.append(list(cmd))
        s = self.state
        if any(cmd[:len(f)] == f for f in s["fail"]):
            raise SystemExit(f"{' '.join(cmd)} failed")
        if cmd[:2] == ["gh", "api"]:
            return self.api(cmd[2])
        if cmd[:3] == ["gh", "release", "view"]:
            if s["release_draft"] is None:
                raise SystemExit("release not found")
            return "true" if s["release_draft"] else "false"
        if cmd[:3] in (["gh", "release", "edit"], ["gh", "release", "delete"], ["gh", "pr", "merge"],
                       ["gh", "pr", "comment"]):
            return ""
        raise AssertionError(f"unexpected command {cmd}")

    def api(self, path):
        s, base = self.state, f"repos/{REPO}/"
        assert path.startswith(base), path
        path = path[len(base):]
        if path == "pulls/7":
            return json.dumps(s["pr"])
        if path == "pulls/7/files":
            return json.dumps(s["files"])
        if path == "pulls/7/commits":
            return json.dumps(s["commits"])
        if path == "issues/7/timeline":
            return json.dumps(s["timeline"][:1]) + "\n" + json.dumps(s["timeline"][1:])   # two pages
        if path == "issues/7/comments":
            return json.dumps(s["comments"])
        if path.startswith("compare/main..."):
            return json.dumps(s["compare"])
        if path == "commits/h1/check-runs":
            return json.dumps({"total_count": len(s["checks"]), "check_runs": s["checks"]})
        if path.startswith("contents/catalog.json?ref="):
            return json.dumps(s["catalogs"][path.split("=")[1]])
        if path.startswith("actions/runs/"):
            return s["run_actor"]
        if path.startswith("pulls?state=open"):
            return json.dumps(s["open_prs"])
        raise AssertionError(f"unexpected api path {path}")


def fake_gh(monkeypatch, pr, release_draft, decision=None, **over):
    fake = FakeGitHub(pr, release_draft, **over)
    monkeypatch.setattr(publish_merge, "run", fake)
    monkeypatch.setattr(publish_merge, "sleep", lambda s: None)
    monkeypatch.setattr(publish_merge, "maintainers", lambda repo_dir=None: {"drewkeriazes"})
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("PUBLISH_APP_LOGIN", APP)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    if decision:
        monkeypatch.setattr(publish_merge, "decide", lambda **kw: decision)
    fake.calls.state = fake.state
    return fake.calls


def released(calls):
    return [c for c in calls if c[:3] == ["gh", "release", "edit"]]


def merged(calls):
    return [c for c in calls if c[:3] == ["gh", "pr", "merge"]]


def comments(calls):
    return [c[c.index("--body") + 1] for c in calls if c[:3] == ["gh", "pr", "comment"]]


def test_merged_pr_with_a_draft_publishes_it(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": True, "headRefName": "publish/a-v1"}, release_draft=True)
    publish_merge.main(["closed", "7"])
    assert ["gh", "release", "edit", "a-v1", "--draft=false"] in calls


def test_merged_pr_whose_catalog_does_not_name_the_draft_leaves_it(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": True}, release_draft=True, catalogs={"m1": {"resorts": []}})
    publish_merge.main(["closed", "7"])
    assert not released(calls)


def test_a_rollback_merges_without_touching_a_published_release(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": False, "headRefName": "publish/a-v1"}, release_draft=False, decision="merge")
    publish_merge.main(["ready", "7"])
    assert not any(c[:3] == ["gh", "release", "edit"] for c in calls)
    assert any(c[:3] == ["gh", "pr", "merge"] for c in calls)


def test_closed_unmerged_deletes_only_a_draft(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": False, "headRefName": "publish/a-v1"}, release_draft=True)
    publish_merge.main(["closed", "7"])
    assert any(c[:3] == ["gh", "release", "delete"] for c in calls)
    calls = fake_gh(monkeypatch, pr={"merged": False, "headRefName": "publish/a-v1"}, release_draft=False)
    publish_merge.main(["closed", "7"])
    assert not any(c[:3] == ["gh", "release", "delete"] for c in calls)


@pytest.mark.parametrize("pr, over", [
    ({"fork": True}, {}),
    ({}, {"open_prs": [{"number": 8}]}),
    ({}, {"fail": [["gh", "api", f"repos/{REPO}/pulls?state=open&head=o:publish/a-v1"]]}),
])
def test_closed_unmerged_keeps_the_draft_when_in_doubt(monkeypatch, pr, over):
    calls = fake_gh(monkeypatch, pr=pr, release_draft=True, **over)
    publish_merge.main(["closed", "7"])
    assert not any(c[:3] == ["gh", "release", "delete"] for c in calls)


def test_ready_releases_the_draft_then_merges_pinned_to_the_checked_head(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True)
    assert publish_merge.main(["ready", "7"]) == 0
    assert released(calls) == [["gh", "release", "edit", "a-v1", "--draft=false"]]
    assert merged(calls) == [["gh", "pr", "merge", "7", "--squash", "--match-head-commit", "h1"]]
    assert calls.index(released(calls)[0]) < calls.index(merged(calls)[0])
    view = [i for i, c in enumerate(calls) if c[:3] == ["gh", "release", "view"]]
    assert view and view[-1] < calls.index(released(calls)[0]), "the draft is re-checked right before publishing"


ANOTHER = commit("2026-11-12T11:00:00Z", "someone")


@pytest.mark.parametrize("why, pr, over", [
    ("label by a non-maintainer", {}, {"timeline": [labeled("automerge", "someone")]}),
    ("label by the App, no run", {}, {"timeline": [labeled("automerge", APP)]}),
    ("label by the App for a stranger's run", {"body": "Run: https://github.com/o/r/actions/runs/5\n"},
     {"timeline": [labeled("automerge", APP)], "run_actor": "someone"}),
    ("timeline unreadable", {}, {"fail": [["gh", "api", f"repos/{REPO}/issues/7/timeline"]]}),
    ("a commit after the label", {}, {"commits": [commit("2026-11-12T09:00:00Z", "drewkeriazes"), ANOTHER]}),
    ("a code file", {}, {"files": [{"filename": "catalog.json"}, {"filename": "pipeline/build_pack.py"}]}),
    ("a file moved out of the code", {}, {"files": [{"filename": "resorts/a/x.py", "previous_filename": "pipeline/x.py"}]}),
    ("more files than listed", {}, {"pr": None}),
    ("more commits than listed", {}, {"pr": "commits"}),
    ("a failing check", {}, {"checks": [{"name": "publish-check", "status": "completed", "conclusion": "failure"}]}),
    ("a running check", {}, {"checks": [{"name": "publish-check", "status": "completed", "conclusion": "success"},
                                        {"name": "x", "status": "in_progress", "conclusion": None}]}),
    ("a queued re-run with an old conclusion", {}, {"checks": [
        {"name": "publish-check", "status": "queued", "conclusion": "success"}]}),
    ("no publish-check", {}, {"checks": [{"name": "pipeline-tests", "status": "completed", "conclusion": "success"}]}),
    ("checks unreadable", {}, {"fail": [["gh", "api", f"repos/{REPO}/commits/h1/check-runs"]]}),
    ("a fork", {"fork": True}, {}),
    ("no automerge label", {"labels": ["publish"]}, {}),
    ("no publish label", {"labels": ["automerge"]}, {}),
    ("another resort's entry", {}, {"catalogs": {"b0": {"resorts": [entry("b", 1)]},
                                                 "h1": {"resorts": [entry("a", 1), entry("b", 2)]}}}),
    ("a url elsewhere", {}, {"catalogs": {"b0": {"resorts": []}, "h1": {"resorts": [entry("a", 1, repo="x/y")]}}}),
    ("no release", {}, {"release_draft": None}),
    ("closed", {"state": "closed"}, {}),
])
def test_ready_never_releases_or_merges_without_every_precondition(monkeypatch, why, pr, over):
    over = {"release_draft": True, **over}
    if "pr" in over:                  # the PR counts one more file (or commit) than the API lists
        calls = fake_gh(monkeypatch, pr=pr, release_draft=True)
        calls.state["pr"]["commits" if over["pr"] == "commits" else "changed_files"] += 1
    else:
        calls = fake_gh(monkeypatch, pr=pr, **over)
    publish_merge.main(["ready", "7"])
    assert not released(calls), why
    assert not merged(calls), why


def test_the_publish_merge_job_does_not_count_itself(monkeypatch):
    mine = [{"name": "publish-merge", "status": "in_progress", "conclusion": None, "details_url": ""},
            {"name": "other", "status": "in_progress", "conclusion": None,
             "details_url": f"https://github.com/{REPO}/actions/runs/99/job/1"}]
    calls = fake_gh(monkeypatch, pr={}, release_draft=True)
    calls.state["checks"] += mine
    monkeypatch.setenv("GITHUB_RUN_ID", "99")
    publish_merge.main(["ready", "7"])
    assert merged(calls)


def test_a_refusal_comments_once(monkeypatch):
    over = {"timeline": [labeled("automerge", "someone")]}
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, **over)
    publish_merge.main(["ready", "7"])
    said = comments(calls)
    assert len(said) == 1 and said[0].startswith("[publish-merge]") and "someone" in said[0]
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, comments=[{"body": said[0]}], **over)
    publish_merge.main(["ready", "7"])
    assert not comments(calls)


def test_a_failed_release_edit_stops_before_the_merge(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, fail=[["gh", "release", "edit"]])
    assert publish_merge.main(["ready", "7"]) == 1
    assert not merged(calls)


def test_a_failed_merge_after_the_release_retries_then_comments(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, fail=[["gh", "pr", "merge"]])
    assert publish_merge.main(["ready", "7"]) == 1
    assert len(merged(calls)) == 4
    assert any("merge failed" in c for c in comments(calls))


def test_behind_main_refreshes_instead_of_merging(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, compare={"behind_by": 2, "base": "b0"})
    seen = []
    monkeypatch.setattr(publish_merge, "refresh", lambda *a, **k: seen.append(a) or "refreshed")
    assert publish_merge.main(["ready", "7"]) == 0
    assert seen and not released(calls) and not merged(calls)


# --- the refresh, with real git ------------------------------------------------------------------------------------

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def write_catalog(d, cat):
    with open(os.path.join(d, "catalog.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(cat, f, indent=1)
        f.write("\n")


def test_refresh_merges_main_into_the_branch_with_both_entries(tmp_path):
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    for k, v in (("user.name", "t"), ("user.email", "t@example.invalid"), ("commit.gpgsign", "false")):
        git(work, "config", k, v)
    write_catalog(work, {"resorts": []})
    git(work, "add", "."); git(work, "commit", "-qm", "base"); git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "switch", "-qc", "publish/a-v1")
    write_catalog(work, {"resorts": [entry("a", 1)]})
    os.makedirs(work / "reports"); (work / "reports" / "a.md").write_text("a\n")
    git(work, "add", "."); git(work, "commit", "-qm", "a v1"); git(work, "push", "-q", "origin", "publish/a-v1")
    head = git(work, "rev-parse", "HEAD")
    git(work, "switch", "-q", "main")
    write_catalog(work, {"resorts": [entry("b", 1)]})
    git(work, "add", "."); git(work, "commit", "-qm", "b v1"); git(work, "push", "-q", "origin", "HEAD:main")

    publish_merge.refresh_branch("publish/a-v1", head, APP, "1+pub[bot]@users.noreply.github.com", str(work))

    git(work, "fetch", "-q", "origin")
    tip = "origin/publish/a-v1"
    cat = json.loads(git(work, "show", f"{tip}:catalog.json"))
    assert sorted(r["slug"] for r in cat["resorts"]) == ["a", "b"]
    assert git(work, "merge-base", "--is-ancestor", "origin/main", tip) == ""
    assert git(work, "log", "-1", "--format=%an <%ae>|%cn", tip) == f"{APP} <1+pub[bot]@users.noreply.github.com>|{APP}"
    assert git(work, "show", f"{tip}:reports/a.md") == "a"
    assert git(work, "worktree", "list", "--porcelain").count("worktree ") == 1, "the temp worktree is removed"


def test_refresh_stops_when_the_branch_moved(tmp_path, monkeypatch):
    seen = []

    def fake(cmd, cwd=None, capture=True):
        seen.append(cmd)
        return "other-sha" if cmd[:2] == ["git", "rev-parse"] else ""
    monkeypatch.setattr(publish_merge, "run", fake)
    assert "moved" in publish_merge.refresh_branch("publish/a-v1", "h1", APP, "e", str(tmp_path))
    assert not any(c[:2] == ["git", "push"] for c in seen)
