"""FEAT-239: the pack format contract, checked against the game.

The pack format is the contract between this repo (the producer) and SnowboardAnywhere (the reader); its spec is
docs/pack-format.md here, and its Contract section lists every value both sides must agree on. This module reads
the game's side of the values a test can compare and says where they disagree.

The game's side comes from its `main` on GitHub (raw.githubusercontent.com), which is what a published pack has to
load in. `game_repo` (--game-repo, or SBA_GAME_REPO) reads a checkout's working files instead: point it at the
game's format PR to check the pair before either lands.

    python pipeline/contract.py [--game-repo DIR]      one line per value; exit 1 on a mismatch, 2 offline
"""
import argparse, os, re, sys, urllib.error, urllib.request
import numpy as np
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from paths import GAME_REPO_URL  # noqa: E402

GAME_MAIN_RAW = GAME_REPO_URL.replace("https://github.com/", "https://raw.githubusercontent.com/") + "/main/"
FORMAT_TS = "game/src/pack/format.ts"
SPECIES_TS = "game/src/world/trees/species.ts"
TREELINE_TS = "game/src/pack/treeline.ts"
WIDTHS_TS = "game/src/world/trees/widths.ts"


class GameUnreachable(Exception):
    """the game's main could not be read (offline, or GitHub down)"""


def game_source(rel: str, game_repo: str | None = None, timeout: float = 5.0) -> tuple[str, str]:
    """(text of the game file `rel`, where it came from). `game_repo` or SBA_GAME_REPO: that checkout's working
    file; else the game's main on GitHub. Raises GameUnreachable when GitHub can't be reached, FileNotFoundError
    when the file is not there."""
    repo = game_repo or os.environ.get("SBA_GAME_REPO")
    if repo:
        p = os.path.join(repo, *rel.split("/"))
        with open(p, encoding="utf-8") as f:
            return f.read(), p
    return _fetch_main(rel, timeout), GAME_MAIN_RAW + rel


@lru_cache(maxsize=None)
def _fetch_main(rel: str, timeout: float) -> str:
    url = GAME_MAIN_RAW + rel
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise FileNotFoundError(f"{url}: 404, the game's main has no {rel}") from e
        raise GameUnreachable(f"{url}: HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:   # no network, DNS, timeout
        raise GameUnreachable(f"{url}: {getattr(e, 'reason', e)}") from e


# ------------------------------------------------------------------ the game's side, parsed from its source
def pack_format(format_ts: str) -> int:
    """PACK_FORMAT in game/src/pack/format.ts"""
    m = re.search(r"export const PACK_FORMAT\s*=\s*(\d+)", format_ts)
    if not m:
        raise ValueError("no `export const PACK_FORMAT = <n>` in format.ts")
    return int(m.group(1))


def species_radii(species_ts: str) -> list[float]:
    """SPECIES[].radius in game/src/world/trees/species.ts, by id; the ids must be 0..n-1 in order"""
    table = species_ts[species_ts.index("export const SPECIES"):]
    table = table[:table.index("];")]
    rows = re.findall(r"\{\s*id:\s*(\d+),[^\n]*?\bradius:\s*([\d.]+)", table)
    if [int(i) for i, _ in rows] != list(range(len(rows))):
        raise ValueError("species.ts SPECIES ids are not 0..n-1 in order")
    return [float(r) for _, r in rows]


def width_step(widths_ts: str) -> int:
    """FEAT-298: WIDTH_STEP in game/src/world/trees/widths.ts (a stand image's width byte per unit of factor)"""
    m = re.search(r"export const WIDTH_STEP\s*=\s*(\d+)", widths_ts)
    if not m:
        raise ValueError("no `export const WIDTH_STEP = <n>` in widths.ts")
    return int(m.group(1))


def drawn_clamp(species_ts: str) -> tuple[float, float]:
    """FEAT-298: the multiples of the natural radius crownRadius keeps a pack's drawn radius within (species.ts)"""
    m = re.search(r"drawn\s*\?\s*nat\s*\*\s*Math\.max\(([\d.]+),\s*Math\.min\(([\d.]+)", species_ts)
    if not m:
        raise ValueError("no `drawn ? nat * Math.max(lo, Math.min(hi, k))` in species.ts crownRadius")
    return float(m.group(1)), float(m.group(2))


def value_mismatch(name: str, ours, game) -> str | None:
    return None if tuple(np.atleast_1d(ours).astype(float)) == tuple(np.atleast_1d(game).astype(float)) else f"{name} {ours} here, {game} in the game"


def default_treeline(treeline_ts: str) -> float:
    """DEFAULT_TREELINE in game/src/pack/treeline.ts"""
    m = re.search(r"export const DEFAULT_TREELINE\s*=\s*([\d.]+)", treeline_ts)
    if not m:
        raise ValueError("no `export const DEFAULT_TREELINE = <m>` in treeline.ts")
    return float(m.group(1))


# ------------------------------------------------------------------ comparisons: None when they agree
def format_mismatch(ours: int, game: int) -> str | None:
    """the bump rule (docs/pack-format.md > formatVersion): the game reads a new format first or together"""
    if ours == game:
        return None
    if ours > game:
        return (f"this pipeline writes pack format {ours}, the game's main reads {game}: land the game's format PR "
                f"first (PACK_FORMAT in {FORMAT_TS}), or test the pair with --game-repo / SBA_GAME_REPO")
    return (f"the game's main reads pack format {game}, this pipeline writes {ours}: every pack built here would show "
            f"'needs rebuild'; land this repo's format PR (FORMAT_VERSION in pipeline/packwriter.py)")


def radii_mismatch(ours, game) -> str | None:
    ours, game = [round(float(x), 6) for x in ours], [round(float(x), 6) for x in game]
    if ours == game:
        return None
    if len(ours) != len(game):
        return f"the game has {len(game)} species, the pipeline's CROWN_RATIO {len(ours)}"
    bad = [f"id {i}: {a} here, {b} in the game" for i, (a, b) in enumerate(zip(ours, game)) if a != b]
    return "crown radius / height differs: " + "; ".join(bad)


def treeline_mismatch(ours: float, game: float) -> str | None:
    return None if float(ours) == float(game) else f"default treeline {ours} m here, {game} m in the game"


def check(game_repo: str | None = None) -> list[tuple[str, str | None, str]]:
    """[(value, mismatch or None, where the game's side came from)] for every contract value a check can compare.
    Raises GameUnreachable when the game's main can't be read."""
    from packwriter import FORMAT_VERSION
    from cover import CROWN_RATIO as COVER_RATIO
    from stands import CROWN_RATIO as STANDS_RATIO
    from species import COLORADO_TREELINE
    out = []
    src, where = game_source(FORMAT_TS, game_repo)
    out.append(("formatVersion", format_mismatch(FORMAT_VERSION, pack_format(src)), where))
    src, where = game_source(SPECIES_TS, game_repo)
    radii = species_radii(src)
    # the species ids (0..7 since DATA-020) are the table's rows: species_radii checks the ids, these the count
    out.append(("crown radius per species (cover.py)", radii_mismatch(COVER_RATIO, radii), where))
    out.append(("crown radius per species (stands.py)", radii_mismatch(STANDS_RATIO, radii), where))
    from cover import DRAWN_CLAMP
    out.append(("drawn crown radius clamp (cover.py)", value_mismatch("clamp", DRAWN_CLAMP, drawn_clamp(src)), where))
    src, where = game_source(TREELINE_TS, game_repo)
    out.append(("default treeline", treeline_mismatch(COLORADO_TREELINE, default_treeline(src)), where))
    from widths import WIDTH_STEP
    src, where = game_source(WIDTHS_TS, game_repo)
    out.append(("stand width factor step (widths.py)", value_mismatch("WIDTH_STEP", WIDTH_STEP, width_step(src)), where))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game-repo", help="read this game checkout's working files instead of the game's main on GitHub")
    a = ap.parse_args(argv)
    try:
        rows = check(a.game_repo)
    except GameUnreachable as e:
        print(f"can't read the game's main ({e}); offline? --game-repo checks against a local checkout")
        return 2
    for name, bad, where in rows:
        print(f"{'FAIL' if bad else 'ok  '}  {name}" + (f": {bad}" if bad else ""))
    print(f"game side: {a.game_repo or os.environ.get('SBA_GAME_REPO') or GAME_MAIN_RAW}")
    return 1 if any(bad for _, bad, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
