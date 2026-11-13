# Pack report: Vail (`vail`)

Build `20261113T211158Z-21531e`, pipeline `4db846b`, format 1. Report 2026-11-13T21:12:18Z by `pipeline/pack_report.py` (FEAT-175).

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
| 7 | Trees and shrubs with species | ✅ | 0.52 M crowns + 2.38 M stems = 21.4 k per km2 (55% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 1.31 M crowns in 363 cells |
| 9 | features.json | ✅ | 33 lifts, 356 runs, 2000 buildings, 1408 roads, 42 water, 1321 peaks, 116 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Born Free, top of Born Free Express Lift |
| 11 | In the resort picker | ✅ | in packs/index.json, in the catalog |
| 12 | Time trial courses | ✅ | 184 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 4 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 52% of runs with a grooming record, 41 reports in raw |
| 16 | Place names | ✅ | GNIS CO; 1321 peaks, 116 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3550 m measured; canopy.grow_ndvi 0.15; canopy.leaf_ndvi 0.45; canopy.veg_ndvi 0.3; rock.bare_ndvi 0.3; rock.dark 60.0; rock.grey_sat 0.2; rock.ndvi 0.18; treeline 3550 |
| 21 | Published figures | ✅ | 6 figures match (Wikipedia: Vail Ski Resort; vail.com terrain status, 2026-04-01; table below) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 135.7 |  |
| Trees (crowns + stems) per km2 | 21,394 | 39,201 |
| Rock share | 1.1% | 1.1% |
| Canopy share | 66% | 66% |
| Canopy on run centre lines | 3.7% | 3.7% |
| Groomed share | 3.1% |  |
| Crowns per km within 5 m of lift lines | 13.2 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 52% |  |
| Runs groomed in OSM | 52% |  |
| Far ring crowns | 1,307,506 |  |
| Mean mogulScore by difficulty | advanced 0.47, easy 0.0, expert 0.88, intermediate 0.05 | |

**Advanced or harder runs never over 15 deg:** Windows Road (advanced, 5 deg), Resolution (advanced, 8 deg), Windows Road (advanced, 12 deg), Ptarmigan Ridge (advanced, 14 deg)

**Lifts with the most crowns on the line:** Orient Express Lift (106), Riva Bahn Express Lift (53), Skyline Express Lift (44), Northwoods Express Lift (36), High Noon Express Lift (36)

## Published figures (gathered 2026-11-13 by published.py)

| Figure | Published | Source | This pack | | Note |
|---|---:|---|---:|---|---|
| Summit | 3,527 m (11,572 ft) | Wikipedia: Vail Ski Resort | 3,526 m (11,568 ft) | ✅ | highest of the lift stations, -1 m |
| Base | 2,475 m (8,120 ft) | Wikipedia: Vail Ski Resort | 2,454 m (8,051 ft) | ✅ | lowest of the lift stations, -21 m |
| Vertical | 1,052 m (3,451 ft) | Wikipedia: Vail Ski Resort | 1,072 m (3,517 ft) | ✅ | +20 m (+2%) |
| Lifts | 31 | Wikipedia: Vail Ski Resort | 33 | ✅ | every lift (23 chairs and gondolas) |
| Runs | 195 | Wikipedia: Vail Ski Resort | 216 | ✅ | 216 run names over 356 segments, 65 unnamed; 111% of the published count; of the 277 trails on vail.com terrain status, 2026-04-01, 246 have an OSM run and 31 have none (the OSM to-do below: not mapped in OSM, or named differently); 9 OSM names are not on the list |
| Skiable area | 21.5 km2 (5,318 acres) | Wikipedia: Vail Ski Resort | 17.6 km2 (4,356 acres) | ✅ | run lines widened 50 m each side, plus the area runs, 0.82 times the published |

**OSM to-do: published trails with no OSM run** (31 of 277 on vail.com terrain status, 2026-04-01). Map each one in OpenStreetMap (or fix its name there) and the next build has it; the link opens the editor where the trail's area's other runs are.

| Trail | Area | Difficulty | Where |
|---|---|---|---|
| 10% Road | Game Creek Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.60724/-106.38066) |
| 12 to 1 Connector | Golden Peak | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62856/-106.36203) |
| Buckskin Glade | Mid-Vail | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.62176/-106.36891) |
| Bwana Junction | Lionshead | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Faro Glade | Game Creek Bowl | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.60724/-106.38066) |
| G-Force Alley | Mid-Vail | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.62176/-106.36891) |
| Gillett's Dream | China Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.59903/-106.32901) |
| Grand Junction CW | Golden Peak | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62856/-106.36203) |
| Ha Ha - West | Lionshead | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Headwall Ridge | Sun Up Bowl | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.59756/-106.35080) |
| High Noon Ridge | Sun Up Bowl | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.59756/-106.35080) |
| Highline Runout | North East Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.61159/-106.34606) |
| Inner Mongolia | Mongolia Bowl | advanced |  |
| Lodgepole Gulch | Lionshead | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Lodgepole Gulch Cutoff | Lionshead | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Magic Forest | Lionshead | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Marmot South Gate | Tea Cup Bowl | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.59181/-106.34137) |
| Outer Mongolia | Mongolia Bowl | advanced |  |
| Owl's Roost 1 | Lionshead | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Owl's Roost 2 | Lionshead | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Poker Flats | Game Creek Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.60724/-106.38066) |
| Powerline | Mid-Vail | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.62176/-106.36891) |
| Ricky's Tube | Sun Down Bowl | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.59790/-106.36645) |
| Rip's Ride Teaching Area | Golden Peak | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62856/-106.36203) |
| Spring Catwalk | Lionshead | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62913/-106.38620) |
| Swingsville Ridge | Mid-Vail | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.62176/-106.36891) |
| The Divide Ridge | Blue Sky Basin | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.57473/-106.32699) |
| Timberline Face - East | North East Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.61159/-106.34606) |
| Timberline Face - South | North East Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.61159/-106.34606) |
| Tin Pants Connector | North East Bowl | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61159/-106.34606) |
| Two Elk Ridge | Tea Cup Bowl | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.59181/-106.34137) |

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2400 | 6.34 | 11,812 | 16,239 | 4,424 |
| 2500 | 10.0 | 24,566 | 94,355 | 11,897 |
| 2600 | 8.35 | 28,542 | 119,664 | 17,743 |
| 2700 | 10.03 | 41,517 | 215,417 | 25,623 |
| 2800 | 11.94 | 53,340 | 268,802 | 26,989 |
| 2900 | 13.43 | 59,398 | 276,989 | 25,050 |
| 3000 | 15.39 | 64,063 | 275,264 | 22,046 |
| 3100 | 18.2 | 71,544 | 286,810 | 19,689 |
| 3200 | 17.8 | 72,094 | 329,592 | 22,572 |
| 3300 | 15.26 | 61,041 | 323,798 | 25,216 |
| 3400 | 7.54 | 29,037 | 159,495 | 24,992 |
| 3500 | 1.39 | 4,274 | 15,996 | 14,559 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 529 | 143.3 | 2026-11-13 |
| mid heights | yes | 25 | 12.0 | 2026-11-13 |
| far heights | yes | 16 | 2.8 | 2026-11-13 |
| mask | yes | 144 | 12.2 | 2026-11-13 |
| AO | yes | 144 | 9.3 | 2026-11-13 |
| piste directions | yes | 144 | 0.5 | 2026-11-13 |
| moguls | yes | 144 | 0.3 | 2026-11-13 |
| cover | yes | 4 | 22.3 | 2026-11-13 |
| trees (crowns) | yes | 144 | 12.5 | 2026-11-13 |
| stands (stems) | yes | 144 | 19.3 | 2026-11-13 |
| far tree ring | yes | 363 | 31.4 | 2026-11-13 |
| shrubs | yes | 144 | 1.1 | 2026-11-13 |
| rocks | yes | 143 | 0.6 | 2026-11-13 |
