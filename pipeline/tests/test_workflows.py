"""FEAT-272: static checks on the publish workflows' YAML, and the `pure` subcommand the reviewer skip runs."""
import os
import sys

import pytest

yaml = pytest.importorskip("yaml")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import publish_merge  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return yaml.safe_load(f)


def all_steps(wf):
    return [s for job in wf["jobs"].values() for s in job.get("steps", [])]


def triggers(wf):
    return wf.get("on", wf.get(True))     # YAML 1.1 reads a bare `on` as True


def test_publish_merge_never_checks_out_the_pr():
    wf = load(".github/workflows/publish-merge.yml")
    seen = [s for s in all_steps(wf) if s.get("uses", "").startswith("actions/checkout")]
    assert seen
    for step in seen:
        assert step.get("with", {}).get("ref") == "main"
        assert step["with"].get("fetch-depth") == 0


def test_publish_merge_uses_the_app_token_and_one_at_a_time():
    wf = load(".github/workflows/publish-merge.yml")
    job = wf["jobs"]["publish-merge"]
    assert "concurrency" not in wf                      # per job: a run the job's `if` skips must not queue
    assert job["concurrency"] == {"group": "publish-merge", "cancel-in-progress": False}
    assert any("create-github-app-token" in s.get("uses", "") for s in all_steps(wf))
    assert list(wf["jobs"]) == ["publish-merge"] and wf["jobs"]["publish-merge"].get("name", "publish-merge") == "publish-merge"


def test_publish_merge_triggers_and_branch_gate():
    wf = load(".github/workflows/publish-merge.yml")
    on = triggers(wf)
    assert on["workflow_run"] == {"workflows": ["Checks"], "types": ["completed"]}
    assert on["pull_request_target"]["types"] == ["labeled", "closed"]
    assert "publish/" in str(wf["jobs"]["publish-merge"]["if"])


def test_publish_merge_narrows_the_app_token():
    wf = load(".github/workflows/publish-merge.yml")
    app = next(s for s in all_steps(wf) if "create-github-app-token" in s.get("uses", ""))
    perms = {k: v for k, v in app["with"].items() if k.startswith("permission-")}
    assert perms == {"permission-contents": "write", "permission-pull-requests": "write",
                     "permission-issues": "read", "permission-actions": "read"}


def test_publish_merge_runs_no_pr_code_and_keeps_the_token_for_the_tool():
    wf = load(".github/workflows/publish-merge.yml")
    steps = all_steps(wf)
    tool = next(s for s in steps if "publish_merge.py" in s.get("run", ""))
    assert tool["env"]["GH_TOKEN"] == "${{ steps.app.outputs.token }}"
    for s in steps:
        assert "pr checkout" not in s.get("run", "") and "pull/" not in s.get("run", "")
        if s.get("uses", "").startswith("actions/checkout"):
            assert "repository" not in s.get("with", {})
    names = [s.get("uses", "") + s.get("run", "") for s in steps]
    pip = next(i for i, n in enumerate(names) if "pip install" in n)
    checkout = next(i for i, n in enumerate(names) if n.startswith("actions/checkout"))
    assert pip < checkout                                # nothing installs while the App token is persisted


def test_publish_merge_hands_the_tool_its_env():
    wf = load(".github/workflows/publish-merge.yml")
    text = open(os.path.join(ROOT, ".github/workflows/publish-merge.yml"), encoding="utf-8").read()
    for name in ("GH_TOKEN", "GITHUB_REPOSITORY", "PUBLISH_APP_LOGIN", "PUBLISH_APP_ID", "PUBLISH_APP_KEY"):
        assert name in text
    assert any("publish_merge.py" in s.get("run", "") for s in all_steps(wf))


def test_review_runs_on_a_publish_pr_with_code():
    assert publish_merge.files_ok(["catalog.json", "pipeline/x.py"], "a") is False   # pure -> false -> review runs
    wf = load(".github/workflows/pr-review.yml")
    assert any("publish_merge.py pure" in s.get("run", "") for s in all_steps(wf))


def test_a_manual_review_run_is_never_skipped():
    wf = load(".github/workflows/pr-review.yml")
    step = next(s for s in all_steps(wf) if "publish_merge.py pure" in s.get("run", ""))
    assert step["env"]["EVENT"] == "${{ github.event_name }}"
    assert "workflow_dispatch" in step["run"] and step["run"].index("workflow_dispatch") < step["run"].index("publish_merge.py")


def test_review_steps_after_the_pure_check_are_skipped_when_true():
    wf = load(".github/workflows/pr-review.yml")
    steps = all_steps(wf)
    i = next(i for i, s in enumerate(steps) if "publish_merge.py pure" in s.get("run", ""))
    pure_id = steps[i]["id"]
    for s in steps[i + 1:]:
        assert f"steps.{pure_id}.outputs.pure != 'true'" in str(s.get("if", "")), s
    co = steps[i - 1] if "checkout" in steps[i - 1].get("uses", "") else None
    assert co and co["with"]["ref"] == "main"
    assert "review loop" in str(wf["jobs"]["review"]["if"])


def fake_pr(monkeypatch, *, labels=("publish",), branch="publish/a-v1", files=("catalog.json",), changed=None, fail=False,
            fork=False, base="main", renamed=None):
    pr = {"labels": [{"name": n} for n in labels], "base": {"ref": base},
          "head": {"ref": branch, "repo": {"full_name": "x/fork" if fork else "o/r"}},
          "changed_files": len(files) if changed is None else changed}

    def api(path):
        if fail:
            raise SystemExit("gh failed")
        return pr
    monkeypatch.setattr(publish_merge, "api", api)
    listed = [{"filename": f, **({"previous_filename": renamed} if renamed and f == files[0] else {})} for f in files]
    monkeypatch.setattr(publish_merge, "api_pages", lambda path, key=None: listed)
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")


@pytest.mark.parametrize("kw, want", [
    ({}, "true"),
    ({"files": ("catalog.json", "reports/a.md", "resorts/a/a.json")}, "true"),
    ({"files": ("catalog.json", "pipeline/x.py")}, "false"),
    ({"labels": ()}, "false"),
    ({"branch": "feature/x"}, "false"),
    ({"branch": "publish/b-v1", "files": ("reports/a.md",)}, "false"),
    ({"changed": 9}, "false"),
    ({"fail": True}, "false"),
    ({"fork": True}, "false"),
    ({"base": "dev"}, "false"),
    ({"files": ("resorts/a/x.py",), "renamed": "pipeline/x.py"}, "false"),
])
def test_pure_prints_true_only_for_a_publish_pr_changing_only_its_files(monkeypatch, capsys, kw, want):
    fake_pr(monkeypatch, **kw)
    assert publish_merge.main(["pure", "7"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == want
