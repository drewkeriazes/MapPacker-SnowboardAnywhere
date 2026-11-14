# Pack report: Whistler Blackcomb (`whistler-blackcomb`)

Build `20261114T090322Z-76474b`, pipeline `e0e0036`, format 1. Report 2026-11-14T09:03:59Z by `pipeline/pack_report.py` (FEAT-175).

**Tier: bronze** (FEAT-225: the weakest layer's)

| Layer | Source | Tier |
|---|---|---|
| terrain | Mapterhorn z15, 1.5 m | silver |
| trees | stands from ETH canopy height + WorldCover | silver |
| surface | WorldCover 10 m | bronze |

**Preview**: MVP lines 8b hold it back.

| # | Item | | Detail |
|---|---|---|---|
| F | Pack format current | ✅ | formatVersion 1 |
| 1 | Resort config | ⚠️ | EPSG:32610 (10N); no start_run |
| 2 | Raw: DEMs, lidar, NAIP, Mapterhorn, OSM | ✅ | all present |
| 3 | Raw: land cover and pistes_wide | ✅ | all present |
| 4 | Raw: LANDFIRE | ⚠️ | outside the US, where LANDFIRE has no data: species from elevation and aspect only (FEAT-225) |
| 5 | Heights fine, mid, far | ✅ | 630 to 2431 m, void 0.00% inside the bounds |
| 6 | Surface: mask, AO, directions, moguls, rocks | ⚠️ | rock 6.6% (reference 1.1%), canopy 68% : more rock than the reference by over 3x, check the thresholds (FEAT-175 step 2) |
| 7 | Trees and shrubs with species | ✅ | 0.00 M crowns + 4.11 M stems = 30.6 k per km2 (78% of the reference) (no lidar: every tree is a stand stem, from the ETH canopy height) |
| 8 | Far terrain: cover levels pack, mid, far | ✅ | three levels |
| 8b | Far tree ring (lidar crowns round the resort) | ❌ | none: no lidar for a far ring at this tier, so the ridges round the resort keep the land cover alone (FEAT-225) |
| 9 | features.json | ⚠️ | 92 runs without a difficulty; 1 of 25 chairs and gondolas without towers; 35 lifts, 921 runs, 3148 buildings, 3029 roads, 77 water, 1106 peaks, 0 labels |
| 10 | Default start on a run, on snow, clear of trees | ✅ | generated (gen_content.py) on Showcase, top of Showcase Quad |
| 11 | In the resort picker | ✅ | in packs/index.json |
| 12 | Time trial courses | ✅ | 313 runs of 300 m and 60 m drop or more |
| 13 | Attribution for every data set | ✅ | 5 lines |
| 14 | Validated | ⚠️ | canopy 25% on run centre lines (trail cuts missing?); 20 advanced+ runs never over 15 deg; ride from the start and views from the top not checked here (shoot.mjs) |
| | **Polish (not gated)** | | |
| 15 | Grooming history | ✅ | 20% of runs with a grooming record, 46 reports in raw |
| 16 | Place names | ❌ | no GNIS file in raw/names; 1106 peaks, 0 town labels |
| 17 | Main menu shot and ghosts | ⚠️ | generated (gen_content.py): 5 shots, no still of this build, 0 ghost takes (the game's tools/auto_attract.mjs makes them) |
| 18 | Landmark | ❌ | none (optional: resorts/whistler-blackcomb/landmarks.json) |
| 19 | Compare spots against photos | ➖ | no SnowboardAnywhere checkout at /home/runner/work/MapPacker-SnowboardAnywhere/SnowboardAnywhere (--game-repo or SBA_GAME_REPO) |
| 20 | Values derived for the resort, not copied from Vail | ❌ | treeline 1800 m measured; treeline 1800; rock and canopy thresholds are Vail's (FEAT-175 step 2) |
| 21 | Published figures | ✅ | 1 figures match (whistlerblackcomb.com terrain status, 2026-04-02; table below) |

## Numbers (reference: vail `20261111T145558Z-c2847e`)

| Measure | This pack | Reference |
|---|---:|---:|
| Area, km2 | 134.5 |  |
| Trees (crowns + stems) per km2 | 30,586 | 39,201 |
| Rock share | 6.6% | 1.1% |
| Canopy share | 68% | 66% |
| Canopy on run centre lines | 25.4% | 3.7% |
| Groomed share | 3.0% |  |
| Runs with a grooming record | 20% |  |
| Runs groomed in OSM | 42% |  |
| Far ring crowns | 0 |  |
| Mean mogulScore by difficulty | advanced 0.55, easy 0.0, expert 0.65, freeride 0.36, intermediate 0.17, none 0.0, novice 0.0 | |

**Advanced or harder runs never over 15 deg:** Poler's Descent (advanced, 7 deg), Upper Panorama (advanced, 8 deg), Sapphire Traverse (expert, 8 deg), Upper Fairway (advanced, 9 deg), Poler's Descent (advanced, 9 deg), Upper Panorama (advanced, 10 deg), Middle Fairway (advanced, 10 deg), Croweman's Challenge (advanced, 10 deg), and 12 more

## Published figures (gathered 2026-11-14 by published.py)

| Figure | Published | Source | This pack | | Note |
|---|---:|---|---:|---|---|
| Runs | 303 | whistlerblackcomb.com terrain status, 2026-04-02 | 576 | ✅ | 576 run names over 921 segments, 118 unnamed; of the 303 trails on whistlerblackcomb.com terrain status, 2026-04-02, 266 have an OSM run and 37 have none (the OSM to-do below: not mapped in OSM, or named differently); 354 OSM names are not on the list |

**OSM to-do: published trails with no OSM run** (37 of 303 on whistlerblackcomb.com terrain status, 2026-04-02). Map each one in OpenStreetMap (or fix its name there) and the next build has it; the link opens the editor where the trail's area's other runs are.

| Trail | Area | Difficulty | Where |
|---|---|---|---|
| Adult Learning | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Animal Adventure Trail | Excalibur / Blackcomb Gondola - Lower | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.10868/-122.92631) |
| Base 2 Carpet | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Bean Bowl | Big Red / Garbanzo / Village Gondola - Upper | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.07960/-122.95812) |
| Blackcomb Base - Whistler Kids Only | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Blackcomb Race Centre | Jersey Cream | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.10074/-122.90019) |
| Bobcat Park | Emerald / Garbanzo / Village Gondola - Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/50.07953/-122.94292) |
| CLC - Whistler Kids Only | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Camel Humps | Harmony | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.06237/-122.93725) |
| Chipmunk Park | Emerald / Garbanzo / Village Gondola - Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/50.07953/-122.94292) |
| Choker | Excelerator / Catskinner / Blackcomb Gondola - Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Creekside Base - Whistler Kids Only | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Enchanted Forest - Adventure Trail | Emerald / Garbanzo / Village Gondola - Upper | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.07953/-122.94292) |
| Entrance to Blackcomb Glacier | Glacier / Showcase T-bar | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.09889/-122.88648) |
| Entrance to Grey Zone | Glacier / Showcase T-bar | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.09889/-122.88648) |
| Flute Bowl | Symphony | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.05297/-122.92900) |
| Flute Road | Symphony | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.05297/-122.92900) |
| Glissando | Symphony | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.05297/-122.92900) |
| Grey Line | Excelerator / Catskinner / Blackcomb Gondola - Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Harmony Horseshoes | Harmony | expert | [edit](https://www.openstreetmap.org/edit#map=16/50.06237/-122.93725) |
| Highest Level | Excelerator / Catskinner / Blackcomb Gondola - Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Magic Castle | Excelerator / Catskinner / Blackcomb Gondola - Upper | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Magic Castle - Blue | Excelerator / Catskinner / Blackcomb Gondola - Upper | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Magic Castle - Green | Excelerator / Catskinner / Blackcomb Gondola - Upper | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Mini Pipe | Excelerator / Catskinner / Blackcomb Gondola - Upper | terrain park | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Piccolo Face | Symphony | expert | [edit](https://www.openstreetmap.org/edit#map=16/50.05297/-122.92900) |
| Rock & Roll - Lower | Crystal Ridge | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.11326/-122.89751) |
| Rock & Roll -Upper | Crystal Ridge | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.11326/-122.89751) |
| Sea to Sky Railway | Excelerator / Catskinner / Blackcomb Gondola - Upper | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Secret Bassin | Glacier / Showcase T-bar | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.09889/-122.88648) |
| Slingshot Connector | Excelerator / Catskinner / Blackcomb Gondola - Upper | intermediate | [edit](https://www.openstreetmap.org/edit#map=16/50.10354/-122.91448) |
| Snowboard Carpet | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Spankys Ladder | Glacier / Showcase T-bar | expert | [edit](https://www.openstreetmap.org/edit#map=16/50.09889/-122.88648) |
| Super Carpet | Learning Areas | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.09641/-122.94787) |
| Sylvain | Glacier / Showcase T-bar | expert | [edit](https://www.openstreetmap.org/edit#map=16/50.09889/-122.88648) |
| T-Bar Bowl | Peak / T-bar | advanced | [edit](https://www.openstreetmap.org/edit#map=16/50.06362/-122.96504) |
| Tree Fort | Big Red / Garbanzo / Village Gondola - Upper | easy | [edit](https://www.openstreetmap.org/edit#map=16/50.07960/-122.95812) |

## Trees by elevation band

| Band, m | Area, km2 | Crowns | Stems | Per km2 |
|---|---:|---:|---:|---:|
| 600 | 10.95 | 0 | 297,559 | 27,169 |
| 700 | 6.19 | 0 | 239,047 | 38,593 |
| 800 | 6.73 | 0 | 275,299 | 40,893 |
| 900 | 6.8 | 0 | 296,519 | 43,636 |
| 1000 | 8.08 | 0 | 342,579 | 42,399 |
| 1100 | 7.54 | 0 | 302,565 | 40,127 |
| 1200 | 7.91 | 0 | 324,024 | 40,986 |
| 1300 | 8.75 | 0 | 372,077 | 42,529 |
| 1400 | 9.11 | 0 | 371,147 | 40,754 |
| 1500 | 10.0 | 0 | 380,242 | 38,036 |
| 1600 | 10.31 | 0 | 375,055 | 36,392 |
| 1700 | 9.83 | 0 | 303,778 | 30,896 |
| 1800 | 9.56 | 0 | 156,598 | 16,385 |
| 1900 | 7.8 | 0 | 65,780 | 8,432 |
| 2000 | 5.02 | 0 | 9,133 | 1,819 |
| 2100 | 5.07 | 0 | 991 | 196 |
| 2200 | 3.34 | 0 | 856 | 256 |
| 2300 | 1.47 | 0 | 1,101 | 751 |

## Layers

| Layer | In meta | Files | MB | Modified |
|---|---|---:|---:|---|
| fine heights | yes | 552 | 121.2 | 2026-11-14 |
| mid heights | yes | 25 | 12.0 | 2026-11-14 |
| far heights | yes | 16 | 2.9 | 2026-11-14 |
| mask | yes | 144 | 4.1 | 2026-11-14 |
| AO | yes | 144 | 4.9 | 2026-11-14 |
| piste directions | yes | 144 | 0.8 | 2026-11-14 |
| moguls | yes | 144 | 0.3 | 2026-11-14 |
| cover | yes | 4 | 11.1 | 2026-11-14 |
| trees (crowns) | no | 0 | 0.0 |  |
| stands (stems) | yes | 142 | 13.9 | 2026-11-14 |
| far tree ring | no | 0 | 0.0 |  |
| shrubs | yes | 114 | 0.3 | 2026-11-14 |
| rocks | yes | 115 | 5.2 | 2026-11-14 |
