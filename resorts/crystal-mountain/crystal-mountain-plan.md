# Crystal Mountain: data plan

Planned 2026-11-13 by `pipeline/resort.py plan crystal-mountain` (FEAT-223). EPSG:26910 (10N), origin 615100, 5198800. Ski area 6.3 km across, buffer 1000 m, box 5.4 x 7.4 km, elevation 914 to 2132 m (Mapterhorn z12).

**Tier: silver** (held there by: trees)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: WA_EasternCascades_2019_B19 (100% of the box) |  | 1 m | 20 | 169 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 256 | 27 MB |  |
| Lidar | EPT WA_EasternCascades_5_2019 (42% of the box, QL 1, 16.7 pts/m2) | 2019-11 to 2020-08, mixed | depth 9: 1.8 m | 200, 7 M points | 60 MB | silver |
| Lidar, far tree ring | same, 5000 m round the box | | depth 8: 3.6 m | 1100 | 522 MB | |
| Imagery | Planetary Computer naip 2023 60cm | 2023 | 1 m | 6 | 91 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 2 | 373 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/washington) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (WA, OR), Census towns |  |  | 4 | 11 MB |  |
| Grooming | none | | | | | |

Total about **1,339 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- WA_EasternCascades_5_2019 was flown 2019-11 to 2020-08, across seasons: deciduous crowns may read low where it was flown leaf-off
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py crystal-mountain`, then `pipeline/fetch.ps1 -Slug crystal-mountain -RawDir <dir>` on Drew's PC.
