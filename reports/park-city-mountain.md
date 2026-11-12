# Pack report: Park City Mountain (`park-city-mountain`)

Build `20261112T165956Z-1e47fa`, pipeline `039b9a7`, format 1. Report 2026-11-12T17:04:46Z by `pipeline/pack_report.py` (FEAT-175).

**Playable**: every DATA-022 MVP line passes.

| # | Item | | Detail |
|---|---|---|---|
| F | Pack format current | ✅ | formatVersion 1 |
| 1 | Resort config | ✅ | EPSG:26912 (12N) |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ✅ | EVT, EVC and EVH; 7.2% of the forest in EVT classes the species rules don't name (west rules) |
| 5 | Heights fine, mid, far | ✅ | 1952 to 3174 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ✅ | rock 1.7% (reference 1.1%), canopy 24% |
| 7 | Trees and shrubs with species | ⚠️ | 0.25 M crowns + 1.52 M stems = 13.4 k per km2 (34% of the reference) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ✅ | 0.14 M crowns in 82 cells |
| 9 | features.json | ⚠️ | 42 runs without a difficulty; 41 lifts, 608 runs, 6190 buildings, 5063 roads, 94 water, 681 peaks, 146 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Panorama, top of Dreamscape |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 309 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 9 lines |
| 14 | Validated | ⚠️ | 14 advanced+ runs never over 15 deg; 10 compare spots measured; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 37% of runs with a grooming record, 44 reports in raw |
| 16 | Place names | ✅ | GNIS UT, WY; 681 peaks, 146 town labels |
| 17 | Main menu shot and ghosts | ✅ | generated (gen_content.py): 5 shots, a still of this build, 6 ghost takes |
| 18 | Landmark | ❌ | none (optional) |
| 19 | Compare spots against photos | ⚠️ | 0 spots with Street View in docs/compare/park-city-mountain, 10 proposed waiting for a Street View link (propose_spots.py) |
| 20 | Values derived for the resort, not copied from Vail | ✅ | no treeline: forested to the top of the box (measured); canopy.grow_ndvi 0.08; canopy.leaf_ndvi 0.3077; canopy.veg_ndvi 0.2; rock.bare_ndvi 0.2; rock.dark 81.6667; rock.grey_sat 0.05; rock.ndvi 0.0647 |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 131.8 |  |
| Trees (crowns + stems) per km2 | 13,449 | 39,201 |
| Rock share | 1.7% | 1.1% |
| Canopy share | 24% | 66% |
| Canopy on run centre lines | 3.3% | 3.7% |
| Groomed share | 3.7% |  |
| Crowns per km within 5 m of lift lines | 9.6 |  |
| Stems per km within 5 m of lift lines | 0.0 |  |
| Runs with a grooming record | 37% |  |
| Runs groomed in OSM | 37% |  |
| Far ring crowns | 142,813 |  |
| Mean mogulScore by difficulty | advanced 0.52, easy 0.0, expert 0.67, freeride 0.3, intermediate 0.09, none 0.0 | |

**Advanced or harder runs never over 15 deg:** Ligity Split (advanced, 8 deg), Barrel Roll (advanced, 9 deg), Nowhere Elks (advanced, 9 deg), unnamed (expert, 10 deg), Farm Nordic Trail (advanced, 10 deg), Sleep Walker (advanced, 11 deg), Illusion (advanced, 11 deg), Crescent Ridge (freeride, 11 deg), and 6 more

**Lifts with the most crowns on the line:** Quicksilver Gondola (46), Payday Hi-Speed Six-Pack (39), Motherlode Express (32), Sunrise Gondola (25), Town Lift (24)

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 1900 | 7.1 | 4,089 | 38,979 | 6,066 |
| 2000 | 16.89 | 22,755 | 201,874 | 13,300 |
| 2100 | 10.55 | 17,694 | 152,038 | 16,086 |
| 2200 | 8.33 | 18,253 | 151,321 | 20,366 |
| 2300 | 8.41 | 18,591 | 131,180 | 17,800 |
| 2400 | 11.02 | 24,174 | 138,020 | 14,715 |
| 2500 | 13.21 | 28,117 | 144,957 | 13,102 |
| 2600 | 17.57 | 39,553 | 202,162 | 13,759 |
| 2700 | 17.94 | 35,383 | 174,135 | 11,676 |
| 2800 | 13.05 | 25,741 | 122,459 | 11,356 |
| 2900 | 6.36 | 10,919 | 53,784 | 10,177 |
| 3000 | 1.22 | 1,989 | 11,571 | 11,122 |

## Compare spots: trees per hectare within 100 m

| Spot | Trees per ha |
|---|---:|
| 10420 | 200 |
| base-of-eagle-lift | 35 |
| base-of-orange-bubble-express | 21 |
| base-of-tombstone-express | 183 |
| scott-hill | 23 |
| top-of-jupiter-lift | 236 |
| top-of-mcconkey-s-hi-speed-six-pack | 71 |
| top-of-ninety-nine-90-express | 4 |
| top-of-peak-5 | 84 |
| top-of-pioneer-lift | 137 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 528 | 136.2 | 2026-11-12 |
| mid heights | yes | 25 | 11.7 | 2026-11-12 |
| far heights | yes | 16 | 2.3 | 2026-11-12 |
| mask | yes | 132 | 17.3 | 2026-11-12 |
| AO | yes | 132 | 8.7 | 2026-11-12 |
| piste directions | yes | 132 | 0.6 | 2026-11-12 |
| moguls | yes | 132 | 0.5 | 2026-11-12 |
| cover | yes | 4 | 16.0 | 2026-11-12 |
| trees (crowns) | yes | 124 | 5.9 | 2026-11-12 |
| stands (stems) | yes | 124 | 12.4 | 2026-11-12 |
| far tree ring | yes | 82 | 3.4 | 2026-11-12 |
| shrubs | yes | 125 | 0.3 | 2026-11-12 |
| rocks | yes | 139 | 1.4 | 2026-11-12 |
