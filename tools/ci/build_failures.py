"""Build pack failures (FEAT-314): why a run failed, a retry when the cause is flaky, and a log of every attempt.

    python tools/ci/build_failures.py record     Build pack's last job (`outcome`, every attempt, pass or fail)
    python tools/ci/build_failures.py retry      build-pack-retry.yml: wait, then re-run the failed jobs
    python tools/ci/build_failures.py summary    the tables, from a metrics file (--file), to stdout

record reads this attempt's jobs and the failed job's log (`gh api`, GH_TOKEN with actions: read), sorts the failure
into a reason code (classify, below: transient or real), appends one row to `build-failures.jsonl` on the `metrics`
branch, rewrites that branch's README.md and `host-tuning.json` (the probe's timeouts, raised for a host that keeps
timing out), and writes the verdict and the tables to the run summary. A transient failure on attempt 1 or 2 starts
build-pack-retry.yml (a workflow_dispatch: the one event the workflow token may start), which waits until this run
has finished, 5 minutes after attempt 1 and 15 after attempt 2, and re-runs the failed jobs (`gh run rerun --failed`;
their dependents, this job among them, run again too). A real failure stops with its reason as an error annotation.

Rows: {time, run_id, pack, attempt, job, step, host, reason, transient, duration_s, outcome}; outcome is passed,
retrying, stopped (real) or gave up (transient, out of retries).
"""
import argparse, json, os, re, subprocess, sys, tempfile, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

MAX_ATTEMPTS = 3               # the first try and 2 retries
WAITS = {1: 5, 2: 15}          # minutes before re-running after attempt N
BRANCH = "metrics"
LOG = "build-failures.jsonl"
TUNING = "host-tuning.json"
# probe_hosts.py defaults and the most the tuning may raise them to: never unlimited
BASE = {"timeout": 60, "tries": 2}
CAP = {"timeout": 180, "tries": 4}

TAIL = 30                      # lines of the failed step's end that classify reads

# (reason, transient, pattern), first match wins; real causes that would also match a transient pattern come first
RULES = [
    ("out-of-disk", False, r"No space left on device|ENOSPC"),
    ("bad-input", False, r"\*\*Refused:\*\*|is not an OSM or Skimap\.org id"),
    ("job-timeout", False, r"has exceeded the maximum execution time"),
    ("overpass-busy", True, r"runtime error|rate_limited|too busy|at capacity|Dispatcher_Client"),
    ("queue-wait", True, r"gave up after \d+ min with \d+ build"),
    ("github-api", True, r"gh api failed|gh: .*\(HTTP 5\d\d\)|api\.github\.com.*5\d\d"),
    ("timeout", True, r"curl: \(28\)|timed out|TaskCanceled|operation was canceled|Timeout"),
    ("connect", True, r"curl: \((6|7|35|52|56)\)|Could not resolve host|Connection reset|Failed to connect"),
    ("rate-limit", True, r"HTTP 429"),
    ("http-5xx", True, r"HTTP 5\d\d|Bad Gateway|Service Unavailable|Gateway Time"),
    # a known-good ArcGIS host's one-off 400 (3DEP WESM, run 43380711559; it passed on a re-run)
    ("arcgis-400", True, r'"code":\s*400,\s*"message":\s*"Failed to execute query'),
    ("lfps-queue", True, r"LFPS jobs queue"),
    ("archive-slow", True, r"Internet Archive is slow"),
    ("fetch-incomplete", True, r"some downloads failed"),
    ("raw-incomplete", False, r"raw data incomplete"),
    ("build-error", False, r"build_pack\.py failed|gen_content\.py failed|pack_report\.py exited"),
    ("publish-refused", False, r"publish_pack|Publishing needs the GitHub App"),
    ("code-error", False, r"Traceback \(most recent call last\)"),
]


def host_of(line: str, step: str) -> str:
    if m := re.search(r"unreachable: ([\w.-]+)", line):
        return m.group(1)
    if "gh api" in line or "gh:" in line or step.startswith("wait") or step == "still my turn":
        return "api.github.com"
    for pat in (r"https?://([\w.-]+)", r"connect to ([\w.-]+\.[a-z]{2,})", r"-> ([\w.-]+\.[a-z]{2,})\s*$",
                r"host ([\w.-]+\.[a-z]{2,})"):
        if m := re.search(pat, line):
            return m.group(1)
    return ""


def classify(step: str, log: str, conclusion: str = "failure") -> dict:
    """{reason, transient, host} of a failed step from its job's log. Only the failed step's last TAIL lines before
    its `##[error]` count: earlier lines are often retries that later passed (aspen-hills' Overpass 502s before its
    real stop), and an unknown stop must stay unknown, never a stale 502. The last of those lines any rule matches
    decides; within a line, the first rule wins"""
    if conclusion == "cancelled":
        return {"reason": "cancelled", "transient": False, "host": ""}
    lines = [re.sub(r"^\S+Z ", "", l) for l in log.splitlines()]      # GitHub's timestamps
    ends = [i for i, l in enumerate(lines) if l.startswith("##[error]")]
    if ends:
        lines = lines[:ends[-1]]
    starts = [i for i, l in enumerate(lines) if l.startswith("##[group]Run ")]
    if starts:                 # the failed step's own output
        lines = lines[starts[-1]:]
    unreachable = next((l for l in reversed(lines) if l.startswith("unreachable: ")), "")
    if unreachable:            # probe_hosts.py: only its FAIL rows (an ok row can say "HTTP 500, LFPS JSON")
        lines = [l for l in lines if "FAIL" in l]
    else:
        lines = lines[-TAIL:]
    for line in reversed(lines):
        for reason, transient, pat in RULES:
            if re.search(pat, line):
                # the probe names the failed hosts on one line; else the deciding line's host
                return {"reason": reason, "transient": transient,
                        "host": host_of(unreachable, step) if unreachable else host_of(line, step)}
    return {"reason": "unknown", "transient": False, "host": host_of(unreachable, step)}


# ---------------------------------------------------------------- GitHub


def gh(*args, check=True) -> str:
    for k in range(3):
        p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if not p.returncode:
            return p.stdout
        if k < 2:
            time.sleep(10)
    if check:
        raise RuntimeError(f"gh {' '.join(args)}: {p.stderr.strip()}")
    return ""


def attempt_jobs(repo: str, run_id: str, attempt: int) -> list:
    return json.loads(gh("api", f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100"))["jobs"]


def job_log(repo: str, job_id) -> str:
    return gh("api", f"repos/{repo}/actions/jobs/{job_id}/logs", check=False)


def when(s):
    return time.mktime(time.strptime(s, "%Y-%m-%dT%H:%M:%SZ")) if s else None


def verdict(jobs: list, own: str, log_of) -> dict:
    """this attempt's row fields from its jobs (all but `own`, this one) and log_of(job) -> text"""
    jobs = [j for j in jobs if j["name"] != own]
    starts = [when(j.get("started_at")) for j in jobs if j.get("started_at")]
    ends = [when(j.get("completed_at")) for j in jobs if j.get("completed_at")]
    dur = round(max(ends) - min(starts)) if starts and ends else None
    bad = [j for j in jobs if j.get("conclusion") in ("failure", "cancelled", "timed_out")]
    if not bad:
        return {"job": "", "step": "", "host": "", "reason": "", "transient": False, "duration_s": dur, "ok": True}
    j = bad[0]
    step = next((s["name"] for s in j.get("steps", []) if s.get("conclusion") in ("failure", "cancelled")), "")
    c = classify(step, log_of(j)[-200_000:], "cancelled" if j["conclusion"] == "cancelled" else "failure")
    if j["conclusion"] == "timed_out":
        c = {"reason": "job-timeout", "transient": False, "host": ""}
    return {"job": j["name"], "step": step, **c, "duration_s": dur, "ok": False}


# ---------------------------------------------------------------- the metrics


def read_rows(path: str) -> list:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def retry_stats(rows: list) -> tuple:
    """(runs that retried, of them passed in the end)"""
    by = {}
    for r in rows:
        by.setdefault(r["run_id"], []).append(r)
    retried = [v for v in by.values() if any(r["outcome"] == "retrying" for r in v)]
    passed = [v for v in retried if max(v, key=lambda r: r["attempt"])["outcome"] == "passed"]
    return len(retried), len(passed)


def tuning(rows: list, last: int = 10) -> dict:
    """{host: {timeout, tries}}: a host whose probe timed out or failed to connect twice or more in its last `last`
    rows gets 1.5 times the timeout and one more try per two such failures, capped (CAP)"""
    out = {}
    for host in sorted({r["host"] for r in rows if r.get("host")}):
        mine = [r for r in rows if r.get("host") == host][-last:]
        n = sum(1 for r in mine if r["reason"] in ("timeout", "connect") and r.get("job") == "probe")
        if n >= 2:
            out[host] = {"timeout": min(CAP["timeout"], int(BASE["timeout"] * 1.5 ** (n - 1))),
                         "tries": min(CAP["tries"], BASE["tries"] + n // 2)}
    return out


def table(title: str, counts: Counter, head: str) -> str:
    if not counts:
        return ""
    rows = "\n".join(f"| {k or '(none)'} | {v} |" for k, v in counts.most_common(10))
    return f"**{title}**\n\n| {head} | failures |\n|---|---|\n{rows}\n\n"


def summary_md(rows: list, tune: dict) -> str:
    fails = [r for r in rows if r["outcome"] != "passed"]
    n, ok = retry_stats(rows)
    out = (f"{len(rows)} attempts logged, {len(fails)} failed. Retried runs: {n}, of them passed in the end: {ok}"
           + (f" ({100 * ok // n}%)" if n else "") + ".\n\n")
    out += table("By host", Counter(r["host"] for r in fails), "host")
    out += table("By reason", Counter(f"{r['reason']} ({'transient' if r['transient'] else 'real'})" for r in fails),
                 "reason")
    out += table("By step", Counter(f"{r['job']} / {r['step']}" for r in fails), "job / step")
    if tune:
        out += ("**Probe timeouts raised** (`host-tuning.json`, from the last 10 rows per host; most "
                f"{CAP['timeout']} s and {CAP['tries']} tries):\n\n| host | timeout | tries |\n|---|---|---|\n"
                + "\n".join(f"| {h} | {t['timeout']} s | {t['tries']} |" for h, t in tune.items()) + "\n\n")
    return out


def git(*args, cwd, check=True):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p


def save_row(row: dict, repo_dir: str = ROOT) -> tuple:
    """append `row` to the metrics branch and push; -> (all rows, tuning). Builds run one at a time, but a push can
    still race a re-run's: fetch, add, push, three times"""
    for k in range(3):
        d = tempfile.mkdtemp(prefix="metrics-")
        if git("fetch", "origin", BRANCH, cwd=repo_dir, check=False).returncode == 0:
            git("worktree", "add", "--detach", d, "FETCH_HEAD", cwd=repo_dir)
        else:                                    # the first row ever: an orphan branch
            git("worktree", "add", "--detach", d, cwd=repo_dir)
            git("checkout", "--orphan", "metrics-new", cwd=d)
            git("rm", "-rfq", ".", cwd=d)
        path = os.path.join(d, LOG)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        rows = read_rows(path)
        tune = tuning(rows)
        with open(os.path.join(d, TUNING), "w", encoding="utf-8") as f:
            json.dump(tune, f, indent=2)
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
            f.write("# Build pack failures (FEAT-314)\n\nWritten by `tools/ci/build_failures.py record` on every Build "
                    f"pack attempt; the rows are in `{LOG}`.\n\n" + summary_md(rows, tune))
        git("add", LOG, TUNING, "README.md", cwd=d)
        git("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-qm", f"metrics: {row['pack']} run {row['run_id']} attempt {row['attempt']}: {row['outcome']}",
            cwd=d)
        pushed = git("push", "origin", f"HEAD:refs/heads/{BRANCH}", cwd=d, check=False).returncode == 0
        git("worktree", "remove", "--force", d, cwd=repo_dir, check=False)
        if pushed:
            return rows, tune
        time.sleep(5 * (k + 1))
    raise RuntimeError("could not push the metrics branch")


# ---------------------------------------------------------------- commands


def write_summary(text: str):
    print(text, flush=True)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def pack_name() -> str:
    sys.path.insert(0, HERE)
    import build_pack_ci
    try:
        return build_pack_ci.from_env()["slug"]
    except build_pack_ci.Refused:
        return "(refused input)"


def record(save=save_row, jobs=None, log_of=None, dispatch=None) -> int:
    repo, run_id = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_RUN_ID"]
    attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    own = os.environ.get("OWN_JOB", "outcome")
    jobs = jobs if jobs is not None else attempt_jobs(repo, run_id, attempt)
    v = verdict(jobs, own, log_of or (lambda j: job_log(repo, j["id"])))
    if v.pop("ok"):
        outcome = "passed"
    elif v["transient"]:
        outcome = "retrying" if attempt < MAX_ATTEMPTS else "gave up"
    else:
        outcome = "stopped"
    row = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "run_id": int(run_id), "pack": pack_name(),
           "attempt": attempt, **v, "outcome": outcome}
    head = {"passed": f"passed on attempt {attempt}",
            "retrying": f"**{v['reason']}** (transient) at {v['job']} / {v['step']}"
                        + (f", host `{v['host']}`" if v["host"] else "")
                        + f": re-running the failed jobs in {WAITS.get(attempt)} min (attempt {attempt + 1} of {MAX_ATTEMPTS})",
            "gave up": f"**{v['reason']}** (transient) at {v['job']} / {v['step']}"
                       + (f", host `{v['host']}`" if v["host"] else "") + f": still failing after {attempt} attempts; "
                       "no more retries",
            "stopped": f"**{v['reason']}** at {v['job']} / {v['step']}: a real failure, not retried. Fix the cause "
                       "and run it again"}[outcome]
    write_summary(f"### Outcome (FEAT-314)\n\n{head}.\n")
    try:
        rows, tune = save(row)
        write_summary("### Build failures so far\n\n" + summary_md(rows, tune))
    except Exception as e:      # the metrics are a record, never the reason a retry does not happen
        print(f"::warning::metrics not saved: {e}")
    if outcome == "retrying":
        (dispatch or (lambda: gh("workflow", "run", "build-pack-retry.yml", "-f", f"run_id={run_id}",
                                 "-f", f"attempt={attempt}")))()
    elif outcome in ("stopped", "gave up"):
        print(f"::error::Build pack {outcome}: {v['reason']} at {v['job']} / {v['step']}"
              + (f" ({v['host']})" if v["host"] else ""))
    return 0


def retry(run_id: str, attempt: int, sleep=time.sleep, view=None, rerun=None) -> int:
    """wait for run `run_id` to finish its attempt `attempt`, then WAITS[attempt] minutes, then re-run its failed jobs,
    unless someone re-ran it by hand meanwhile"""
    repo = os.environ["GITHUB_REPOSITORY"]
    view = view or (lambda: json.loads(gh("api", f"repos/{repo}/actions/runs/{run_id}")))
    rerun = rerun or (lambda: gh("run", "rerun", run_id, "--failed", "--repo", repo))
    if not str(view().get("path", "")).endswith("build-pack.yml"):
        print(f"run {run_id} is not a Build pack run: not re-run")
        return 2
    for _ in range(40):                          # the outcome job ends a few seconds after it starts this one
        r = view()
        if r["status"] == "completed":
            break
        sleep(30)
    else:
        print(f"run {run_id} still {r['status']} after 20 min: not re-run")
        return 1
    print(f"run {run_id} attempt {attempt} finished ({r['conclusion']}); waiting {WAITS[attempt]} min", flush=True)
    sleep(WAITS[attempt] * 60)
    r = view()
    if r.get("run_attempt") != attempt or r["status"] != "completed" or r["conclusion"] == "success":
        print(f"run {run_id} is now attempt {r.get('run_attempt')} ({r['status']}, {r.get('conclusion')}): "
              "someone re-ran it already, nothing to do")
        return 0
    rerun()
    print(f"re-ran the failed jobs of run {run_id} (attempt {attempt + 1})")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("record")
    r = sub.add_parser("retry")
    r.add_argument("--run-id", default=os.environ.get("RETRY_RUN_ID"))
    r.add_argument("--attempt", default=os.environ.get("RETRY_ATTEMPT", ""))
    s = sub.add_parser("summary")
    s.add_argument("--file", default=LOG)
    a = ap.parse_args(argv)
    if a.cmd == "record":
        return record()
    if a.cmd == "retry":
        if not (a.run_id or "").isdigit() or not str(a.attempt).isdigit() or int(a.attempt) not in WAITS:
            print(f"run id must be digits and attempt one of {sorted(WAITS)}")
            return 2
        return retry(a.run_id, int(a.attempt))
    rows = read_rows(a.file)
    print(summary_md(rows, tuning(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
