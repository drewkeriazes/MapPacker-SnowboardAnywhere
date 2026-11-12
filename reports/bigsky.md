# Pack report: Big Sky (`bigsky`)

Build `20261112T223031Z-5ce36a`, pipeline `9596769`, format 1. Report 2026-11-12T22:35:20Z by `pipeline/pack_report.py` (FEAT-175).

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
| 7 | Trees and shrubs with species | ✅ | 0.46 M crowns + 3.57 M stems = 34.9 k per km2 (89% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.66 M crowns in 212 cells |
| 9 | features.json | ⚠️ | 3 of 28 chairs and gondolas without towers; 40 lifts, 602 runs, 1190 buildings, 1161 roads, 43 water, 513 peaks, 58 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Morningstar, top of Powder Seeker 6 |
| 11 | In the resort picker | ✅ | in packs/index.json, in game/src/resorts.ts, in the catalog |
| 12 | Time trial courses | ✅ | 218 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 15 advanced+ runs never over 15 deg; 10 compare spots measured; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS ID, MT, WY; 513 peaks, 58 town labels |
| 17 | Main menu shot and ghosts | ✅ | generated (gen_content.py): 5 shots, a still of this build, 6 ghost takes |
| 18 | Landmark | ❌ | none (optional) |
| 19 | Compare spots against photos | ⚠️ | 0 spots with Street View in docs/compare/bigsky, 10 proposed waiting for a Street View link (propose_spots.py) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 2700 m measured; canopy.grow_ndvi 0.15; canopy.leaf_ndvi 0.52; canopy.veg_ndvi 0.3636; rock.bare_ndvi 0.3636; rock.dark 35.0; rock.grey_sat 0.0933; rock.ndvi 0.18; treeline 2700 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 115.6 |  |
| Trees (crowns + stems) per km2 | 34,883 | 39,201 |
| Rock share | 3.3% | 1.1% |
| Canopy share | 56% | 66% |
| Canopy on run centre lines | 5.8% | 3.7% |
| Groomed share | 0.3% |  |
| Crowns per km within 5 m of lift lines | 11.9 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 4% |  |
| Far ring crowns | 662,746 |  |
| Mean mogulScore by difficulty | advanced 0.42, easy 0.0, expert 0.39, extreme 0.11, intermediate 0.14, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Comet (advanced, 6 deg), unnamed (advanced, 8 deg), LRT Traverse (advanced, 10 deg), Summit (advanced, 10 deg), unnamed (advanced, 10 deg), Siberia (advanced, 10 deg), unnamed (advanced, 11 deg), Iron Horse (advanced, 12 deg), and 7 more

**Lifts with the most crowns on the line:** Highlands (48), Ramcharger 8 - High Speed (47), Southern Comfort (46), One and Only (45), Thunder Wolf (29)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 1900 | 0.62 | 2,456 | 17,713 | 32,469 |
| 2000 | 5.14 | 26,566 | 170,181 | 38,297 |
| 2100 | 11.65 | 51,330 | 363,337 | 35,591 |
| 2200 | 17.68 | 72,034 | 629,708 | 39,695 |
| 2300 | 19.48 | 82,162 | 758,824 | 43,167 |
| 2400 | 18.94 | 79,697 | 719,151 | 42,169 |
| 2500 | 16.35 | 69,174 | 568,274 | 38,989 |
| 2600 | 11.98 | 46,733 | 277,181 | 27,035 |
| 2700 | 5.99 | 18,891 | 51,480 | 11,749 |
| 2800 | 3.6 | 6,309 | 15,551 | 6,072 |
| 2900 | 1.99 | 1,451 | 2,851 | 2,167 |
| 3000 | 1.12 | 21 | 2 | 21 |
| 3100 | 0.57 | 0 | 0 | 0 |
| 3200 | 0.29 | 0 | 0 | 0 |

## Compare spots: trees per hectare within 100 m

| Spot | Trees per ha |
|---|---:|
| base-of-madison-8 | 136 |
| base-of-southern-comfort | 148 |
| base-of-swift-current-6 | 6 |
| castle-rock | 0 |
| mount-chipperfield | 13 |
| top-of-dakota-3 | 13 |
| top-of-headwaters-2 | 0 |
| top-of-lone-peak-tram | 0 |
| top-of-powder-seeker-6 | 1 |
| top-of-shedhorn-4-high-speed | 1 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 462 | 126.0 | 2026-11-12 |
| mid heights | yes | 25 | 11.6 | 2026-11-12 |
| far heights | yes | 16 | 2.5 | 2026-11-12 |
| mask | yes | 121 | 18.9 | 2026-11-12 |
| AO | yes | 121 | 8.8 | 2026-11-12 |
| piste directions | yes | 121 | 0.1 | 2026-11-12 |
| moguls | yes | 121 | 0.8 | 2026-11-12 |
| cover | yes | 4 | 20.0 | 2026-11-12 |
| trees (crowns) | yes | 121 | 11.0 | 2026-11-12 |
| stands (stems) | yes | 121 | 15.4 | 2026-11-12 |
| far tree ring | yes | 212 | 15.9 | 2026-11-12 |
| shrubs | yes | 121 | 1.9 | 2026-11-12 |
| rocks | yes | 121 | 1.9 | 2026-11-12 |
