# Pack report: Deer Valley (`deer-valley`)

Build `20261114T154440Z-bf8262`, pipeline `30c6fb1`, format 1. Report 2026-11-14T15:45:02Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ⚠️ | EPSG:26912 (12N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 14.1% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 1756 to 3047 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 0.6% (reference 1.1%), canopy 46% |
| 7 | Trees and shrubs with species | ⚠️ | 0.28 M crowns + 1.10 M stems = 15.1 k per km2 (39% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.63 M crowns in 190 cells |
| 9 | features.json | ⚠️ | 57 runs without a difficulty; 34 lifts, 388 runs, 2943 buildings, 2320 roads, 29 water, 678 peaks, 147 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Orion, top of Empire Express |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 175 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | canopy 16% on run centre lines (trail cuts missing?); 3 advanced+ runs never over 15 deg; 25 crowns per km within 5 m of lift lines; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ❌ | 0% of runs with a grooming record, 0 reports in raw |
| 16 | Place names | ✅ | GNIS UT, WY; 678 peaks, 147 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/deer-valley/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 2900 m measured; canopy.grow_ndvi 0.08; canopy.leaf_ndvi 0.3; canopy.veg_ndvi 0.2; rock.bare_ndvi 0.2; rock.dark 72.3333; rock.grey_sat 0.0882; rock.ndvi 0.05; treeline 2900 |
| 21 | Published figures | ➖ | no English Wikipedia article with an Infobox ski area for Deer Valley Resort |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 91.0 |  |
| Trees (crowns + stems) per km2 | 15,144 | 39,201 |
| Rock share | 0.6% | 1.1% |
| Canopy share | 46% | 66% |
| Canopy on run centre lines | 15.6% | 3.7% |
| Groomed share | 0.0% |  |
| Crowns per km within 5 m of lift lines | 24.9 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 0% |  |
| Runs groomed in OSM | 0% |  |
| Far ring crowns | 630,497 |  |
| Mean mogulScore by difficulty | advanced 0.42, easy 0.0, expert 0.55, freeride 0.15, intermediate 0.2, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Pick Axe (freeride, 11 deg), Boulder Bumps (advanced, 14 deg), Anchor Treess (advanced, 15 deg)

**Lifts with the most crowns on the line:** East Village Gondola II (93), Keetley Express (66), Vulcan Express (63), Sultan Express (55), Pioche Express (51)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 1700 | 2.06 | 5,157 | 10,609 | 7,643 |
| 1800 | 6.05 | 7,807 | 8,760 | 2,736 |
| 1900 | 8.04 | 22,432 | 11,894 | 4,271 |
| 2000 | 6.02 | 24,573 | 21,734 | 7,686 |
| 2100 | 7.97 | 24,925 | 59,424 | 10,579 |
| 2200 | 10.19 | 37,879 | 78,101 | 11,377 |
| 2300 | 8.98 | 38,951 | 99,401 | 15,407 |
| 2400 | 9.42 | 31,429 | 167,884 | 21,157 |
| 2500 | 10.36 | 29,270 | 230,300 | 25,048 |
| 2600 | 10.87 | 28,913 | 252,282 | 25,873 |
| 2700 | 8.1 | 17,863 | 126,343 | 17,795 |
| 2800 | 2.37 | 6,300 | 32,677 | 16,438 |
| 2900 | 0.44 | 737 | 2,031 | 6,292 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 360 | 96.8 | 2026-11-14 |
| mid heights | yes | 25 | 11.4 | 2026-11-14 |
| far heights | yes | 16 | 2.3 | 2026-11-14 |
| mask | yes | 90 | 11.5 | 2026-11-14 |
| AO | yes | 90 | 6.1 | 2026-11-14 |
| piste directions | yes | 90 | 0.0 | 2026-11-14 |
| moguls | yes | 90 | 0.5 | 2026-11-14 |
| cover | yes | 4 | 14.4 | 2026-11-14 |
| trees (crowns) | yes | 100 | 6.6 | 2026-11-14 |
| stands (stems) | yes | 100 | 11.1 | 2026-11-14 |
| far tree ring | yes | 190 | 15.1 | 2026-11-14 |
| shrubs | yes | 100 | 0.6 | 2026-11-14 |
| rocks | yes | 100 | 0.4 | 2026-11-14 |
