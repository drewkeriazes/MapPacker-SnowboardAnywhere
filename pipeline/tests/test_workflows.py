"""FEAT-272: static checks on the publish workflows' YAML, and the `pure` subcommand the reviewer skip runs. FEAT-266:
the issue forms against the form schema and the build-pack inputs."""
import os
import re
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
    assert on["workflow_run"] == {"workflows": ["Checks", "Claude PR review"], "types": ["completed"]}
    assert on["pull_request_target"]["types"] == ["labeled", "closed"]
    assert "publish/" in str(wf["jobs"]["publish-merge"]["if"])


def test_the_review_workflow_name_is_the_one_publish_merge_waits_on():
    waits_on = triggers(load(".github/workflows/publish-merge.yml"))["workflow_run"]["workflows"]
    assert load(".github/workflows/pr-review.yml")["name"] in waits_on
    assert load(".github/workflows/checks.yml")["name"] == "Checks"


def test_publish_merge_also_runs_on_a_schedule_and_by_hand():
    wf = load(".github/workflows/publish-merge.yml")
    on, job = triggers(wf), wf["jobs"]["publish-merge"]
    assert on["schedule"] == [{"cron": "*/15 * * * *"}] and "workflow_dispatch" in on
    cond = " ".join(str(job["if"]).split())
    assert "github.event_name == 'schedule' && vars.PUBLISH_APP_LOGIN != ''" in cond   # no App yet: no failing run
    assert "github.event_name == 'workflow_dispatch'" in cond
    assert "'sweep'" in job["env"]["ACTION"] and "schedule" in job["env"]["ACTION"]
    tool = next(s for s in all_steps(wf) if "publish_merge.py" in s.get("run", ""))
    assert "publish_merge.py sweep" in tool["run"] and 'publish_merge.py "$ACTION" "$PR_NUMBER"' in tool["run"]


def test_publish_merge_narrows_the_app_token():
    wf = load(".github/workflows/publish-merge.yml")
    app = next(s for s in all_steps(wf) if "create-github-app-token" in s.get("uses", ""))
    perms = {k: v for k, v in app["with"].items() if k.startswith("permission-")}
    assert perms == {"permission-contents": "write", "permission-pull-requests": "write",
                     "permission-issues": "read", "permission-actions": "read", "permission-checks": "read"}


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


# ------------------------------------------------------------------------------------------------ build-pack (FEAT-245)

BUILD = ".github/workflows/build-pack.yml"


def test_build_pack_never_interpolates_an_input_or_a_secret_into_a_shell_line():
    for step in all_steps(load(BUILD)):
        run = step.get("run", "")
        assert "${{" not in run, f"step {step.get('name') or run[:40]!r} puts an expression in its shell line"


def test_build_pack_inputs_reach_the_steps_as_env():
    wf = load(BUILD)
    assert set(triggers(wf)["workflow_dispatch"]["inputs"]) == {"rebuild", "slug", "name", "osm_id", "requested_by"}
    assert wf["env"] == {"SLUG": "${{ inputs.slug }}", "REBUILD": "${{ inputs.rebuild }}", "NAME": "${{ inputs.name }}",
                         "OSM_ID": "${{ inputs.osm_id }}", "REQUESTED_BY": "${{ inputs.requested_by }}"}


def test_build_pack_rebuild_list_names_only_packs_that_can_be_rebuilt():
    """FEAT-297: a choice list, the new-resort entry first, then packs with a config that is not a relocate source.
    Only this direction is checked: a publish PR adds a resort to the catalog but can't edit the workflow (the App
    has no Workflows permission), so a new resort waits for rebuild_choices.py --write"""
    sys.path.insert(0, os.path.join(ROOT, "tools", "ci"))
    import rebuild_choices as rc
    inp = triggers(load(BUILD))["workflow_dispatch"]["inputs"]["rebuild"]
    assert inp["type"] == "choice" and inp["required"] is False and inp["default"] == rc.NEW
    assert inp["options"][0] == rc.NEW and len(inp["options"]) > 1
    assert inp["options"] == rc.read_list(open(os.path.join(ROOT, BUILD), encoding="utf-8").read())
    for slug in inp["options"][1:]:
        assert rc.rebuildable(slug, os.path.join(ROOT, "resorts")), f"{slug} is on the rebuild list but can't be rebuilt"
    assert inp["options"][1:] == sorted(inp["options"][1:])
    assert triggers(load(BUILD))["workflow_dispatch"]["inputs"]["slug"]["required"] is False
    assert load(BUILD)["run-name"] == "Build pack ${{ inputs.slug || inputs.rebuild }}"   # the game reads the slug off it


def test_rebuild_choices_writes_the_list_in_place():
    sys.path.insert(0, os.path.join(ROOT, "tools", "ci"))
    import rebuild_choices as rc
    text = "a:\n  options:\n    " + rc.MARKER + "\n    - '" + rc.NEW + "'\n    - old\n  next: 1\n"
    out = rc.write_list(text, [rc.NEW, "bigsky", "vail"])
    assert rc.read_list(out) == [rc.NEW, "bigsky", "vail"] and out.endswith("    - vail\n  next: 1\n")
    assert rc.write_list(out, [rc.NEW, "bigsky", "vail"]) == out


def test_build_pack_queues_then_probes_then_builds_on_hosted_runners():
    wf = load(BUILD)
    jobs = wf["jobs"]
    assert list(jobs) == ["queue", "probe", "build", "outcome"]
    assert jobs["probe"]["needs"] == "queue" and jobs["build"]["needs"] == "probe"
    # FEAT-314: every attempt is judged and logged, and that job never turns the run red
    assert jobs["outcome"]["needs"] == ["queue", "probe", "build"] and jobs["outcome"]["if"] == "always()"
    (rec,) = [s for s in jobs["outcome"]["steps"] if "build_failures.py" in s.get("run", "")]
    assert rec["continue-on-error"] is True and rec["run"].strip().endswith("build_failures.py record")
    assert all(j["runs-on"] == "ubuntu-latest" for j in jobs.values())
    assert "concurrency" not in wf and not any("concurrency" in j for j in jobs.values())   # wait_turn.py queues
    assert any("wait_turn.py" in s.get("run", "") for s in jobs["queue"]["steps"])
    assert any("probe_hosts.py" in s.get("run", "") for s in jobs["probe"]["steps"])


def test_build_pack_runs_main_without_kept_credentials():
    for step in all_steps(load(BUILD)):
        if step.get("uses", "").startswith("actions/checkout"):
            assert step["with"]["ref"] == "main" and step["with"]["persist-credentials"] is False


def test_build_pack_names_a_step_per_stage_in_order():
    names = [s.get("name") for s in load(BUILD)["jobs"]["build"]["steps"]]
    stages = ["inputs", "resolve", "fetch", "build", "report", "publish"]
    assert [n for n in names if n in stages] == stages
    for s in load(BUILD)["jobs"]["build"]["steps"]:
        if s.get("name") in stages:
            assert s["run"].strip().splitlines()[-1] == f"python tools/ci/build_pack_ci.py {s['name']}"


def test_build_pack_gives_the_secrets_only_to_the_steps_that_need_them():
    steps = load(BUILD)["jobs"]["build"]["steps"]
    holders = {s.get("name") or s.get("id"): s for s in steps if "secrets." in str(s) or "steps.app" in str(s)}
    assert set(holders) == {"fetch", "the App is set up", "app", "publish"}
    assert holders["fetch"]["env"] == {"LANDFIRE_EMAIL": "${{ secrets.LANDFIRE_EMAIL }}"}
    assert holders["publish"]["env"]["GH_TOKEN"] == "${{ steps.app.outputs.token }}"
    names = [s.get("name") or s.get("id") for s in steps]
    assert names.index("app") == names.index("publish") - 1     # minted last: the token lasts an hour


def test_build_pack_narrows_the_app_token_to_publishing():
    (app,) = [s for s in all_steps(load(BUILD)) if "create-github-app-token" in s.get("uses", "")]
    assert {k for k in app["with"] if k.startswith("permission-")} == {"permission-contents", "permission-pull-requests"}


def test_build_pack_retry_reruns_a_run_from_env_only():
    """FEAT-314: the retry workflow is a workflow_dispatch (the one event the workflow token may start), its inputs
    reach the step as env, and it can re-run runs but not push"""
    wf = load(".github/workflows/build-pack-retry.yml")
    assert set(triggers(wf)["workflow_dispatch"]["inputs"]) == {"run_id", "attempt"}
    assert wf["permissions"] == {"actions": "write", "contents": "read"}
    for step in all_steps(wf):
        assert "${{" not in step.get("run", "")
        if step.get("uses", "").startswith("actions/checkout"):
            assert step["with"]["ref"] == "main" and step["with"]["persist-credentials"] is False
    (run,) = [s for s in all_steps(wf) if "run" in s]
    assert run["env"]["RETRY_RUN_ID"] == "${{ inputs.run_id }}" and run["run"] == "python tools/ci/build_failures.py retry"


# ------------------------------------------------------------------------------------------------ issue forms (FEAT-266)

FORMS = [".github/ISSUE_TEMPLATE/resort-request.yml", ".github/ISSUE_TEMPLATE/pack-bug.yml"]
ELEMENT_KEYS = {"markdown": {"value"}, "input": {"label", "description", "placeholder", "value"},
                "textarea": {"label", "description", "placeholder", "value", "render"},
                "dropdown": {"label", "description", "multiple", "options", "default"},
                "checkboxes": {"label", "description", "options"}, "upload": {"label", "description"}}


@pytest.mark.parametrize("path", FORMS)
def test_issue_forms_follow_the_form_schema(path):
    form = load(path)
    assert {"name", "description", "body"} <= set(form) <= {"name", "description", "body", "title", "labels",
                                                           "assignees", "projects", "type"}
    ids = []
    for el in form["body"]:
        assert set(el["attributes"]) <= ELEMENT_KEYS[el["type"]], el
        if el["type"] == "markdown":
            assert "id" not in el and el["attributes"]["value"]
        else:
            assert el["attributes"]["label"] and re.fullmatch(r"[A-Za-z0-9_-]+", el["id"])
            ids.append(el["id"])
    assert len(ids) == len(set(ids))
    names = [load(p)["name"] for p in FORMS]
    assert len(names) == len(set(names))


def form_fields(path):
    return {el["id"]: el for el in load(path)["body"] if "id" in el}


def test_a_resort_request_asks_for_every_build_pack_input_in_its_shape():
    sys.path.insert(0, os.path.join(ROOT, "tools", "ci"))
    import build_pack_ci as ci
    fields = form_fields(FORMS[0])
    inputs = set(triggers(load(BUILD))["workflow_dispatch"]["inputs"])
    assert {"name", "osm_id", "slug"} <= set(fields) and {"name", "osm_id", "slug"} <= inputs
    assert fields["name"]["validations"]["required"] and fields["osm_id"]["validations"]["required"]
    assert ci.SLUG_RE.fullmatch(fields["slug"]["attributes"]["placeholder"])
    assert ci.OSM_RE.fullmatch(fields["osm_id"]["attributes"]["placeholder"])
    assert len(fields["name"]["attributes"]["placeholder"]) <= ci.MAX_NAME
    assert "type: resort-request" in load(FORMS[0])["labels"]


def test_a_pack_bug_asks_for_the_release_tag_and_points_gameplay_at_the_game():
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*/v[1-9][0-9]*", form_fields(FORMS[1])["version"]["attributes"]["placeholder"])
    links = load(".github/ISSUE_TEMPLATE/config.yml")["contact_links"]
    assert any(link["url"].startswith("https://github.com/drewkeriazes/SnowboardAnywhere/") for link in links)
