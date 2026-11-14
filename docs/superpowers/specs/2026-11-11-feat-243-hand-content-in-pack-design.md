# FEAT-243: per-resort content travels in the pack (design)

Card: MapPacker-SnowboardAnywhere#13, part of EPIC-16 (#9). Two PRs: one in SnowboardAnywhere (the reader,
the picker, the authoring tools) and one here (the writer, the spec, the moved files, the report). The game's
lands first or together (pack format bump rule, `docs/pack-format.md` > formatVersion).

## Reconciled 2026-11-13 (after FEAT-175 step 4)

FEAT-175 step 4 (MapPacker#32: #51 here, SnowboardAnywhere#584) landed first. It writes a generated menu into the
pack's `attract/` in this design's layout, with `meta.attract` telling the game to ask for it, and a generated
`meta.start` with a `label`, and the game already reads both. That changes the plan:

- **No format bump.** Everything this card adds is optional and ignored by a game that does not read it, so the
  pack stays on format 1 (`docs/pack-format.md` > formatVersion rule 1) and the synthetic-pack dance in "Order of
  work" step 3 is not needed. Landmarks go in `meta.landmarks` (one small list) instead of a `landmarks.json`
  beside it, and `attract/` is asked for through `meta.attract` as #51 does, so no request 404s.
- **Order:** this repo's PR first (the content stage writes `meta.landmarks` and the resolved start; an old game
  ignores them), then republish Vail and Breckenridge (Drew's go), then the game PR, which drops `LANDMARKS`,
  `STARTS`, `landmarkStart` and `RESORTS` and reads the pack. Until the republish the game PR waits, or the game's
  `main` would lose Vail's gateway and both placed starts.
- **The content step** is `pipeline/pack_content.py`, run in process right after gen_content.py in
  `build_resort.py`'s `content` stage (no separate stage); its fingerprint adds `resorts/<slug>/landmarks.json`,
  `start.json` and `attract/`. A hand-made menu copied into the pack keeps #51's rules: its `index.json` has no
  `generated` (it gets `"hand": true`), so gen_content.py and the attract stage leave it alone.
- **Deferred to a follow-up card:** moving the menu files (`game/public/attract/`) and the compare spots
  (`docs/compare/`) here, with the game tools that write them (`attract_files.mjs`, the dev server's saves,
  `ghost_lines.mjs`, `shoot_attract.mjs`, `attract_look.mjs`, `shoot_spots.mjs`, `gmaps2game.py`, `propose_spots.py`,
  the CI lines), and `pack_report.py` lines 17 and 19 and `canopy_spots.py` reading them here. Moving the files
  before the tools would leave two homes. `pack_content.py` already copies a `resorts/<slug>/attract/` when one
  exists. The resort picker's favorites tier is its own card too.
- **Republish:** Vail and Breckenridge (the two with hand content) through `pack_content.py` on the released pack
  and `publish_pack.py`, as in "Order of work" step 4, but no other resort needs it (no format change).

## Why

A new resort should need no game PR. Today the game repo still holds, per slug:

| What | Where in the game today | Read by |
|---|---|---|
| Main menu shot, still, ghost takes | `game/public/attract/<slug>/`, `game/public/attract/index.json` | `world/AttractShots.ts`, `world/AttractGhosts.ts`, `core/Game.ts` |
| Landmarks (Vail's Back Bowls gateway) | `LANDMARKS` in `game/src/world/Landmarks.ts` | `Landmarks` class, `session/World.ts`, `ui/ResortMap.ts` |
| Placed Free ride start (Breckenridge) | `STARTS` in `game/src/world/Landmarks.ts` | `landmarkStart()` in `core/Game.ts`, `session/Session.ts` |
| Compare spots | `docs/compare/<slug>/<spot>/` | dev tools (`?spot=`, `/__compare/save`, `shoot_spots.mjs`), `pipeline/canopy_spots.py`, `pipeline/pack_report.py` |
| Menu order and names | `RESORTS` in `game/src/resorts.ts` | `availableResorts`, `resortsFromIndex` |

## What Drew wants (from the conversation)

- **The menu shot is creative work done in the running game:** a pretty view, a slope in front of the camera
  for the ghosts to ride down, and where possible something iconic to the place (the Back Bowls sign at Vail,
  a resort-name sign people photograph). Drew frames it with the eye camera (Shift+P with `?debug`), records live
  takes, then draws linked turns on a menu screenshot and `game/tools/ghost_lines.mjs` puts ghosts on each line.
  **That workflow stays in the game and keeps working; only where it saves changes.**
- **One home per file:** the authored files live in this repo's `resorts/<slug>/`, are committed here, and the
  pipeline copies what players need into the pack.
- **Don't fill the pack with data players don't need:** compare spots stay out of the pack.
- **Stay efficient:** moving Vail, Breckenridge and Big Sky to the new format must not rebuild terrain.
- **Favorites in the resort picker** (new, replaces the hard-coded order): resorts the player stars sit in a
  tier above the rest; both tiers alphabetical.

## Goals

1. Menu content, landmarks and the start come from the pack. The game has no per-slug table left
   (`git grep -n "vail\|breckenridge\|bigsky" game/src` finds comments only).
2. The authoring tools in the game save into `resorts/<slug>/` in the MapPacker checkout next door, and into the
   served pack so the change shows at once.
3. Pack format 2, with an upgrade path from format 1 that adds the new files without a rebuild or a new build stamp.
4. `pack_report.py` reads the pack and the resort folder; it needs the game only for the ride.
5. Vail, Breckenridge and Big Sky republished on format 2.
6. The picker: favorites tier, then the rest, alphabetical, the test mountain last.

## Non-goals

- Generating menu shots, ghost takes, starts or compare spots automatically (FEAT-175 step 4, SnowboardAnywhere#409).
- New landmark kinds, or changing how the gateway is built (the arch code stays in `Landmarks.ts`).
- Moving the authoring tools out of the game (they need its renderer).
- Shipping compare spots to players.

## Anti-goals (a failure even if it works)

- The menu still goes stale because adding content to a pack changed `meta.build`.
- A republish of an existing resort waits on a terrain rebuild.
- A shot saved in the game ends up only in the game checkout, or only in a gitignored pack, so it is lost.
- An older pack breaks the game: a format 1 pack must still load (shown "needs rebuild"), just without its menu
  shot, landmarks or placed start.

## Design

### Source layout here (one home per file)

```
resorts/<slug>/
  <slug>.json              config (unchanged)
  start.json               optional: a placed Free ride start (below)
  landmarks.json           optional: [Landmark, ...], the game's Landmark shape, `note` for the old code comment
  attract/
    index.json             this resort's entry of the old game manifest: { shots?, stills?, ghosts?, looks?, shotGhosts? }
    shots.json             the menu shots (the menu uses the first)
    <shot>.jpg             the rendered still
    take-<n>.json, <shot>-<line>[-v<n>]-<i>.json   recorded and generated ghost takes
  compare/<spot>/          spot.json, notes.md, eye-*.jpg, game-*.png (never copied into a pack)
```

`docs/compare/README.md` and `docs/compare/.gitignore` (which keeps Street View photos out of git) move with
the spots: the README to `docs/compare.md` here, the ignore rule to `resorts/*/compare/` in this repo's
`.gitignore` (same patterns). `pipeline/paths.py` gains `attract_dir(slug)`, `landmarks_path(slug)`,
`compare_dir(slug)`.

**`start.json`** (replaces `STARTS`): `{"x", "y", "heading", "label", "source"}`, pack metres, heading in
degrees clockwise from north, as in `STARTS` today. Optional; the config's `start_run` stays. *Builder's call:*
a file of its own, not a config key, because the config's hash is part of the build fingerprint
(`build_resort.py` `build_inputs`), so a hand-placed start would otherwise trigger a terrain rebuild.

### What the pack carries (format 2)

```
packs/<slug>/
  meta.json         "formatVersion": 2; "start" resolved (below), with an optional "label"
  landmarks.json    always present on format 2 ([] when the resort has none)
  attract/
    index.json      always present on format 2 ({} when the resort has none); the same shape as resorts/<slug>/attract/index.json
    shots.json, <shot>.jpg, the takes listed in index.json
```

Always present, so the game fetches them without asking first and nothing 404s. Only files listed in
`attract/index.json` are copied (plus `shots.json` when `shots` is true); anything else in the folder stays behind.

**The start is resolved by the pipeline, not the game.** In order: a landmark with `start: true` (the rider
15 m uphill of it, facing through it: today's `landmarkStart` maths, `START_BACK = 15`, label
`Starts at <name>`), else `start.json`, else what `build_pack.py` wrote from `start_run`. The result
goes in `meta.start` as `{x, y, heading (radians, as now), run?, label?}`. The game drops `landmarkStart`
and reads `meta.start` and `meta.start.label` (its label fallback `Starts on <run>` stays). The report's start
check then checks the start players actually get, which today it does not.

### The content step (no rebuild, no new stamp)

`pipeline/pack_content.py <slug> <pack_dir>` (and a function `apply(slug, pack_dir)`):

1. copy `landmarks.json` and the listed `attract/` files from `resorts/<slug>/` into the pack (removing the
   pack's old `attract/` first, so a dropped take does not linger);
2. resolve the start into `meta.start`;
3. set `formatVersion` to 2 when the pack is on 1 or 2 (format 2 is format 1 plus these files, so a format 1
   pack becomes a valid format 2 pack); a format 0 pack is left alone (it needs a real rebuild);
4. `write_meta(..., stamp=False)`: `meta.build` does not change, so a still rendered from this build stays valid.

`build_pack.py` calls `apply` at its end, so a pack that says format 2 always has the files. `build_resort.py`
gains a `content` stage after `build`, before `index` and `report`; its fingerprint is the content files
(`attract/`, `landmarks.json`, `start.json`) and the pack's `meta.build`. A content-only change (a new shot)
reruns only `content`, `index` and `report`.

**Upgrading the published packs is `pack_content.py` on its own, not `build_resort.py`** (*builder's call*,
from the builder check): `build_resort.py`'s build fingerprint includes the pipeline's code and
`build_present` wants `formatVersion == FORMAT_VERSION`, so after this PR it would rebuild every pack's
terrain. The packs to upgrade are the published ones, exactly as released (`vail-v1`, `breckenridge-v1`,
`bigsky-v1`, `boston-mills-v2`): the main checkout's `packs/vail`, `breckenridge`, `bigsky` are older
format 0 builds, not what players have. Each published zip is unpacked into the main checkout's
`packs/<slug>/` (Drew confirms before the stale copies there are replaced), `pack_content.py` applies the
content (the build id stays the released one), and it is published as the next version.

### The game reads the pack

- `Pack.load` (or a small `pack/content.ts`) fetches `landmarks.json` and `attract/index.json` when
  `meta.formatVersion >= 2`, else uses `[]` / `{}`. Failures read as empty.
- `AttractShots.ts`: `loadAttractShots`, `shippedStill`, `loadAttractManifest` take the pack (or its base URL)
  and read `packs/<slug>/attract/...`; the manifest is the pack's own (no slug level). The look check
  (`look.pack === meta.build`) is unchanged.
- `AttractGhosts.ts` and `game/tools/ghost_lines/page.mjs` fetch takes from `packs/<slug>/attract/`.
- `Landmarks` and `ResortMap` take the list from the pack. `LANDMARKS`, `STARTS` and `landmarkStart` go.
- `game/public/attract/` and `docs/compare/vail/` are deleted from the game repo (they arrive here in the same
  pair of PRs; the commit here names the game commit they came from).

### The authoring tools save here

*Builder's call, from the builder check:* the menu still is valid only for the pack build it was rendered
from, so authoring happens against the build that gets published: the game's `packs/<slug>` is that build,
either downloaded (`npm run get <slug>`) or copied from this repo (`npm run get <slug> -- --from <pack dir>`,
FEAT-242; FEAT-242 replaces junctions with copies). The dual write below keeps the two copies' content the
same; `pack_report.py` line 17 warns when the still's `look.pack` is not the pack's `meta.build`, so a still
rendered against another build shows up before publishing.

The game finds this repo at `../MapPacker-SnowboardAnywhere` next to its checkout, or `SBA_PACKER_REPO`
(the mirror of `SBA_GAME_REPO`). `game/tools/attract_files.mjs` (shared by the dev server's `/__attract/shot`,
`/__attract/save` and `ghost_lines.mjs`) writes each file and index change to **both**
`<packer>/resorts/<slug>/attract/` (the home, to commit) and `<game>/packs/<slug>/attract/` (so the running
game shows it now). `shoot_attract.mjs` does the same for the still and its look. The dev server's
`/__compare/save`, `shoot_spots.mjs`, `tools/gmaps2game.py` and `?spot=` use `<packer>/resorts/<slug>/compare/`.
With no MapPacker checkout, the save says so in the toast and falls back to the browser download it already
has for a hosted build. Messages that say "commit game/public/attract/..." say the new path.

**Look key:** `attract_look.mjs`'s code half still hashes the game's LOOK files; the resort part hashes the
pack's `attract/shots.json` and `landmarks.json` (the landmark is in the shot) from the served pack, instead of
`game/public/attract/<slug>/shots.json`. Its CI check (`checks.yml` > repo-rules) can no longer list stills (CI
has no Vail pack): when a PR changes a LOOK file it prints one warning, "re-render the menu stills
(`shoot_attract.mjs <slug>`) for the resorts on main", still never a failure. The synthetic pack's menu still
in CI renders into `packs/synth/attract/`.

### Resort picker and favorites (game only)

- `resorts.ts`: `RESORTS` goes. Names come from `packs/index.json` (always written by `packwriter.index_packs`
  and `get_pack.mjs`); a slug without a name shows the slug. No index: no built resorts (the probe goes with
  the table). The synthetic mountain is always last.
- Settings gain `favoriteResorts: string[]`, saved with the rest.
- The picker shows one list: favorites first, alphabetical; then the rest, alphabetical; synthetic last.
  Built, downloaded-from-catalog and downloadable rows mix in that order; each keeps its note ("here now",
  "needs rebuild", "Update (...)", "Download (...)"). A favorite that is not downloaded still sits on top.
- A star at the right of each row toggles it (the row becomes a container with two buttons, since a button
  cannot hold a button); F on the keyboard and Y on a controller (FEAT-137 pad nav) toggle the focused row.
- Default pack with no `?pack` and no last pack: the first built resort in this order (a favorite if any),
  else the synthetic mountain. (Was: the first in `RESORTS`, Vail.)

### `pack_report.py`

- 10 start: checks `meta.start` (now the real one).
- 11 picker: drops the `resorts.ts` lookup (index and catalog only).
- 17 menu shot and ghosts: the pack's `attract/index.json` has `shots` and at least one ghost; warn when the
  first shot's still is missing or its `look.pack` is not `meta.build`.
- 18 landmark: the pack's `landmarks.json` is non-empty (statuses as today).
- 19 compare spots and the tree measure near them: `resorts/<slug>/compare/*/spot.json`.
- The game checkout is no longer read for 11, 17, 18, 19; the docstring and CLAUDE.md say so.
  `canopy_spots.py` reads `resorts/<slug>/compare/` too.

### Spec and contract

- `FORMAT_VERSION = 2` here, `PACK_FORMAT = 2` in the game. `docs/pack-format.md`: the tree listing, a
  `landmarks.json` and `attract/` section (shapes: `Landmark` and `AttractShot` as in the game's
  `world/Landmarks.ts` and `world/AttractShots.ts`, and the manifest), `meta.start.label`, a format 2 row in the
  table ("format 1 plus landmarks.json, attract/, resolved start; a format 1 pack upgrades with `pack_content.py`").
- A contract line for the landmarks and attract shapes (writer: `pack_content.py`; reader: the two game files).
  `contract.py` checks what it can parse (at least that the game reads `landmarks.json` and `attract/index.json`).
- `synth_pack.py` writes format 2 with `[]` / `{}` (the synthetic pack's CI still goes in its `attract/`).

## Order of work

As the card says, after FEAT-241 (SnowboardAnywhere#570) and FEAT-242 (#571): the game PR is cut from the
game's `main` once they merge (from #571's branch if they are still open), so it has no `pipeline/` copy to
keep in step and its CI downloads the synthetic pack for its own `PACK_FORMAT` from the catalog's `test` list.

1. Game PR (branch per the game's BOARD.md, `Fixes drewkeriazes/MapPacker-SnowboardAnywhere#13`): the reader,
   the picker, the tools' new save path, `PACK_FORMAT = 2`, tests. It keeps loading format 1 packs.
2. MapPacker PR (`issue-13-pack-content`): the moved files, `pack_content.py`, the `content` stage, the report,
   the spec, `FORMAT_VERSION = 2`, `synth_pack.py` on format 2, tests. `test_contract.py` passes against the
   game PR's checkout (`SBA_GAME_REPO=<game worktree>`).
3. Merging, "together" in the bump rule's sense (*builder's call*): the game PR's CI cannot go green until a
   format 2 synthetic pack is published, and that is published from this repo's `main`. So: merge the MapPacker
   PR, `publish_pack.py --synth` on `main` (the format 1 synth stays in the `test` list for the game's `main`),
   re-run the game PR's checks, merge it. In between, this repo's contract test against the game's `main` is
   red for those minutes, and no resort is published on format 2 (the game's `main` would call it
   "needs a newer game").
4. Right after: upgrade and republish all four published resorts, **Boston Mills included** (it is published on
   format 1 and would otherwise show "needs rebuild" once the game is on 2): unpack each released zip,
   `pack_content.py`, re-render Vail's and Breckenridge's menu stills with `shoot_attract.mjs` against the
   upgraded pack (their recorded `look.pack` matches no published build today, so they don't show now either),
   the report, a headless ride, Drew rides Vail and Breck on his GPU (menu shot, still, ghosts, gateway, start),
   then `publish_pack.py` for each in the main checkout. Publishing is Drew's go. Until this step is done the
   game's `main` shows the published resorts as "needs rebuild"; it is minutes of work, not a rebuild.

## Checks

- Here: `python -m pytest pipeline/tests`; new tests for `pack_content.apply` (copy only listed files, start
  resolution order with the landmark maths, format 1 to 2 and not 0, `meta.build` unchanged), the `content`
  stage's skipping, and the report lines on a pack with and without content.
- Game: its unit tests for the picker order (favorites, alphabetical, synthetic last), the content load with
  format 1 and 2 packs, and the start label; the game's CI; a render of Vail's menu on Drew's GPU (the PR says so).

## Left to the builder

- Whether the game's content fetch lives in `Pack.load` or a separate loader, and the exact function signatures.
- Test file layout and names in both repos.
- The wording of toasts, warnings and the report's lines, in the repos' plain style.
- How `ghost_lines.mjs`'s trial runs (which write nowhere permanent today) pick their output.
