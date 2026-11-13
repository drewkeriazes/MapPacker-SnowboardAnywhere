# Heavenly Mountain: data plan

Planned 2026-11-13 by `pipeline/resort.py plan heavenly` (FEAT-223). EPSG:26911 (11N), origin 247600, 4314200. Ski area 8.5 km across, buffer 1000 m, box 7.8 x 8.4 km, elevation 1761 to 3065 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: CA_SierraNevada_B22, NV_Reno_Carson_QL1_2017, NV_USFSR4_D23, NV_WestCentral_EarthMRI_2020_D20 (100% of the box) |  | 1 m | 36 | 276 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 196 | 21 MB |  |
| Lidar | EPT CA_SierraNevada_8_2022 (87% of the box, QL 1, 25.1 pts/m2) | 2021-11 to 2022-08, mixed | depth 10: 1.7 m | 1264, 58 M points | 512 MB | gold |
| Lidar (extra) | EPT NV_WestCentralEarthMRI_3_2020 (13% of the box, QL 2, 5.3 pts/m2) | 2020-10 to 2020-11, mixed | depth 9: 2.4 m | 278, 11 M points | 99 MB |  |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 3.4 m | 1767 | 591 MB | |
| Imagery | Planetary Computer naip 2024 60cm (5 quarter quads from 2022 where 2024 has none) | 2024, 2022 | 1 m | 26 | 286 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 8 | 1,492 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/nevada) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (NV, CA), Census towns |  |  | 4 | 11 MB |  |
| Grooming | https://www.skiheavenly.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx | | | | | |

Total about **3,374 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- CA_SierraNevada_8_2022 was flown 2021-11 to 2022-08, across seasons: deciduous crowns may read low where it was flown leaf-off
- NV_WestCentralEarthMRI_3_2020 was flown 2020-10 to 2020-11, across seasons: deciduous crowns may read low where it was flown leaf-off

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py heavenly`, then `pipeline/fetch.ps1 -Slug heavenly -RawDir <dir>` on Drew's PC.
