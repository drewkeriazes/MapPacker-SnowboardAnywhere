# Pack report: Aspen Snowmass (`aspen-snowmass`)

Build `20261114T074849Z-d30ffa`, pipeline `50b0207`, format 1. Report 2026-11-14T07:49:07Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ⚠️ | EPSG:26913 (13N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 0.0% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 2404 to 3994 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ⚠️ | rock 5.4% (reference 1.1%), canopy 11% : more rock than the reference by over 3x, check the thresholds (FEAT-175 step 2) |
| 7 | Trees and shrubs with species | ⚠️ | 0.05 M crowns + 0.34 M stems = 5.7 k per km2 (14% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.28 M crowns in 124 cells |
| 9 | features.json | ⚠️ | 1 of 14 chairs and gondolas without towers; 18 lifts, 209 runs, 1341 buildings, 643 roads, 46 water, 990 peaks, 82 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on High Pass, top of Cirque T-Bar |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 120 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 7 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS CO; 990 peaks, 82 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/aspen-snowmass/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3600 m measured; canopy.grow_ndvi 0.1153; canopy.leaf_ndvi 0.3366; canopy.veg_ndvi 0.227; rock.bare_ndvi 0.227; rock.dark 65.3333; rock.grey_sat 0.2; rock.ndvi 0.1388; treeline 3600 |
| 21 | Published figures | ➖ | no English Wikipedia article with an Infobox ski area for Aspen Snowmass |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 68.9 |  |
| Trees (crowns + stems) per km2 | 5,656 | 39,201 |
| Rock share | 5.4% | 1.1% |
| Canopy share | 11% | 66% |
| Canopy on run centre lines | 0.0% | 3.7% |
| Groomed share | 0.8% |  |
| Crowns per km within 5 m of lift lines | 0.0 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 23% |  |
| Far ring crowns | 275,536 |  |
| Mean mogulScore by difficulty | advanced 0.5, easy 0.0, expert 0.54, extreme 0.34, intermediate 0.14 | |

**Advanced or harder runs never over 15 deg:** Terminator (advanced, 5 deg), Terminator (advanced, 10 deg), Hanging Valley Exit (expert, 12 deg), Hanging Valley Exit (expert, 12 deg), Wildcat (Lower) (advanced, 13 deg), Terminator (advanced, 14 deg), Terminator (advanced, 15 deg)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2400 | 2.63 | 0 | 0 | 0 |
| 2500 | 7.17 | 0 | 0 | 0 |
| 2600 | 6.56 | 3 | 8 | 2 |
| 2700 | 6.65 | 964 | 11,118 | 1,817 |
| 2800 | 5.55 | 3,144 | 28,085 | 5,629 |
| 2900 | 5.56 | 4,300 | 39,438 | 7,867 |
| 3000 | 6.14 | 6,369 | 57,033 | 10,324 |
| 3100 | 5.54 | 6,524 | 54,857 | 11,089 |
| 3200 | 5.13 | 7,010 | 50,692 | 11,253 |
| 3300 | 5.01 | 7,501 | 46,706 | 10,818 |
| 3400 | 3.87 | 5,314 | 30,142 | 9,173 |
| 3500 | 3.34 | 4,145 | 21,273 | 7,620 |
| 3600 | 3.02 | 1,392 | 3,543 | 1,632 |
| 3700 | 1.77 | 27 | 8 | 20 |
| 3800 | 0.78 | 3 | 0 | 4 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 289 | 64.4 | 2026-11-14 |
| mid heights | yes | 25 | 12.0 | 2026-11-14 |
| far heights | yes | 16 | 2.8 | 2026-11-14 |
| mask | yes | 81 | 5.2 | 2026-11-14 |
| AO | yes | 81 | 3.7 | 2026-11-14 |
| piste directions | yes | 81 | 0.1 | 2026-11-14 |
| moguls | yes | 81 | 0.3 | 2026-11-14 |
| cover | yes | 4 | 8.9 | 2026-11-14 |
| trees (crowns) | yes | 24 | 1.1 | 2026-11-14 |
| stands (stems) | yes | 24 | 2.2 | 2026-11-14 |
| far tree ring | yes | 124 | 6.6 | 2026-11-14 |
| shrubs | yes | 80 | 0.6 | 2026-11-14 |
| rocks | yes | 78 | 1.5 | 2026-11-14 |
