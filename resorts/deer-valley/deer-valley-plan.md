# Deer Valley: data plan

Planned 2026-11-14 by `pipeline/resort.py plan deer-valley` (FEAT-223). EPSG:26912 (12N), origin 459200, 4495750. Ski area 10.5 km across, buffer 1000 m, box 10.0 x 9.1 km, elevation 1756 to 3067 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: NV_USFSR4_D23, UT_Central_QL1_B1_2018, UT_FEMAHQ_2018_D18, UT_StatewideNCentral_2020_A20 (100% of the box) |  | 1 m | 49 | 384 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 210 | 22 MB |  |
| Lidar | EPT USGS_LPC_UT_FEMAHQ_B2_QL1_2018_LAS_2019 (92% of the box, QL 1, 13.8 pts/m2) | 2018-04 to 2018-10, mixed | depth 7: 2.6 m | 932, 36 M points | 316 MB | gold |
| Lidar (extra) | EPT USGS_LPC_UT_Central_QL1_B1_2018_LAS_2019 (8% of the box, QL 1, 14.9 pts/m2) | 2018-08 to 2018-08, leaf-on | depth 9: 2.8 m | 128, 4 M points | 38 MB |  |
| Lidar, far tree ring | same, 5000 m round the box | | depth 7: 2.6 m | 2729 | 718 MB | |
| Imagery | Planetary Computer naip 2021 60cm | 2021 | 1 m | 12 | 203 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/utah) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (UT, WY), Census towns |  |  | 4 | 11 MB |  |
| Grooming | none | | | | | |

Total about **2,525 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- USGS_LPC_UT_FEMAHQ_B2_QL1_2018_LAS_2019 was flown 2018-04 to 2018-10, across seasons: deciduous crowns may read low where it was flown leaf-off
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Left out

- Park City Mountain Resort: 507 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py deer-valley`, then `pipeline/fetch.ps1 -Slug deer-valley -RawDir <dir>` on Drew's PC.
