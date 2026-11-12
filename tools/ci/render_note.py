#!/usr/bin/env python3
"""FEAT-240: adapts the game's render report (SnowboardAnywhere's tools/ci/render_report.py, run from a checkout of
the game's main) to what the check compares here: one build of the game's main drawing two synthetic packs, the one
this repo's main builds (before) and the one the PR builds (after). The game's report says "Before is `main`, after
is this PR"; this rewrites that sentence, or adds the line under the heading when the game's wording has moved on.

python tools/ci/render_note.py <report.md> --game-repo <owner/name> --game-sha <sha> [--same-pack]

--same-pack: main and the PR build the same synthetic pack (the PR changes no pipeline code), so before and after
are the same pack and the numbers can only differ by noise. Standard library only.
"""
import argparse
import re
import sys

OLD = re.compile(r"Before is `main`, after is this PR, both on the same synthetic pack build\.")


def note(game_repo, game_sha, same_pack):
    game = f"[`{game_sha[:12]}`](https://github.com/{game_repo}/commit/{game_sha})"
    s = (f"Before is the synthetic pack built by this repo's `main`, after is the one this PR builds, both drawn by "
         f"the game's `main` at {game}.")
    if same_pack:
        s += " This PR builds the same synthetic pack as `main`, so any difference is run-to-run noise."
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--game-repo", required=True)
    ap.add_argument("--game-sha", required=True)
    ap.add_argument("--same-pack", action="store_true")
    a = ap.parse_args()
    with open(a.report, encoding="utf-8") as f:
        text = f.read()
    line = note(a.game_repo, a.game_sha, a.same_pack)
    if OLD.search(text):
        text = OLD.sub(lambda _: line, text, count=1)
    else:
        lines = text.split("\n")
        at = next((i + 1 for i, l in enumerate(lines) if l.startswith("## ")), 0)
        lines[at:at] = ["", line]
        text = "\n".join(lines)
    with open(a.report, "w", encoding="utf-8") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
