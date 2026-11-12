# Mad River Mountain: data plan

Planned 2026-11-12 by `pipeline/resort.py plan mad-river-mountain` (FEAT-223). EPSG:26917 (17N), origin 272600, 4466250. Ski area 1.4 km across, buffer 500 m, box 2.2 x 2.1 km, elevation 345 to 448 m (Mapterhorn z12).

**Tier: gold**

**Source only (FEAT-268).** This config is a relocate source for the Ohio Hills pack (`resorts/ohio-hills/`), not a pack of its own: `"source_only": true` stops `build_resort.py` after the data stages, and `build_pack.py` and `publish_pack.py` refuse it. The plan below is as `resort.py plan` wrote it; the config then drops the far tree ring (`lidar.far`, 790 MB) and the far land cover (`landcover.enabled: false`, 746 MB), which a patch pasted into another pack never uses, and keeps the lidar at depth 7 over the whole box (2.5 m, close to Boston Mills' 2.2 m). Fetch: `python pipeline/build_resort.py mad-river-mountain --stop-after landfire`.

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: OH_Statewide_Phase3_2021_B21 (100% of the box) |  | 1 m | 4 | 19 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 196 | 21 MB |  |
| Lidar | EPT OH_StatewideP3_4_B21 (100% of the box, QL 1, 11.4 pts/m2) | 2022-04 to 2022-04, leaf-off | depth 7: 2.5 m | 65, 2 M points | 16 MB | gold |
| Lidar, far tree ring | same, 5000 m round the box | | depth 7: 2.5 m | 2702 | 790 MB | |
| Imagery | Planetary Computer naip 2023 30cm | 2023 | 1 m | 4 | 12 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/ohio) |  |  | 5 | 19 MB |  |
| Grooming | none | | | | | |

Total about **1,691 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- OH_StatewideP3_4_B21 was flown 2022-04 to 2022-04 (leaf-off): deciduous crowns read low and sparse; compare crown count against NAIP canopy
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py mad-river-mountain`, then `pipeline/fetch.ps1 -Slug mad-river-mountain -RawDir <dir>` on Drew's PC.
