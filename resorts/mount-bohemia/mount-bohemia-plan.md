# Mount Bohemia: data plan

Planned 2026-11-14 by `pipeline/resort.py plan mount-bohemia` (FEAT-223). EPSG:26916 (16N), origin 423750, 5249000. Ski area 2.6 km across, buffer 800 m, box 3.9 x 3.0 km, elevation 183 to 445 m (Mapterhorn z12).

**Tier: gold**

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | 3DEP ImageServer; 1 m tiles: MI_FEMA_2019_C19 (100% of the box) |  | 1 m | 6 | 49 MB | gold |
| Terrain, mid ring | 3DEP ImageServer |  | 10 m | 4 | 65 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 240 | 25 MB |  |
| Lidar | EPT MI_FEMA_Houghton_Keweenaw_Ontonagon_2019 (100% of the box, QL 2, 5.1 pts/m2) | 2019-05 to 2021-06, mixed | depth 9: 2.7 m | 100, 4 M points | 36 MB | gold |
| Lidar, far tree ring | same, 5000 m round the box | | depth 9: 2.7 m | 1890 | 747 MB | |
| Imagery | Planetary Computer naip 2022 60cm (1 quarter quad from 2024 where 2022 has none) | 2024, 2022 | 1 m | 2 | 25 MB | gold |
| Land cover, far terrain | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 8 | 1,492 MB |  |
| Vegetation type | LANDFIRE EVT, EVC, EVH (`fetch_landfire.mjs`) | | 30 m | | 2 MB | |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: us/michigan) |  |  | 5 | 19 MB |  |
| Place names | USGS GNIS summits (MI, WI), Census towns |  |  | 4 | 11 MB |  |
| Grooming | none | | | | | |

Total about **2,471 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- MI_FEMA_Houghton_Keweenaw_Ontonagon_2019 was flown 2019-05 to 2021-06, across seasons: deciduous crowns may read low where it was flown leaf-off
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py mount-bohemia`, then `pipeline/fetch.ps1 -Slug mount-bohemia -RawDir <dir>` on Drew's PC.
