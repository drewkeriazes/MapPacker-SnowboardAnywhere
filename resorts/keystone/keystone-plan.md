# Keystone: data plan

Planned 2026-11-13 by `pipeline/resort.py plan keystone` (FEAT-223). EPSG:26913 (13N), origin 419850, 4380700. Ski area 9.3 km across, buffer 1000 m, box 7.3 x 9.8 km, elevation 2804 to 3844 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: CO_ArapahoRooseveltPikeNF_D23, CO_Central_Western_2016, CO_DRCOG_2020_B20, CO_ParkFremontCuster_2018_C21 (100% of the box) |  | 1 m | 35 | 302 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 210 | 22 MB |  |
| Lidar | EPT USGS_LPC_CO_Central_Western_2016_LAS_2018 (100% of the box, QL 2, 6.1 pts/m2) | 2016-05 to 2016-10, leaf-on | depth 9: 2.9 m | 261, 33 M points | 286 MB | gold |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 2.9 m | 985 | 1,117 MB | |
| Imagery | Planetary Computer naip 2023 30cm | 2023 | 1 m | 12 | 166 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 8 | 1,492 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/colorado) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (CO), Census towns |  |  | 3 | 10 MB |  |
| Grooming | https://www.keystoneresort.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx | | | | | |

Total about **3,480 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Left out

- Arapahoe Basin: 124 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py keystone`, then `pipeline/fetch.ps1 -Slug keystone -RawDir <dir>` on Drew's PC.
