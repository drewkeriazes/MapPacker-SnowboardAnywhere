# MapPacker-SnowboardAnywhere

Resort packs for [SnowboardAnywhere](https://github.com/drewkeriazes/SnowboardAnywhere): the pipeline that builds a pack from a resort's name, the recipe each pack is built from, the catalog of published packs, and the packs themselves as release assets. The game repo just plays them (EPIC-16, #9; plan in [`docs/pipeline-move.md`](docs/pipeline-move.md)).

Issues here go on the game's board, [project 2](https://github.com/users/drewkeriazes/projects/2), by themselves (`.github/workflows/add-to-project.yml`); how the board works is in the game repo's [`docs/BOARD.md`](https://github.com/drewkeriazes/SnowboardAnywhere/blob/main/docs/BOARD.md).

## Get a resort

In a SnowboardAnywhere checkout:

```
cd game
npm run get vail        # downloads, checks and unpacks into packs/vail
npm run get -- --list   # what is published
npm run dev
```

Or open **Change resort** on the main menu (with `npm run dev` or `npm run host` running) and pick a resort marked "Download".

## Build a resort

On Drew's PC (Windows; Python 3.13 with `pip install -r pipeline/requirements.txt`, Node, `gh` signed in), from this checkout:

```
add_resort.cmd "Boston Mills"     :: name to publish PR: resolve, plan, fetch, build, report, publish (add --ride for the headless ride)
build_resort.cmd vail             :: config to scored pack in packs\vail with its start, menu and proposed compare spots (no ride, no publish)
python pipeline\resort.py add --help
```

Every stage is skipped when its inputs have not changed, so both are safe to re-run. The first `add_resort.cmd` run for a new resort stops after the data plan (`resorts/<slug>/<slug>-plan.md`) so it can be read before a 1+ GB fetch.

### Add a resort yourself, step by step

Without Claude, on Windows:

1. **Set up once.**
   - Install Python 3.13 and run `pip install -r pipeline\requirements.txt`, then install Node.
   - Clone the game next to this repo (`..\SnowboardAnywhere`) and run `npm install` in its `game\` folder; the ride stage builds the game.
   - Optional: set `SBA_RAW_ROOT` to a drive with room (a resort's raw data is a few GB) and `LANDFIRE_EMAIL` to skip the LANDFIRE email question.
   - To publish you need `gh auth login` with push access to this repo. Without it, add `--no-publish` (step 5).
2. **Find the name.** Use the resort's name as [OpenSkiMap](https://openskimap.org) shows it ("Boston Mills", "Park City"); case and accents don't matter.
3. **First run: resolve and plan.** Double-click `add_resort.cmd` and type the name, or run `add_resort.cmd "Park City"`. It may ask two things (BUG-103):
   - *Several ski areas match*: type the number of the one you mean.
   - *Neighbours in its box or sold with it* (Park City lists Deer Valley, Solitude, Brighton, Alta): type the numbers of any to build into the same pack, commas between, or press Enter to leave their runs and lifts out. It prints the flags that give the same answer (`--with "<name>"`, `--alone`) for scripts.

   It then writes `resorts\<slug>\<slug>.json` and the data plan `resorts\<slug>\<slug>-plan.md`, and stops.
4. **Read the plan.** It shows the box, the tier (gold, silver or bronze, below), each layer's source, year and size, and the total download. If the tier or the box looks wrong, stop here and open an issue.
5. **Second run: everything else.** Run `add_resort.cmd` again with the same name. It does not ask again: the config remembers your answers (`--force resolve` asks again). Then:
   - It fetches (the long part; resumable).
   - It asks the LANDFIRE email once (US resorts only).
   - It builds the pack into `packs\<slug>\` (about 10 minutes for Vail).
   - It writes the scorecard `packs\<slug>\report.md` and publishes: a draft release and a publish PR (see Publishing below). The headless ride in the game runs only with `--ride`.

   After the report it prints the DATA-022 gate: *playable* when every MVP line passes, else *preview* with the lines that hold it back. Add `--no-publish` to stop before the release and PR.
6. **When a stage stops,** the message says which stage and what to do. Fix that and run the same command again: finished stages are skipped. `add_resort.cmd "<name>" --force <stage>` reruns one stage, and `python pipeline\resort.py add --help` lists the rest.
7. **Ride it.** In the game: `cd game`, then `npm run get <slug>` once the publish PR has merged, or `npm run get -- --from ..\..\MapPacker-SnowboardAnywhere\packs\<slug>` for the local build. Then `npm run dev` and open `/?pack=<slug>`.

- **Any resort with terrain** (FEAT-225): the plan picks the best source per layer and records the tier, the weakest layer's. Gold is 1 m 3DEP, lidar crowns and NAIP (most US resorts); Silver has no lidar (the trees are stands from the ETH 10 m canopy height) or Mapterhorn terrain at z15 or finer; Bronze has no NAIP (masks from ESA WorldCover), as everywhere outside the US, where the terrain comes from Mapterhorn at the best zoom it has there. Same pack format; the report shows each layer's source, and the DATA-022 gate still decides playable or preview.
- **Raw data** goes to `SBA_RAW_ROOT`, else `raw\` in the main checkout (worktrees share it). It is gitignored and never committed. On Drew's PC `SBA_RAW_ROOT` points at the raw data still in the game's clone, `C:\Users\Drew\git\SnowboardAnywhere\raw`, until it is moved here.
- **Moving an area** (FEAT-249): a config's `relocate` list cuts an area out and pastes it next to the rest (Brandywine beside Boston Mills), and `pack_bbox` is the box the pack is built on while `utm_bbox` stays the box the raw data was fetched for, so moving an area needs no new download. `python pipeline\relocate.py <slug> [--write]` works out `pack_bbox` from the runs and lifts after the move (`--write` puts it in the config).
- **Moving in another resort** (FEAT-268): a move with `"source": "<slug>"` cuts its area from that place's own raw data, a config marked `"source_only": true` (fetched with `build_resort.py <slug> --stop-after landfire`, never built or published), so a custom map can put hills from far apart side by side. `"raw_from": "<slug>"` builds a config on another resort's raw data and manifest, with its own state file. Ohio Hills (`resorts/ohio-hills/`) is Boston Mills' data with Mad River Mountain (`resorts/mad-river-mountain/`) moved in north of it.
- **The game** must be cloned next to this repo (`..\SnowboardAnywhere`) for the headless ride (`--ride`), the game-side lines of the build report and a few tests. `--game-repo <path>` or `SBA_GAME_REPO` points elsewhere; without it those parts say so and stop or skip.
- **Publishing** (`pipeline\publish_pack.py`, the last stage of `add_resort.cmd`, FEAT-272) never pushes to `main`. It runs from any checkout and needs `gh` signed in. It refuses a pack whose `meta.json` `pipeline` stamp is missing, `+dirty` or not on origin/main (build on a clean, merged `main`). Then it:
  1. uploads a draft release `<slug>-v<N>` (zip, `meta.json`, report; players and the catalog don't see a draft);
  2. opens a PR from the branch `publish/<slug>-v<N>`, built in a throwaway worktree off origin/main, with the `catalog.json` entry, `reports/<slug>.md` and the resort's config, node lists, plan and manifest, labelled `publish`, plus `automerge` when your GitHub login is in `.github/maintainers.txt`. Flags: `--accept-change` (a pack whose look changed; labels the PR `accept-change`, for FEAT-264's big-change check, not yet enforced), `--requested-by`, `--run-url`. It refuses a pack `pack_lint.py` finds problems in (dry run too), before anything is uploaded.
  3. The `publish-check` job downloads the draft zip and checks size, sha256 and the pack lint (`pipeline\pack_lint.py`: 600 MB, 5,000 files, 80,000 trees per km2), with scripts from `main`.
  4. When the checks are green, `publish-merge.yml` (`pipeline\publish_merge.py`) publishes the draft and then squash-merges the PR with the GitHub App token. It first checks who added `automerge` (who added `accept-change` is FEAT-264's check, not yet enforced), that the PR changes only the publish file set (`catalog.json`, `RELEASES.md`, `reports/<slug>.md`, `resorts/<slug>/`, `manifests/<slug>.json`) and that nobody but the App pushed after the label. It runs again every 15 minutes (and by hand: Actions > Publish merge > Run workflow), and every run looks at each open `publish/` PR labelled `automerge`, so a PR whose own run was dropped or that was still waiting on a check is picked up. A closed, unmerged PR's draft and branch are deleted. **Approve a publish with the `automerge` label, never the merge button:** a merge by hand would put a catalog entry on `main` whose release is still a draft.
  5. `resort.py add` counts an open publish PR for the same build as published, and reads `catalog.json` from origin/main. The headless ride runs only with `--ride`.

  After a NEW resort's PR merges, its `resorts\<slug>\` and `manifests\<slug>.json` are still untracked in the checkout that published, so `git pull` there refuses ("untracked working tree files would be overwritten"). Delete those untracked copies (they are identical to what merged), then pull.

  One-time setup (Drew): a GitHub App "MapPacker publisher" installed on this repo (Contents and Pull requests: write; Issues, Actions, Checks and Metadata: read; no `workflows` permission), the secrets `PUBLISH_APP_ID` and `PUBLISH_APP_KEY`, and the repository variable `PUBLISH_APP_LOGIN`. Until the App, its secrets and the variable exist, nothing merges itself; the safe manual path is `gh release edit <tag> --draft=false` first, then merge the PR (never the merge button with the release still a draft). A publish PR whose branch predates a workflow-file change on `main` needs a hand refresh: merge `main` into its branch locally and push, then remove and re-add the `automerge` label (a push after the label by anyone but the App is refused as untrusted).

  Rolling back a bad pack: a `publish/<slug>-v<old N>` branch whose catalog entry points back at the older (already public) release, labelled `publish` + `automerge`; it merges without touching a release. Or GitHub's Revert button on the publish PR, followed by a normal reviewed merge. The bad release stays on GitHub with nothing pointing at it.
- **To ride a pack before publishing it**, in the game: `cd game && npm run get -- --from ..\..\MapPacker-SnowboardAnywhere\packs\<slug>` (FEAT-242; it copies the pack in as the release zip would carry it, and again after a rebuild). Don't junction or symlink it into a game worktree: `git worktree remove` follows the link and empties the pack.
- **The synthetic pack** (`pipeline\synth_pack.py`, a made-up mountain the game's CI checks run on) is published the same way as a test pack (draft release and publish PR, as above), release `synth-v<N>`: `python pipeline\publish_pack.py --synth` from a checkout of the merged `main` builds it (about 2 minutes) and opens the PR only if its content changed. Run it after merging a change to the pipeline or the pack format (FEAT-241).

More in the `pack-build` skill (`.claude/skills/pack-build/SKILL.md`) and the notes in `CLAUDE.md`.

## Checks

Before pushing: `python -m pytest pipeline/tests` (about 5 s; the tests marked `game` compare with files in the game clone and skip without it).

Every PR gets the jobs in `.github/workflows/checks.yml` (FEAT-240), each its own check, and a review from the Claude PR reviewer (`pr-review.yml`, rules in `.claude/agents/pr-reviewer.md`):

| Check | Runs when | What |
|---|---|---|
| `pipeline-tests` | `pipeline/` changed | pytest, without the game |
| `format-check` | `pipeline/` changed | the pack format contract (`python pipeline/contract.py`, [`docs/pack-format.md`](docs/pack-format.md) > Contract) against the game's `main`, then the `game` tests against a checkout of it: the contract tests, the course rule and `get_pack.mjs` |
| `render-budgets` | PRs, `pipeline/` changed | the game's `main` draws the synthetic pack from this repo's `main` and from the PR (its `cishot.mjs`, on SwiftShader): shader compile and scene budgets, more than 10% over `main` fails. The report goes on the PR as a comment. Add the `stills` label for before / after stills. Nothing is drawn when the PR builds the same synthetic pack as `main` (by content, `tools/ci/pack_content_key.py`), or when an earlier commit of the PR passed with the same two packs, game commit and tools: that run's report is reused, with a line saying so (FEAT-251) |
| `publish-check` | catalog changed | a publish PR's draft zip: size, sha256 and `pack_lint.py`, and the entry's slug, version and `pack.url` (600 MB, 5,000 files, 80,000 trees per km2); scripts from `main` |
| `repo-rules` | every PR | no em dashes in added Markdown, plain commit messages; warns when a new script or flag comes with no docs change |
| `public-guards` | every PR | no `.env` files, no packs, raw data or data files in git, files up to 2 MB, images up to 1 MB under `docs/` or `reports/`, gitleaks |

Not a check but part of every publish PR: `publish-merge.yml` (its own workflow) publishes the draft and merges a trusted publish PR once these are green (see Publishing above). `pr-review.yml` skips a pure same-repo publish PR; a publish PR that touches anything else is reviewed as usual.

Rerun one: the PR's Checks tab > Re-run jobs, or Actions > Checks > Run workflow with the PR number.

**On Drew's GPU**, `node tools/ci/local_render_budgets.mjs` (in the PR's worktree, clean tree) runs `render-budgets` on the real GPU, posts the report and a `render-budgets/local` status, and CI skips its own run for that commit. With the hook switched on, a plain `git push` of a PR branch that changes `pipeline/` does the same first (it never blocks the push; `--no-verify` or `SA_SKIP_GPU_BUDGETS=1` skips it). Once per clone:

```
git config core.hooksPath .githooks
git config sa.gpuBudgets true
```

It needs the game clone next to this one with `npm ci` done in `game/`. Builds of the game's `main` and the synthetic packs are cached in `~/.cache/mappacker-ci` (`RB_CACHE`).

**README update** (`readme-update.yml`, FEAT-250, the game's FEAT-227 workflow ported here) brings this README up to date with what shipped. It runs only by hand: Actions > Update README > Run workflow, or `gh workflow run readme-update.yml`, with an optional `since` (a commit, tag, branch or date; `-f since=2026-11-01`). Without it, it starts from the last change to `README.md` on `main`, or, when that change was a merged README update PR, from the `main` commit that PR was made from. It lists the PRs merged into `main` since then, the cards closed without one of those PRs (this repo and the game) and the commits pushed straight to `main`; Claude checks them against the code (and a clone of the game's `main`) and edits `README.md` only. The workflow then pushes `readme-update-YYYY-MM-DD`, opens a PR and starts the Checks and the Claude review on it. Nothing to change: the run's summary says so and no PR is opened. A run while a README update PR is open stops and links to it. It never pushes to `main`. One-time setup: Settings > Actions > General > Workflow permissions > tick "Allow GitHub Actions to create and approve pull requests"; without it the run pushes the branch and its summary links to open the PR by hand.

## What is here

| Path | What |
|---|---|
| `catalog.json` | Every published pack: slug, name, region, tier, status, and the release zip's version, pack format, size, sha256, URL and the pipeline commit that built it. Test packs (the synthetic pack) are in a separate `test` list the resort picker does not read, one entry per pack format, with a `content` hash |
| `pipeline/` | The pipeline: `resort.py` (name to config and data plan, and `add`), `build_resort.py`, `build_pack.py` and its stages, `pack_report.py`, `publish_pack.py`, the fetch scripts, tests in `pipeline/tests/`. Moved from the game repo with its history (FEAT-238) |
| `docs/pipeline-scripts.md` | Every script in `pipeline/`: what it reads and writes, its options (moved from the game's developer guide in FEAT-242) |
| `docs/pack-format.md` | The pack format: the layout, the encodings, `formatVersion` and its bump rule, and the Contract, every value this repo and the game must agree on (FEAT-239) |
| `resorts/<slug>/` | A folder per resort: `<slug>.json`, the config the pipeline reads, the EPT node lists it names (`nodes_file`, beside it) and the data plan (`<slug>-plan.md`) |
| `manifests/<slug>.json` | The download manifest the raw data was fetched with |
| `reports/<slug>.md` | The build report of the published pack |
| `*.cmd` | Launchers for Drew's PC (above) |
| Releases `<slug>-v<N>` | `<slug>.zip` (the pack, stored), its `meta.json`, and the report; `synth-v<N>` for the synthetic pack |

Packs live in releases, never in git history: a pack is 50 to 250 MB per build, and releases can be deleted when a build is replaced. A catalog entry's `pipeline` is the commit of this repo that built the pack; entries published before the pipeline moved here (FEAT-238) name a SnowboardAnywhere commit instead.

`status` is `playable` when every DATA-022 check passes in the build report, else `preview`. `formatVersion` is the pack format; a game reads only its own format and shows an older pack as "needs rebuild". A format change goes into the game first or together ([`docs/pack-format.md`](docs/pack-format.md) > formatVersion); `python pipeline/contract.py` compares this pipeline with the game's `main`.

## Data sources and licences

The packs are built from these sources. OpenStreetMap-derived parts of a pack (`features.json`: runs, lifts, buildings, roads, water, names; the groomed-run and run-direction masks) are a derivative of OpenStreetMap and are available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The rest is public domain or CC BY 4.0 as listed.

- Elevation and lidar: U.S. Geological Survey 3D Elevation Program (public domain)
- Terrain tiles: Mapterhorn, built from USGS 3DEP in the US and from national elevation models elsewhere (credit per pack in meta.json attribution)
- Imagery: USDA NAIP via Microsoft Planetary Computer (public domain)
- Vegetation type, cover and height: LANDFIRE, USGS and U.S. Forest Service (public domain)
- Geographic names: USGS GNIS (public domain); town names and sizes: US Census Bureau Gazetteer and population estimates (public domain)
- Map data © OpenStreetMap contributors, ODbL; ski area data: OpenSkiMap.org
- Land cover: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium (CC BY 4.0)
- Canopy height: Lang, Jetz, Schindler, Wegner, "A high-resolution canopy height model of the Earth", Nature Ecology & Evolution 7, 1778-1789 (2023), ETH Global Sentinel-2 10 m Canopy Height 2020 (CC BY 4.0)

Each pack's own list is in its `meta.json` (`attribution`). Resort names are used as facts; no resort trademarks or trail map artwork are included.
