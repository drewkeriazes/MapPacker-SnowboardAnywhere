# Copper Mountain: data plan

Planned 2026-11-13 by `pipeline/resort.py plan copper-mountain` (FEAT-223). EPSG:26913 (13N), origin 400000, 4370100. Ski area 7.5 km across, buffer 1000 m, box 6.8 x 8.0 km, elevation 2948 to 4026 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: CO_Central_Western_2016, CO_ParkFremontCuster_2018_C21, CO_SanLuisJuanMiguel_2020_D20 (100% of the box) |  | 1 m | 30 | 230 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 196 | 21 MB |  |
| Lidar | EPT USGS_LPC_CO_Central_Western_2016_LAS_2018 (100% of the box, QL 2, 6.1 pts/m2) | 2016-05 to 2016-10, leaf-on | depth 9: 2.9 m | 173, 22 M points | 191 MB | gold |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 2.9 m | 884 | 1,022 MB | |
| Imagery | Planetary Computer naip 2023 30cm | 2023 | 1 m | 16 | 139 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 8 | 1,492 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/colorado) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (CO), Census towns |  |  | 3 | 10 MB |  |
| Grooming | none | | | | | |

Total about **3,190 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py copper-mountain`, then `pipeline/fetch.ps1 -Slug copper-mountain -RawDir <dir>` on Drew's PC.
