# Pack report: Beaver Creek Resort (Arrowhead Mountain) (`beaver-creek-resort-arrowhead-mountain`)

Build `20261114T160535Z-be6f5c`, pipeline `30c6fb1`, format 1. Report 2026-11-14T16:05:56Z by `pipeline/pack_report.py` (FEAT-175).

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
| 5 | Heights fine, mid, far | ✅ | 2211 to 3617 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 1.9% (reference 1.1%), canopy 60% |
| 7 | Trees and shrubs with species | ✅ | 0.25 M crowns + 2.09 M stems = 30.2 k per km2 (77% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.99 M crowns in 288 cells |
| 9 | features.json | ✅ | 25 lifts, 311 runs, 2588 buildings, 1721 roads, 54 water, 1248 peaks, 100 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Red Buffalo, top of Cinch Express Lift |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 126 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 3 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 51% of runs with a grooming record, 33 reports in raw |
| 16 | Place names | ✅ | GNIS CO; 1248 peaks, 100 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/beaver-creek-resort-arrowhead-mountain/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | treeline 3525 m measured; canopy.grow_ndvi 0.1138; canopy.leaf_ndvi 0.3333; canopy.veg_ndvi 0.2377; rock.bare_ndvi 0.2377; rock.dark 72.0; rock.grey_sat 0.1884; rock.ndvi 0.1419; treeline 3525 |
| 21 | Published figures | ✅ | 1 figures match (beavercreek.com terrain status, 2026-04-18; table below) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 77.6 |  |
| Trees (crowns + stems) per km2 | 30,174 | 39,201 |
| Rock share | 1.9% | 1.1% |
| Canopy share | 60% | 66% |
| Canopy on run centre lines | 3.8% | 3.7% |
| Groomed share | 4.4% |  |
| Crowns per km within 5 m of lift lines | 10.1 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 51% |  |
| Runs groomed in OSM | 56% |  |
| Far ring crowns | 993,258 |  |
| Mean mogulScore by difficulty | advanced 0.5, easy 0.0, expert 0.45, intermediate 0.1, none 0.0 | |

**Advanced or harder runs never over 15 deg:** West Fall Road (advanced, 7 deg), Upper Stone Creek (expert, 11 deg), Ripsaw (advanced, 12 deg)

**Lifts with the most crowns on the line:** Lower Beaver Creek Mountain Express Lift (48), Rose Bowl Express Lift (41), Centennial Express Lift (38), Upper Beaver Creek Mountain Express Lift (37), Strawberry Park Express Lift (20)

## Published figures (gathered 2026-11-14 by published.py)

| Figure | Published | Source | This pack | | Note |
|---|---:|---|---:|---|---|
| Runs | 181 | beavercreek.com terrain status, 2026-04-18 | 162 | ✅ | 162 run names over 311 segments, 52 unnamed; of the 181 trails on beavercreek.com terrain status, 2026-04-18, 153 have an OSM run and 28 have none (the OSM to-do below: not mapped in OSM, or named differently); 27 OSM names are not on the list |

**OSM to-do: published trails with no OSM run** (28 of 181 on beavercreek.com terrain status, 2026-04-18). Map each one in OpenStreetMap (or fix its name there) and the next build has it; the link opens the editor where the trail's area's other runs are.

| Trail | Area | Difficulty | Where |
|---|---|---|---|
| Anderson's Alley | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| BC Expressway - Lower | Larkspur | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.58465/-106.53660) |
| BC Expressway - Upper | Larkspur | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.58465/-106.53660) |
| Beginner Area Ch. #2 | Beaver Creek Lower | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.59128/-106.51228) |
| Big Bark/Little Bark | Beaver Creek Lower | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.59128/-106.51228) |
| Borders | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Camp Robber RD | Grouse Mountain | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.57652/-106.52492) |
| Creekside | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Gallagher Glade | Arrowhead | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.62205/-106.55600) |
| Golden Eagle Connector | Beaver Creek Lower | advanced | [edit](https://www.openstreetmap.org/edit#map=16/39.59128/-106.51228) |
| Larkspur - Lower | Larkspur | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.58465/-106.53660) |
| Larkspur - Upper | Larkspur | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.58465/-106.53660) |
| Latigo Flats | Beaver Creek Lower | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.59128/-106.51228) |
| Lumber Yard | Beaver Creek Lower | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/39.59128/-106.51228) |
| Park 101 | Beaver Creek Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/39.58387/-106.50626) |
| Pines/Chateau | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Primrose- BG to AH | Larkspur | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.58465/-106.53660) |
| Primrose- Straw. Park to BG | Strawberry Park | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.60119/-106.53081) |
| Primrose-Larkspur to Straw | Strawberry Park | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.60119/-106.53081) |
| Rhubarb | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Ridge Rider | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Ridgepoint | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Ripperoo's Retreat | Rose Bowl | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.58468/-106.50026) |
| Saddleridge Skiway | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Stone Creek Chutes | Rose Bowl | extreme | [edit](https://www.openstreetmap.org/edit#map=16/39.58468/-106.50026) |
| Toyota Race Center | Beaver Creek Lower | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/39.59128/-106.51228) |
| Wampum | Resort Skiways | easy | [edit](https://www.openstreetmap.org/edit#map=16/39.61592/-106.53555) |
| Zoom Room | Beaver Creek Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/39.58387/-106.50626) |

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 2200 | 6.73 | 8,475 | 50,547 | 8,768 |
| 2300 | 7.29 | 11,199 | 90,267 | 13,921 |
| 2400 | 7.83 | 19,368 | 161,373 | 23,084 |
| 2500 | 8.81 | 23,939 | 202,128 | 25,661 |
| 2600 | 7.78 | 24,694 | 234,312 | 33,304 |
| 2700 | 6.51 | 22,099 | 198,354 | 33,885 |
| 2800 | 6.23 | 21,736 | 199,676 | 35,537 |
| 2900 | 5.92 | 19,228 | 189,026 | 35,157 |
| 3000 | 5.25 | 19,621 | 184,473 | 38,859 |
| 3100 | 4.42 | 20,779 | 175,182 | 44,305 |
| 3200 | 4.2 | 22,989 | 182,019 | 48,769 |
| 3300 | 3.85 | 20,836 | 156,809 | 46,160 |
| 3400 | 1.91 | 9,453 | 58,944 | 35,808 |
| 3500 | 0.8 | 2,315 | 11,629 | 17,442 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 304 | 81.9 | 2026-11-14 |
| mid heights | yes | 25 | 11.9 | 2026-11-14 |
| far heights | yes | 16 | 2.8 | 2026-11-14 |
| mask | yes | 80 | 8.5 | 2026-11-14 |
| AO | yes | 80 | 5.5 | 2026-11-14 |
| piste directions | yes | 80 | 0.4 | 2026-11-14 |
| moguls | yes | 80 | 0.2 | 2026-11-14 |
| cover | yes | 4 | 16.5 | 2026-11-14 |
| trees (crowns) | yes | 80 | 5.9 | 2026-11-14 |
| stands (stems) | yes | 80 | 11.5 | 2026-11-14 |
| far tree ring | yes | 288 | 23.8 | 2026-11-14 |
| shrubs | yes | 80 | 0.3 | 2026-11-14 |
| rocks | yes | 80 | 0.7 | 2026-11-14 |
