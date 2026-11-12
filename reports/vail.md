# Pack report: Vail (`vail`)

Build `20261112T175000Z-85054c`, pipeline `6a5ec5e`, format 1. Report 2026-11-12T17:52:19Z by `pipeline/pack_report.py` (FEAT-175).

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
| 5 | Heights fine, mid, far | ✅ | 2409 to 3603 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 1.1% (reference 1.1%), canopy 66% |
| 7 | Trees and shrubs with species | ✅ | 0.52 M crowns + 4.80 M stems = 39.2 k per km2 (100% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 1.31 M crowns in 363 cells |
| 9 | features.json | ✅ | 33 lifts, 354 runs, 2000 buildings, 1406 roads, 42 water, 1315 peaks, 74 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Born Free, top of Born Free Express Lift |
| 11 | In the resort picker | ✅ | in packs/index.json, in game/src/resorts.ts, in the catalog |
| 12 | Time trial courses | ✅ | 185 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 4 advanced+ runs never over 15 deg; 15 compare spots measured; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 48% of runs with a grooming record, 42 reports in raw |
| 16 | Place names | ✅ | GNIS gnis.json; 1315 peaks, 74 town labels |
| 17 | Main menu shot and ghosts | ✅ | hand-made, game/public/attract/vail/ |
| 18 | Landmark | ✅ | in Landmarks.ts |
| 19 | Compare spots against photos | ✅ | 15 spots with Street View in docs/compare/vail |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3550 m measured; canopy.grow_ndvi 0.15; canopy.leaf_ndvi 0.45; canopy.veg_ndvi 0.3; rock.bare_ndvi 0.3; rock.dark 60.0; rock.grey_sat 0.2; rock.ndvi 0.18; treeline 3550 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 135.7 |  |
| Trees (crowns + stems) per km2 | 39,201 | 39,201 |
| Rock share | 1.1% | 1.1% |
| Canopy share | 66% | 66% |
| Canopy on run centre lines | 3.7% | 3.7% |
| Groomed share | 2.9% |  |
| Crowns per km within 5 m of lift lines | 12.9 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 48% |  |
| Runs groomed in OSM | 48% |  |
| Far ring crowns | 1,307,506 |  |
| Mean mogulScore by difficulty | advanced 0.47, easy 0.0, expert 0.88, intermediate 0.06 | |

**Advanced or harder runs never over 15 deg:** Windows Road (advanced, 5 deg), Resolution (advanced, 8 deg), Windows Road (advanced, 12 deg), Ptarmigan Ridge (advanced, 14 deg)

**Lifts with the most crowns on the line:** Orient Express Lift (103), Skyline Express Lift (45), Riva Bahn Express Lift (43), High Noon Express Lift (38), Northwoods Express Lift (36)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2400 | 6.34 | 11,812 | 94,905 | 16,831 |
| 2500 | 10.0 | 24,562 | 211,324 | 23,597 |
| 2600 | 8.35 | 28,540 | 239,862 | 32,133 |
| 2700 | 10.03 | 41,517 | 357,676 | 39,811 |
| 2800 | 11.94 | 53,340 | 468,698 | 43,736 |
| 2900 | 13.43 | 59,397 | 553,842 | 45,667 |
| 3000 | 15.39 | 64,063 | 619,918 | 44,438 |
| 3100 | 18.2 | 71,544 | 690,648 | 41,878 |
| 3200 | 17.8 | 72,094 | 687,866 | 42,704 |
| 3300 | 15.26 | 61,041 | 553,982 | 40,298 |
| 3400 | 7.54 | 29,037 | 278,055 | 40,708 |
| 3500 | 1.39 | 4,274 | 42,422 | 33,540 |

## Compare spots: trees per hectare within 100 m

| Spot | Trees per ha |
|---|---:|
| back-bowls-campbells | 5 |
| back-bowls-yonder | 0 |
| blue-sky-belles-camp | 378 |
| blue-sky-hornsilver | 334 |
| blue-sky-in-the-wuides | 73 |
| blue-sky-petes-express | 261 |
| blue-sky-the-divide | 450 |
| born-free | 231 |
| china-bowl-north-rim | 0 |
| china-bowl-poppyfields | 0 |
| eagles-nest-deck | 24 |
| mid-vail-wildwood | 142 |
| mongolia-bowl | 2 |
| prima-browns-face | 231 |
| sleepy-time-road | 4 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 529 | 143.3 | 2026-11-12 |
| mid heights | yes | 25 | 12.0 | 2026-11-12 |
| far heights | yes | 16 | 2.8 | 2026-11-12 |
| mask | yes | 144 | 11.7 | 2026-11-12 |
| AO | yes | 144 | 9.3 | 2026-11-12 |
| piste directions | yes | 144 | 0.4 | 2026-11-12 |
| moguls | yes | 144 | 0.3 | 2026-11-12 |
| cover | yes | 4 | 23.3 | 2026-11-12 |
| trees (crowns) | yes | 144 | 12.5 | 2026-11-12 |
| stands (stems) | yes | 144 | 19.8 | 2026-11-12 |
| far tree ring | yes | 363 | 31.4 | 2026-11-12 |
| shrubs | yes | 144 | 1.1 | 2026-11-12 |
| rocks | yes | 141 | 0.7 | 2026-11-12 |
