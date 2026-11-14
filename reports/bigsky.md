# Pack report: Big Sky (`bigsky`)

Build `20261114T144754Z-a3c8ed`, pipeline `8255205`, format 1. Report 2026-11-14T14:48:32Z by `pipeline/pack_report.py` (FEAT-175).

**Tier: gold** (FEAT-225: the weakest layer's)

| Layer | Source | Tier |
|---|---|---|
| terrain | 3DEP 1 m | gold |
| trees | lidar crowns + stands | gold |
| surface | NAIP | gold |

**Playable**: every DATA-022 MVP line passes.

| # | Item | | Detail |
|---|---|---|---|
| F | Pack format current | ✅ | formatVersion 1 |
| 1 | Resort config | ✅ | EPSG:26912 (12N) |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 0.0% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 1925 to 3405 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ⚠️ | rock 3.3% (reference 1.1%), canopy 56% : more rock than the reference by over 3x, check the thresholds (FEAT-175 step 2) |
| 7 | Trees and shrubs with species | ✅ | 0.46 M crowns + 2.50 M stems = 25.6 k per km2 (65% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.66 M crowns in 212 cells |
| 9 | features.json | ⚠️ | 4 of 27 chairs and gondolas without towers; 39 lifts, 593 runs, 1367 buildings, 1443 roads, 43 water, 513 peaks, 58 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Morningstar, top of Powder Seeker 6 |
| 11 | In the resort picker | ✅ | in packs/index.json, in the catalog |
| 12 | Time trial courses | ✅ | 215 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 15 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS ID, MT, WY; 513 peaks, 58 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/bigsky/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 2700 m measured; canopy.grow_ndvi 0.15; canopy.leaf_ndvi 0.52; canopy.veg_ndvi 0.3636; rock.bare_ndvi 0.3636; rock.dark 35.0; rock.grey_sat 0.0933; rock.ndvi 0.18; treeline 2700 |
| 21 | Published figures | ✅ | 6 figures match (Wikipedia: Big Sky Resort; table below) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 115.6 |  |
| Trees (crowns + stems) per km2 | 25,594 | 39,201 |
| Rock share | 3.3% | 1.1% |
| Canopy share | 56% | 66% |
| Canopy on run centre lines | 5.9% | 3.7% |
| Groomed share | 0.3% |  |
| Crowns per km within 5 m of lift lines | 12.4 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 4% |  |
| Far ring crowns | 662,746 |  |
| Mean mogulScore by difficulty | advanced 0.4, easy 0.0, expert 0.36, extreme 0.16, intermediate 0.14, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Comet (advanced, 6 deg), unnamed (advanced, 8 deg), LRT Traverse (advanced, 10 deg), Summit (advanced, 10 deg), unnamed (advanced, 10 deg), Siberia (advanced, 10 deg), unnamed (advanced, 11 deg), Iron Horse (advanced, 12 deg), and 7 more

**Lifts with the most crowns on the line:** Ramcharger 8 - High Speed (48), Explorer Gondola (48), Highlands (47), One and Only (46), Southern Comfort (45)

## Published figures (gathered 2026-11-13 by published.py)

| Figure | Published | Source | This pack | | Note |
|---|---:|---|---:|---|---|
| Summit | 3,403 m (11,165 ft) | Wikipedia: Big Sky Resort | 3,402 m (11,161 ft) | ✅ | highest of the lift stations, -1 m |
| Base | 2,073 m (6,801 ft) | Wikipedia: Big Sky Resort | 2,078 m (6,818 ft) | ✅ | lowest of the lift stations, +5 m |
| Vertical | 1,326 m (4,350 ft) | Wikipedia: Big Sky Resort | 1,324 m (4,344 ft) | ✅ | -2 m (-0%) |
| Lifts | 40 | Wikipedia: Big Sky Resort | 39 | ✅ | every lift (27 chairs and gondolas) |
| Runs | 320 | Wikipedia: Big Sky Resort | 329 | ✅ | 329 run names over 593 segments, 146 unnamed; 103% of the published count |
| Skiable area | 23.7 km2 (5,849 acres) | Wikipedia: Big Sky Resort | 21.3 km2 (5,268 acres) | ✅ | run lines widened 50 m each side, plus the area runs, 0.90 times the published |

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 1900 | 0.62 | 2,456 | 4,906 | 11,851 |
| 2000 | 5.14 | 26,566 | 58,461 | 16,550 |
| 2100 | 11.65 | 51,325 | 233,947 | 24,485 |
| 2200 | 17.68 | 72,026 | 490,944 | 31,845 |
| 2300 | 19.48 | 82,118 | 577,426 | 33,854 |
| 2400 | 18.94 | 79,645 | 540,066 | 32,713 |
| 2500 | 16.35 | 69,149 | 403,216 | 28,892 |
| 2600 | 11.98 | 46,714 | 170,682 | 18,145 |
| 2700 | 5.99 | 18,892 | 17,447 | 6,067 |
| 2800 | 3.6 | 6,309 | 3,547 | 2,738 |
| 2900 | 1.99 | 1,452 | 365 | 915 |
| 3000 | 1.12 | 21 | 0 | 19 |
| 3100 | 0.57 | 0 | 0 | 0 |
| 3200 | 0.29 | 0 | 0 | 0 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 462 | 126.0 | 2026-11-14 |
| mid heights | yes | 25 | 11.6 | 2026-11-14 |
| far heights | yes | 16 | 2.5 | 2026-11-14 |
| mask | yes | 121 | 19.3 | 2026-11-14 |
| AO | yes | 121 | 8.8 | 2026-11-14 |
| piste directions | yes | 121 | 0.1 | 2026-11-14 |
| moguls | yes | 121 | 0.8 | 2026-11-14 |
| cover | yes | 4 | 19.8 | 2026-11-14 |
| trees (crowns) | yes | 121 | 11.0 | 2026-11-14 |
| stands (stems) | yes | 121 | 16.7 | 2026-11-14 |
| far tree ring | yes | 212 | 15.9 | 2026-11-14 |
| shrubs | yes | 121 | 1.9 | 2026-11-14 |
| rocks | yes | 121 | 1.9 | 2026-11-14 |
