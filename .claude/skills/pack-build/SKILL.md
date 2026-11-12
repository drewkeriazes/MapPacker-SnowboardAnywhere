---
name: pack-build
description: Build or rebuild a resort pack (packs/<slug>/) from raw downloads with pipeline/build_pack.py, validate each stage's output, and fix the usual failures. Use when the user asks to build, rebuild, validate or debug a pack, or when the game shows wrong terrain, trees or masks for a resort.
---

# Build a resort pack

## Where things are (MapPacker-SnowboardAnywhere, FEAT-238)
- Configs, EPT node lists and data plans: `resorts/<slug>/` (a folder per resort); download manifests: `manifests/`; packs: `packs/<slug>/` (gitignored).
- Raw data: `SBA_RAW_ROOT`, else `raw/` in the main checkout (worktrees share it). On Drew's PC it stays in the game's clone until it is moved: `SBA_RAW_ROOT=C:\Users\Drew\git\SnowboardAnywhere\raw`.
- The game is a sibling clone, `..\SnowboardAnywhere` (`--game-repo` or `SBA_GAME_REPO` overrides). Only the ride stage and `pack_report.py`'s game-side lines (11's `resorts.ts`, 17 to 19) read it; the contract tests (`tests/test_contract.py`) read the game's `main` on GitHub instead, or `SBA_GAME_REPO`. To look at a pack in the game, run `npm run get -- --from <this checkout>/packs/<slug>` in the game's `game/` (it copies the pack in), or publish it and run `npm run get <slug>` there. Never junction a pack into a game worktree: `git worktree remove` empties the target.
- Usually you want `build_resort.cmd <slug>` (every stage, each skipped when done) or `add_resort.cmd "<name>"` (from a name to a published pack). The direct call below is for debugging one build.

## Run
```
pip install -r pipeline/requirements.txt
python pipeline/build_pack.py <slug> <raw_dir> packs/<slug>
# Vail on Drew's PC:
python pipeline/build_pack.py vail %SBA_RAW_ROOT%\vail packs\vail
```
`raw_dir` is the folder that directly contains `dem1m/`, `ept/`, `osm/` etc. (manifest paths carry no slug prefix). Run from PowerShell or cmd, or quote `packs\vail` in Git Bash, where the unquoted backslash is eaten and the pack lands in an untracked `packsvail/`. The script reads `resorts/<slug>/<slug>.json` and `manifests/<slug>.json` for chunk bboxes, so the manifest must be the one the data was fetched with. Needs about 6 GB RAM for Vail (11,600 x 11,700 1 m grid). Stages print `[  123s] name` lines; a full run is 5 to 15 minutes.

## Stage checks (do these before loading the pack in the game)
1. DEM: log line `dem (H, W), void x%` with void under 1%, range roughly 2400..3600 m for Vail. `packs/<slug>/fine/` should have ~24 x 23 PNG tiles of 200 to 500 KB each. Decode one with `python -c` using `pipeline/packwriter.decode_terrarium` and confirm heights are plausible at a known spot (Vail Village base about 2,475 m; Vail summit about 3,433 m).
2. Mid and far: `mid/` 5 x 5 tiles at 16 m covering 40 km, `far/` 4 x 4 tiles at 128 m covering 262 km, far coverage above 95%.
3. Lidar: `N M points`, `cells with data` above 70%, `CHM: x% of cells > 2 m` between 20% and 60% for Vail. If 0%, the EPT to UTM transform is wrong (EPT is EPSG:3857, see `docs/research/vegetation-and-landcover.md`).
4. NAIP: coverage above 95%; canopy 20% to 50%; rock 2% to 10%. The crops are 2048 px (about 2 m), handled by the script.
5. OSM: runs ~350, lifts ~33, buildings ~2,000 to 4,000, peaks a few hundred. Zero runs means `<raw root>/<slug>/osm/ski.json` is missing or is an Overpass error page.
6. Masks: `mask/` tiles 12 x 12 at 2 m. Open one as an image: blue = groomed corridors should follow pistes, alpha = canopy should show the trail cuts.
7. Trees: `treeCount` in `meta.json` between 500k and 3M for Vail; `trees/*.bin` sizes are 24 bytes per tree. Krummholz only above ~3,350 m, aspen only below ~3,150 m.
8. `meta.json`: `start` should be the top of a named chair lift; `bounds` match `resorts/<slug>/<slug>.json` `pack_bbox` (else `utm_bbox`) minus origin.

## Moved areas (FEAT-249)
A resort split across far-apart areas (Boston Mills / Brandywine) can paste the far one next to the rest so the box is just the rideable area: the config's `relocate` list (`from` box, `to` centre, `turn_deg` clockwise, `feather_m` seam) and `pack_bbox`, the box the pack is built on; `utm_bbox` stays the fetched box, so no new download. `python pipeline/relocate.py <slug>` prints the pack box from the runs and lifts after the move (300 m buffer at least for a small hill, grown until every pasted patch is inside it); `--write` puts it in the config. The build logs `relocate <name>: ... height shift` (the median step between the ground there and the patch over the seam's outer half) and how many OSM elements moved. Check the seam on a hillshade of the composed `fine/` heights: it should run through woods, away from the runs. Where the destination's ground doesn't match the patch's rim (a valley floor pasted onto a terrace walls it in as a pit), try another `to` or `turn_deg`, or a wider `feather_m` with a bigger `from` box.

## Quick visual validation
Render a top-down check image: decode `fine/` heights into one array, hillshade with numpy, overlay `mask/` alpha (canopy) and blue (groomed), draw `features.json` runs and lift lines, save PNG, compare against the official trail map. Trail cuts in the canopy must line up with the run polylines within about 5 m.

## Common failures
- `tifffile` reads a NAIP crop as (H, W, 5): band 5 is the mask; the script keeps bands 1 to 4.
- Memory error in the DEM stage: process is holding `dem` (float32 1 m) plus `naip2`; drop `naip2` early or run on a machine with more RAM.
- laspy `LazBackend` error: `pip install lazrs`.
- Pack loads but terrain is flat at 2,300 m: tiles are missing (404) because `fine.minX/minY` in meta does not match the tile grid; regenerate rather than hand-editing meta.
- Game shows trees floating or buried: tree `z` must come from the same DEM the terrain uses (`dem2` in the script), not the lidar ground returns.
