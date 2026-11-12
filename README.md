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
add_resort.cmd "Boston Mills"     :: name to published pack: resolve, plan, fetch, build, report, ride, publish
build_resort.cmd vail             :: config to scored pack in packs\vail (no ride, no publish)
python pipeline\resort.py add --help
```

Every stage is skipped when its inputs have not changed, so both are safe to re-run. The first `add_resort.cmd` run for a new resort stops after the data plan (`resorts/<slug>/<slug>-plan.md`) so it can be read before a 1+ GB fetch.

- **Raw data** goes to `SBA_RAW_ROOT`, else `raw\` in the main checkout (worktrees share it). It is gitignored and never committed. On Drew's PC `SBA_RAW_ROOT` points at the raw data still in the game's clone, `C:\Users\Drew\git\SnowboardAnywhere\raw`, until it is moved here.
- **The game** must be cloned next to this repo (`..\SnowboardAnywhere`) for the headless ride, the game-side lines of the build report and a few tests. `--game-repo <path>` or `SBA_GAME_REPO` points elsewhere; without it those parts say so and stop or skip.
- **Publishing** (`pipeline\publish_pack.py`, the last stage of `add_resort.cmd`) runs in the main checkout on `main`: it makes the release `<slug>-v<N>` and commits `catalog.json` with the resort's config, node lists, plan, manifest and report straight to `main`.
- **To ride a pack before publishing it**, copy `packs\<slug>` into the game's `packs\`.

More in the `pack-build` skill (`.claude/skills/pack-build/SKILL.md`) and the notes in `CLAUDE.md`.

## What is here

| Path | What |
|---|---|
| `catalog.json` | Every published pack: slug, name, region, tier, status, and the release zip's version, pack format, size, sha256, URL and the pipeline commit that built it |
| `pipeline/` | The pipeline: `resort.py` (name to config and data plan, and `add`), `build_resort.py`, `build_pack.py` and its stages, `pack_report.py`, `publish_pack.py`, the fetch scripts, tests in `pipeline/tests/`. Moved from the game repo with its history (FEAT-238) |
| `docs/pack-format.md` | The pack format: the layout, the encodings, `formatVersion` and its bump rule, and the Contract, every value this repo and the game must agree on (FEAT-239) |
| `resorts/<slug>/` | A folder per resort: `<slug>.json`, the config the pipeline reads, the EPT node lists it names (`nodes_file`, beside it) and the data plan (`<slug>-plan.md`) |
| `manifests/<slug>.json` | The download manifest the raw data was fetched with |
| `reports/<slug>.md` | The build report of the published pack |
| `*.cmd` | Launchers for Drew's PC (above) |
| Releases `<slug>-v<N>` | `<slug>.zip` (the pack, stored), its `meta.json`, and the report |

Packs live in releases, never in git history: a pack is 50 to 250 MB per build, and releases can be deleted when a build is replaced. A catalog entry's `pipeline` is the commit of this repo that built the pack; entries published before the pipeline moved here (FEAT-238) name a SnowboardAnywhere commit instead.

`status` is `playable` when every DATA-022 check passes in the build report, else `preview`. `formatVersion` is the pack format; a game reads only its own format and shows an older pack as "needs rebuild". A format change goes into the game first or together ([`docs/pack-format.md`](docs/pack-format.md) > formatVersion); `python pipeline/contract.py` compares this pipeline with the game's `main`.

## Data sources and licences

The packs are built from these sources. OpenStreetMap-derived parts of a pack (`features.json`: runs, lifts, buildings, roads, water, names; the groomed-run and run-direction masks) are a derivative of OpenStreetMap and are available under the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). The rest is public domain or CC BY 4.0 as listed.

- Elevation and lidar: U.S. Geological Survey 3D Elevation Program (public domain)
- Terrain tiles: Mapterhorn, built from USGS 3DEP
- Imagery: USDA NAIP via Microsoft Planetary Computer (public domain)
- Vegetation type, cover and height: LANDFIRE, USGS and U.S. Forest Service (public domain)
- Geographic names: USGS GNIS (public domain)
- Map data © OpenStreetMap contributors, ODbL; ski area data: OpenSkiMap.org
- Land cover: © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium (CC BY 4.0)
- Canopy height: Lang, Jetz, Schindler, Wegner, "A high-resolution canopy height model of the Earth", Nature Ecology & Evolution 7, 1778-1789 (2023), ETH Global Sentinel-2 10 m Canopy Height 2020 (CC BY 4.0)

Each pack's own list is in its `meta.json` (`attribution`). Resort names are used as facts; no resort trademarks or trail map artwork are included.
