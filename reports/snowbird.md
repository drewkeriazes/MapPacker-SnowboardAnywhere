# Pack report: Snowbird (`snowbird`)

Build `20261114T083908Z-5cf65f`, pipeline `2dbc3d3`, format 1. Report 2026-11-14T08:39:33Z by `pipeline/pack_report.py` (FEAT-175).

**Tier: silver** (FEAT-225: the weakest layer's)

| Layer | Source | Tier |
|---|---|---|
| terrain | 3DEP 1 m | gold |
| trees | lidar crowns + stands | silver |
| surface | NAIP | gold |

**Playable**: every DATA-022 MVP line passes.

| # | Item | | Detail |
|---|---|---|---|
| F | Pack format current | ✅ | formatVersion 1 |
| 1 | Resort config | ⚠️ | EPSG:26912 (12N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 2.1% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 2239 to 3501 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ⚠️ | rock 15.6% (reference 1.1%), canopy 2% : more rock than the reference by over 3x, check the thresholds (FEAT-175 step 2) |
| 7 | Trees and shrubs with species | ⚠️ | 0.02 M crowns + 0.00 M stems = 0.4 k per km2 (1% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.45 M crowns in 176 cells |
| 9 | features.json | ✅ | 14 lifts, 256 runs, 233 buildings, 648 roads, 30 water, 662 peaks, 142 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Path To Paradise, top of Aerial Tram |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 122 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 12 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS UT, WY; 662 peaks, 142 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/snowbird/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ❌ | no measured treeline (client uses Colorado's 3,480 m); canopy.grow_ndvi 0.08; canopy.leaf_ndvi 0.3; canopy.veg_ndvi 0.2; rock.bare_ndvi 0.2; rock.dark 90.0; rock.grey_sat 0.05; rock.ndvi 0.05; rock and canopy thresholds are Vail's (FEAT-175 step 2) |
| 21 | Published figures | ✅ | 6 figures match (Wikipedia: Snowbird, Utah; table below) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 51.8 |  |
| Trees (crowns + stems) per km2 | 430 | 39,201 |
| Rock share | 15.6% | 1.1% |
| Canopy share | 2% | 66% |
| Canopy on run centre lines | 0.2% | 3.7% |
| Groomed share | 0.1% |  |
| Crowns per km within 5 m of lift lines | 0.7 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 0% |  |
| Far ring crowns | 453,285 |  |
| Mean mogulScore by difficulty | advanced 0.44, easy 0.0, expert 0.44, extreme 0.27, freeride 0.0, intermediate 0.19, none 0.0, novice 0.0 | |

**Advanced or harder runs never over 15 deg:** Regulator Johnson (advanced, 5 deg), Bookends Traverse (advanced, 6 deg), Regulator Johnson (advanced, 7 deg), Bookends Bowl Return Road (advanced, 7 deg), Bookends Traverse (advanced, 8 deg), Bookends Bowl (expert, 8 deg), Regulator Johnson (advanced, 10 deg), Red Lens Line (advanced, 12 deg), and 4 more

**Lifts with the most crowns on the line:** Wilbere (7), Aerial Tram (2)

## Published figures (gathered 2026-11-14 by published.py)

| Figure | Published | Source | This pack | | Note |
|---|---:|---|---:|---|---|
| Summit | 3,353 m (11,001 ft) | Wikipedia: Snowbird, Utah | 3,342 m (10,965 ft) | ✅ | highest of the lift stations, -11 m |
| Base | 2,365 m (7,759 ft) | Wikipedia: Snowbird, Utah | 2,365 m (7,759 ft) | ✅ | lowest of the lift stations, +0 m |
| Vertical | 988 m (3,241 ft) | Wikipedia: Snowbird, Utah | 977 m (3,205 ft) | ✅ | -11 m (-1%) |
| Lifts | 13 | Wikipedia: Snowbird, Utah | 14 | ✅ | every lift (11 chairs and gondolas) |
| Runs | 169 | Wikipedia: Snowbird, Utah | 202 | ✅ | 202 run names over 256 segments, 19 unnamed; 120% of the published count |
| Skiable area | 10.1 km2 (2,501 acres) | Wikipedia: Snowbird, Utah | 9.2 km2 (2,286 acres) | ✅ | run lines widened 50 m each side, plus the area runs, 0.91 times the published |

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2300 | 1.11 | 118 | 0 | 107 |
| 2400 | 1.81 | 611 | 1 | 338 |
| 2500 | 2.55 | 848 | 47 | 351 |
| 2600 | 4.0 | 2,095 | 783 | 720 |
| 2700 | 5.93 | 3,548 | 642 | 706 |
| 2800 | 7.57 | 4,527 | 696 | 690 |
| 2900 | 8.51 | 4,819 | 469 | 621 |
| 3000 | 8.16 | 2,209 | 57 | 278 |
| 3100 | 6.36 | 679 | 5 | 108 |
| 3200 | 3.88 | 137 | 0 | 35 |
| 3300 | 1.36 | 8 | 0 | 6 |
| 3400 | 0.38 | 0 | 0 | 0 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 210 | 62.7 | 2026-11-14 |
| mid heights | yes | 25 | 11.5 | 2026-11-14 |
| far heights | yes | 16 | 2.2 | 2026-11-14 |
| mask | yes | 56 | 9.1 | 2026-11-14 |
| AO | yes | 56 | 4.5 | 2026-11-14 |
| piste directions | yes | 56 | 0.0 | 2026-11-14 |
| moguls | yes | 56 | 0.6 | 2026-11-14 |
| cover | yes | 4 | 7.6 | 2026-11-14 |
| trees (crowns) | yes | 51 | 0.5 | 2026-11-14 |
| stands (stems) | yes | 37 | 1.8 | 2026-11-14 |
| far tree ring | yes | 176 | 10.9 | 2026-11-14 |
| shrubs | yes | 36 | 0.0 | 2026-11-14 |
| rocks | yes | 64 | 3.2 | 2026-11-14 |
