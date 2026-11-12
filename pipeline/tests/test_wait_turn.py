"""tools/ci/wait_turn.py (FEAT-245): build-pack runs queue in run-id order."""
import os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "ci"))
import wait_turn  # noqa: E402


def run(i, status="in_progress"):
    return {"id": i, "status": status, "run_number": i % 100, "html_url": f"https://x/runs/{i}"}


def test_blocking_is_the_earlier_runs_not_yet_completed_oldest_first():
    runs = [run(30), run(10, "queued"), run(50), run(20, "completed"), run(40, "waiting")]
    assert [r["id"] for r in wait_turn.blocking(runs, 40)] == [10, 30]


def test_the_oldest_run_is_never_blocked():
    assert wait_turn.blocking([run(10), run(11, "queued")], 10) == []


def env(monkeypatch, own=40):
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_RUN_ID", str(own))


def test_waits_until_the_earlier_run_completes(monkeypatch, capsys):
    env(monkeypatch)
    views = iter([[run(30), run(40)], [run(30), run(40)], [run(30, "completed"), run(40)]])
    slept = []
    code = wait_turn.main(["--poll", "5"], list_runs=lambda: next(views), sleep=slept.append, clock=lambda: 0)
    assert code == 0
    assert slept == [5, 5]
    out = capsys.readouterr().out
    assert out.count("waiting for 1 earlier build") == 1   # printed once while the queue stays the same
    assert "my turn" in out


def test_gives_up_after_max_wait(monkeypatch, capsys):
    env(monkeypatch)
    t = iter(range(0, 10_000, 60))
    code = wait_turn.main(["--poll", "60", "--max-wait", "2"], list_runs=lambda: [run(30)], sleep=lambda s: None,
                          clock=lambda: next(t))
    assert code == 1
    assert "gave up" in capsys.readouterr().out


def test_needs_the_workflow_env(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    assert wait_turn.main([], list_runs=lambda: []) == 2


def test_a_rerun_of_an_old_run_queues_behind_the_builds_in_flight():
    runs = [{"id": 10, "status": "in_progress", "run_started_at": "2026-11-12T12:00:00Z"},   # re-run just now
            {"id": 20, "status": "in_progress", "run_started_at": "2026-11-12T10:00:00Z"},
            {"id": 30, "status": "queued", "run_started_at": "2026-11-12T11:00:00Z"}]
    assert [r["id"] for r in wait_turn.blocking(runs, 10)] == [20, 30]
    assert wait_turn.blocking(runs, 20) == []
    assert [r["id"] for r in wait_turn.blocking(runs, 30)] == [20]
