# Whistler Blackcomb: data plan

Planned 2026-11-14 by `pipeline/resort.py plan whistler-blackcomb` (FEAT-223). EPSG:32610 (10N), origin 505300, 5547600. Ski area 13.4 km across, buffer 1000 m, box 11.8 x 11.4 km, elevation 630 to 2430 m (Mapterhorn z12).

**Tier: bronze** (held there by: surface)

| Layer | Source | Year | Resolution | Items | Size | Tier |
|---|---|---|---|---|---|---|
| Terrain, resort | Mapterhorn z15 (finest there z15: Canada DTM 2018-2024) |  | 1.5 m | 240 | 25 MB | silver |
| Terrain, mid ring | Mapterhorn z13 |  | 6 m | 182 | 19 MB |  |
| Terrain, far ring | Mapterhorn |  | z11 | 289 | 30 MB |  |
| Trees | stands from the ETH canopy height and WorldCover (no lidar: no crowns, no far tree ring) | 2020, 2021 | 10 m | | (land cover) | silver |
| Surface masks | ESA WorldCover 2021 classes (no NAIP) | 2021 | 10 m | | (land cover) | bronze |
| Land cover, far terrain, masks and stands | ESA WorldCover 2021 + ETH canopy height 2020 (3 degree tiles) | 2021, 2020 | 10 m | 4 | 746 MB |  |
| Runs, lifts, buildings | OSM via Overpass (Geofabrik extract: british-columbia) |  |  | 5 | 19 MB |  |
| Grooming | https://www.whistlerblackcomb.com/the-mountain/mountain-conditions/terrain-and-lift-status.aspx | | | | | |

Total about **840 MB**.

Lidar size is points x 8.8 bytes (LAZ), raster sizes are pixels x bytes per pixel, both measured on Vail's raw data.

## Notes

- outside the US: terrain from Mapterhorn z15 (1.5 m; it has z15 here, from Canada DTM 2018-2024), the mid ring from z13 (6 m)
- no EPT lidar over the box: the trees are stands from the ETH canopy height and WorldCover (Silver trees), no crowns and no far tree ring
- no NAIP: rock, scree and canopy masks from ESA WorldCover 10 m (Bronze surface)
- outside the US: no LANDFIRE; tree species from elevation and aspect

## Next

- `start_run` is empty: FEAT-175 step 4 picks it after the build.
- `python pipeline/gen_manifest.py whistler-blackcomb`, then `pipeline/fetch.ps1 -Slug whistler-blackcomb -RawDir <dir>` on Drew's PC.
