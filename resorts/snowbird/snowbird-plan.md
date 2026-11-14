# Snowbird: data plan

Planned 2026-11-14 by `pipeline/resort.py plan snowbird` (FEAT-223). EPSG:26912 (12N), origin 444950, 4490750. Ski area 7.2 km across, buffer 1000 m, box 7.3 x 7.1 km, elevation 2239 to 3500 m (Mapterhorn z12).

**Tier: silver** (held there by: trees)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: NV_USFSR4_D23, UT_Central_QL1_B1_2018, UT_StatewideNCentral_2020_A20 (100% of the box) |  | 1 m | 25 | 219 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 196 | 21 MB |  |
| Lidar | EPT USGS_LPC_UT_Central_QL1_B1_2018_LAS_2019 (93% of the box, QL 1, 14.9 pts/m2) | 2018-08 to 2018-08, leaf-on | depth 9: 2.8 m | 505, 14 M points | 127 MB | silver |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 2.8 m | 2475 | 829 MB | |
| Imagery | Planetary Computer naip 2021 60cm | 2021 | 1 m | 12 | 124 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/utah) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (UT, WY), Census towns |  |  | 4 | 11 MB |  |
| Grooming | none | | | | | |

Total about **2,162 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Left out

- Alta Ski Area: 150 run and lift ways by OSM id
- Solitude Mountain Resort: 72 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py snowbird`, then `pipeline/fetch.ps1 -Slug snowbird -RawDir <dir>` on Drew's PC.
