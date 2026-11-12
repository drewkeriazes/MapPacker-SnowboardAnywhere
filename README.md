# MapPacker-SnowboardAnywhere

Resort data for [SnowboardAnywhere](https://github.com/drewkeriazes/SnowboardAnywhere): the recipe each resort pack is built from, the catalog of published packs, and the packs themselves as release assets.

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

## What is here

| Path | What |
|---|---|
| `catalog.json` | Every published pack: slug, name, region, tier, status, and the release zip's version, pack format, size, sha256 and URL |
| `resorts/<slug>.json` | The resort config the pack was built from, plus its EPT node lists |
| `manifests/<slug>.json` | The download manifest the raw data was fetched with |
| `reports/<slug>.md` | The build report, when there is one |
| Releases `<slug>-v<N>` | `<slug>.zip` (the pack, stored), its `meta.json`, and the report |

Packs live in releases, never in git history: a pack is 150 to 250 MB per build, and releases can be deleted when a build is replaced. Everything here is written by `pipeline/publish_pack.py` in the game repo; edit the configs there, not here (these are copies for now). That changes with EPIC-16 (#9): the pipeline moves here and the game repo just plays packs. Plan: [`docs/pipeline-move.md`](docs/pipeline-move.md).

`status` is `playable` when every DATA-022 check passes in the build report, else `preview`. `formatVersion` is the pack format; a game reads only its own format and shows an older pack as "needs rebuild".

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
