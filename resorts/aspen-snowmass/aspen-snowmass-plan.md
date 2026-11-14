# Aspen Snowmass: data plan

Planned 2026-11-14 by `pipeline/resort.py plan aspen-snowmass` (FEAT-223). EPSG:26913 (13N), origin 331600, 4339200. Ski area 8.8 km across, buffer 1000 m, box 8.4 x 8.2 km, elevation 2403 to 4004 m (Mapterhorn z12).

**Tier: silver** (held there by: trees)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: CO_CONMGaps_D24, CO_SanLuisJuanMiguel_2020_D20, CO_WestCentral_2019_A19 (100% of the box) |  | 1 m | 36 | 291 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 210 | 22 MB |  |
| Lidar | EPT CO_SanLuisJuanMiguel_2_2020 (39% of the box, QL 2, 6.7 pts/m2) | 2019-09 to 2019-10, leaf-on | depth 9: 2.0 m | 298, 11 M points | 95 MB | silver |
| Lidar, far tree ring | same, 5000 m round the box | | depth 8: 4.0 m | 889 | 270 MB | |
| Imagery | Planetary Computer naip 2023 30cm | 2023 | 1 m | 16 | 164 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 8 | 1,492 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/colorado) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (CO), Census towns |  |  | 3 | 10 MB |  |
| Grooming | none | | | | | |

Total about **2,429 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Left out

- Buttermilk: 59 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py aspen-snowmass`, then `pipeline/fetch.ps1 -Slug aspen-snowmass -RawDir <dir>` on Drew's PC.
