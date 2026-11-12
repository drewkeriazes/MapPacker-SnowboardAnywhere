"""FEAT-272: publish_merge.py decides whether a publish PR releases its draft and merges itself. Every gh call is
faked (FakeGitHub); the refresh test runs real git against a local bare repo, no network."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_merge  # noqa: E402
from publish_merge import (activity_complete, catalog_problem, decide, files_ok, label_ok,  # noqa: E402
                           parse_branch, publish_file_patterns, pushes_after_label_ok, rebase_catalog)
from publish_pack import asset_url  # noqa: E402

REPO = "o/r"
APP = "pub[bot]"
T_LABEL = "2026-11-12T10:00:00Z"


def labeled(label, login, at=T_LABEL):
    return {"event": "labeled", "label": {"name": label}, "actor": {"login": login}, "created_at": at}


def act(kind, login, at, after="h1", ref="refs/heads/publish/a-v1"):
    """an entry of GitHub's activity log for a branch (GET repos/{repo}/activity): who pushed, when, to what"""
    return {"activity_type": kind, "actor": {"login": login}, "timestamp": at, "after": after, "before": "b",
            "ref": ref}


CREATED = act("branch_creation", "drewkeriazes", "2026-11-12T09:00:00Z")


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


def test_a_push_after_the_label_blocks_unless_it_is_the_refresh():
    t = T_LABEL
    # a commit backdated to 09:00 still shows as a push at 11:00 by whoever pushed it
    assert not pushes_after_label_ok([CREATED, act("push", "someone", "2026-11-12T11:00:00Z")], t, APP)
    assert pushes_after_label_ok([CREATED, act("push", APP, "2026-11-12T11:00:00Z")], t, APP)
    assert not pushes_after_label_ok([CREATED, act("force_push", "drewkeriazes", "2026-11-12T11:00:00Z")], t, APP)
    assert not pushes_after_label_ok([CREATED, act("push", "drewkeriazes", T_LABEL)], t, APP), "at the label counts"
    assert pushes_after_label_ok([act("branch_creation", "drewkeriazes", T_LABEL)], t, APP)
    assert not pushes_after_label_ok([act("branch_deletion", "someone", "2026-11-12T11:00:00Z")], t, APP)
    assert not pushes_after_label_ok([CREATED, act("push", APP, "2026-11-12T11:00:00Z")], t, ""), "no App login"
    assert not pushes_after_label_ok([{"activity_type": "push", "actor": None}], t, APP), "no timestamp"


def test_the_activity_log_must_reach_the_head_and_the_label():
    assert activity_complete([CREATED], T_LABEL, "h1")
    assert not activity_complete([], T_LABEL, "h1")
    assert not activity_complete([CREATED], T_LABEL, "h2"), "the newest entry is not the head: stale"
    assert not activity_complete([act("push", APP, "2026-11-12T11:00:00Z")], T_LABEL, "h1"), "cut short"
    assert not activity_complete([{"after": "h1"}], T_LABEL, "h1")


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
        self.state = {
            "pr": {"number": 7, "state": p["state"], "merged": p["merged"], "body": p["body"],
                   "labels": [{"name": n} for n in p["labels"]], "base": {"ref": "main"},
                   "head": {"ref": p["headRefName"], "sha": "h1", "repo": {"full_name": "x/fork" if p["fork"] else REPO}},
                   "merge_commit_sha": "m1", "changed_files": len(files)},
            "files": files, "activity": [CREATED],
            "timeline": [labeled("automerge", "drewkeriazes"), {"event": "committed"}],
            "compare": {"behind_by": 0, "base": "b0"},
            "checks": [{"name": "publish-check", "status": "completed", "conclusion": "success", "details_url": ""},
                       {"name": "pipeline-tests", "status": "completed", "conclusion": "skipped", "details_url": ""}],
            "catalogs": {"b0": {"resorts": []}, "h1": {"resorts": [entry("a", 1)]}, "m1": {"resorts": [entry("a", 1)]}},
            "release_draft": release_draft, "comments": [], "open_prs": [], "run_actor": "drewkeriazes",
            "fail": [], "merge_says_moved": False, "closed_prs": [], "open_list": [], "others": {},
        }
        self.state.update(over)
        self.calls = Calls()

    def __call__(self, cmd, cwd=None, capture=True):
        self.calls.append(list(cmd))
        s = self.state
        if cmd[:3] == ["gh", "pr", "merge"] and s["merge_says_moved"]:     # gh's error for --match-head-commit
            raise SystemExit("GraphQL: Head branch was modified. Review and try the merge again.")
        if any(cmd[:len(f)] == f for f in s["fail"]):
            raise SystemExit(f"{' '.join(cmd)} failed")
        if cmd[:4] == ["gh", "api", "-X", "DELETE"]:
            return ""
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
        if path.startswith("pulls/") and path[6:].isdigit() and int(path[6:]) in s["others"]:
            return json.dumps(s["others"][int(path[6:])])
        if path == "pulls/7/files":
            return json.dumps(s["files"])
        if path == "activity?ref=refs/heads/publish/a-v1&per_page=100":
            return json.dumps(s["activity"])
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
            return json.dumps(s["run"] if "run" in s else
                              {"triggering_actor": {"login": s["run_actor"]}, "path": publish_merge.BUILD_WORKFLOW,
                               "head_branch": "main", "event": "workflow_dispatch"})
        if path.startswith("pulls?state=closed"):
            return json.dumps(s["closed_prs"])
        if path.startswith("pulls?state=open&base=main"):          # advance_open's listing
            return json.dumps(s["open_list"])
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
    assert ["gh", "release", "edit", "a/v1", "--draft=false"] in calls


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
    assert released(calls) == [["gh", "release", "edit", "a/v1", "--draft=false"]]
    assert merged(calls) == [["gh", "pr", "merge", "7", "--squash", "--match-head-commit", "h1"]]
    assert calls.index(released(calls)[0]) < calls.index(merged(calls)[0])
    view = [i for i, c in enumerate(calls) if c[:3] == ["gh", "release", "view"]]
    assert view and view[-1] < calls.index(released(calls)[0]), "the draft is re-checked right before publishing"


@pytest.mark.parametrize("why, pr, over", [
    ("label by a non-maintainer", {}, {"timeline": [labeled("automerge", "someone")]}),
    ("label by the App, no run", {}, {"timeline": [labeled("automerge", APP)]}),
    ("label by the App for a stranger's run", {"body": "Run: https://github.com/o/r/actions/runs/5\n"},
     {"timeline": [labeled("automerge", APP)], "run_actor": "someone"}),
    ("label by the App for a maintainer's run of a branch's workflow copy",
     {"body": "Run: https://github.com/o/r/actions/runs/5\n"},
     {"timeline": [labeled("automerge", APP)], "run": {"triggering_actor": {"login": "drewkeriazes"},
      "path": ".github/workflows/build-pack.yml", "head_branch": "evil", "event": "workflow_dispatch"}}),
    ("timeline unreadable", {}, {"fail": [["gh", "api", f"repos/{REPO}/issues/7/timeline"]]}),
    ("a backdated commit pushed after the label", {}, {"activity": [act("branch_creation", "drewkeriazes",
     "2026-11-12T09:00:00Z", after="h0"), act("push", "someone", "2026-11-12T11:00:00Z")]}),
    ("a force push after the label", {}, {"activity": [act("branch_creation", "drewkeriazes", "2026-11-12T09:00:00Z",
     after="h0"), act("force_push", "drewkeriazes", "2026-11-12T11:00:00Z")]}),
    ("activity unreadable", {}, {"fail": [["gh", "api",
                                           f"repos/{REPO}/activity?ref=refs/heads/publish/a-v1&per_page=100"]]}),
    ("activity stale", {}, {"activity": [act("branch_creation", "drewkeriazes", "2026-11-12T09:00:00Z", after="h0")]}),
    ("activity cut short", {}, {"activity": [act("push", APP, "2026-11-12T11:00:00Z")]}),
    ("activity of another branch", {}, {"activity": [act("branch_creation", "drewkeriazes", "2026-11-12T09:00:00Z",
                                                         ref="refs/heads/main")]}),
    ("a code file", {}, {"files": [{"filename": "catalog.json"}, {"filename": "pipeline/build_pack.py"}]}),
    ("a file moved out of the code", {}, {"files": [{"filename": "resorts/a/x.py", "previous_filename": "pipeline/x.py"}]}),
    ("more files than listed", {}, {"pr": None}),
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
    if "pr" in over:                  # the PR counts one more file than the API lists
        calls = fake_gh(monkeypatch, pr=pr, release_draft=True)
        calls.state["pr"]["changed_files"] += 1
    else:
        calls = fake_gh(monkeypatch, pr=pr, **over)
    publish_merge.main(["ready", "7"])
    assert not released(calls), why
    assert not merged(calls), why


def test_the_apps_refresh_push_after_the_label_still_merges(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, activity=[
        act("branch_creation", "drewkeriazes", "2026-11-12T09:00:00Z", after="h0"),
        act("push", APP, "2026-11-12T11:00:00Z")])
    assert publish_merge.main(["ready", "7"]) == 0
    assert merged(calls)


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
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, comments=[{"body": said[0], "user": {"login": APP}}], **over)
    publish_merge.main(["ready", "7"])
    assert not comments(calls)


def test_someone_elses_prefixed_comment_does_not_silence_a_refusal(monkeypatch):
    over = {"timeline": [labeled("automerge", "someone")]}
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, **over)
    publish_merge.main(["ready", "7"])
    said = comments(calls)[0]
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, comments=[{"body": said, "user": {"login": "someone"}}],
                    **over)
    publish_merge.main(["ready", "7"])
    assert comments(calls) == [said]


def test_a_failed_release_edit_stops_before_the_merge(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, fail=[["gh", "release", "edit"]])
    assert publish_merge.main(["ready", "7"]) == 1
    assert not merged(calls)


def test_a_failed_merge_after_the_release_retries_then_comments(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, fail=[["gh", "pr", "merge"]])
    assert publish_merge.main(["ready", "7"]) == 1
    assert len(merged(calls)) == 4
    assert any("merge failed" in c for c in comments(calls))


def test_a_branch_that_moved_before_the_merge_stops_without_retrying(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, merge_says_moved=True)
    assert publish_merge.main(["ready", "7"]) == 0
    assert len(merged(calls)) == 1
    assert [c for c in comments(calls) if "moved" in c] and not [c for c in comments(calls) if "4 times" in c]


def test_a_moved_head_found_by_rereading_the_pr_stops_too(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, fail=[["gh", "pr", "merge"]])
    real = publish_merge.run

    def moved(cmd, cwd=None, capture=True):
        if cmd[:3] == ["gh", "pr", "merge"]:
            calls.state["pr"]["head"]["sha"] = "h2"
        return real(cmd, cwd, capture)
    monkeypatch.setattr(publish_merge, "run", moved)
    assert publish_merge.main(["ready", "7"]) == 0
    assert len(merged(calls)) == 1 and any("moved" in c for c in comments(calls))


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
    (work / "RELEASES.md").write_text("a v1 only\n")         # both sides change it: a conflict the refresh rewrites
    os.makedirs(work / "reports"); (work / "reports" / "a.md").write_text("a\n")
    git(work, "add", "."); git(work, "commit", "-qm", "a v1"); git(work, "push", "-q", "origin", "publish/a-v1")
    head = git(work, "rev-parse", "HEAD")
    git(work, "switch", "-q", "main")
    write_catalog(work, {"resorts": [entry("b", 1)]})
    (work / "RELEASES.md").write_text("b v1 only\n")
    git(work, "add", "."); git(work, "commit", "-qm", "b v1"); git(work, "push", "-q", "origin", "HEAD:main")
    rels = [{"tag_name": "a/v1", "name": "a v1", "draft": True, "created_at": "2026-11-12T00:00:00Z", "assets": []},
            {"tag_name": "b/v1", "name": "b v1", "draft": False, "published_at": "2026-11-11T00:00:00Z", "assets": []},
            {"tag_name": "c/v1", "name": "c v1", "draft": True, "created_at": "2026-11-12T00:00:00Z", "assets": []}]

    publish_merge.refresh_branch("publish/a-v1", head, APP, "1+pub[bot]@users.noreply.github.com", str(work),
                                 releases=rels, repo=REPO)

    git(work, "fetch", "-q", "origin")
    tip = "origin/publish/a-v1"
    cat = json.loads(git(work, "show", f"{tip}:catalog.json"))
    assert sorted(r["slug"] for r in cat["resorts"]) == ["a", "b"]
    index = git(work, "show", f"{tip}:RELEASES.md")
    assert "releases/tag/a/v1) (latest)" in index and "releases/tag/b/v1) (latest)" in index
    assert "c/v1" not in index, "another publish's draft is not out yet"
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


def test_refresh_pushes_nothing_when_the_merge_did_not_start(tmp_path, monkeypatch):
    seen = []

    def fake(cmd, cwd=None, capture=True):
        seen.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            if "MERGE_HEAD" in cmd:
                raise SystemExit("no MERGE_HEAD")
            return "h1"
        if cmd[:2] == ["git", "show"]:
            return json.dumps({"resorts": []})
        if "merge" in cmd and "--no-commit" in cmd:
            raise SystemExit("fatal: refusing to merge unrelated histories")
        return ""
    monkeypatch.setattr(publish_merge, "run", fake)
    with pytest.raises(SystemExit, match="did not start"):
        publish_merge.refresh_branch("publish/a-v1", "h1", APP, "e", str(tmp_path))
    assert not any(c[:2] in (["git", "commit"], ["git", "push"]) or "commit" in c for c in seen)


def test_ready_first_publishes_the_draft_of_a_recently_merged_publish_pr(monkeypatch):
    other = [{"number": 7, "merged_at": "2026-11-12T10:00:00Z", "head": {"ref": "publish/a-v1"}},
             {"number": 8, "merged_at": None, "head": {"ref": "publish/b-v1"}},          # closed unmerged: left alone
             {"number": 9, "merged_at": "2026-11-12T10:00:00Z", "head": {"ref": "feature/x"}}]
    calls = fake_gh(monkeypatch, pr={"merged": True, "state": "closed"}, release_draft=True, closed_prs=other)
    publish_merge.sweep(REPO)
    assert released(calls) == [["gh", "release", "edit", "a/v1", "--draft=false"]]
    assert not any(c[:3] == ["gh", "release", "delete"] for c in calls)


def test_sweep_leaves_a_draft_main_does_not_name_and_never_raises(monkeypatch):
    other = [{"number": 7, "merged_at": "t", "head": {"ref": "publish/a-v1"}}]
    calls = fake_gh(monkeypatch, pr={"merged": True, "state": "closed"}, release_draft=True, closed_prs=other,
                    catalogs={"m1": {"resorts": []}})
    publish_merge.sweep(REPO)
    assert not released(calls)
    calls = fake_gh(monkeypatch, pr={"merged": True, "state": "closed"}, release_draft=True)

    def boom(*a, **k):
        raise SystemExit("gh failed")
    monkeypatch.setattr(publish_merge, "api", boom)
    publish_merge.sweep(REPO)
    assert not released(calls)


def test_ready_runs_the_sweep_before_its_own_decision(monkeypatch):
    seen = []
    fake_gh(monkeypatch, pr={}, release_draft=True)
    monkeypatch.setattr(publish_merge, "sweep", lambda repo, skip=None: seen.append(skip))
    publish_merge.main(["ready", "7"])
    assert seen == [7]


def test_sweep_reads_one_page_not_the_whole_history(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": True, "state": "closed"}, release_draft=True)
    publish_merge.sweep(REPO)
    listing = [c for c in calls if len(c) > 2 and "pulls?state=closed" in c[2]]
    assert len(listing) == 1 and "--paginate" not in listing[0] and "per_page=20" in listing[0][2]


@pytest.mark.parametrize("pr, base", [({"fork": True}, "main"), ({}, "dev")])
def test_sweep_leaves_a_merged_fork_or_non_main_pr_alone(monkeypatch, pr, base):
    other = [{"number": 7, "merged_at": "t", "head": {"ref": "publish/a-v1"}}]
    calls = fake_gh(monkeypatch, pr={"merged": True, "state": "closed", **pr}, release_draft=True, closed_prs=other)
    calls.state["pr"]["base"]["ref"] = base
    publish_merge.sweep(REPO)
    assert not released(calls)


# --- every run also advances the other open publish PRs (advance_open) ---------------------------------------------

def listed_pr(n, ref="publish/a-v1", labels=("publish", "automerge"), repo=REPO, base="main"):
    """a PR as GET pulls?state=open lists it"""
    return {"number": n, "head": {"ref": ref, "repo": {"full_name": repo}}, "base": {"ref": base},
            "labels": [{"name": x} for x in labels]}


def deleted_branches(calls):
    return [c for c in calls if c[:4] == ["gh", "api", "-X", "DELETE"]]


def test_a_run_for_pr_a_also_releases_and_merges_pr_b(monkeypatch):
    # A (#6) merged; its `closed` run is the only run left in the queue (B's `ready` was dropped). B (#7) is green.
    a = {"number": 6, "state": "closed", "merged": True, "merge_commit_sha": "m1", "labels": [{"name": "publish"}],
         "base": {"ref": "main"}, "head": {"ref": "publish/c-v1", "sha": "c1", "repo": {"full_name": REPO}}}
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, others={6: a}, open_list=[listed_pr(7)])
    calls.state["catalogs"]["m1"] = {"resorts": [entry("a", 1), entry("c", 1)]}
    assert publish_merge.main(["closed", "6"]) == 0
    assert ["gh", "release", "edit", "c/v1", "--draft=false"] in calls          # A's own job
    assert ["gh", "release", "edit", "a/v1", "--draft=false"] in calls          # B, advanced
    assert merged(calls) == [["gh", "pr", "merge", "7", "--squash", "--match-head-commit", "h1"]]


def test_a_run_for_pr_a_refreshes_pr_b_left_behind_main(monkeypatch):
    a = {"number": 6, "state": "closed", "merged": True, "merge_commit_sha": "m1", "labels": [{"name": "publish"}],
         "base": {"ref": "main"}, "head": {"ref": "publish/c-v1", "sha": "c1", "repo": {"full_name": REPO}}}
    calls = fake_gh(monkeypatch, pr={}, release_draft=False, others={6: a}, open_list=[listed_pr(7)],
                    compare={"behind_by": 1, "base": "b0"})
    seen = []
    monkeypatch.setattr(publish_merge, "refresh", lambda repo, branch, sha, app: seen.append(branch) or "refreshed")
    assert publish_merge.main(["closed", "6"]) == 0
    assert seen == ["publish/a-v1"] and not merged(calls)


def test_the_schedule_with_no_pr_advances_the_open_publish_prs(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, open_list=[listed_pr(7)])
    assert publish_merge.main(["sweep"]) == 0
    assert any(len(c) > 2 and "pulls?state=closed" in c[2] for c in calls), "the merged-draft sweep runs too"
    assert merged(calls) == [["gh", "pr", "merge", "7", "--squash", "--match-head-commit", "h1"]]


def test_the_schedule_with_nothing_open_does_nothing(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True)
    assert publish_merge.main(["sweep"]) == 0
    assert not released(calls) and not merged(calls) and not comments(calls)


def test_sweep_takes_no_pr_and_the_others_need_one(monkeypatch):
    fake_gh(monkeypatch, pr={}, release_draft=True)
    for argv in (["sweep", "7"], ["ready"], ["closed"]):
        with pytest.raises(SystemExit):
            publish_merge.main(argv)


def test_advance_picks_only_open_same_repo_main_automerge_publish_prs_and_skips_this_runs(monkeypatch):
    seen = []
    fake_gh(monkeypatch, pr={}, release_draft=True, open_list=[
        listed_pr(7), listed_pr(8, ref="feature/x"), listed_pr(9, labels=("publish",)),
        listed_pr(10, repo="x/fork"), listed_pr(11, base="dev"), listed_pr(12, ref="publish/b-v2"), listed_pr(13)])
    monkeypatch.setattr(publish_merge, "ready", lambda n, repo, app, sweep_closed=True: seen.append((n, sweep_closed)))
    publish_merge.advance_open(REPO, APP, skip=13)
    assert seen == [(7, False), (12, False)]


def test_advance_reads_one_page_and_a_failure_in_one_pr_does_not_stop_the_next(monkeypatch):
    seen = []
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, open_list=[listed_pr(n) for n in range(1, 30)])

    def ready(n, repo, app, sweep_closed=True):
        seen.append(n)
        raise SystemExit("gh failed") if n == 1 else RuntimeError("odd data") if n == 2 else None
    monkeypatch.setattr(publish_merge, "ready", ready)
    publish_merge.advance_open(REPO, APP)
    assert seen == list(range(1, 21))
    listing = [c for c in calls if len(c) > 2 and "pulls?state=open&base=main" in c[2]]
    assert len(listing) == 1 and "--paginate" not in listing[0] and "per_page=20" in listing[0][2]


def test_advance_never_changes_the_runs_own_exit_code(monkeypatch):
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, fail=[["gh", "release", "edit"]],
                    open_list=[listed_pr(8)])
    assert publish_merge.main(["ready", "7"]) == 1           # its own release edit failed
    calls = fake_gh(monkeypatch, pr={}, release_draft=True,
                    fail=[["gh", "api", f"repos/{REPO}/pulls?state=open&base=main&sort=updated&direction=desc&per_page=20"]])
    assert publish_merge.main(["ready", "7"]) == 0 and merged(calls)   # the listing failed: still 0
    calls = fake_gh(monkeypatch, pr={}, release_draft=True, open_list=[listed_pr(8)])
    monkeypatch.setattr(publish_merge, "ready", lambda *a, **k: (_ for _ in ()).throw(SystemExit("boom")))
    assert publish_merge.main(["closed", "7"]) == 0        # #8 blew up in advance; closed's own result stands


# --- a closed, unmerged publish PR also loses its branch ------------------------------------------------------------

def test_closed_unmerged_deletes_the_branch_after_the_draft(monkeypatch):
    calls = fake_gh(monkeypatch, pr={"merged": False}, release_draft=True)
    assert publish_merge.main(["closed", "7"]) == 0
    dele = ["gh", "api", "-X", "DELETE", f"repos/{REPO}/git/refs/heads/publish/a-v1"]
    assert dele in calls
    assert calls.index(dele) > next(i for i, c in enumerate(calls) if c[:3] == ["gh", "release", "delete"])
    calls = fake_gh(monkeypatch, pr={"merged": False}, release_draft=False)   # a rollback's: no draft, still goes
    publish_merge.main(["closed", "7"])
    assert deleted_branches(calls) == [dele]


@pytest.mark.parametrize("pr, over", [
    ({"merged": True}, {}),                                   # merged: GitHub deletes it (delete_branch_on_merge)
    ({"fork": True}, {}),
    ({"headRefName": "feature/x"}, {}),
    ({}, {"open_prs": [{"number": 8}]}),                      # another open PR uses the branch
    ({}, {"fail": [["gh", "api", f"repos/{REPO}/pulls?state=open&head=o:publish/a-v1"]]}),
])
def test_the_branch_is_deleted_only_for_an_unmerged_same_repo_publish_pr(monkeypatch, pr, over):
    calls = fake_gh(monkeypatch, pr=pr, release_draft=True, **over)
    publish_merge.closed(7, REPO)
    assert not deleted_branches(calls)


def test_a_failed_branch_delete_only_warns(monkeypatch, capsys):
    fake_gh(monkeypatch, pr={"merged": False}, release_draft=True, fail=[["gh", "api", "-X", "DELETE"]])
    assert publish_merge.closed(7, REPO) == 0
    assert "could not delete the branch publish/a-v1" in capsys.readouterr().out


@pytest.mark.parametrize("run,want", [
    ({"path": ".github/workflows/build-pack.yml", "head_branch": "main", "event": "workflow_dispatch",
      "triggering_actor": {"login": "drewkeriazes"}}, "drewkeriazes"),
    ({"path": ".github/workflows/build-pack.yml", "head_branch": "evil", "event": "workflow_dispatch",
      "triggering_actor": {"login": "drewkeriazes"}}, None),
    ({"path": ".github/workflows/other.yml", "head_branch": "main", "event": "workflow_dispatch",
      "triggering_actor": {"login": "drewkeriazes"}}, None),
    ({"path": ".github/workflows/build-pack.yml", "head_branch": "main", "event": "push",
      "triggering_actor": {"login": "drewkeriazes"}}, None),
    ({}, None),
])
def test_only_a_build_pack_run_dispatched_on_main_vouches_for_an_app_label(run, want):
    assert publish_merge.build_run_actor(run) == want
