# Pack report: Copper Mountain (`copper-mountain`)

Build `20261113T072155Z-8a6f55`, pipeline `fa4c657`, format 1. Report 2026-11-13T07:22:08Z by `pipeline/pack_report.py` (FEAT-175).

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
| 5 | Heights fine, mid, far | ✅ | 2948 to 4026 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 1.2% (reference 1.1%), canopy 56% |
| 7 | Trees and shrubs with species | ✅ | 0.18 M crowns + 1.85 M stems = 37.3 k per km2 (95% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.66 M crowns in 258 cells |
| 9 | features.json | ✅ | 23 lifts, 156 runs, 238 buildings, 300 roads, 34 water, 1328 peaks, 154 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Ram's Run, top of Three Bears |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 115 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 1 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS CO; 1328 peaks, 154 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3550 m measured; canopy.grow_ndvi 0.1549; canopy.leaf_ndvi 0.408; canopy.veg_ndvi 0.3; rock.bare_ndvi 0.3; rock.dark 53.6667; rock.grey_sat 0.2; rock.ndvi 0.1937; treeline 3550 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 54.4 |  |
| Trees (crowns + stems) per km2 | 37,320 | 39,201 |
| Rock share | 1.2% | 1.1% |
| Canopy share | 56% | 66% |
| Canopy on run centre lines | 4.8% | 3.7% |
| Groomed share | 0.2% |  |
| Crowns per km within 5 m of lift lines | 5.9 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 2% |  |
| Far ring crowns | 661,825 |  |
| Mean mogulScore by difficulty | advanced 0.49, easy 0.0, expert 0.54, intermediate 0.26, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Boardwalk (advanced, 14 deg)

**Lifts with the most crowns on the line:** Timberline Express (30), Excelerator (15), Woodward Express (14), Super Bee (13), Kokomo Express (11)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2900 | 2.59 | 3,521 | 35,700 | 15,155 |
| 3000 | 5.55 | 18,927 | 214,196 | 42,035 |
| 3100 | 9.46 | 38,779 | 422,725 | 48,808 |
| 3200 | 8.42 | 39,066 | 393,336 | 51,371 |
| 3300 | 6.92 | 34,008 | 337,191 | 53,652 |
| 3400 | 6.79 | 29,438 | 286,814 | 46,573 |
| 3500 | 6.43 | 17,200 | 148,015 | 25,681 |
| 3600 | 4.86 | 2,170 | 9,060 | 2,310 |
| 3700 | 2.45 | 61 | 16 | 31 |
| 3800 | 0.68 | 0 | 0 | 0 |
| 3900 | 0.25 | 6 | 0 | 24 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 224 | 56.7 | 2026-11-13 |
| mid heights | yes | 25 | 11.6 | 2026-11-13 |
| far heights | yes | 16 | 2.8 | 2026-11-13 |
| mask | yes | 56 | 3.8 | 2026-11-13 |
| AO | yes | 56 | 3.9 | 2026-11-13 |
| piste directions | yes | 56 | 0.0 | 2026-11-13 |
| moguls | yes | 56 | 0.4 | 2026-11-13 |
| cover | yes | 4 | 13.1 | 2026-11-13 |
| trees (crowns) | yes | 56 | 4.4 | 2026-11-13 |
| stands (stems) | yes | 56 | 6.2 | 2026-11-13 |
| far tree ring | yes | 258 | 15.9 | 2026-11-13 |
| shrubs | yes | 56 | 0.5 | 2026-11-13 |
| rocks | yes | 54 | 0.3 | 2026-11-13 |
