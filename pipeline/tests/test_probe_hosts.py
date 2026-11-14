"""tools/ci/probe_hosts.py (FEAT-245): the data host probe, checked without the network."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tools", "ci"))
import probe_hosts as ph  # noqa: E402

TIFF = b"II*\x00" + b"\x00" * 60
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 20


def test_checks():
    assert ph.tiff(200, TIFF)[0] and not ph.tiff(200, b"<html>error</html>")[0] and not ph.tiff(500, TIFF)[0]
    assert ph.webp(200, WEBP)[0] and not ph.webp(200, TIFF)[0]
    assert ph.range_ok(206, b"x")[0] and ph.range_ok(200, b"x")[0]
    assert not ph.range_ok(206, b"")[0] and not ph.range_ok(404, b"x")[0]
    ept = ph.json_with("bounds", "schema")
    assert ept(200, json.dumps({"bounds": [], "schema": []}).encode())[0]
    assert not ept(200, b'{"bounds": []}')[0] and not ept(200, b"not json")[0] and not ept(403, b"{}")[0]
    # LFPS: an unknown job id is HTTP 500 with JSON (seen 2026-11-12), and that means the service is up
    assert ph.any_json(500, b'{"message":"JobId not found.","success":false}')[0]
    assert not ph.any_json(200, b"<html>maintenance</html>")[0] and not ph.any_json(503, b"{}")[0]
    assert ph.overpass(200, b'{"version": 0.6, "elements": []}')[0]
    assert not ph.overpass(200, b"<?xml?><remark>runtime error</remark>")[0]   # 200 with an error body
    assert ph.cdx(200, b'[["urlkey"]]')[0] and not ph.cdx(200, b"<html>")[0]


def test_every_probe_has_a_url_and_a_check_and_only_grooming_is_optional():
    ps = ph.probes()
    assert all(p.url.startswith("https://") and callable(p.check) for p in ps)
    assert [p.host for p in ps if not p.required] == ["web.archive.org"]
    names = " ".join(p.name for p in ps)
    for host in ("ImageServer", "EPT", "Planetary Computer", "Mapterhorn", "Overpass", "LFPS", "WorldCover", "ETH",
                 "GNIS", "Census", "OpenSkiData"):
        assert host in names
    assert len([p for p in ps if p.host == "Overpass"]) == 3


def by_name(ps, *names):
    return [p for p in ps if p.name in names]


def test_a_host_with_mirrors_passes_when_one_mirror_passes():
    ps = [p for p in ph.probes() if p.host == "Overpass"]
    results = [(ps[0], False, "HTTP 504", 1.0), (ps[1], True, "ok", 1.0), (ps[2], False, "HTTP 504", 1.0)]
    assert ph.failed_hosts(results) == ([], [])
    assert "down (mirror ok)" in ph.table(results)
    results = [(p, False, "HTTP 504", 1.0) for p in ps]
    assert ph.failed_hosts(results) == (["Overpass"], [])


def fake(answers):
    """fetch(url, range) answering by a substring of the url; everything else answers like a healthy host"""
    def fetch(url, rng):
        for key, reply in answers.items():
            if key in url:
                return reply
        if "interpreter" in url:
            return 200, b'{"version": 0.6, "elements": []}'
        if "exportImage" in url or "/crop/" in url:
            return 200, TIFF
        if url.endswith(".webp"):
            return 200, WEBP
        if "lfps" in url:
            return 400, b'{"message": "bad job"}'
        if "cdx" in url:
            return 200, b"[]"
        if rng:
            return 206, b"x" * 1024
        if "ept.json" in url:
            return 200, b'{"bounds": [], "schema": []}'
        if "tnmaccess" in url:
            return 200, b'{"items": []}'
        if "MapServer" in url:
            return 200, b'{"features": []}'
        if "collections/naip" in url:
            return 200, b'{"id": "naip", "extent": {}}'
        return 200, b"{}"
    return fetch


def test_main_passes_when_every_host_answers_and_writes_the_summary(tmp_path, monkeypatch, capsys):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert ph.main([], fetch=fake({})) == 0
    text = summary.read_text(encoding="utf-8")
    assert "| host | result |" in text and "FAIL" not in text
    assert "every host answered" in capsys.readouterr().out


def test_main_fails_on_a_required_host_after_the_inline_retries(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(ph.time, "sleep", lambda s: None)
    calls = []

    def fetch(url, rng):
        if "lfps" in url:
            calls.append(url)
            return 0, b"curl: (28) Operation timed out"
        return fake({})(url, rng)
    assert ph.main([], fetch=fetch) == 1
    assert len(calls) == 3                     # retry.json probe.tries
    assert "unreachable: lfps.usgs.gov" in capsys.readouterr().out


def test_the_archive_only_warns(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(ph.time, "sleep", lambda s: None)
    assert ph.main([], fetch=fake({"cdx": (503, b"down")})) == 0
    assert "warning: web.archive.org" in capsys.readouterr().out


def test_only_picks_probes_by_name_or_host(monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    seen = []

    def fetch(url, rng):
        seen.append(url)
        return fake({})(url, rng)
    assert ph.main(["--only", "overpass"], fetch=fetch) == 0
    assert len(seen) == 1 and "interpreter" in seen[0]     # the mirrors only when it fails
    assert ph.main(["--only", "no-such-host"], fetch=fetch) == 2


def test_a_mirror_is_not_tried_once_its_host_answered():
    seen = []

    def fetch(url, rng):
        seen.append(url)
        return 200, b'{"version": 0.6, "elements": []}' if "interpreter" in url else b"{}"
    over = [p for p in ph.probes() if p.host == "Overpass"]
    assert len(over) == 3
    ph.main(["--only", "Overpass"], fetch=fetch)
    assert seen == [over[0].url]


def test_tuning_raises_one_hosts_tries_within_the_caps(monkeypatch, tmp_path, capsys):
    """FEAT-314: host-tuning.json from the metrics branch; a bad file is the defaults"""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(ph.time, "sleep", lambda s: None)
    t = tmp_path / "host-tuning.json"
    t.write_text(json.dumps({"lfps.usgs.gov": {"timeout": 9999, "tries": 99}}))
    assert ph.load_tuning(str(t)) == {"lfps.usgs.gov": {"timeout": 180, "tries": 4}}
    assert ph.load_tuning(str(tmp_path / "missing.json")) == {} and ph.load_tuning(None) == {}
    (tmp_path / "bad.json").write_text("not json")
    assert ph.load_tuning(str(tmp_path / "bad.json")) == {}
    calls = []

    def fetch(url, rng):
        if "lfps" in url:
            calls.append(url)
            return 0, b"curl: (28) Operation timed out"
        return fake({})(url, rng)
    assert ph.main(["--tuning", str(t)], fetch=fetch) == 1
    assert len(calls) == 4 and "tuned: lfps.usgs.gov 180 s, 4 tries" in capsys.readouterr().out


def test_a_one_off_connect_failure_recovers_inline_and_is_logged(monkeypatch, tmp_path, capsys):
    """FEAT-314 refinement: the Deer Valley case (Geofabrik curl 7 once) passes in the same attempt"""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    log = tmp_path / "inline.jsonl"
    monkeypatch.setenv("SBA_RETRY_LOG", str(log))
    waits = []
    monkeypatch.setattr(ph.time, "sleep", waits.append)
    calls = []

    def fetch(url, rng):
        if "geofabrik" in url:
            calls.append(url)
            if len(calls) == 1:
                return 0, b"curl: (7) Failed to connect to download.geofabrik.de port 443"
        return fake({})(url, rng)
    assert ph.main([], fetch=fetch) == 0
    assert len(calls) == 2 and len(waits) == 1 and 8 <= waits[0] <= 12        # 10 s, jitter 20%
    rows = {d["host"]: d for d in map(json.loads, log.read_text().splitlines())}
    assert rows["download.geofabrik.de"] == {"tool": "probe", "host": "download.geofabrik.de", "calls": 1,
                                             "retried": 1, "recovered": 1, "failed": 0}
    assert rows["lfps.usgs.gov"]["retried"] == 0
    assert "Recovered inline: download.geofabrik.de" in capsys.readouterr().out


def test_a_4xx_is_not_retried_and_retry_after_is_respected(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    waits = []
    monkeypatch.setattr(ph.time, "sleep", waits.append)
    calls = []

    def fetch(url, rng):
        if "geofabrik" in url:
            calls.append(url)
            return 404, b"not found"
        if "tiles.openskimap" in url:
            calls.append(url)
            return (429, b"slow down", 90) if calls.count(url) == 1 else (206, b"x")
        return fake({})(url, rng)
    assert ph.main([], fetch=fetch) == 1
    assert len(calls) == 3 and len(waits) == 1 and waits[0] >= 90 * 0.8     # Retry-After 90 over the 10 s wait
    assert "HTTP 404 (a 4xx: not retried)" in capsys.readouterr().out


def test_the_retry_budget_caps_the_waits_of_a_whole_run(monkeypatch):
    monkeypatch.setattr(ph.time, "sleep", lambda s: None)
    p = ph.Probe("x", "x.org", "https://x.org/", ph.http_ok)
    budget = [15]
    ok, detail, _, k = ph.run_probe(p, lambda u, r: (503, b""), budget=budget)
    assert not ok and k == 2 and "retry budget used up" in detail and budget[0] < 15    # 10 s spent, 30 s refused
