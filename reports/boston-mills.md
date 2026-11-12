# Pack report: Boston Mills / Brandywine (`boston-mills`)

Build `20261112T013748Z-b77540`, pipeline `d3d9993+dirty`, format 1. Report 2026-11-12T01:37:52Z by `pipeline/pack_report.py` (FEAT-175).

**Preview**: MVP lines 12 hold it back.

| # | Item | | Detail |
|---|---|---|---|
| F | Pack format current | ✅ | formatVersion 1 |
| 1 | Resort config | ⚠️ | EPSG:26917 (17N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH |
| 5 | Heights fine, mid, far | ✅ | 192 to 311 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 0.1% (reference 1.1%), canopy 74% |
| 7 | Trees and shrubs with species | ✅ | 0.05 M crowns + 0.49 M stems = 27.3 k per km2 (70% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.50 M crowns in 209 cells |
| 9 | features.json | ⚠️ | 3 runs without a difficulty; 16 lifts, 20 runs, 85 buildings, 587 roads, 43 water, 66 peaks, 0 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | on Outer Limits |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ❌ | 0 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 8 lines |
| 14 | Validated | ⚠️ | 4 advanced+ runs never over 15 deg; 23 crowns per km within 5 m of lift lines; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ❌ | no raw/names |
| 17 | Main menu shot and ghosts | ❌ | game/public/attract/boston-mills/shots.json missing |
| 18 | Landmark | ❌ | none (optional) |
| 19 | Compare spots against photos | ❌ | 0 spots in docs/compare/boston-mills |
| 20 | Values derived for the resort, not copied from Vail | ❌ | no measured treeline (client uses Colorado's 3,480 m); canopy.grow_ndvi 0.25; canopy.leaf_ndvi 0.45; canopy.veg_ndvi 0.4138; rock.bare_ndvi 0.4138; rock.dark 67.0; rock.grey_sat 0.1064; rock.ndvi 0.25; rock and canopy thresholds are Vail's (FEAT-175 step 2) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 19.9 |  |
| Trees (crowns + stems) per km2 | 27,302 | 39,201 |
| Rock share | 0.1% | 1.1% |
| Canopy share | 74% | 66% |
| Canopy on run centre lines | 0.8% | 3.7% |
| Groomed share | 0.1% |  |
| Crowns per km within 5 m of lift lines | 22.6 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 15% |  |
| Far ring crowns | 500,113 |  |
| Mean mogulScore by difficulty | advanced 0.45, easy 0.0, intermediate 0.06, none 0.0, novice 0.0 | |

**Advanced or harder runs never over 15 deg:** North Bowl (advanced, 12 deg), Champagne (advanced, 14 deg), Croyle (advanced, 14 deg), Tiger (advanced, 15 deg)

**Lifts with the most crowns on the line:** Lift 1 (22), Lift 5 (13), Lift 2 (11), Ram Quad (7), Lift 3 (5)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 100 | 3.03 | 6,239 | 62,341 | 22,664 |
| 200 | 16.78 | 44,243 | 428,865 | 28,195 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 80 | 18.3 | 2026-11-12 |
| mid heights | yes | 25 | 9.7 | 2026-11-12 |
| far heights | yes | 16 | 1.3 | 2026-11-12 |
| mask | yes | 20 | 1.4 | 2026-11-12 |
| AO | yes | 20 | 1.4 | 2026-11-12 |
| piste directions | yes | 20 | 0.0 | 2026-11-12 |
| moguls | yes | 20 | 0.0 | 2026-11-12 |
| cover | yes | 4 | 10.2 | 2026-11-12 |
| trees (crowns) | yes | 24 | 1.2 | 2026-11-12 |
| stands (stems) | yes | 24 | 3.1 | 2026-11-12 |
| far tree ring | yes | 209 | 12.0 | 2026-11-12 |
| shrubs | yes | 24 | 0.1 | 2026-11-12 |
| rocks | yes | 19 | 0.0 | 2026-11-12 |
