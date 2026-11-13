# Pack report: Keystone (`keystone`)

Build `20261113T150026Z-11a2d5`, pipeline `839bf62`, format 1. Report 2026-11-13T15:00:49Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ⚠️ | EPSG:26913 (13N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 0.0% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 2804 to 3845 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 0.9% (reference 1.1%), canopy 66% |
| 7 | Trees and shrubs with species | ✅ | 0.30 M crowns + 2.92 M stems = 44.9 k per km2 (115% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.93 M crowns in 280 cells |
| 9 | features.json | ⚠️ | 1 of 13 chairs and gondolas without towers; 20 lifts, 198 runs, 525 buildings, 643 roads, 38 water, 1323 peaks, 202 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Ten Mile, top of Bergman Express |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 126 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 7 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 37% of runs with a grooming record, 24 reports in raw |
| 16 | Place names | ✅ | GNIS CO; 1323 peaks, 202 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3575 m measured; canopy.grow_ndvi 0.1045; canopy.leaf_ndvi 0.3793; canopy.veg_ndvi 0.2477; rock.bare_ndvi 0.2477; rock.dark 60.0; rock.grey_sat 0.2; rock.ndvi 0.1218; treeline 3575 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 71.5 |  |
| Trees (crowns + stems) per km2 | 44,888 | 39,201 |
| Rock share | 0.9% | 1.1% |
| Canopy share | 66% | 66% |
| Canopy on run centre lines | 5.6% | 3.7% |
| Groomed share | 2.8% |  |
| Crowns per km within 5 m of lift lines | 7.2 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 37% |  |
| Runs groomed in OSM | 48% |  |
| Far ring crowns | 934,958 |  |
| Mean mogulScore by difficulty | advanced 0.53, easy 0.0, extreme 0.17, intermediate 0.1 | |

**Advanced or harder runs never over 15 deg:** unnamed (advanced, 4 deg), sampler (advanced, 7 deg), Coyote Caper (advanced, 10 deg), to lower go devil (advanced, 11 deg), Richter (advanced, 11 deg), Coyote Caper (advanced, 12 deg), Park Lane (advanced, 15 deg)

**Lifts with the most crowns on the line:** River Run Gondola (33), Outpost Gondola (29), Summit Express (26), Wayback (15), Santiago Express (12)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2800 | 5.04 | 13,098 | 121,559 | 26,706 |
| 2900 | 6.29 | 28,765 | 290,588 | 50,778 |
| 3000 | 7.95 | 37,728 | 386,205 | 53,333 |
| 3100 | 7.95 | 40,685 | 418,904 | 57,796 |
| 3200 | 9.98 | 52,498 | 528,325 | 58,174 |
| 3300 | 10.52 | 56,883 | 556,522 | 58,294 |
| 3400 | 8.26 | 41,023 | 392,388 | 52,501 |
| 3500 | 7.12 | 23,011 | 212,775 | 33,119 |
| 3600 | 5.49 | 1,474 | 8,728 | 1,859 |
| 3700 | 2.76 | 38 | 54 | 33 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 300 | 75.6 | 2026-11-13 |
| mid heights | yes | 25 | 11.7 | 2026-11-13 |
| far heights | yes | 16 | 2.7 | 2026-11-13 |
| mask | yes | 80 | 6.1 | 2026-11-13 |
| AO | yes | 80 | 4.8 | 2026-11-13 |
| piste directions | yes | 80 | 0.2 | 2026-11-13 |
| moguls | yes | 80 | 0.2 | 2026-11-13 |
| cover | yes | 4 | 15.4 | 2026-11-13 |
| trees (crowns) | yes | 80 | 7.1 | 2026-11-13 |
| stands (stems) | yes | 80 | 9.2 | 2026-11-13 |
| far tree ring | yes | 280 | 22.4 | 2026-11-13 |
| shrubs | yes | 79 | 0.3 | 2026-11-13 |
| rocks | yes | 78 | 0.3 | 2026-11-13 |
