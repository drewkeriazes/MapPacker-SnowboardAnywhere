# Jackson Hole Mountain: data plan

Planned 2026-11-14 by `pipeline/resort.py plan jackson-hole-mountain` (FEAT-223). EPSG:26912 (12N), origin 512150, 4826950. Ski area 5.7 km across, buffer 1000 m, box 6.5 x 5.7 km, elevation 1908 to 3266 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: WY_GrandTetonElkRefuge_2014, WY_GrandTetonNP_D22, WY_North_Converse_2020_D20 (100% of the box) |  | 1 m | 20 | 156 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 225 | 24 MB |  |
| Lidar | EPT WY_NConverse_5_2020 (93% of the box, QL 1, 25.8 pts/m2) | 2021-05 to 2021-06, leaf-on | depth 8: 2.3 m | 449, 15 M points | 132 MB | gold |
| Lidar (extra) | EPT USGS_LPC_WY_GrandTetonElkRefuge_2014_LAS_2016 (7% of the box, QL 2, 5.2 pts/m2) | 2014-08 to 2014-09, leaf-on | depth 7: 2.2 m | 59, 5 M points | 48 MB |  |
| Lidar, far tree ring | same, 5000 m round the box | | depth 8: 2.3 m | 2217 | 693 MB | |
| Imagery | Planetary Computer naip 2022 60cm | 2022 | 1 m | 8 | 86 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/wyoming) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (WY, ID, MT), Census towns |  |  | 5 | 13 MB |  |
| Grooming | none | | | | | |

Total about **1,984 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py jackson-hole-mountain`, then `pipeline/fetch.ps1 -Slug jackson-hole-mountain -RawDir <dir>` on Drew's PC.
