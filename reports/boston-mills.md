# Pack report: Boston Mills / Brandywine (`boston-mills`)

Build `20261112T224417Z-7cba89`, pipeline `c2cc1e6`, format 1. Report 2026-11-12T22:46:56Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ⚠️ | EPSG:26917 (17N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 0.0% of the forest in EVT classes the species rules don't name (east rules) |
| 5 | Heights fine, mid, far | ✅ | 194 to 294 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 0.1% (reference 1.1%), canopy 70% |
| 7 | Trees and shrubs with species | ⚠️ | 0.01 M crowns + 0.04 M stems = 12.5 k per km2 (32% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.54 M crowns in 238 cells |
| 9 | features.json | ⚠️ | 3 runs without a difficulty; 16 lifts, 20 runs, 85 buildings, 582 roads, 42 water, 69 peaks, 445 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Buttermilk, top of Lift 2 |
| 11 | In the resort picker | ✅ | in packs/index.json, in the catalog |
| 12 | Time trial courses | ✅ | 11 runs of 150 m and 30 m drop or more |
| 13 | Attribution for every data set | ✅ | 10 lines |
| 14 | Validated | ⚠️ | 3 advanced+ runs never over 15 deg; 56 crowns per km within 5 m of lift lines; 10 compare spots measured; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS MI, OH, PA, WV; 69 peaks, 445 town labels |
| 17 | Main menu shot and ghosts | ✅ | generated (gen_content.py): 5 shots, a still of this build, 6 ghost takes |
| 18 | Landmark | ❌ | none (optional) |
| 19 | Compare spots against photos | ⚠️ | 0 spots with Street View in docs/compare/boston-mills, 10 proposed waiting for a Street View link (propose_spots.py) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | no treeline: forested to the top of the box (measured); canopy.grow_ndvi 0.25; canopy.leaf_ndvi 0.45; canopy.veg_ndvi 0.4286; rock.bare_ndvi 0.4286; rock.dark 67.3333; rock.grey_sat 0.1075; rock.ndvi 0.25; Brandywine relocated (turned -25 deg, height shift +3.0 m) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 3.8 |  |
| Trees (crowns + stems) per km2 | 12,452 | 39,201 |
| Rock share | 0.1% | 1.1% |
| Canopy share | 70% | 66% |
| Canopy on run centre lines | 0.5% | 3.7% |
| Groomed share | 0.4% |  |
| Crowns per km within 5 m of lift lines | 56.5 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 15% |  |
| Far ring crowns | 542,598 |  |
| Mean mogulScore by difficulty | advanced 0.45, easy 0.0, intermediate 0.06, none 0.0, novice 0.0 | |

**Advanced or harder runs never over 15 deg:** North Bowl (advanced, 12 deg), Champagne (advanced, 14 deg), Croyle (advanced, 14 deg)

**Lifts with the most crowns on the line:** Lift 1 (45), Lift 5 (26), Lift 2 (22), Lift 3 (18), Lift 2 (15)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 100 | 0.54 | 6,812 | 3,878 | 19,958 |
| 200 | 3.26 | 43,364 | 34,108 | 23,791 |

## Compare spots: trees per hectare within 100 m

| Spot | Trees per ha |
|---|---:|
| base-of-lift-2 | 83 |
| base-of-lift-5 | 10 |
| base-of-ram-quad | 67 |
| top-of-handle-tow | 8 |
| top-of-lift-1 | 107 |
| top-of-lift-2 | 146 |
| top-of-lift-4-2 | 37 |
| top-of-lift-4 | 100 |
| top-of-lift-6 | 106 |
| top-of-ram-quad | 48 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 80 | 18.1 | 2026-11-12 |
| mid heights | yes | 25 | 9.7 | 2026-11-12 |
| far heights | yes | 16 | 1.3 | 2026-11-12 |
| mask | yes | 20 | 1.4 | 2026-11-12 |
| AO | yes | 20 | 1.4 | 2026-11-12 |
| piste directions | yes | 20 | 0.0 | 2026-11-12 |
| moguls | yes | 20 | 0.0 | 2026-11-12 |
| cover | yes | 4 | 8.6 | 2026-11-12 |
| trees (crowns) | yes | 24 | 1.2 | 2026-11-12 |
| stands (stems) | yes | 24 | 3.0 | 2026-11-12 |
| far tree ring | yes | 238 | 13.0 | 2026-11-12 |
| shrubs | yes | 24 | 0.1 | 2026-11-12 |
| rocks | yes | 20 | 0.0 | 2026-11-12 |
