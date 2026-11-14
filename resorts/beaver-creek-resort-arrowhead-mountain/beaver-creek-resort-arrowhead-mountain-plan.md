# Beaver Creek Resort (Arrowhead Mountain): data plan

Planned 2026-11-14 by `pipeline/resort.py plan beaver-creek-resort-arrowhead-mountain` (FEAT-223). EPSG:26913 (13N), origin 368600, 4384450. Ski area 9.6 km across, buffer 1000 m, box 8.0 x 9.7 km, elevation 2211 to 3630 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: CO_Central_Western_2016 (100% of the box) |  | 1 m | 42 | 327 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 210 | 22 MB |  |
| Lidar | EPT USGS_LPC_CO_Central_Western_2016_LAS_2018 (100% of the box, QL 2, 6.1 pts/m2) | 2016-05 to 2016-10, leaf-on | depth 9: 2.9 m | 232, 29 M points | 255 MB | gold |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 2.9 m | 1057 | 1,435 MB | |
| Imagery | Planetary Computer naip 2023 30cm | 2023 | 1 m | 16 | 206 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/colorado) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (CO), Census towns |  |  | 3 | 10 MB |  |
| Grooming | https://www.beavercreek.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx | | | | | |

Total about **3,086 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py beaver-creek-resort-arrowhead-mountain`, then `pipeline/fetch.ps1 -Slug beaver-creek-resort-arrowhead-mountain -RawDir <dir>` on Drew's PC.
