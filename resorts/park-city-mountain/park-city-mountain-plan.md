# Park City Mountain: data plan

Planned 2026-11-12 by `pipeline/resort.py plan park-city-mountain` (FEAT-223). EPSG:26912 (12N), origin 453600, 4500500. Ski area 13.3 km across, buffer 1000 m, box 10.8 x 12.2 km, elevation 1952 to 3174 m (Mapterhorn z12).

**Tier: silver** (held there by: trees)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: NV_USFSR4_D23, UT_Central_QL1_B1_2018, UT_FEMAHQ_2018_D18, UT_StatewideNCentral_2020_A20 (100% of the box) |  | 1 m | 72 | 556 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 225 | 24 MB |  |
| Lidar | EPT USGS_LPC_UT_Central_QL1_B1_2018_LAS_2019 (84% of the box, QL 1, 14.9 pts/m2) | 2018-08 to 2018-08, leaf-on | depth 9: 2.8 m | 1144, 42 M points | 373 MB | silver |
| Lidar (extra) | EPT NV_USFSR4_2_D23 (10% of the box, QL 1, 16.9 pts/m2) | 2023-08 to 2023-09, leaf-on | depth 9: 1.6 m | 3106, 156 M points | 1,372 MB |  |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 2.8 m | 1184 | 335 MB | |
| Imagery | Planetary Computer naip 2021 60cm | 2021 | 1 m | 20 | 301 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/utah) |  |  | 5 | 19 MB |  |
| Grooming | https://www.parkcitymountain.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx | | | | | |

Total about **3,793 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Left out

- Brighton Resort: 99 run and lift ways by OSM id
- Solitude Mountain Resort: 72 run and lift ways by OSM id
- Deer Valley Resort: 421 run and lift ways by OSM id
- Utah Olympic Park: 20 run and lift ways by OSM id
- Alta Ski Area: 150 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py park-city-mountain`, then `pipeline/fetch.ps1 -Slug park-city-mountain -RawDir <dir>` on Drew's PC.
