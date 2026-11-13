# Pack report: Heavenly Mountain (`heavenly`)

Build `20261113T080524Z-de30c9`, pipeline `6d6c981`, format 1. Report 2026-11-13T08:05:41Z by `pipeline/pack_report.py` (FEAT-175).

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
| 1 | Resort config | ⚠️ | EPSG:26911 (11N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ⚠️ | EVT, EVC and EVH; 41.2% of the forest in EVT classes the species rules don't name (west rules): over 20%, map them in species.classify_evt |
| 5 | Heights fine, mid, far | ✅ | 1790 to 3066 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 2.2% (reference 1.1%), canopy 54% |
| 7 | Trees and shrubs with species | ✅ | 0.20 M crowns + 1.58 M stems = 27.2 k per km2 (69% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.50 M crowns in 174 cells |
| 9 | features.json | ⚠️ | 9 runs without a difficulty; 24 lifts, 173 runs, 2087 buildings, 1798 roads, 20 water, 912 peaks, 183 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Skyline Trail, top of Sky Express |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 99 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 1 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 35% of runs with a grooming record, 37 reports in raw |
| 16 | Place names | ✅ | GNIS CA, NV; 912 peaks, 183 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 2800 m measured; canopy.grow_ndvi 0.08; canopy.leaf_ndvi 0.3; canopy.veg_ndvi 0.2; rock.bare_ndvi 0.2; rock.dark 90.0; rock.grey_sat 0.05; rock.ndvi 0.0745; treeline 2800 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 65.5 |  |
| Trees (crowns + stems) per km2 | 27,222 | 39,201 |
| Rock share | 2.2% | 1.1% |
| Canopy share | 54% | 66% |
| Canopy on run centre lines | 2.9% | 3.7% |
| Groomed share | 3.1% |  |
| Crowns per km within 5 m of lift lines | 12.9 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 35% |  |
| Runs groomed in OSM | 57% |  |
| Far ring crowns | 499,456 |  |
| Mean mogulScore by difficulty | advanced 0.39, easy 0.0, expert 0.1, intermediate 0.14, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Mott Canyon Trail (advanced, 12 deg)

**Lifts with the most crowns on the line:** Heavenly Gondola (68), Mott Canyon (37), Gunbarrel Express (30), Stagecoach Express (25), North Bowl Express (23)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 1800 | 2.23 | 1,722 | 10,226 | 5,355 |
| 1900 | 12.98 | 37,237 | 264,918 | 23,285 |
| 2000 | 7.55 | 24,358 | 179,276 | 26,970 |
| 2100 | 6.89 | 21,747 | 186,608 | 30,233 |
| 2200 | 6.52 | 18,920 | 173,132 | 29,453 |
| 2300 | 5.08 | 16,467 | 146,252 | 32,014 |
| 2400 | 5.49 | 18,163 | 161,890 | 32,822 |
| 2500 | 4.99 | 17,922 | 146,191 | 32,892 |
| 2600 | 5.4 | 17,472 | 145,513 | 30,170 |
| 2700 | 4.12 | 14,446 | 103,320 | 28,577 |
| 2800 | 2.61 | 8,831 | 47,563 | 21,581 |
| 2900 | 1.39 | 4,268 | 14,758 | 13,737 |
| 3000 | 0.27 | 663 | 1,707 | 8,820 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 272 | 70.8 | 2026-11-13 |
| mid heights | yes | 25 | 8.8 | 2026-11-13 |
| far heights | yes | 16 | 2.6 | 2026-11-13 |
| mask | yes | 72 | 11.2 | 2026-11-13 |
| AO | yes | 72 | 4.6 | 2026-11-13 |
| piste directions | yes | 72 | 0.3 | 2026-11-13 |
| moguls | yes | 72 | 0.1 | 2026-11-13 |
| cover | yes | 4 | 15.5 | 2026-11-13 |
| trees (crowns) | yes | 70 | 4.9 | 2026-11-13 |
| stands (stems) | yes | 70 | 9.2 | 2026-11-13 |
| far tree ring | yes | 174 | 12.0 | 2026-11-13 |
| shrubs | yes | 72 | 0.2 | 2026-11-13 |
| rocks | yes | 70 | 0.8 | 2026-11-13 |
