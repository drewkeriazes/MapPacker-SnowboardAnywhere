"""FEAT-245: fetch.ps1 downloads a manifest's nested paths to real folders, under Windows PowerShell on Drew's PC
and under pwsh on the Linux build runner (CI's pytest job), and a rerun skips what is already there. A local http
server stands in for the data hosts."""
import functools
import http.server
import json
import os
import shutil
import subprocess
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FETCH = os.path.join(HERE, "..", "fetch.ps1")
SHELL = shutil.which("powershell") or shutil.which("pwsh")

pytestmark = pytest.mark.skipif(SHELL is None, reason="no powershell or pwsh on PATH")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def server(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(site)))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield site, f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def fetch(raw, manifest):
    return subprocess.run([SHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", FETCH, "-Slug", "t",
                           "-RawDir", str(raw), "-ManifestPath", str(manifest), "-Concurrency", "2"],
                          capture_output=True, text=True, timeout=120)


def test_fetch_writes_nested_paths_and_a_rerun_skips_them(tmp_path, server):
    site, base = server
    data = os.urandom(5000)
    (site / "file.bin").write_bytes(data)
    manifest = tmp_path / "t.json"
    manifest.write_text(json.dumps({"slug": "t", "items": [{"url": f"{base}/file.bin", "path": "sub/dir/file.bin"}]}))
    raw = tmp_path / "raw"

    p = fetch(raw, manifest)
    assert p.returncode == 0, p.stdout + p.stderr
    got = raw / "t" / "sub" / "dir" / "file.bin"
    assert got.read_bytes() == data
    assert (raw / "t" / "FETCH_COMPLETE.txt").is_file()
    assert not list((raw / "t").rglob("*.part"))
    assert not [f for f in os.listdir(raw / "t") if "\\" in f]   # no file named with a backslash (Linux)

    (site / "file.bin").unlink()      # a rerun must not ask for it again
    p = fetch(raw, manifest)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "Skipping 1 already downloaded; 0 to fetch" in p.stdout
    assert got.read_bytes() == data

