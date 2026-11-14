# Pack report: Mount Bohemia (`mount-bohemia`)

Build `20261114T131518Z-5695db`, pipeline `fea5f82`, format 1. Report 2026-11-14T13:15:25Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ⚠️ | EPSG:26916 (16N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 0.0% of the forest in EVT classes the species rules don't name (east rules) |
| 5 | Heights fine, mid, far | ✅ | 183 to 446 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 0.0% (reference 1.1%), canopy 76% |
| 7 | Trees and shrubs with species | ⚠️ | 0.04 M crowns + 0.17 M stems = 18.2 k per km2 (46% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.60 M crowns in 161 cells |
| 9 | features.json | ✅ | 2 lifts, 159 runs, 266 buildings, 224 roads, 4 water, 52 peaks, 41 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Ghost Trail, top of Mountain Dew Hoist |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 26 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | canopy 26% on run centre lines (trail cuts missing?); 27 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS MI, WI; 52 peaks, 41 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 1 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/mount-bohemia/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | no treeline: forested to the top of the box (measured); canopy.grow_ndvi 0.21; canopy.leaf_ndvi 0.45; canopy.veg_ndvi 0.3463; rock.bare_ndvi 0.3463; rock.dark 65.3333; rock.grey_sat 0.1013; rock.ndvi 0.241 |
| 21 | Published figures | ✅ | 4 figures match (Wikipedia: Mount Bohemia; table below) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 11.7 |  |
| Trees (crowns + stems) per km2 | 18,157 | 39,201 |
| Rock share | 0.0% | 1.1% |
| Canopy share | 76% | 66% |
| Canopy on run centre lines | 26.4% | 3.7% |
| Groomed share | 0.0% |  |
| Crowns per km within 5 m of lift lines | 7.3 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 0% |  |
| Far ring crowns | 600,199 |  |
| Mean mogulScore by difficulty | advanced 0.9, expert 0.02, freeride 0.02, intermediate 0.57 | |

**Advanced or harder runs never over 15 deg:** unnamed (advanced, 3 deg), Medicine Man (expert, 6 deg), unnamed (expert, 7 deg), Celestrial Earth (expert, 7 deg), Big Bad Wolf (expert, 8 deg), unnamed (advanced, 8 deg), Plank (advanced, 8 deg), Monkey King (expert, 9 deg), and 19 more

**Lifts with the most crowns on the line:** Honey Pot Hoist (8), Mountain Dew Hoist (3)

## Published figures (gathered 2026-11-14 by published.py)

| Figure | Published | Source | This pack | | Note |
|---|---:|---|---:|---|---|
| Vertical | 245 m (804 ft) | Wikipedia: Mount Bohemia | 246 m (807 ft) | ✅ | +1 m (+0%) |
| Lifts | 1 | Wikipedia: Mount Bohemia | 2 | ✅ | every lift (2 chairs and gondolas) |
| Runs | 95 | Wikipedia: Mount Bohemia | 133 | ✅ | 133 run names over 159 segments, 18 unnamed; 140% of the published count |
| Skiable area | 2.2 km2 (551 acres) | Wikipedia: Mount Bohemia | 1.8 km2 (452 acres) | ✅ | run lines widened 50 m each side, plus the area runs, 0.82 times the published |

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 100 | 3.67 | 8,687 | 58,955 | 18,445 |
| 200 | 3.02 | 12,961 | 47,285 | 19,979 |
| 300 | 4.87 | 21,906 | 59,398 | 16,703 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 48 | 9.7 | 2026-11-14 |
| mid heights | yes | 25 | 4.1 | 2026-11-14 |
| far heights | yes | 16 | 0.5 | 2026-11-14 |
| mask | yes | 12 | 0.7 | 2026-11-14 |
| AO | yes | 12 | 0.8 | 2026-11-14 |
| piste directions | yes | 12 | 0.0 | 2026-11-14 |
| moguls | yes | 12 | 0.0 | 2026-11-14 |
| cover | yes | 4 | 2.4 | 2026-11-14 |
| trees (crowns) | yes | 12 | 1.1 | 2026-11-14 |
| stands (stems) | yes | 12 | 1.8 | 2026-11-14 |
| far tree ring | yes | 161 | 14.4 | 2026-11-14 |
| shrubs | yes | 10 | 0.0 | 2026-11-14 |
| rocks | yes | 10 | 0.0 | 2026-11-14 |
