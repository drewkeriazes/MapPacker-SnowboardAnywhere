"""pipeline/retry.py (FEAT-314): the inline retry rules the probe and the fetch share."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import retry  # noqa: E402


def test_only_no_answer_408_429_5xx_and_listed_one_offs_are_transient():
    for code in (0, 200, 408, 429, 500, 502, 503, 504):
        assert retry.transient(code, "x.org"), code
    for code in (400, 401, 403, 404, 410):
        assert not retry.transient(code, "x.org"), code
    assert retry.transient(400, "elevation.nationalmap.gov") and not retry.transient(404, "elevation.nationalmap.gov")


def test_waits_grow_respect_retry_after_and_are_capped():
    mid = lambda: 0.5                     # no jitter
    assert [retry.wait("probe", k, rand=mid) for k in (1, 2, 3)] == [10, 30, 30]
    assert retry.wait("probe", 1, retry_after=60, rand=mid) == 60
    assert retry.wait("probe", 1, retry_after=9999, rand=mid) == retry.RULES["max_retry_after_s"]
    assert 8 <= retry.wait("probe", 1, rand=lambda: 0.0) < 10 < retry.wait("probe", 1, rand=lambda: 1.0) <= 12
    assert retry.worst_wait("fetch") == sum(retry.RULES["fetch"]["waits_s"]) * 1.2
    assert "probe 3 tries per host" in retry.caps_md()


def test_the_tally_logs_one_line_per_host(tmp_path, monkeypatch):
    t = retry.Tally()
    t.add("a.org", 1, True)
    t.add("a.org", 2, True)
    t.add("a.org", 3, False)
    t.add("b.org", 1, True)
    log = tmp_path / "x.jsonl"
    t.save("probe", str(log))
    rows = [json.loads(l) for l in log.read_text().splitlines()]
    assert rows[0] == {"tool": "probe", "host": "a.org", "calls": 3, "retried": 2, "recovered": 1, "failed": 1}
    monkeypatch.delenv("SBA_RETRY_LOG", raising=False)
    t.save("probe")                       # no log asked for: nothing written, no error


def test_fetch_ps1_reads_the_same_rules():
    """retry.json's keys fetch.ps1 reads by name"""
    with open(os.path.join(os.path.dirname(__file__), "..", "fetch.ps1"), encoding="utf-8") as f:
        ps = f.read()
    for key in ("transient_status", "one_off_4xx", "max_retry_after_s", "jitter", "fetch.tries", "fetch.waits_s"):
        assert "$rules." + key in ps, key
        node = retry.RULES
        for part in key.split("."):
            node = node[part]
