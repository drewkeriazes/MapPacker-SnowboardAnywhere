# Killington: data plan

Planned 2026-11-14 by `pipeline/resort.py plan killington` (FEAT-223). EPSG:26918 (18N), origin 678650, 4831050. Ski area 7.4 km across, buffer 1000 m, box 7.9 x 6.7 km, elevation 308 to 1287 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: VT_Connecticut_River_2016, VT_Rutland-Lot8_2013, VT_Statewide_A23 (100% of the box) |  | 1 m | 30 | 223 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 240 | 25 MB |  |
| Lidar | EPT USGS_LPC_VT_Rutland_Lot8_2013_LAS_2016 (100% of the box, QL 2, 8.4 pts/m2) | 2013-11 to 2015-11, mixed | depth 7: 2.7 m | 204, 31 M points | 270 MB | gold |
| Lidar, far tree ring | same, 5000 m round the box | | depth 7: 2.7 m | 741 | 1,453 MB | |
| Imagery | Planetary Computer naip 2023 30cm | 2023 | 1 m | 12 | 139 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/vermont) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (VT, MA, NH, NY), Census towns |  |  | 6 | 14 MB |  |
| Grooming | none | | | | | |

Total about **2,957 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- USGS_LPC_VT_Rutland_Lot8_2013_LAS_2016 was flown 2013-11 to 2015-11, across seasons: deciduous crowns may read low where it was flown leaf-off
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Left out

- Pico Mountain Resort: 88 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py killington`, then `pipeline/fetch.ps1 -Slug killington -RawDir <dir>` on Drew's PC.
