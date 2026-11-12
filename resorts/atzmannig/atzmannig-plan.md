# Atzmännig: data plan

Planned 2026-11-12 by `pipeline/resort.py plan atzmannig` (FEAT-223). EPSG:32632 (32N), origin 500150, 5236550. Ski area 2.1 km across, buffer 600 m, box 3.1 x 2.5 km, elevation 700 to 1280 m (Mapterhorn z12).

**Tier: bronze** (held there by: surface)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | Mapterhorn z16 (finest there z17: swissALTI3D) |  | 0.8 m | 56 | 6 MB | silver |
| Terrain, mid ring | Mapterhorn z13 |  | 6 m | 169 | 18 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 256 | 27 MB |  |
| Trees | stands from the ETH canopy height and WorldCover (no lidar: no crowns, no far tree ring) | 2020, 2021 | 10 m | | (land cover) | silver |
| Surface masks | ESA WorldCover 2021 classes (no NAIP) | 2021 | 10 m | | (land cover) | bronze |
| Land cover, far terrain, masks and stands | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 8 | 1,492 MB |  |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: switzerland) |  |  | 5 | 19 MB |  |
| Grooming | none | | | | | |

Total about **1,562 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- outside the US: terrain from Mapterhorn z16 (0.8 m; it has z17 here, from swissALTI3D), the mid ring from z13 (6 m)
- no EPT lidar over the box: the trees are stands from the ETH canopy height and WorldCover (Silver trees), no crowns and no far tree ring
- no NAIP: rock, scree and canopy masks from ESA WorldCover 10 m (Bronze surface)
- outside the US: no LANDFIRE; tree species from elevation and aspect
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py atzmannig`, then `pipeline/fetch.ps1 -Slug atzmannig -RawDir <dir>` on Drew's PC.
