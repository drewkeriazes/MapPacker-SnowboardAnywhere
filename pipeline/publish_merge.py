"""FEAT-272: decide whether a publish PR releases its draft and merges itself (design section 3 and 4).

    python pipeline/publish_merge.py ready <pr>     refresh onto main, release the draft then merge, wait, or refuse
    python pipeline/publish_merge.py pure <pr>      print true when it is a publish PR changing only the publish file set
    python pipeline/publish_merge.py closed <pr>    merged: publish a draft still unpublished; unmerged: delete it

`ready` merges only a `publish/<slug>-v<N>` PR from this repo (not a fork) into main, labelled `publish` and
`automerge`, whose latest `automerge` label came from a maintainer (.github/maintainers.txt, main's copy) or from
the App (PUBLISH_APP_LOGIN) on a PR whose `Run:` line names a run a maintainer started; with no push to the branch
after that label (GitHub's activity log) except the App's own refresh; changing only the publish file set and in
catalog.json only <slug> v<N>, at this repo's release url; with every check run on the head success or skipped and
`publish-check` success. Then it re-checks the release, publishes it if it is still a draft (a rollback's release
is already out), and squash-merges pinned to the head it checked (a branch that moved stops it, no retry). Any gh
failure or missing data waits or refuses, never merges. A refusal comments on the PR once per reason (counting
only the tool's own comments). Env: GITHUB_REPOSITORY, PUBLISH_APP_LOGIN, GITHUB_RUN_ID (this run's jobs don't count as
checks); gh signed in with the App token, run from a full-history checkout of main.
Trust assumption: GitHub's server-side push record is accurate and only this workflow holds the App's token, so a
push by the App after the label is the refresh."""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, time
from datetime import datetime
from typing import Callable
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from publish_check import changed_entries  # noqa: E402
from publish_pack import REPO, RESORTS_REPO, all_entries, asset_url, maintainers, run, update_catalog  # noqa: E402

SLUG = r"[a-z0-9][a-z0-9-]*"
BRANCH = re.compile(rf"^publish/({SLUG})-v([1-9][0-9]*)$")
RUN_LINE = re.compile(r"^Run: https://github\.com/([^/\s]+/[^/\s]+)/actions/runs/(\d+)\s*$", re.M)
GOOD = ("success", "skipped")
REQUIRED = "publish-check"            # the check that downloads the draft zip and lints it: must be success
SELF_JOBS = {"publish-merge"}         # this workflow's job name: its own check run never counts
PREFIX = "[publish-merge]"
UNTRUSTED = "refuse: the automerge label is not trusted"
sleep = time.sleep


# --- pure ----------------------------------------------------------------------------------------------------------

def publish_file_patterns(slug: str) -> list[str]:
    return ["catalog.json", "RELEASES.md", f"reports/{slug}.md", f"resorts/{slug}/**", f"manifests/{slug}.json"]


def parse_branch(ref: str) -> tuple[str, int] | None:
    m = BRANCH.match(ref or "")
    return (m.group(1), int(m.group(2))) if m else None


def files_ok(files: list[str], slug: str) -> bool:
    """every path is in the publish file set; an empty list, or a path with `..`, `\\` or an empty part, is not"""
    pats = publish_file_patterns(slug)
    exact, dirs = {p for p in pats if not p.endswith("/**")}, [p[:-2] for p in pats if p.endswith("/**")]

    def ok(f):
        if "\\" in f or any(part in ("", ".", "..") for part in f.split("/")):
            return False
        return f in exact or any(f.startswith(d) for d in dirs)
    return bool(files) and bool(re.fullmatch(SLUG, slug)) and all(ok(f) for f in files)


def last_label(events: list[dict], label: str) -> dict | None:
    evs = [e for e in events if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == label]
    return sorted(evs, key=lambda e: e.get("created_at") or "")[-1] if evs else None


def _is(login, logins) -> bool:
    return bool(login) and login.lower() in {m.lower() for m in logins}


def label_ok(events: list[dict], label: str, maintainers: set[str], app_login: str, body: str,
             run_actor: Callable[[int], str | None], repo: str | None = None) -> bool:
    """the latest `labeled` event for `label` was by a maintainer, or by `app_login` on a PR whose body has exactly
    one `Run:` line (in `repo`, when given) whose run `run_actor` says a maintainer started"""
    ev = last_label(events, label)
    if not ev or not ev.get("created_at"):
        return False
    who = (ev.get("actor") or {}).get("login")
    if _is(who, maintainers):
        return True
    runs = set(RUN_LINE.findall(body or ""))
    if not app_login or who != app_login or len(runs) != 1:
        return False
    run_repo, run_id = runs.pop()
    if repo and run_repo.lower() != repo.lower():
        return False
    try:
        return _is(run_actor(int(run_id)), maintainers)
    except (Exception, SystemExit):
        return False


def _time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def activity_complete(activity: list[dict], label_time: str, head_sha: str) -> bool:
    """the branch's activity log covers the label: some entry is at or before it, and the newest one left the branch
    at `head_sha` (else the log is stale or cut short)"""
    try:
        acts = sorted(activity, key=lambda a: _time(a["timestamp"]))
        return bool(acts) and _time(acts[0]["timestamp"]) <= _time(label_time) and acts[-1].get("after") == head_sha
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def pushes_after_label_ok(activity: list[dict], label_time: str, app_login: str) -> bool:
    """no entry in the branch's activity log (push, force_push, branch_deletion, ...) at or after `label_time` by
    anyone but `app_login`; a branch_creation at the label's second is before it (a PR needs its branch first)"""
    try:
        t = _time(label_time)
        for a in activity:
            ts, who = _time(a["timestamp"]), (a.get("actor") or {}).get("login")
            if app_login and who == app_login:
                continue
            if ts > t or (ts == t and a.get("activity_type") != "branch_creation"):
                return False
        return True
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def rebase_catalog(base: dict, pr: dict, main: dict) -> dict:
    """main's catalog plus the entries the PR changed against base (test packs stay in the test list)"""
    out = main
    for e in changed_entries(base, pr):
        out = update_catalog(out, e, test=any(e is t for t in pr.get("test", [])))
    return out


def catalog_problem(base: dict, head: dict, slug: str, version: int, repo: str) -> str | None:
    """None when head only adds or changes <slug> v<version> against base, at this repo's release url"""
    gone = {e.get("slug") for e in all_entries(base)} - {e.get("slug") for e in all_entries(head)}
    if gone:
        return f"the catalog drops {', '.join(sorted(gone))}"
    changed = changed_entries(base, head)
    if not changed:
        return f"no change to {slug} in the catalog"
    other = [f"{e.get('slug')} v{(e.get('pack') or {}).get('version')}" for e in changed
             if e.get("slug") != slug or (e.get("pack") or {}).get("version") != version]
    if other:
        return f"the catalog changes {', '.join(other)}, not only {slug} v{version}"
    want = asset_url(slug, version, repo).lower()
    if any(str(e["pack"].get("url", "")).lower() != want for e in changed):
        return f"the {slug} entry's url is not {want}"
    return None


def decide(*, labels: list[str], files: list[str], branch: str, checks: list[dict], automerge_ok: bool,
           behind_main: bool) -> str:
    """"merge", "refresh", "wait" or "refuse: <why>"; checks are {"name", "conclusion"}"""
    parsed = parse_branch(branch)
    if not parsed:
        return f"refuse: {branch} is not a publish/<slug>-v<N> branch"
    if "publish" not in labels:
        return "refuse: no publish label"
    if not files_ok(files, parsed[0]):
        return f"refuse: it changes files outside the publish set ({', '.join(publish_file_patterns(parsed[0]))})"
    if "automerge" not in labels:
        return "wait"
    if not automerge_ok:
        return UNTRUSTED
    if behind_main:
        return "refresh"
    if not any(c.get("name") == REQUIRED and c.get("conclusion") == "success" for c in checks):
        return "wait"
    return "wait" if any(c.get("conclusion") not in GOOD for c in checks) else "merge"


# --- gh ------------------------------------------------------------------------------------------------------------

def gh(*args: str) -> str:
    return run(["gh", *args], cwd=REPO)


def api(path: str):
    return json.loads(gh("api", path))


def api_pages(path: str, key: str | None = None) -> list:
    """every page of a paginated list (gh prints the pages one after another)"""
    text, dec, out = gh("api", path, "--paginate").strip(), json.JSONDecoder(), []
    while text:
        page, end = dec.raw_decode(text)
        out += page[key] if key else page
        text = text[end:].lstrip()
    return out


def catalog_at(repo: str, ref: str) -> dict:
    return json.loads(gh("api", f"repos/{repo}/contents/catalog.json?ref={ref}",
                         "-H", "Accept: application/vnd.github.raw+json"))


def release_draft(tag: str) -> bool | None:
    """True for a draft, False for a published release, None when it can't be read"""
    try:
        return gh("release", "view", tag, "--json", "isDraft", "--jq", ".isDraft") == "true"
    except SystemExit:
        return None


def whoami(app_login: str) -> str | None:
    """the login comments are posted as: the App's in the workflow, else gh's signed-in user (None if unknown)"""
    if app_login:
        return app_login
    try:
        return gh("api", "user", "--jq", ".login") or None
    except SystemExit:
        return None


def say(n: int, repo: str, text: str, me: str | None) -> None:
    """comment `[publish-merge] text` on the PR, unless it is already the last such comment by `me` (anyone can
    post the prefix; with `me` unknown it always comments)"""
    body = f"{PREFIX} {text}"
    try:
        mine = [c.get("body") for c in api_pages(f"repos/{repo}/issues/{n}/comments") if me and
                (c.get("user") or {}).get("login") == me and str(c.get("body", "")).startswith(PREFIX)]
        if mine and mine[-1] == body:
            return print(f"already said: {body}")
        gh("pr", "comment", str(n), "--body", body)
    except SystemExit as e:
        print(f"warning: could not comment: {e}")


def checks_on(repo: str, sha: str) -> list[dict]:
    runs = api_pages(f"repos/{repo}/commits/{sha}/check-runs", key="check_runs")
    me = os.environ.get("GITHUB_RUN_ID")
    mine = lambda c: c.get("name") in SELF_JOBS or (me and f"/actions/runs/{me}/" in str(c.get("details_url")))
    return [{"name": c.get("name"), "conclusion": c.get("conclusion") if c.get("status") == "completed" else None}
            for c in runs if not mine(c)]


def assess(n: int, repo: str, pr: dict, app_login: str) -> tuple[str, dict]:
    """(decision, facts) for an open PR; raises (gh failure, odd data) when something can't be read"""
    labels = [lb["name"] for lb in pr.get("labels", [])]
    branch, sha = pr["head"]["ref"], pr["head"]["sha"]
    if (pr["head"].get("repo") or {}).get("full_name", "").lower() != repo.lower():
        return "refuse: the branch is in a fork, not this repo", {}
    if pr["base"]["ref"] != "main":
        return f"refuse: it targets {pr['base']['ref']}, not main", {}
    listed = api_pages(f"repos/{repo}/pulls/{n}/files")
    if len(listed) != pr.get("changed_files"):
        return f"refuse: listed {len(listed)} of its {pr.get('changed_files')} files", {}
    files = [f["filename"] for f in listed] + [f["previous_filename"] for f in listed if f.get("previous_filename")]
    trusted = False
    if "automerge" in labels:
        events = api_pages(f"repos/{repo}/issues/{n}/timeline")
        ref = f"refs/heads/{branch}"
        activity = [a for a in api_pages(f"repos/{repo}/activity?ref={quote(ref)}&per_page=100")
                    if a.get("ref") in (ref, branch)]
        ev, maint = last_label(events, "automerge"), maintainers()
        run_actor = lambda i: gh("api", f"repos/{repo}/actions/runs/{i}", "--jq", ".triggering_actor.login")
        if not ev or not label_ok(events, "automerge", maint, app_login, pr.get("body") or "", run_actor, repo):
            who = ((ev or {}).get("actor") or {}).get("login")
            return f"{UNTRUSTED}: added by {who}, not a maintainer (nor by the App on a maintainer's run)", {}
        if not activity_complete(activity, ev["created_at"], sha):
            print(f"the activity log of {branch} does not reach {sha[:7]} or back to the label yet")
            return "wait", {}
        if not pushes_after_label_ok(activity, ev["created_at"], app_login):
            return f"{UNTRUSTED}: someone other than the App pushed to {branch} after it", {}
        trusted = True
    cmp = json.loads(gh("api", f"repos/{repo}/compare/main...{sha}", "--jq",
                        "{behind_by: .behind_by, base: .merge_base_commit.sha}"))
    decision = decide(labels=labels, files=files, branch=branch, checks=checks_on(repo, sha), automerge_ok=trusted,
                      behind_main=cmp["behind_by"] > 0)
    parsed = parse_branch(branch)
    if not decision.startswith("refuse"):
        problem = catalog_problem(catalog_at(repo, cmp["base"]), catalog_at(repo, sha), *parsed, repo)
        decision = f"refuse: {problem}" if problem else decision
    return decision, {"slug": parsed and parsed[0], "version": parsed and parsed[1], "sha": sha, "branch": branch}


def refresh_branch(branch: str, sha: str, name: str, email: str, src: str = REPO) -> str:
    """merge origin/main into `branch` at `sha` with catalog.json rebuilt by rebase_catalog, committed as
    `name <email>`, pushed to that branch (only a publish/ one); stops when the branch is no longer at `sha` and
    raises, pushing nothing, when the merge did not start (no MERGE_HEAD) or conflicts in any other file"""
    if not parse_branch(branch):
        raise SystemExit(f"refusing to push {branch}: not a publish branch")
    run(["git", "fetch", "origin", "main", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"], cwd=src)
    if run(["git", "rev-parse", f"origin/{branch}"], cwd=src) != sha:
        return f"{branch} moved since it was checked: the next run looks again"
    tmp = tempfile.mkdtemp(prefix="publish-refresh-")
    wt, who = os.path.join(tmp, "wt"), ["-c", f"user.name={name}", "-c", f"user.email={email}"]
    try:
        run(["git", "worktree", "add", "--detach", wt, sha], cwd=src)
        base = run(["git", "merge-base", "origin/main", sha], cwd=wt)
        base_c, pr_c, main_c = (json.loads(run(["git", "show", f"{ref}:catalog.json"], cwd=wt))
                                for ref in (base, sha, "origin/main"))
        try:
            run(["git", *who, "merge", "--no-commit", "--no-ff", "origin/main"], cwd=wt)
        except SystemExit as e:       # a conflict (catalog.json is rewritten below) still leaves MERGE_HEAD
            merge_error = e
        else:
            merge_error = None
        try:
            run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=wt)
        except SystemExit:
            raise SystemExit(f"git merge of main did not start, nothing pushed: {merge_error}")
        with open(os.path.join(wt, "catalog.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(rebase_catalog(base_c, pr_c, main_c), f, indent=1)
            f.write("\n")
        run(["git", "add", "catalog.json"], cwd=wt)
        if left := run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wt):
            raise SystemExit(f"conflicts with main outside catalog.json: {left.split()}")
        run(["git", *who, "commit", "-q", "-m", f"{branch[8:]}: catalog refreshed onto main (FEAT-272)"], cwd=wt)
        run(["git", "push", "origin", f"HEAD:refs/heads/{branch}"], cwd=wt)
        return f"refreshed {branch} onto main: checks run again"
    finally:
        if os.path.isdir(wt):
            subprocess.run(["git", "worktree", "remove", "--force", wt], cwd=src, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def refresh(repo: str, branch: str, sha: str, app_login: str) -> str:
    uid = api(f"users/{quote(app_login)}")["id"]
    return refresh_branch(branch, sha, app_login, f"{uid}+{app_login}@users.noreply.github.com")


def head_moved(n: int, repo: str, sha: str, err: SystemExit) -> bool:
    """the merge failed because the branch is no longer at `sha` (--match-head-commit)"""
    if "head branch was modified" in str(err).lower():
        return True
    try:
        return api(f"repos/{repo}/pulls/{n}")["head"]["sha"] != sha
    except (Exception, SystemExit):
        return False


def release_then_merge(n: int, repo: str, tag: str, sha: str, me: str | None) -> int:
    draft = release_draft(tag)        # re-read right before publishing
    if draft is None:
        say(n, repo, f"Not merging: can't read release {tag}", me)
        return 0
    try:
        if draft:
            gh("release", "edit", tag, "--draft=false")
    except SystemExit as e:           # no merge without a live release
        say(n, repo, f"Not merging: publishing release {tag} failed: {e}", me)
        return 1
    for attempt in range(4):
        try:
            gh("pr", "merge", str(n), "--squash", "--match-head-commit", sha)
            return 0
        except SystemExit as e:
            err = e
            if head_moved(n, repo, sha, e):
                say(n, repo, "Not merged: the branch moved after the check; the next run looks again", me)
                return 0
            if attempt < 3:
                sleep(20)
    say(n, repo, f"Release {tag} is published but the merge failed 4 times: {err}", me)
    return 1


SWEEP = 20     # how many recently closed PRs `ready` looks through for a merged publish PR with its draft unpublished


def sweep(repo: str, skip: int | None = None) -> None:
    """a `closed` run can be dropped when runs queue up (one pending run per concurrency group), so each `ready` run
    first does what `closed` would for the last SWEEP merged publish/ PRs: a draft still unpublished whose tag main's
    catalog names is published (closed() keeps its fail-closed rules). Never raises: a failure here must not stop `ready`."""
    try:
        listed = api_pages(f"repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page={SWEEP}")[:SWEEP]
    except (Exception, SystemExit) as e:
        return print(f"sweep: could not list closed PRs: {e}") or None
    for p in listed:
        if p.get("number") == skip or not p.get("merged_at") or not parse_branch((p.get("head") or {}).get("ref", "")):
            continue
        try:
            closed(p["number"], repo)
        except (Exception, SystemExit) as e:
            print(f"sweep: #{p.get('number')}: {e}")


def ready(n: int, repo: str, app_login: str) -> int:
    pr = api(f"repos/{repo}/pulls/{n}")
    labels = [lb["name"] for lb in pr.get("labels", [])]
    if not parse_branch(pr["head"]["ref"]) and "publish" not in labels:
        return print(f"#{n} is not a publish PR") or 0
    if pr.get("state") != "open":
        return print(f"#{n} is {pr.get('state')}") or 0
    sweep(repo, skip=n)
    try:
        decision, facts = assess(n, repo, pr, app_login)
    except (Exception, SystemExit) as e:
        return print(f"wait: could not read #{n}: {e}") or 1
    print(f"#{n}: {decision}")
    me = whoami(app_login) if decision.startswith("refuse") or decision in ("refresh", "merge") else None
    if decision.startswith("refuse"):
        say(n, repo, f"Not merging: {decision.split(': ', 1)[1]}", me)
    elif decision == "refresh":
        if not app_login:
            return say(n, repo, "Not merging: behind main, and PUBLISH_APP_LOGIN is not set to refresh it", me) or 0
        try:
            print(refresh(repo, facts["branch"], facts["sha"], app_login))
        except SystemExit as e:
            say(n, repo, f"Not merging: the refresh onto main failed: {e}", me)
            return 1
    elif decision == "merge":
        return release_then_merge(n, repo, f"{facts['slug']}-v{facts['version']}", facts["sha"], me)
    return 0


def closed(n: int, repo: str) -> int:
    pr = api(f"repos/{repo}/pulls/{n}")
    parsed = parse_branch(pr["head"]["ref"])
    if not parsed or (pr["head"].get("repo") or {}).get("full_name", "").lower() != repo.lower() \
            or pr["base"]["ref"] != "main":
        return print(f"#{n} is not a publish PR of this repo") or 0
    tag = f"{parsed[0]}-v{parsed[1]}"
    draft = release_draft(tag)
    if not draft:
        return print(f"{tag}: {'no draft release' if draft is False else 'release not readable'}") or 0
    try:
        if pr.get("merged"):
            cat = catalog_at(repo, pr["merge_commit_sha"])
            if not any(e.get("slug") == parsed[0] and (e.get("pack") or {}).get("version") == parsed[1]
                       for e in all_entries(cat)):
                return print(f"main's catalog does not name {tag}: leaving the draft") or 1
            gh("release", "edit", tag, "--draft=false")
        else:
            owner = repo.split("/")[0]
            if api_pages(f"repos/{repo}/pulls?state=open&head={owner}:{pr['head']['ref']}"):
                return print(f"another open PR uses {pr['head']['ref']}: keeping {tag}") or 0
            gh("release", "delete", tag, "--yes")
    except SystemExit as e:
        return print(f"{tag}: {e}") or 1
    return 0


def pure(n: int, repo: str) -> bool:
    """a `publish`-labelled publish/<slug>-v<N> PR whose every changed path (renames count both names) is in the
    publish file set: the Claude reviewer has nothing to review there. Anything unreadable or odd is False."""
    try:
        pr = api(f"repos/{repo}/pulls/{n}")
        parsed = parse_branch(pr["head"]["ref"])
        if not parsed or "publish" not in [lb["name"] for lb in pr.get("labels", [])]:
            return False
        if (pr["head"].get("repo") or {}).get("full_name", "").lower() != repo.lower() or pr["base"]["ref"] != "main":
            return False
        listed = api_pages(f"repos/{repo}/pulls/{n}/files")
        if len(listed) != pr.get("changed_files"):
            return False
        files = [f["filename"] for f in listed] + [f["previous_filename"] for f in listed if f.get("previous_filename")]
        return files_ok(files, parsed[0])
    except (SystemExit, KeyError, TypeError, ValueError):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=["ready", "closed", "pure"])
    ap.add_argument("pr", type=int)
    a = ap.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY") or RESORTS_REPO
    if a.action == "pure":
        print("true" if pure(a.pr, repo) else "false")
        return 0
    if a.action == "closed":
        return closed(a.pr, repo)
    return ready(a.pr, repo, os.environ.get("PUBLISH_APP_LOGIN", ""))


if __name__ == "__main__":
    sys.exit(main())
