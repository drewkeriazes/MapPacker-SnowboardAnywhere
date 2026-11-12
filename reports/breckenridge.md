# Pack report: Breckenridge (`breckenridge`)

Build `20261112T222950Z-db9d1a`, pipeline `9596769`, format 1. Report 2026-11-12T22:32:33Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ✅ | EPSG:26913 (13N) |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 0.0% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 2829 to 4223 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ⚠️ | rock 3.5% (reference 1.1%), canopy 48% : more rock than the reference by over 3x, check the thresholds (FEAT-175 step 2) |
| 7 | Trees and shrubs with species | ✅ | 0.32 M crowns + 3.04 M stems = 31.6 k per km2 (81% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 1.01 M crowns in 332 cells |
| 9 | features.json | ⚠️ | 1 of 22 chairs and gondolas without towers; 36 lifts, 356 runs, 5458 buildings, 2424 roads, 163 water, 1341 peaks, 168 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on 4 O'Clock, top of Colorado SuperChair |
| 11 | In the resort picker | ✅ | in packs/index.json, in game/src/resorts.ts, in the catalog |
| 12 | Time trial courses | ✅ | 151 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 7 advanced+ runs never over 15 deg; 10 compare spots measured; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 32% of runs with a grooming record, 36 reports in raw |
| 16 | Place names | ✅ | GNIS CO; 1341 peaks, 168 town labels |
| 17 | Main menu shot and ghosts | ✅ | hand-made, game/public/attract/breckenridge/ |
| 18 | Landmark | ❌ | none (optional) |
| 19 | Compare spots against photos | ⚠️ | 0 spots with Street View in docs/compare/breckenridge, 10 proposed waiting for a Street View link (propose_spots.py) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3525 m measured; canopy.grow_ndvi 0.1174; canopy.leaf_ndvi 0.3981; canopy.veg_ndvi 0.2632; rock.bare_ndvi 0.2632; rock.dark 60.0; rock.grey_sat 0.2; rock.ndvi 0.1518; treeline 3525 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 106.0 |  |
| Trees (crowns + stems) per km2 | 31,642 | 39,201 |
| Rock share | 3.5% | 1.1% |
| Canopy share | 48% | 66% |
| Canopy on run centre lines | 5.3% | 3.7% |
| Groomed share | 3.0% |  |
| Crowns per km within 5 m of lift lines | 7.4 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 32% |  |
| Runs groomed in OSM | 58% |  |
| Far ring crowns | 1,011,130 |  |
| Mean mogulScore by difficulty | advanced 0.41, easy 0.0, expert 0.78, extreme 0.36, intermediate 0.03, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Peak Seven Timber Road (advanced, 7 deg), Peak Seven Timber Road (advanced, 9 deg), Shock Hill (advanced, 11 deg), Flapjack (advanced, 11 deg), Hoo Doo Voo Doo (advanced, 12 deg), Hoo Doo Voo Doo (advanced, 13 deg), Hang Ten (advanced, 13 deg)

**Lifts with the most crowns on the line:** Peak 8 SuperConnect (82), BreckConnect Gondola (46), Snowflake (37), Freedom Superchair (15), Kensho SuperChair (10)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2800 | 3.69 | 7,633 | 66,435 | 20,070 |
| 2900 | 14.56 | 42,715 | 388,983 | 29,640 |
| 3000 | 17.84 | 67,569 | 675,822 | 41,659 |
| 3100 | 12.27 | 57,037 | 571,596 | 51,245 |
| 3200 | 9.58 | 48,120 | 472,951 | 54,395 |
| 3300 | 8.61 | 42,413 | 413,079 | 52,922 |
| 3400 | 7.96 | 33,360 | 315,782 | 43,856 |
| 3500 | 7.47 | 16,020 | 123,266 | 18,640 |
| 3600 | 7.87 | 2,285 | 10,166 | 1,581 |
| 3700 | 7.13 | 58 | 46 | 15 |
| 3800 | 4.9 | 89 | 0 | 18 |
| 3900 | 2.41 | 114 | 0 | 47 |
| 4000 | 1.3 | 80 | 0 | 62 |
| 4100 | 0.36 | 40 | 0 | 110 |

## Compare spots: trees per hectare within 100 m

| Spot | Trees per ha |
|---|---:|
| base-of-colorado-superchair | 8 |
| base-of-peak-8-superconnect | 186 |
| base-of-quicksilver-superchair | 143 |
| crystal-peak | 2 |
| peak-10 | 3 |
| top-of-6-chair | 1 |
| top-of-falcon-superchair | 275 |
| top-of-horseshoe-bowl-t-bar | 0 |
| top-of-imperial-superchair | 0 |
| top-of-kensho-superchair | 2 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 420 | 108.4 | 2026-11-12 |
| mid heights | yes | 25 | 11.6 | 2026-11-12 |
| far heights | yes | 16 | 2.7 | 2026-11-12 |
| mask | yes | 110 | 10.9 | 2026-11-12 |
| AO | yes | 110 | 7.7 | 2026-11-12 |
| piste directions | yes | 110 | 0.4 | 2026-11-12 |
| moguls | yes | 110 | 0.5 | 2026-11-12 |
| cover | yes | 4 | 17.3 | 2026-11-12 |
| trees (crowns) | yes | 120 | 7.6 | 2026-11-12 |
| stands (stems) | yes | 114 | 11.1 | 2026-11-12 |
| far tree ring | yes | 332 | 24.3 | 2026-11-12 |
| shrubs | yes | 121 | 0.7 | 2026-11-12 |
| rocks | yes | 110 | 1.5 | 2026-11-12 |
