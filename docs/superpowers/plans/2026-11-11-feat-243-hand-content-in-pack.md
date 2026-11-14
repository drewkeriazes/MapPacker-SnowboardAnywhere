# FEAT-243 Per-resort content in the pack: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Superseded in part (2026-11-13):** see the spec's "Reconciled 2026-11-13" section. No format bump, landmarks in
> `meta.landmarks`, and the menu, compare spots and favorites moved to follow-up cards; tasks A1 to A5 and B1 to B3 are
> what this card's two PRs did, in that reduced form.

**Goal:** A resort's menu shot, ghost takes, still, landmarks and start come from its pack (format 2), authored in
the game but saved into MapPacker's `resorts/<slug>/`; the game has no per-resort tables and its picker gains favorites.

**Architecture:** MapPacker gains `pipeline/pack_content.py`, which copies a resort's hand content into its pack
and resolves the start into `meta.start` without a new build stamp (also the format 1 to 2 upgrade). The game
loads `landmarks.json` and `attract/index.json` with the pack, and its authoring tools write to the resort folder
here and mirror into the served pack.

**Tech Stack:** Python 3.13 + pytest (MapPacker); TypeScript + Vite + three.js, Node 22 check tools bundled with
esbuild, Playwright browser checks (SnowboardAnywhere).

**Spec:** `docs/superpowers/specs/2026-11-11-feat-243-hand-content-in-pack-design.md` (approved 2026-11-11).

## Global Constraints

- Pack format: `FORMAT_VERSION = 2` (`pipeline/packwriter.py`), `PACK_FORMAT = 2` (`game/src/pack/format.ts`).
- Format 2 = format 1 plus `landmarks.json` (always, `[]` when none), `attract/index.json` (always, `{}` when none)
  and the files it lists, and the resolved `meta.start` with an optional `label`.
- Adding content never changes `meta.build`: `write_meta(..., stamp=False)`.
- A format 0 pack is never marked format 2; a format 1 pack becomes format 2 by `pack_content.apply`.
- Start order: a landmark with `start: true` (15 m uphill of it: `x - sin(h)*15, y - cos(h)*15`, heading `h` in
  radians, label `Starts at <name>`), else `resorts/<slug>/start.json` (heading in degrees, converted to radians),
  else `build_pack.py`'s own `meta.start` from `start_run`.
- Compare spots live in `resorts/<slug>/compare/` and are never copied into a pack.
- The game finds MapPacker at `SBA_PACKER_REPO`, else `../MapPacker-SnowboardAnywhere` next to the game checkout.
- Images under 1 MB (both repos' `public_guards.py`); compare PNGs over that become JPG at quality 90.
- Repo rules: plain commit messages with the card id (`FEAT-243`), authored as Drew, no em dashes in prose,
  `python -m pytest pipeline/tests` before pushing here; `npm run typecheck` and the game's checks there.
- MapPacker branch `issue-13-pack-content` (worktree `../wt-mp13`, exists). Game branch `mp13-pack-content` in
  worktree `../wt-mp13-game`, from the game's `origin/main` once FEAT-241/242 (#570, #571) merge, else from
  `origin/issue-561-drop-pipeline`.

## Review Focus

1. A pack whose `attract/index.json` lists a file that is missing from `resorts/<slug>/attract/`: the content step
   should stop with the file's name, not ship a pack the menu half-loads. (Task A2 test.)
2. Running the content step twice, or after a take was dropped: the pack's `attract/` matches the resort folder
   exactly, with nothing stale left. (Task A2 test.)
3. A format 1 pack loaded by the format 2 game (the "needs rebuild" case): it loads, with no menu shot,
   landmarks or label, and requests neither file. (Task B1 check.)
4. The dev server with no MapPacker checkout next door: a Shift+P shot still saves into the served pack, and the
   toast says it was not saved to MapPacker. (Task B4 check.)
5. Favorites holding a slug that is no longer in the index or catalog: it is ignored, not shown as an empty row.
   (Task B5 check.)

---

## Part A: MapPacker (`c:\Users\Drew\git\wt-mp13`)

### Task A1: Move the hand content into the resort folders

**Files:**
- Modify: `pipeline/paths.py` (add three functions), `tools/ci/public_guards.py:28` (`IMAGE_DIRS`), `.gitignore`
- Create: `resorts/vail/attract/` (from game `game/public/attract/vail/`), `resorts/breckenridge/attract/`,
  `resorts/vail/attract/index.json` and `resorts/breckenridge/attract/index.json` (each the slug's entry of the
  game's `game/public/attract/index.json`, no slug level), `resorts/vail/landmarks.json`,
  `resorts/breckenridge/start.json`, `resorts/vail/compare/` (from `docs/compare/vail/`), `docs/compare.md`
  (from `docs/compare/README.md`, paths rewritten)
- Test: `pipeline/tests/test_paths.py`, Create `pipeline/tests/test_resort_content.py`

**Interfaces:**
- Produces: `paths.attract_dir(slug, resorts=RESORTS) -> str` (`resorts/<slug>/attract`),
  `paths.landmarks_path(slug, resorts=RESORTS) -> str`, `paths.start_path(slug, resorts=RESORTS) -> str`,
  `paths.compare_dir(slug, resorts=RESORTS) -> str`.
- Data shapes (used by A2 and the game): `landmarks.json` = list of the game's `Landmark` objects
  (`id, kind: "gateway", name, x, y, heading, span, clearance, text, sub?, source, start?`, plus `note`: the code
  comment above it in `Landmarks.ts`); `start.json` = `{"x", "y", "heading" (deg), "label", "source", "note"}`
  (Breckenridge: x -1688, y -244, heading 140, label "Starts at the top of Imperial Bowl", source and comment
  from `STARTS.breckenridge`).

- [ ] **Step 1:** Record the game commit the files come from: `git -C ../SnowboardAnywhere rev-parse --short origin/main`.
- [ ] **Step 2: Write the failing tests.** `test_paths.py::test_resort_content_paths` asserts the four paths for
  slug `vail` under a temp `resorts`. `test_resort_content.py` (real repo files):
  `test_every_listed_attract_file_exists` (for each `resorts/*/attract/index.json`: every `ghosts` entry and every
  `stills` id `.jpg` exists in that folder, `shots.json` exists when `shots` is true, every `shotGhosts` file is in
  `ghosts`); `test_vail_has_its_gateway_as_start` (one landmark, id `back-bowls-gateway`, `start` true, x -718.0,
  y 495.9, heading 162); `test_breckenridge_start` (the values above); `test_compare_spots_parse` (each
  `resorts/*/compare/*/spot.json` has `game.x`, `game.y`); `test_no_image_over_1mb_in_resorts`.
- [ ] **Step 3:** Run `python -m pytest pipeline/tests/test_paths.py pipeline/tests/test_resort_content.py -v`. Expected: FAIL (no functions, no files).
- [ ] **Step 4:** Add the path functions. Copy the files with `git -C ../SnowboardAnywhere archive origin/main game/public/attract docs/compare | tar -x -C <scratch>`, then place them; write the split `index.json` files (keep key order). Re-encode the seven `docs/compare/vail/**/game-*.png` over 1 MB as `.jpg` quality 90 (Pillow) and update every reference to them in that spot's `notes.md` and `spot.json`. Move `docs/compare/.gitignore`'s two patterns into the root `.gitignore` as `resorts/*/compare/**/real*.png` and `resorts/*/compare/**/eye-*.png`.
- [ ] **Step 5:** `public_guards.py`: images are allowed under `docs/`, `reports/`, `resorts/<slug>/attract/`, `resorts/<slug>/compare/` (a regex `^resorts/[^/]+/(attract|compare)/` beside `IMAGE_DIRS`); its message names them.
- [ ] **Step 6:** Run the Step 3 command. Expected: PASS. Run `python tools/ci/public_guards.py --base origin/main --head HEAD` after committing. Expected: no errors.
- [ ] **Step 7: Commit** `FEAT-243: the menu shots, ghost takes, landmarks, Breckenridge's start and Vail's compare spots move into resorts/<slug>/ (from SnowboardAnywhere <sha>)`.

### Task A2: `pack_content.py`

**Files:**
- Create: `pipeline/pack_content.py`, `pipeline/tests/test_pack_content.py`

**Interfaces:**
- Consumes: A1's path functions; `packwriter.write_meta(out_dir, meta, stamp=False)`, `packwriter.FORMAT_VERSION`.
- Produces:
  - `resolve_start(meta_start: dict, landmarks: list[dict], placed: dict | None) -> dict` (pure; returns
    `{x, y, heading, run?, label?}`; `run` is kept only when the start is the `start_run` one).
  - `apply(slug: str, pack_dir: str, resorts: str = paths.RESORTS) -> dict` returns
    `{"landmarks": int, "attract": int (files copied), "start": "landmark" | "placed" | "run", "formatVersion": int}`;
    raises `SystemExit("<file> is listed in resorts/<slug>/attract/index.json but missing")`.
  - CLI: `python pipeline/pack_content.py <slug> <pack_dir>` prints the summary.

- [ ] **Step 1: Write the failing tests** (temp resorts and pack dirs; a pack is a `meta.json` with `slug`,
  `formatVersion`, `build`, `start`, `bounds`):
  - `test_landmark_start_beats_placed_and_run`: landmark heading 162 at (-718.0, 495.9) gives
    `x == approx(-718.0 - sin(radians(162))*15)`, `y == approx(495.9 - cos(radians(162))*15)`,
    `heading == approx(radians(162))`, `label == "Starts at The Legendary Back Bowls"`, no `run`.
  - `test_placed_start_in_degrees`: `start.json` heading 140 gives `heading == approx(radians(140))`, its label.
  - `test_run_start_kept_without_content`: `meta.start` unchanged, `run` kept.
  - `test_copies_only_listed_files_and_clears_stale`: `attract/` holds `take-1.json`, `extra.json`, `shots.json`,
    `a.jpg`; index lists `ghosts: ["take-1.json"]`, `stills: ["a"]`, `shots: true`; the pack already has
    `attract/old.json`. After `apply`: the pack's `attract/` is exactly `{index.json, take-1.json, shots.json, a.jpg}`.
  - `test_missing_listed_file_stops`: index lists `take-9.json` that is not there: `SystemExit` naming it.
  - `test_no_content_writes_empty_files`: a resort with no `attract/` and no `landmarks.json`: the pack gets
    `landmarks.json == []` and `attract/index.json == {}`.
  - `test_format_1_becomes_2_build_unchanged`: `formatVersion` 1, `build` "b1" becomes 2 and "b1".
  - `test_format_0_left_alone`: no `formatVersion`: still none after `apply`, content still copied.
  - `test_twice_is_the_same`: two `apply` runs leave identical files and `meta.json`.
- [ ] **Step 2:** Run `python -m pytest pipeline/tests/test_pack_content.py -v`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement. `apply` reads `meta.json`, removes the pack's `attract/`, copies the listed files,
  writes `landmarks.json`, sets `meta["start"] = resolve_start(...)`, sets `formatVersion = FORMAT_VERSION` when
  it is `FORMAT_VERSION - 1` or `FORMAT_VERSION`, then `write_meta(pack_dir, meta, stamp=False)`. Keep the
  original run start under `meta["runStart"]` so a second `apply` resolves from it, not from a landmark start
  (`resolve_start` takes `meta.get("runStart", meta["start"])`).
- [ ] **Step 4:** Run the Step 2 command. Expected: PASS (this needs Task A3's `FORMAT_VERSION = 2`; until then
  parametrise the format tests on `FORMAT_VERSION` and `FORMAT_VERSION - 1`).
- [ ] **Step 5: Commit** `FEAT-243: pack_content.py copies a resort's hand content into its pack and resolves the start, without a new build`.

### Task A3: Format 2, the build and the `content` stage

**Files:**
- Modify: `pipeline/packwriter.py:15` (`FORMAT_VERSION = 2`), `pipeline/build_pack.py` (end of the build: `pack_content.apply`),
  `pipeline/synth_pack.py:250` (after `write_meta`: `pack_content.apply("synth", out)`), `pipeline/build_resort.py`
  (`STAGES`, new `content_inputs/present/run`)
- Test: `pipeline/tests/test_build_resort.py`, `pipeline/tests/test_packwriter.py`

**Interfaces:**
- Consumes: `pack_content.apply`.
- Produces: `STAGES = ["nodes", "manifest", "fetch", "landfire", "grooming", "build", "content", "index", "report"]`;
  `content_inputs(r)` = sha of every file under `attract_dir`, `landmarks_path`, `start_path` (names and bytes)
  plus the pack's `meta.build`; `content_present(r)` = the pack's `landmarks.json` and `attract/index.json` exist.

- [ ] **Step 1: Write the failing tests** in `test_build_resort.py` (its `Fake` and `resort` fixtures):
  `test_a_new_shot_runs_only_content_index_and_report` (after a full run, add a file to `resorts/<slug>/attract/`
  and list it: the next run's stages run are exactly `content, index, report`); update
  `test_first_run_runs_every_stage_then_nothing_but_index_and_report` for the new stage; `test_a_rebuild_runs_content_again`
  (a new `meta.build` reruns `content`). In `test_packwriter.py`: `test_synth_pack_is_format_2_with_empty_content`
  if a synth build fits the test budget, else assert `synth_pack.py` calls `pack_content.apply` (grep the source).
- [ ] **Step 2:** Run `python -m pytest pipeline/tests/test_build_resort.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement the bump, the calls and the stage; the `Fake` runner treats `content` as an in-process call (`content_run` calls `apply`, no subprocess).
- [ ] **Step 4:** Run `python -m pytest pipeline/tests -v`. Expected: PASS except `test_contract.py`'s format test
  against the game's `main` (expected until the game PR lands). Then
  `SBA_GAME_REPO=../wt-mp13-game python -m pytest pipeline/tests/test_contract.py -v` once Task B1 exists. Expected: PASS.
- [ ] **Step 5: Commit** `FEAT-243: pack format 2; build_pack.py, synth_pack.py and a content stage in build_resort.py apply the hand content`.

### Task A4: `pack_report.py` and `canopy_spots.py` read the pack and the resort folder

**Files:**
- Modify: `pipeline/pack_report.py` (docstring lines 10-13; `measure` compare spots ~434; lines 11, 17, 18, 19 ~605-680),
  `pipeline/canopy_spots.py:13,96,168,175`
- Test: `pipeline/tests/test_pack_report.py`, `pipeline/tests/test_canopy_spots.py`

**Interfaces:**
- Consumes: A1's `compare_dir`; the pack's `attract/index.json`, `landmarks.json`.
- Produces: report lines with these statuses (mvp False, as today):
  - 11: `in packs/index.json` / `in the catalog` only (no `resorts.ts`).
  - 17: PASS when the pack's `attract/index.json` has `shots` and at least one ghost; WARN when the first shot's
    still is not in `stills` or its `looks[id].pack != meta.build` ("still from build X, the pack is Y: shoot_attract.mjs <slug>");
    FAIL when no shots ("no menu shot in the pack (resorts/<slug>/attract/)").
  - 18: PASS with `<n> in landmarks.json`, else FAIL "none (optional)".
  - 19: PASS with `<n> spots in resorts/<slug>/compare`, else FAIL.
  - None of 11, 17, 18, 19 reads the game checkout; `Report.game` stays only for what still needs it.

- [ ] **Step 1: Write the failing tests** with `make_pack` extended to write `attract/index.json` and `landmarks.json`:
  `test_menu_line_passes_with_shots_and_ghosts`, `test_menu_line_warns_on_a_still_from_another_build`,
  `test_menu_line_fails_without_shots`, `test_landmark_line_reads_the_pack`, `test_compare_spots_from_the_resort_folder`
  (a temp resorts dir with one `spot.json`), `test_hand_content_lines_do_not_need_the_game` (game path set to a
  missing folder: lines 17, 18, 19 are not SKIP). `test_canopy_spots.py`: the spots come from `resorts/<slug>/compare`.
- [ ] **Step 2:** Run `python -m pytest pipeline/tests/test_pack_report.py pipeline/tests/test_canopy_spots.py -v`. Expected: FAIL.
- [ ] **Step 3:** Implement (`Report` and `canopy_spots` take a `resorts` path, default `paths.RESORTS`, for tests).
- [ ] **Step 4:** Run the Step 2 command, then all of `pipeline/tests`. Expected: PASS (contract aside, as in A3).
- [ ] **Step 5: Commit** `FEAT-243: pack_report.py checks the menu, landmarks and start in the pack and compare spots in resorts/, not the game`.

### Task A5: Spec, contract and docs

**Files:**
- Modify: `docs/pack-format.md` (title "v2", tree listing, a new `## landmarks.json and attract/` section,
  `meta.start.label` and `runStart` in the meta block, formatVersion table row, a Contract row),
  `pipeline/contract.py` (a check), `pipeline/tests/test_contract.py`, `CLAUDE.md` (flow and the game-dependency
  sentence), `pipeline/paths.py` docstring, `.claude/skills/pack-build/SKILL.md` (where hand content lives),
  `docs/compare.md`.

**Interfaces:**
- Produces: `contract.reads_content(pack_ts: str) -> str | None` (the game's `game/src/pack/content.ts` source
  must mention `landmarks.json` and `attract/index.json`; message otherwise), added to `check()` as
  `("hand content files", ..., where)`.
- Table row: `| 2 | FEAT-243, <date> | Format 1 plus landmarks.json, attract/ and the resolved start (meta.start.label); a format 1 pack upgrades with pipeline/pack_content.py, no rebuild |`.

- [ ] **Step 1: Write the failing test** `test_contract.py::test_reads_content` (a string with both names: None; without: a message).
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Implement and write the docs.
- [ ] **Step 4:** Run `python -m pytest pipeline/tests -v` and `SBA_GAME_REPO=../wt-mp13-game python pipeline/contract.py`. Expected: PASS, every contract line ok against the game worktree.
- [ ] **Step 5: Commit** `FEAT-243: pack format 2 in the spec and the contract; docs point at resorts/<slug>/ for hand content`.

---

## Part B: SnowboardAnywhere (`c:\Users\Drew\git\wt-mp13-game`)

Setup: `git -C ../SnowboardAnywhere worktree add ../wt-mp13-game -b mp13-pack-content <base>` (base per Global
Constraints); `cd game && npm ci`.

### Task B1: The pack carries its content

**Files:**
- Create: `game/src/pack/content.ts`, `game/tools/contentcheck.mjs`
- Modify: `game/src/pack/format.ts` (`PACK_FORMAT = 2`), `game/src/pack/types.ts:109` (`start` gains `label?: string`),
  `game/src/pack/Pack.ts` (fields and `load`), `game/src/world/AttractShots.ts` (move `AttractManifest`'s per-resort
  type here as `AttractFiles`), `.github/workflows/checks.yml` (`PHYSICS_CHECKS` += `contentcheck`)

**Interfaces:**
- Produces:
  - `export type AttractFiles = { shots?: boolean; stills?: string[]; ghosts?: string[]; looks?: Record<string, StillLook>; shotGhosts?: Record<string, string[]> }` (AttractShots.ts).
  - `export async function loadPackContent(baseUrl: string, meta: PackMeta, get?: typeof fetch): Promise<{ landmarks: Landmark[]; attract: AttractFiles }>` (content.ts): format < 2 returns `{ landmarks: [], attract: {} }` without fetching; else fetches `${baseUrl}/landmarks.json` and `${baseUrl}/attract/index.json`, a failure or a wrong shape reading as empty (landmarks filtered to finite `x`, `y`, `heading`).
  - `Pack.landmarks: Landmark[]`, `Pack.attract: AttractFiles`, `Pack.baseUrl: string` (public readonly), set in `Pack.load`.

- [ ] **Step 1: Write the failing check** `contentcheck.mjs` (esbuild-bundles `content.ts` as `conditionscheck.mjs` does; a fake `get`):
  format 1 meta: returns empties and the fake saw no request; format 2: returns the parsed files; a 404 on
  either: that one empty; landmarks with a NaN `x` dropped; `attract` not an object: `{}`.
- [ ] **Step 2:** Run `cd game && node tools/contentcheck.mjs`. Expected: FAIL (no content.ts).
- [ ] **Step 3:** Implement content.ts, the types, the Pack fields; bump `PACK_FORMAT`.
- [ ] **Step 4:** Run `node tools/contentcheck.mjs && npm run typecheck`. Expected: all ok. (Typecheck errors in later tasks' files are expected only where they use the removed tables: none yet.)
- [ ] **Step 5: Commit** `FEAT-243 (MapPacker-SnowboardAnywhere#13): pack format 2: the pack loads its landmarks.json and attract/index.json`.

### Task B2: Landmarks and the start from the pack

**Files:**
- Modify: `game/src/world/Landmarks.ts` (delete `LANDMARKS`, `START_BACK`, `PlacedStart`, `STARTS`, `landmarkStart`;
  constructor reads `pack.landmarks`; keep `Landmark` exported), `game/src/ui/ResortMap.ts:238`,
  `game/src/session/Session.ts:3,232,326`, `game/src/core/Game.ts:5,67`, `game/tools/statecheck.mjs` or
  whichever check builds a start label (grep `landmarkStart`)

**Interfaces:**
- Consumes: B1's `Pack.landmarks`; `meta.start.label`.
- Produces: `startLabel(start: PackMeta['start']): string` in `Session.ts` (or a small export beside it):
  `label` if set, else `Starts on <run>`, else `Starts at the resort start`.

- [ ] **Step 1:** Add to `contentcheck.mjs` (bundle the file that exports `startLabel`): label wins; run next; fallback last.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Implement; every `landmarkStart(...) ?? pack.meta.start` becomes `pack.meta.start`.
- [ ] **Step 4:** Run `node tools/contentcheck.mjs && npm run typecheck && git grep -n "LANDMARKS\|STARTS\|landmarkStart" -- game`. Expected: checks ok, no grep hits.
- [ ] **Step 5: Commit** `FEAT-243: landmarks and the start come from the pack; Landmarks.ts keeps the gateway code, not the tables`.

### Task B3: The menu reads its files from the pack

**Files:**
- Modify: `game/src/world/AttractShots.ts` (`loadAttractShots(pack: Pack)`, `shippedStill(pack: Pack, shotId: string)`,
  delete `loadAttractManifest` and `AttractManifest`), `game/src/world/AttractGhosts.ts:95-98`
  (`load(ghosts: string[])` fetching `${pack.baseUrl}/attract/<f>`), `game/src/core/Game.ts:63-75`,
  `game/src/session/Session.ts:66,316` (`SessionOpts.attractFiles` becomes `ghosts: string[]`), `game/tools/ghost_lines/page.mjs:392`

**Interfaces:**
- Consumes: `Pack.attract`, `Pack.baseUrl`.
- Produces: `loadAttractShots(pack: Pack): Promise<AttractShot[]>` (fetches `attract/shots.json` only when
  `pack.attract.shots`); `shippedStill(pack: Pack, shotId: string): string` (same look rule as today, URL
  `${pack.baseUrl}/attract/<id>.jpg`). Headless still loads no ghosts or stills.

- [ ] **Step 1:** Add to `contentcheck.mjs` (bundle AttractShots.ts with a fake pack): `shippedStill` returns '' when the id is not in `stills`, '' when `looks[id].pack !== meta.build`, the pack URL otherwise.
- [ ] **Step 2:** Run it. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `node tools/contentcheck.mjs && npm run typecheck && npx vite build && node tools/menucheck.mjs synth --cpu`. Expected: ok (synth has empty content: the menu uses the start shot).
- [ ] **Step 5: Commit** `FEAT-243: the main menu's shot, still and ghosts load from the pack's attract/`.

### Task B4: The authoring tools save into MapPacker

**Files:**
- Modify: `game/tools/paths.mjs` (add `PACKER`, `attractHome`, `attractServed`, `compareHome`),
  `game/tools/attract_files.mjs` (every function takes one resort's attract folder; index has no slug level;
  add `mirror`), `game/vite.config.ts:101-191`, `game/tools/ghost_lines.mjs:63-84` and its uses,
  `game/tools/shoot_attract.mjs:5,35-37,80,150-152`, `game/tools/attract_look.mjs`, `game/tools/shoot_spots.mjs:3,23`,
  `tools/gmaps2game.py:16-17,83,117,135`, `game/src/session/devSaves.ts:28,80` (toast text),
  `game/tools/ghost_lines/README.md`, `docs/developer-guide.md` (where menu content lives),
  `.github/workflows/checks.yml:349-351` (`cp ../packs/synth/attract/*.jpg`), `:462`, `tools/ci/public_guards.py:32-34`
- Delete: `game/public/attract/`, `docs/compare/` (moved to MapPacker in Task A1)
- Create: `game/tools/attractcheck.mjs` (node only, temp folders), added to `PHYSICS_CHECKS`

**Interfaces:**
- Produces (paths.mjs): `PACKER: string | null` (`SBA_PACKER_REPO`, else `../MapPacker-SnowboardAnywhere`
  beside `REPO`, null when it has no `resorts/`); `attractHome(pack): string | null`
  (`<PACKER>/resorts/<pack>/attract`); `attractServed(pack): string` (`<PACKS>/<pack>/attract`);
  `compareHome(pack): string | null`.
- Produces (attract_files.mjs): `saveTake(pack, take) -> { file, mirrored: boolean, home: string | null }`,
  `saveShot(pack, posted) -> { file, shot, removed, home }`, `mirror(pack)` (replace `attractServed(pack)` with a
  copy of `attractHome(pack)`), the read helpers taking `pack`. With `PACKER` null every write goes to
  `attractServed(pack)` only and `home` is null; the HTTP handlers' reply carries `home` so the dev toast can say
  "saved to the pack only: no MapPacker checkout (SBA_PACKER_REPO)".
- `attract_look.mjs`: `lookCode(slug)` hashes LOOK files plus `attractServed(slug)/shots.json` and
  `<PACKS>/<slug>/landmarks.json`; `--check` with no packs prints one `::warning::` when the PR changes a LOOK file.

- [ ] **Step 1: Write the failing check** `attractcheck.mjs` (sets `SBA_PACKER_REPO` and `SHOT_PACKS` to temp
  folders before importing): a saved take lands in home and served with the next `take-<n>` name and is listed
  in both `index.json` files; a saved shot replaces the old one and its generated takes in both; with
  `SBA_PACKER_REPO` pointing at an empty folder, a take lands only in served and `home` is null.
- [ ] **Step 2:** Run `node tools/attractcheck.mjs`. Expected: FAIL.
- [ ] **Step 3:** Implement; then point every caller listed above at the new helpers and paths; delete the moved folders; update the docs and CI lines.
- [ ] **Step 4:** Run `node tools/attractcheck.mjs && node tools/getpackcheck.mjs && npm run typecheck && git grep -n "public/attract\|docs/compare" -- . ':!docs/research' ':!docs/superpowers'`. Expected: ok, and grep hits only in historical notes.
- [ ] **Step 5: Commit** `FEAT-243: the menu and compare tools save into MapPacker's resorts/<slug>/ and mirror into the served pack`.

### Task B5: Resort list and favorites

**Files:**
- Modify: `game/src/resorts.ts` (delete `RESORTS` and the probe), `game/src/ui/Settings.ts:13,DEFAULTS` (`favoriteResorts: string[]`, default `[]`),
  `game/src/ui/ResortPicker.ts` (one ordered list, a star per row, F key), `game/src/ui/PadNav.ts` (Y fires a bubbling `pady` event on the focused element),
  `game/src/ui/MainMenu.ts:262` (pass settings), `game/src/core/Game.ts:30-35` (default pack), `game/src/ui/theme.css` (star style), `game/tools/menucheck.mjs`
- Create: `game/tools/resortcheck.mjs` (esbuild bundle of `resorts.ts`), added to `PHYSICS_CHECKS`

**Interfaces:**
- Produces: `resortsFromIndex(index: PackIndex): { slug: string; name: string }[]` (name from `names`, else slug;
  sorted by name, `synth` last); `orderResorts<T extends { slug: string; name: string }>(rows: T[], favorites: string[]): T[]`
  (favorites tier then the rest, each by `name.localeCompare`, `synth` last overall; favorites not in `rows` ignored);
  `availableResorts(base): Promise<{slug, name}[]>` returns `[]` without an index.
- Picker: rows from `rows()` are passed through `orderResorts(.., settings.favoriteResorts)`; each row is
  `<div class="resort-row"><button class="course" data-pack ...>...</button><button class="fav" data-fav="<slug>" aria-pressed="true|false" aria-label="Favorite <name>">★ or ☆</button></div>`;
  clicking the star, F on a focused row, or `pady` on it toggles the slug in `settings.favoriteResorts`,
  `saveSettings`, redraws with focus kept.

- [ ] **Step 1: Write the failing check** `resortcheck.mjs`: index `{packs: ["vail","synth","bigsky","breckenridge"], names: {vail:"Vail", bigsky:"Big Sky", breckenridge:"Breckenridge", synth:"Test mountain (synthetic)"}}` gives
  Big Sky, Breckenridge, Vail, Test mountain; `orderResorts(that, ["vail","gone"])` gives Vail, Big Sky,
  Breckenridge, Test mountain; `orderResorts(that, ["vail","bigsky"])` gives Big Sky, Vail, Breckenridge, Test
  mountain; a slug with no name sorts by the slug.
- [ ] **Step 2:** Run `node tools/resortcheck.mjs`. Expected: FAIL.
- [ ] **Step 3:** Implement; Game.ts default pack: `orderResorts(resorts, settings.favoriteResorts)` first non-synth, else synth (load settings before it).
- [ ] **Step 4:** Add to `menucheck.mjs`: open Change resort, F on the focused row flips its `aria-pressed` and the row moves to the top; the setting survives a reload. Run `node tools/resortcheck.mjs && npm run typecheck && npx vite build && node tools/menucheck.mjs synth --cpu`. Expected: ok.
- [ ] **Step 5: Commit** `FEAT-243: the resort picker lists favorites first, then the rest, by name; RESORTS goes`.

### Task B6: Whole-pair verification and PRs

- [ ] **Step 1:** In `../wt-mp13`: `python pipeline/pack_content.py vail <a copy of the vail-v1 pack in scratch>` (download the release zip with `gh release download vail-v1` into the scratchpad); serve it in the game worktree with `npm run get vail -- --from <that dir> --force` into a temp packs folder via `SHOT_PACKS`; `node tools/shoot.mjs vail` on the GPU. Expected: the menu shows the Back Bowls shot and ghosts, the gateway stands, the start label reads "Starts at The Legendary Back Bowls".
- [ ] **Step 2:** `SBA_GAME_REPO=../wt-mp13-game python -m pytest pipeline/tests` in `../wt-mp13`. Expected: all pass.
- [ ] **Step 3:** Push both branches; open the game PR ("Part of drewkeriazes/MapPacker-SnowboardAnywhere#13", says it needs a format 2 synthetic pack published before its CI is green) and the MapPacker PR (`Fixes #13`), each saying what was run and that the menu was rendered on Drew's GPU, and the merge order from the spec.
- [ ] **Step 4 (after Drew merges, his go):** the spec's Order of work steps 3 and 4: publish the format 2 synthetic pack, then upgrade and republish Vail, Breckenridge, Big Sky and Boston Mills.
