"""FEAT-238: where the pipeline reads and writes, now that it lives in MapPacker-SnowboardAnywhere.

    resorts/<slug>/                                   a folder per resort (FEAT-244): <slug>.json (the config), the
                                                      EPT node lists it names and <slug>-plan.md; resort.py
                                                      writes them, every stage reads them
    manifests/<slug>.json                             download lists (gen_manifest.py)
    packs/<slug>/                                     built packs (this checkout's; gitignored)
    raw/<slug>/                                       raw data: SBA_RAW_ROOT, else raw/ in the main checkout,
                                                      which every worktree shares
    ../SnowboardAnywhere                              the game, for the headless ride, pack_report.py's game-side
                                                      lines and the format check: --game-repo or SBA_GAME_REPO
"""
import os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RESORTS = os.path.join(REPO, "resorts")
MANIFESTS = os.path.join(REPO, "manifests")
PACKS = os.path.join(REPO, "packs")
GAME_NAME = "SnowboardAnywhere"
GAME_REPO_URL = "https://github.com/drewkeriazes/SnowboardAnywhere"


def resort_dir(slug, resorts=RESORTS) -> str:
    """resorts/<slug>/, the resort's folder: its config, the EPT node lists the config names (`nodes_file`, resolved
    in this folder) and its data plan. `resorts` is the folder that holds every resort's (tests pass a temp one)"""
    return os.path.join(resorts, slug)


def config_path(slug, resorts=RESORTS) -> str:
    """resorts/<slug>/<slug>.json"""
    return os.path.join(resort_dir(slug, resorts), f"{slug}.json")


def main_checkout(repo=REPO) -> str:
    """the main checkout of this repo (a worktree's is the folder that holds the shared .git); `repo` outside git"""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo,
                                capture_output=True, text=True, check=True).stdout.strip()
        return os.path.dirname(os.path.normpath(common))
    except (OSError, subprocess.CalledProcessError):
        return repo


def raw_root(repo=REPO) -> str:
    """where raw data lives: SBA_RAW_ROOT, else raw/ in the main checkout. Every worktree shares the main
    checkout's raw/ (a worktree's own raw/ is empty: a run there would fetch the resort again from scratch)"""
    if os.environ.get("SBA_RAW_ROOT"):
        return os.path.abspath(os.environ["SBA_RAW_ROOT"])
    return os.path.join(main_checkout(repo), "raw")


def game_repo(override=None, repo=REPO) -> str:
    """the game checkout: `override` (--game-repo), else SBA_GAME_REPO, else SnowboardAnywhere next to the main
    checkout (C:\\Users\\Drew\\git\\SnowboardAnywhere on Drew's PC). The path, whether or not it is there."""
    p = override or os.environ.get("SBA_GAME_REPO") or os.path.join(os.path.dirname(main_checkout(repo)), GAME_NAME)
    return os.path.abspath(p)


def has_game(path) -> bool:
    return os.path.isfile(os.path.join(path, "game", "package.json"))


def require_game(why, override=None, repo=REPO) -> str:
    """the game checkout, or SystemExit saying what needs it and how to point at it"""
    p = game_repo(override, repo)
    if not has_game(p):
        raise SystemExit(f"{why} needs the game: no SnowboardAnywhere checkout at {p}. Clone {GAME_REPO_URL} "
                         f"next to this repo, or pass --game-repo <path> (or set SBA_GAME_REPO)")
    return p
