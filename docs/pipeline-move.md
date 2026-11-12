# Moving the pipeline to MapPacker (EPIC-16)

**MapPacker builds the packs; SnowboardAnywhere just plays them.** Epic: #9. This reverses EPIC-15 rule 3 (drewkeriazes/SnowboardAnywhere#516: "game and all pipeline code stay in the game repo") now that the build is one command (`resort.py add`, FEAT-224) and the format is versioned (`formatVersion`, FEAT-222).

Researched 2026-11-11 against SnowboardAnywhere `main` at `2a0b12f`.

## 1. What moves, what stays

| Moves to MapPacker | Stays in SnowboardAnywhere |
|---|---|
| `pipeline/` (30 files, about 1.6 MB, 16 test files) | `game/` (client, check tools, `get_pack.mjs`, `host.mjs`) |
| `pipeline/resorts/*`, `pipeline/manifests/*` (into `resorts/`, `manifests/`, replacing the copies) | `packs/` as the place packs are downloaded to |
| `add_resort.cmd`, `build_resort.cmd`, `fetch_static.cmd`, `fetch_landfire.cmd` | `tools/card_id.py`, `tools/gmaps2game.py`, `tools/ci/*` (less the pipeline parts) |
| `.claude/skills/pack-build/` | the other skills, `pr-reviewer.md` (ported, not moved) |
| `docs/pack-format.md` (the contract, section 2) | the developer guide, with a link for the pipeline |
| `raw/` on Drew's PC (later; `SBA_RAW_ROOT` bridges it) | |

Undecided, picked in FEAT-242: `prep_textures.py` writes the game's own rock textures (`game/public/textures/`), not a pack, so it may stay as a game tool.

## 2. The contract (FEAT-239)

The two repos agree on one thing: the pack format. The producer owns the spec.

| Contract item | MapPacker side | Game side |
|---|---|---|
| `formatVersion` | `pipeline/packwriter.py` `FORMAT_VERSION`, `meta.json`, `catalog.json` | `game/src/pack/format.ts` `PACK_FORMAT` |
| Pack layout and tile sets | `docs/pack-format.md` | `game/src/pack/types.ts` and the loaders |
| Species ids and crown radius per id | `pipeline/cover.py`, `pipeline/stands.py` | `game/src/world/trees/species.ts` |
| Default treeline | `pipeline/species.py` | `game/src/pack/treeline.ts` |
| `packs/index.json` | `packwriter.index_packs` | `game/tools/get_pack.mjs`, `game/src/resorts.ts` |
| `catalog.json` | `publish_pack.py` | `game/tools/get_pack.mjs`, the resort picker |

Today `pipeline/tests/test_publish_pack.py` checks `FORMAT_VERSION == PACK_FORMAT` by reading `format.ts` from the same checkout. After the move it reads the game's `main` instead: equal passes, MapPacker ahead fails ("land the game's format PR first"), offline skips with a warning.

**Bump rule:** any change a current game can't read bumps `formatVersion`. The game PR lands first or together. Every catalog pack on an older format shows "needs rebuild" (FEAT-222) until it's republished.

## 3. The move (FEAT-238)

1. **When:** after DATA-023 (#4) publishes, so the Boston Mills run isn't split across repos. Check the game repo has no open PR touching `pipeline/` (on 2026-11-11 the only open PR, #559, is client perf).
2. **History:** `git filter-repo --path pipeline/ --path add_resort.cmd --path build_resort.cmd --path fetch_static.cmd --path fetch_landfire.cmd --path .claude/skills/pack-build/` on a fresh game clone, then merge into a branch here with `--allow-unrelated-histories`. Then move `pipeline/resorts/*` and `pipeline/manifests/*` into `resorts/` and `manifests/`.
3. **Paths that change:** configs from `resorts/` here; raw data from `SBA_RAW_ROOT`, else `raw/` in this repo's main checkout (worktrees share it, as now); packs build to `packs/<slug>/` here; `publish_pack.py` commits in place instead of into a sibling clone; the catalog's `pipeline` field becomes this repo's commit.
4. **Where the pipeline still needs the game**, found at `../SnowboardAnywhere` (`--game-repo` or `SBA_GAME_REPO` overrides):
   - `resort.py add` stage `ride` runs `npx vite build` and `game/tools/shoot.mjs` with `SHOT_PACKS` on the pack.
   - `pack_report.py` checks game-side content (attract shots, compare spots, `Landmarks.ts`, `resorts.ts`) until FEAT-243 moves it into the pack.
   - The format check (section 2).
5. **Drew's PC:** sibling clones in `C:\Users\Drew\git`. Set `SBA_RAW_ROOT=C:\Users\Drew\git\SnowboardAnywhere\raw` first so nothing is fetched again; move the folder later.
6. **Agent docs:** a `CLAUDE.md` here and the `pack-build` skill, so sessions opened in this repo can build and publish.

## 4. CI (FEAT-240 here, FEAT-241 in the game)

Today one workflow (`SnowboardAnywhere/.github/workflows/checks.yml`) covers both sides:

| Job today | Runs when | After the move |
|---|---|---|
| `pipeline-tests` (pytest) | `pipeline/` changed | MapPacker `checks.yml` |
| `synth-pack` (Python, about 2 min, cached on `tools/ci/synth_key.sh`) | `game/` or `pipeline/` changed | Game downloads release `synth-v<N>` (FEAT-241) |
| `browser-checks` on the synthetic pack | `game/` or `pipeline/` changed | Game, on the downloaded pack |
| `render-budgets`, main vs PR, with main's synthetic pack when the PR changes the pipeline | PRs, `game/` or `pipeline/` changed | Game: same pack both sides, game changes only. MapPacker: synthetic pack from main vs PR, rendered by the game's `main` (FEAT-240) |
| Repo rules, public guards | every PR | Both repos |
| PR reviewer (`pr-review.yml`, `pr-reviewer.md`) | every PR | Ported to MapPacker; needs the `CLAUDE_CODE_OAUTH_TOKEN` secret there |

The GPU pre-push hook (`.githooks/pre-push`) runs `render-budgets` on `game/` or `pipeline/` changes; its pipeline half moves with FEAT-240.

## 5. Game repo cleanup (FEAT-242)

- Remove `pipeline/`, the four launchers, the `pack-build` skill, the `pipeline-tests` job and the `pipeline/**` filters.
- Local packs: `npm run get <slug> --from <pack dir>` (or `SBA_PACKS` for the dev server) so a fresh MapPacker build can be ridden before it's published.
- Docs: `CLAUDE.md`, `README.md`, developer guide ("Pipeline scripts" becomes a link here), `HANDOFF.md`, `workspace-and-sessions.md`. Research and plan docs keep their old paths as history.
- Code comments that name `pipeline/<file>` (`format.ts`, `types.ts`, `resorts.ts`, `treeline.ts`, `stands.ts`, `Courses.ts`, `rockShader.ts`, `get_pack.mjs`) point here.
- Open game cards whose work is all pipeline move here with `gh issue transfer`. Candidates on 2026-11-11: #507 BUG-083, #439 DATA-022, #433 BUG-079, #409 FEAT-175, #358 BUG-067, #336 FEAT-150, #333 FEAT-149, #195 DATA-018. #458 FEAT-192 and #516 EPIC-15 span both and stay.

## 6. Later: per-resort content in the pack (FEAT-243)

A new resort should need no game PR. Today these still live in the game repo per slug: `game/public/attract/<slug>/`, `docs/compare/<slug>/`, `LANDMARKS` and `STARTS` in `game/src/world/Landmarks.ts`, entries in `game/src/resorts.ts`. Each moves into the pack (a format bump), written from the resort's config here. Overlaps FEAT-175 step 4 (generated start, attract shots, compare spots).

## Risks

| Risk | Answer |
|---|---|
| A format change now needs two PRs | Rare once settled; the bump rule and "needs rebuild" keep a mismatch safe |
| A pipeline change can change what the game draws, and the game's CI no longer sees it | FEAT-240's render check here, against the game's `main` |
| Shared constants drift (species radii, treeline) | Listed in the spec's contract section with both file paths; FEAT-243 moves more of them into `meta.json` |
| Raw data paths break on Drew's PC | `SBA_RAW_ROOT` first, move later |
| Cards in flight split across repos | Start after DATA-023; transfer cards rather than copy them |
