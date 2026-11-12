#!/usr/bin/env bash
# FEAT-240 (from SnowboardAnywhere's FEAT-176): hash of this repo's render-budgets tools at a commit, so a local pass
# (tools/ci/local_render_budgets.mjs) only counts in CI when CI would have run the same tools. The game's side
# (cishot.mjs, render_report.py) is pinned by the game commit in the status instead. Built from git blob ids, which do
# not depend on how the checkout converts line endings, so Drew's Windows checkout and the Linux runner agree.
# bash tools/ci/render_budgets_key.sh <rev>   (prints 12 hex characters)
set -euo pipefail
rev=${1:-HEAD}
files="tools/ci/synth_key.sh tools/ci/render_budgets_key.sh tools/ci/render_note.py tools/ci/local_render_budgets.mjs
tools/ci/render_budgets_lib.mjs tools/ci/pack_content_key.py .github/workflows/checks.yml"
for f in $files; do
  echo "$f $(git rev-parse --verify -q "$rev:$f" || echo missing)"
done | sha256sum | cut -c1-12
