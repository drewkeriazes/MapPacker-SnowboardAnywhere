"""Wait for this run's turn among the build-pack runs (FEAT-245): one build at a time, the rest queue in order.

    python tools/ci/wait_turn.py [--workflow build-pack.yml] [--poll 60] [--max-wait 330]

GitHub's `concurrency` keeps only one pending run per group and cancels an older pending one when a newer one
arrives, so it cannot hold a queue of more than one. Instead every run starts at once and this waits while any
run of the same workflow that started earlier (its current attempt's `run_started_at`, then the id) has not
completed. The oldest run never waits, so the queue always moves. The workflow runs it again at the start of the
build job, so "Re-run failed jobs", which skips a queue job that passed, still waits its turn. Reads the runs with `gh api` (GH_TOKEN; actions: read), for GITHUB_REPOSITORY and
GITHUB_RUN_ID. Gives up after --max-wait minutes with exit 1 (a job may run 6 hours at most).
"""
import argparse, json, os, subprocess, sys, time
from typing import Callable

ACTIVE = ("queued", "in_progress", "waiting", "requested", "pending")


def order(r: dict, own: dict | None = None) -> tuple:
    """a run's place in the queue: when its current attempt started (`run_started_at`, which a re-run resets, so
    a re-run of an old run queues behind the builds in flight), then its id; the id alone when either run has no
    start time"""
    if own is not None and not (r.get("run_started_at") and own.get("run_started_at")):
        return ("", int(r["id"]))
    return (r.get("run_started_at") or "", int(r["id"]))


def blocking(runs: list, own_id: int) -> list:
    """the runs ahead of `own_id`: not completed and started before it, oldest first"""
    own = next((r for r in runs if int(r["id"]) == own_id), {"id": own_id})
    key = lambda r: order(r, own)   # noqa: E731
    ahead = [r for r in runs if int(r["id"]) != own_id and r.get("status") in ACTIVE and key(r) < key(own)]
    return sorted(ahead, key=key)


def gh_runs(repo: str, workflow: str) -> list:
    """this workflow's runs in every not-completed status"""
    out = []
    for st in ACTIVE:
        for k in range(3):     # FEAT-314: GitHub's API answers 502 at times (bigsky, run 43573684184)
            p = subprocess.run(["gh", "api", "--paginate",
                                f"repos/{repo}/actions/workflows/{workflow}/runs?status={st}&per_page=100",
                                "--jq", ".workflow_runs[] | {id, status, run_number, html_url, run_started_at}"],
                               capture_output=True, text=True)
            if not p.returncode or k == 2:
                break
            print(f"gh api failed, trying again in 15 s: {p.stderr.strip()}", flush=True)
            time.sleep(15)
        if p.returncode:
            raise RuntimeError(f"gh api failed: {p.stderr.strip()}")
        out += [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
    return out


def describe(r: dict) -> str:
    return f"#{r.get('run_number', '?')} ({r['status']}) {r.get('html_url', r['id'])}"


def main(argv=None, list_runs: Callable | None = None, sleep: Callable = time.sleep,
         clock: Callable = time.monotonic) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workflow", default="build-pack.yml", help="workflow file name (default build-pack.yml)")
    ap.add_argument("--poll", type=int, default=60, help="seconds between looks (default 60)")
    ap.add_argument("--max-wait", type=float, default=330, help="minutes to wait before giving up (default 330)")
    a = ap.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY")
    own = os.environ.get("GITHUB_RUN_ID")
    if not repo or not own:
        print("GITHUB_REPOSITORY and GITHUB_RUN_ID must be set (this runs inside a workflow)")
        return 2
    own_id = int(own)
    list_runs = list_runs or (lambda: gh_runs(repo, a.workflow))
    t0 = clock()
    last = None
    while True:
        ahead = blocking(list_runs(), own_id)
        if not ahead:
            waited = clock() - t0
            print("my turn" + (f" after {waited / 60:.0f} min" if waited >= 60 else ""), flush=True)
            return 0
        ids = [r["id"] for r in ahead]
        if ids != last:
            print(f"waiting for {len(ahead)} earlier build(s): " + ", ".join(describe(r) for r in ahead), flush=True)
            last = ids
        if clock() - t0 > a.max_wait * 60:
            print(f"gave up after {a.max_wait:.0f} min with {len(ahead)} build(s) still ahead; run it again later")
            return 1
        sleep(a.poll)


if __name__ == "__main__":
    sys.exit(main())
