"""Inline retries (FEAT-314): the one set of rules (retry.json, beside this file) for the calls a build makes, so a
one-second blip is retried in the call instead of failing the job. tools/ci/probe_hosts.py uses this module;
fetch.ps1 reads the same retry.json and does the same in PowerShell.

    transient(code, host)        retry this answer? (code 0: no answer at all)
    wait(tool, k, retry_after)   seconds before retry k (1 = the first retry)
    Tally                        per host: calls, retried, recovered, failed; save() appends them to $SBA_RETRY_LOG
"""
import json, os, random

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "retry.json"), encoding="utf-8") as _f:
    RULES = json.load(_f)


def transient(code: int, host: str = "") -> bool:
    """no answer (0), a 2xx or 3xx whose body failed the check, 408, 429, 5xx, or a host's listed one-off 4xx"""
    if code < 400 or code >= 500 or code in RULES["transient_status"]:
        return True
    return code in RULES["one_off_4xx"].get(host, [])


def wait(tool: str, k: int, retry_after=None, rand=random.random) -> float:
    waits = RULES[tool]["waits_s"]
    s = float(waits[min(k, len(waits)) - 1])
    if retry_after:
        s = max(s, min(float(retry_after), RULES["max_retry_after_s"]))
    return s * (1 + RULES["jitter"] * (2 * rand() - 1))


def worst_wait(tool: str, tries: int | None = None) -> float:
    """the most one call can sleep between its tries (jitter included)"""
    n = (tries or RULES[tool]["tries"]) - 1
    waits = RULES[tool]["waits_s"]
    total = sum(waits[min(k, len(waits)) - 1] for k in range(1, n + 1))
    return total * (1 + RULES["jitter"])


def caps_md() -> str:
    p, f = RULES["probe"], RULES["fetch"]
    return (f"Inline retry caps (`pipeline/retry.json`): probe {p['tries']} tries per host, waits "
            f"{', '.join(map(str, p['waits_s']))} s, at most {p['budget_s']} s of waiting per run; fetch "
            f"{f['tries']} tries per download, waits {', '.join(map(str, f['waits_s']))} s "
            f"(at most {worst_wait('fetch'):.0f} s per download). Never a 4xx, except "
            + ", ".join(f"{h} {'/'.join(map(str, c))}" for h, c in RULES["one_off_4xx"].items()) + ".")


class Tally:
    def __init__(self):
        self.hosts = {}

    def add(self, host: str, tries: int, ok: bool):
        """one call to `host` that took `tries` tries and ended ok or not"""
        t = self.hosts.setdefault(host, {"calls": 0, "retried": 0, "recovered": 0, "failed": 0})
        t["calls"] += 1
        t["retried"] += tries > 1
        t["recovered"] += tries > 1 and ok
        t["failed"] += not ok

    def save(self, tool: str, path: str | None = None):
        """one JSON line per host to `path` (default $SBA_RETRY_LOG; nothing when unset)"""
        path = path or os.environ.get("SBA_RETRY_LOG")
        if not path:
            return
        with open(path, "a", encoding="utf-8") as f:
            for h, t in sorted(self.hosts.items()):
                f.write(json.dumps({"tool": tool, "host": h, **t}) + "\n")
