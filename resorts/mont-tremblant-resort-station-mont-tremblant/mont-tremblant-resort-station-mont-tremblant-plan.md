# Mont Tremblant Resort, Station Mont Tremblant: data plan

Planned 2026-11-14 by `pipeline/resort.py plan mont-tremblant-resort-station-mont-tremblant` (FEAT-223). EPSG:32618 (18N), origin 534250, 5119150. Ski area 8.3 km across, buffer 1000 m, box 7.7 x 8.1 km, elevation 206 to 933 m (Mapterhorn z12).

**Tier: bronze** (held there by: surface)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | Mapterhorn z15 (finest there z15: Canada DTM 2018-2024) |  | 1.7 m | 100 | 10 MB | silver |
| Terrain, mid ring | Mapterhorn z13 |  | 7 m | 156 | 16 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 256 | 27 MB |  |
| Trees | stands from the ETH canopy height and WorldCover (no lidar: no crowns, no far tree ring) | 2020, 2021 | 10 m | | (land cover) | silver |
| Surface masks | ESA WorldCover 2021 classes (no NAIP) | 2021 | 10 m | | (land cover) | bronze |
| Land cover, far terrain, masks and stands | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: quebec) |  |  | 5 | 19 MB |  |
| Grooming | none | | | | | |

Total about **819 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- outside the US: terrain from Mapterhorn z15 (1.7 m; it has z15 here, from Canada DTM 2018-2024), the mid ring from z13 (7 m)
- no EPT lidar over the box: the trees are stands from the ETH canopy height and WorldCover (Silver trees), no crowns and no far tree ring
- no NAIP: rock, scree and canopy masks from ESA WorldCover 10 m (Bronze surface)
- outside the US: no LANDFIRE; tree species from elevation and aspect
- no archived Vail Resorts terrain status page: groomed runs come from OSM tags only

## Left out

- Ski de fond Mont-Tremblant: 152 run and lift ways by OSM id

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py mont-tremblant-resort-station-mont-tremblant`, then `pipeline/fetch.ps1 -Slug mont-tremblant-resort-station-mont-tremblant -RawDir <dir>` on Drew's PC.
