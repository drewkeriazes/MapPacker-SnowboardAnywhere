# Resort pack format v1

The pack format is the contract between this repo, which builds packs, and SnowboardAnywhere, which plays them
(EPIC-16). This spec lives with the producer (FEAT-239); the game's `docs/pack-format.md` points here. Paths are
this repo's, except those under `game/`, which are the game's. [Contract](#contract) lists the values both sides
must agree on, [formatVersion](#formatversion) the bump rule.

A pack is a static folder served over HTTP. Everything is in **local metres**: x east, y north, z up,
relative to `meta.origin` (a UTM easting/northing). The client never touches lat/lon.

```
pack/<slug>/
  meta.json
  fine/<tx>_<ty>.png        1 m heights, 512 x 512 samples per tile, resort area only
  coarse/<tx>_<ty>.png      4 m heights, 512 x 512 samples per tile, over the fine area (optional, FEAT-229)
  mid/<tx>_<ty>.png         16 m heights, 512 x 512 samples per tile, 40 km square
  far/<tx>_<ty>.png         128 m heights, 512 x 512 samples per tile, 262 km square
  mask/<tx>_<ty>.png        2 m RGBA surface classes, 512 x 512 per tile, resort area
  ao/<tx>_<ty>.png          2 m greyscale sky visibility (baked AO), same grid as mask (optional)
  dir/<tx>_<ty>.png         2 m greyscale piste direction (groomed run axis), same grid as mask (optional)
  cover/<level>.png         RGBA forest cover for the terrain at a distance, one image per level (optional)
  trees/<tx>_<ty>.bin       tree instances per 1 km cell (the detected crowns)
  stands/<tx>_<ty>.png      stand density per 4 m cell, one RGB image per 1 km tree cell (optional, FEAT-074)
  farTrees/<tx>_<ty>.bin    the lidar crowns on the ridges round the resort, outside the bounds (optional, BUG-081)
  rocks/<tx>_<ty>.bin       rock instances per 1 km cell
  features.json             lifts, runs, buildings, roads, water, peaks, labels
  report.json, report.md    the DATA-022 scorecard from pipeline/pack_report.py (optional, not read by the game)
  attract/                  the main menu's shots, still and ghost takes (optional, FEAT-175: generated)
```

## Height tiles (Terrarium RGB)

Outside the US (FEAT-225) `fine` and `mid` come from Mapterhorn instead of 3DEP, at the zoom `resort.py plan` picked (about
0.8 m for z16 at 47 degrees); same encoding and grids.

8-bit RGB PNG, `h = (R * 256 + G + B / 256) - 32768` metres (1/256 m precision, same scheme as
Mapterhorn so the far ring can be re-encoded without loss). Pixel (0,0) is the **north-west**
corner (image row 0 = max y), so `y = tileMaxY - row * res`, `x = tileMinX + col * res`.
Tiles abut without overlap; a sampler reads the neighbour tile across an edge.

`meta.terrain.<set>` gives for each set: `res`, `tileSize` (512), `minX`, `minY` (lower-left of
tile (0,0) in local metres), `tilesX`, `tilesY`. Tile `<tx>_<ty>` covers
`x in [minX + tx*size, minX + (tx+1)*size)`, `y in [minY + ty*size, ...)` with `size = res*tileSize`.
Void samples are encoded as height -32768 (R=G=B=0) and must be treated as "no data".

`coarse` (FEAT-229, optional, `pipeline/coarse_set.py`) is a 4 m set over the fine set's area, with the fine
set's `minX`, `minY` (2 km tiles): each sample is the mean of the 4 x 4 fine samples it covers, void ones left out,
so its centre is at `minX + (i + 0.5) * 4` like any set's. The game's 4 and 8 m terrain chunks read it instead of
the 1 m tiles (only 1 and 2 m chunks and physics load `fine`); a pack without it behaves as before. Vail: 36 tiles,
14 MB, against 529 fine tiles, 143 MB. At the Vail start the 4 and 8 m chunks (about 350 m to 1.7 km out) then load
6 coarse tiles instead of 40 fine ones, and look the same. Add it to a built pack: `python pipeline/coarse_set.py packs/<slug>`.

## Mask tiles

RGBA PNG at 2 m. R = rock (0..255), G = scree/talus, B = groomed piste, A = canopy cover.
Snow is implicit: `snow = 1 - max(rock, scree)`. Alpha drives forest-floor darkening and
snow-depth reduction under trees.

R is rock the imagery saw (full weight on steep bare ground, half on grey rock on gentler slopes),
softened over about 2 m; it carries no slope-only term. The renderer adds rock on faces steeper than
about 45 degrees, on wind-scoured ridges and talus below cliffs, and thresholds the weights against
noise so rock shows as crisp patches (FEAT-020). Packs built before FEAT-020 put 0.3 to 0.6 rock on
every 30 to 40 degree slope and should be rebuilt.

## AO tiles (optional)

Greyscale PNG on the mask grid: sky visibility 0..255 from `pipeline/terrain_ao.py` (16 directions,
horizon angles up to 170 m measured above the cell's tangent plane, visibility `1 - sin(h)`).
Planar slopes and ridges are 255; gullies, couloirs, cirques and cliff feet are darker. Padding
outside the data is 255. The terrain uses it for chunks at 32 m or finer; packs without it render
with open sky everywhere.

## Piste direction tiles (optional)

Greyscale PNG on the mask grid from `pipeline/piste_dir.py` (DATA-002): the axis a groomer drives
along, so corduroy follows the run and not the raw fall line (a traversing cat track has ridges along
the track). Byte 0 = no direction; 1..255 = axis angle `(byte - 1) / 254 * 180` degrees from east
toward north, in [0, 180). The axis is undirected; the client picks the downhill sense from the
heights. Every cell takes the nearest groomed centre line's segment direction (doubled-angle field,
blurred 6 m across polyline kinks), kept where the mask is groomed or within 30 m of a groomed run.
Padding and everything else is 0. Packs built before DATA-002 lack it; add it without a rebuild with
`python pipeline/piste_dir.py packs/<slug>` (reads `features.json` and the mask tiles).
## Mogul tiles (optional, FEAT-059)

Greyscale PNG on the mask grid: mogul field strength 0..255 = 0..1 from `pipeline/moguls.py` (read as metres
of amplitude before FEAT-147; the client now sizes the bumps from the slope, see below). Each run's
`mogulScore` is painted along its corridor (fading over the outer 3 m, where real bumps shrink; closed
`area` runs are filled), times a slope window (none below 15 degrees, full 20 to 35, none above 40),
and removed under canopy, on groomed corduroy, built-up ground and rock. Padding outside the data is 0.
The client turns the strength into bumps cut by rider lines down the fall line (`game/src/terrain/Moguls.ts`,
FEAT-147: 4 to 7 m apart along a line, about 0.55 m per unit strength at 16 degrees up to 1.38 m at 32 degrees
and steeper, each bump +-30%, at most 1.8 m; the pattern changes every 80 m) in both the physics height and
the near terrain mesh (chunks at 2 m or finer), and shades
the same field per pixel in the terrain shader on every chunk up to 16 m (BUG-062: the bump normal and a
relief colouring from the bump's own height and slope). Packs without the set have no bumps.

## Cover levels (optional, FEAT-153)

One RGBA PNG per level from `pipeline/cover.py`, each over its own rectangle (image row 0 = north):
R = forest, the share of the cell under closed canopy 0..255 = 0..1; G = canopy height of the forested
part, 0..255 = 0..`heightMax` m; B = rock / bare ground, the mask's rock weight (0.5 is where patches
start); A = 255 minus built-up (inverted so a decoder that premultiplies alpha keeps RGB). The `pack`
level is 4 m over the pack bounds: the 2 m mask's canopy, contrast-lifted as the shader lifts the
under-detected lidar canopy (0.08 to 0.45) and then box-averaged, with the pack's OSM runs burned in as
cleared strips (areas filled, lines at 0.6 of their corridor width; gladed runs keep their trees), the
mask's rock, and the mean tree height per 16 m from the tree instances. The forest is then weighted by
the pack's tree instances (BUG-069), so a sparse stand the lidar canopy reads as closed is not a dark patch
around its few trees. R, the forest seen from far off, is weighted by the share of the ground under the
detected crowns (averaged over 16 m, full weight from 0.05 up, a quarter of the 0.2 all drawn trees reach in timber;
BUG-120: before, it counted the generated stems in expectation, which now fill closed stands only). The level's optional `stands` image (greyscale, same
grid, `cover/pack-stands.png`) is the forest seen from near, where single trees show: only closed stands
keep it (the detected trees' crown share averaged over 10 m passes 0.05 to 0.14, and the stand is at least 40 m across:
smaller clumps are dropped, holes that size inside a stand filled; BUG-101: the generated stems do not count here,
the thresholds were tuned without them; a pack without lidar, FEAT-225, has no detected trees and reads its stems at a
quarter of their share, the part the detected crowns are of all drawn trees on Vail; it reads R from them the same way). The shader shows `stands` to 1.2 km and
R from 2.8 km, and (game BUG-120) `stands` as far as it draws the generated stems (2.5 km on High), R from 1.5 times that. With `"crowns": true` on the level the image is RGB and its G is where the drawn trees
stand: the share of each cell under their crowns, each tree weighted by its height over 12 m (FEAT-168; the
shader throws their shadows on the snow from it). A pack without tree instances keeps the canopy as is.

The `mid` (16 m over the mid height grid, 40 km) and `far` (100 m over the far ring's data, 200 km) levels
come from the land cover (DATA-019): ESA WorldCover 2021 classes and the ETH 2020 canopy height, read on a
4 x 4 (mid) or 3 x 3 (far) sub-grid per cell. R is the share of sub-samples that are WorldCover tree cover
(class 10) and at least 3 m tall in ETH; G the mean ETH height of those, averaged over about 3 cells; B the
bare / sparse share (class 60) times 0.6, since snow covers the gentler part; A from built-up (class 50).
The downhill pistes of every resort in view (`osm/pistes_wide.json`) are burned in as cleared sub-samples,
so Beaver Creek's and Copper's trails show. G, B and A are quantised (2.5 m, 1/8, 1/4) to keep the files
small. Without `raw/<slug>/landcover/` the build skips these two levels.

When a pack level exists, R of `mid` and `far` is calibrated to the lidar forest (BUG-081): a lookup on the
WorldCover share (blurred over 16 m) and how south-facing the cell is (from the level's own height set), fitted
per pack on the cells at least `blend` m inside the pack bounds (and the far tree ring's cells, below), then
stored in 1/32 steps. WorldCover calls a 10 m pixel tree cover from about 10% canopy; on a current Vail build
(stems counted, FEAT-074) it reads 0.75 where the lidar forest is 0.71, and 0.65 against 0.57 on south faces.
The share hands over to the pack level at its edge without a step. The build log prints the fit by aspect.

In the far tree ring (`farTrees/`, below) R of `mid` and `far` comes from the lidar crowns instead of the land
cover: the drawn crowns' share of each cell (the pack's and the ring's, averaged over 16 m) mapped onto the pack
level's R by the same kind of lookup, fitted where the pack's own crowns and its R overlap (so a ring crown counts
for the stems a pack stand would have), with G from the crowns' heights. It fades to the calibrated land cover
over `blend` m inside the ring's outer edge (`instances.farTreeBox`).

The terrain shader samples R per pixel from a mipmapped GPU texture past about 300 m, so a trail
narrower than a far chunk's vertex spacing still shows as a white cut; chunks coarser than 8 m take all
four channels per vertex (forest, rock, and the canopy lift past the instanced trees). Finer levels fade
in over `blend` metres inside their edges; outside every level the terrain keeps the procedural
treeline. Add it to a built pack without a rebuild: `python pipeline/cover.py <slug> <raw_dir> packs/<slug>`.

## Instances

`trees/<tx>_<ty>.bin`: little-endian Float32 records of 6:
`x, y, z, height, crownRadius, species`. Packs with `meta.treeSpecies` 3 (FEAT-233) use ids 0 to 9, with
`treeSpecies` 2 (DATA-020) ids 0 to 7; older packs have no `treeSpecies` and only ids 0 to 2, where 0 is any conifer.
A client that doesn't know an id draws it as species 0 (spruce), so a game from before FEAT-233 loads a `treeSpecies` 3
pack and draws its hardwoods and hemlocks as spruce (see [formatVersion](#formatversion)).

| id | species | assigned (`pipeline/species.py`) | crown radius |
|---|---|---|---|
| 0 | Engelmann spruce | spruce-fir LANDFIRE classes and the conifer share of other classes; about 60 % of spruce-fir above 3,200 m | 0.13 h |
| 1 | aspen | aspen classes (85 %, aspen-mixed 50 %), or a NAIP bright-green crown (50 %), below 3,300 m | 0.20 h |
| 2 | krummholz | lidar height 1 to 4 m above 3,450 m or in an alpine class | 0.50 h |
| 3 | subalpine fir | the rest of spruce-fir: 50 % below 3,200 m, 40 % above, more on north and east aspects and near streams | 0.10 h |
| 4 | lodgepole pine | lodgepole (and ponderosa) classes, 85 %; without LANDFIRE, the lower slopes below 3,250 m | 0.09 h |
| 5 | Douglas-fir | Douglas-fir and montane mixed conifer classes below about 3,200 m | 0.17 h |
| 6 | limber pine | the trees under 12 m in limber-bristlecone and pinyon-juniper classes (BUG-129: a taller one is spruce or fir); half the short (< 10 m) trees on exposed crests above 3,200 m | 0.35 h |
| 7 | snag | standing dead: CHM peak over 6 m with NAIP NDVI under 0.15 inside forest, at most 3 % of trees | 0.05 h |
| 8 | bare hardwood | FEAT-233: eastern broadleaf classes (oak, beech-maple, ruderal, floodplain and swamp forest), the class's `hardwood` share (88 % in beech-maple to 96 % in dry oak), less on cool north and east aspects and near water; the broadleaf share of eastern spruce-fir-hardwood and oak-pine classes; in the east the no-LANDFIRE and no-group fallback below the boreal line | 0.28 h |
| 9 | eastern hemlock | FEAT-233: the rest of an eastern hardwood or hemlock class (hemlock-hardwood 60 %), up to 1.5 times more on north and east aspects and near water; 12 % of the eastern fallback on flat dry ground | 0.17 h |

The spruce / fir, group and crest draws are hashes of the tree position, so a rebuild gives each tree the same species.

**Regions** (FEAT-233, `species.region_for`): a pack centred east of 100 W is in the east. There the eastern LANDFIRE
classes (told apart by the region in their name: North-Central, Northeastern, Appalachian, Laurentian, Acadian,
Eastern, Northern & Central, ...) map to the hardwood, hemlock, spruce-fir (red spruce, balsam fir) or pine
(lodgepole stands in) groups, there is no aspen (NAIP's bright leaf-on canopy is the hardwoods), and wherever nothing
names the stand (no LANDFIRE, a class with no group, the far tree ring) trees are bare hardwood with hemlock below the
boreal line and spruce and fir above it (1,650 m at 35 N to 850 m at 44 N, blended over 150 m). West of 100 W the
Colorado rules above are unchanged. The build logs the region, the LANDFIRE forest under the pack by group, the share
of it in classes the rules don't name (pack_report.py line 4 warns over 20 %), and the species per group.

Since FEAT-074 the trees are the lidar's detected crowns (local maxima of the canopy height) and the snags; the stems
between them are the stand density below, generated by the client. A pack built without lidar (FEAT-225, Silver and
Bronze trees: the ETH 10 m canopy height on WorldCover tree cover) has no crowns, `treeCount` 0 and `treeCells` []:
every tree is a stand stem, and the stand height is 0.85 of the ETH height. Older packs also hold synthetic fill trees (a
share of the canopy cells without a crown nearby).

## Far tree ring (optional, BUG-081)

`farTrees/<tx>_<ty>.bin` (`pipeline/far_trees.py`): the crowns on the ridges round the resort, found the way the
pack's are (local maxima of a 2 m canopy height model from the same 3DEP lidar, the tallest return round each
peak) in the ring `lidar.far.pad_m` past the resort box, and only outside the pack bounds. Same record and grid
as `trees/`, but the cells run `instances.treeRing` cells past the grid on every side, so `tx`, `ty` may be
negative or reach `cellsX` / `cellsY` and over; a grid edge cell can have both files. No NAIP or LANDFIRE out
there: canopy is lidar height over 2.5 m off cliffs (45 degrees), no snags, and species from `species.py`'s
no-LANDFIRE rules for the pack's region (FEAT-233: bare hardwood and hemlock in the east). Ground heights follow the lidar ground where it has returns and the `mid` height set elsewhere.

| meta `instances` field | |
|---|---|
| `treeRing` | ring cells past the grid on each side |
| `farTreeCells` | the `farTrees/` cells that have a file, `"tx_ty"` |
| `farTreeCount` | crowns in all of them |
| `farTreeBox` | the ring's outer edge, `[minX, minY, maxX, maxY]` local metres |

Vail (5 km ring, 2026-11-11): 1.31 M crowns in 363 cells, 31 MB, from 1,485 more lidar nodes (1.9 GB raw).

## Stands (optional, FEAT-074)

`stands/<tx>_<ty>.png` (`pipeline/stands.py`): per 1 km tree cell, an RGB PNG `size` (250) wide and `2 * size`
tall, row 0 = north, one pixel per 4 m cell. RGB only, because a decoder that premultiplies alpha would zero the
colour where alpha is 0.

| rows | R | G | B |
|---|---|---|---|
| 0 .. size-1 | chance of one stem in the 4 m cell, 0..255 = 0..1 | stand height, `hStep` (0.25) m per step | species id 0..9 |
| size .. 2*size-1 | ground height high byte | low byte | 0 |

Ground height = `(R * 256 + G) / zScale + zBase` m, stored where a stem can stand and one cell round it (0 = none).
`zBase` is the pack's lowest ground and `zScale` 32, so a pack spans at most 2,048 m of relief.

The chance is the stems a closed stand needs (`K_CLOSE` crown area per m2 of canopy: canopy share / (pi r^2),
r = the species' crown ratio times the stand height), less the detected crowns within about 6 m, times the closed-stand
weight of the cell (BUG-120: the same test as the cover's `stands` image below, on the detected crowns; the canopy mask
reads a sparse stand as closed, so without it the stems filled sparse stands at about 4x their detected crowns; a pack
without lidar keeps every stem). Stems stand only
on canopy, off truly open LANDFIRE classes, groomed runs, built-up ground, cliffs and lift lines. Stand height is
the tallest lidar return in the 4 m cell, LANDFIRE EVH (DATA-010) where the lidar reads under 4 m, at least 3 m.
Species come from the same rules as the trees (`species.assign_species`) at the cell centre.

The client keeps a stem where `hash(cell centre) < chance x density` (the Forest setting), jitters it within 90 %
of the cell, draws it 0.75 to 1 times the stand height with the species' own crown, and reads the ground height
bilinearly. So a cell gives the same stems every time, and a lower density is a subset of a higher one. The cover
(`cover.py`) counts the stems in expectation (chance x crown area) for the shadow raster.

`shrubs/<tx>_<ty>.bin` (DATA-020, optional): Float32 records of 6: `x, y, z, height, radius, kind` with
kind 0 = willow (clumps of 3 to 8 stems, 1 to 3 m, within 25 m of an OSM stream on a valley bottom or in a riparian class),
1 = juniper (0.3 to 1 m mats in spruce-fir gaps and on open south crests), 2 = sagebrush (0.5 to 1.2 m, sagebrush classes),
3 = young conifer (1 to 4 m spruce or fir at forest edges and in canopy gaps, about 15 per hectare of edge),
4 = Gambel oak (1 to 3 m, Gambel oak shrubland classes). Density follows NAIP NDVI where there is no canopy, at most 200 per hectare.
The build writes `debug/species.png` into the pack: the most common species per 10 m (left; colours in
`species.SPECIES_RGB`) next to the LANDFIRE tree group (right), for a visual check.

`rocks/<tx>_<ty>.bin`: Float32 records of 6: `x, y, z, size, yaw, type` with type 0 = outcrop,
1 = boulder, 2 = talus clump.

Cell size is `meta.instances.cellSize` (1000 m), origin `meta.instances.minX/minY`. `treeCells`, `rockCells` and `shrubCells` list the cells that have a file (`"cx_cy"`); the client only requests those. Packs built before BUG-036 lack the lists and the client requests every cell in range; add them without a rebuild with `python pipeline/packwriter.py packs/<slug>`.

`packs/index.json` (`{"packs": ["synth", "vail"], "names": {"synth": "Test mountain (synthetic)", "vail": "Vail"}}`) lists every pack folder with a `meta.json`, and each pack's `meta.json` `name` (FEAT-175). `write_meta` rewrites it after each build, and `get_pack.mjs` after each install; the menu reads it instead of probing each resort's `meta.json`, and lists every pack in it under that name, so a new resort needs no entry in `game/src/resorts.ts` (which only orders the known ones and names packs in an index without `names`).

## Main menu (optional, FEAT-175)

`attract/` holds a resort's main menu content when the game has no hand-made one: `pipeline/gen_content.py` writes
`shots.json` (a list of the game's `AttractShot`, `game/src/world/AttractShots.ts`: id, x, y in pack metres, h heading
in degrees clockwise from grid north, pitch, vertical fov, eye height over the snow, place, region, elev, the drift
dolly / pan / period and conditions; the menu uses the first) and `index.json`, the resort's entry of the game's attract
manifest: `{"shots": true, "generated": true, "stills": [<shot id>], "ghosts": [<take file>], "looks": {<shot id>:
{"code", "pack": <meta.build>}}, "shotGhosts": {<shot id>: [<take file>]}}`. The game's `tools/auto_attract.mjs` adds
the still `<shot id>.jpg` (1920 x 1080, shown only while `looks.<id>.pack` is the pack's `build`) and the ghost takes
`<shot id>-start-run[-v<n>]-<i>.json` (the game's `AttractTake`: replay samples at 20 Hz). `meta.attract`
(`{"generated": true}`) tells the game the folder is there, so a pack without it requests nothing. A game whose own
`game/public/attract/index.json` lists the resort uses that instead. An `index.json` without `generated` is hand-made
content (FEAT-243 moves Vail's and Breckenridge's here) and `gen_content.py` leaves it alone. Optional and ignored by
an older game: no format bump.

## features.json

```
{
  "lifts":     [{ "name", "type", "stations": [[x,y,z],...], "towers": [[x,y,zGround,height],...],
                 "cable": [[x,y,z],...], "capacity" }],
  "runs":      [{ "name", "difficulty": "easy|intermediate|advanced|expert|freeride",
                 "groomed": bool, "gladed": bool, "points": [[x,y,z],...], "osmId",
                 "groomNights", "mogulScore", "altName" }],  // groomNights: nights the resort's reports groomed it (absent when never); mogulScore: 0..1 from pipeline/moguls.py (absent in packs before FEAT-059); altName (FEAT-296, optional, not read by the game): the way's OSM `name` when `piste:name` differs and is the run's name
  "buildings": [{ "name", "points": [[x,y],...], "zBase", "zMax", "height", "heightDefault", "kind" }],  // zMax: highest ground under the footprint, absent in packs before BUG-024; heightDefault: true when OSM had no height or levels and the pipeline used its 5.5 / 9 m fallback (absent in older packs, where the client guesses from those values)
  "roads":     [{ "name", "kind", "points": [[x,y,z],...], "width" }],
  "water":     [{ "name", "points": [[x,y],...], "z" }],
  "peaks":     [{ "name", "x", "y", "z" }],                 // OSM peaks, plus USGS GNIS summits OSM lacks (FEAT-235; z: the highest ground near it)
  "labels":    [{ "name", "kind", "x", "y", "z" }]          // towns: OSM places_far, else US Census places (FEAT-235); kind city (100,000 people), town (10,000) or village
}
```

## meta.json

```
{
  "version": 1, "slug": "vail", "name": "Vail",
  "formatVersion": 1,                                      // FEAT-222: the pack format (see below); absent = 0
  "build": "20261110T171500Z-3fa2c1",                      // FEAT-177: new on every write by any stage (packwriter.stamp_build)
  "pipeline": "1e2e586",                                   // FEAT-175: commit of the pipeline that wrote it, "+dirty" with local changes; optional
  "crs": "EPSG:26913", "origin": [384300, 4384250], "lonlat": [-106.35, 39.60],
  "bounds": { "minX", "minY", "maxX", "maxY" },           // resort area, local metres: the config's pack_bbox (FEAT-249,
                                                           // else utm_bbox) minus origin; need not be centred on it
  "zRange": [2300, 3700],
  "terrain": { "fine": {...}, "mid": {...}, "far": {...} },
  "mask": { "res": 2, "tileSize": 512, "minX", "minY", "tilesX", "tilesY" },
  "ao": { same fields as mask },                           // optional
  "dir": { same fields as mask },                          // optional, DATA-002
  "moguls": { same fields as mask },                       // optional, FEAT-059
  "cover": { "heightMax": 40, "blend": 500,                 // optional, FEAT-153
             "levels": [{ "name": "pack", "res": 4, "minX", "minY", "w", "h", "file": "cover/pack.png", "stands": "cover/pack-stands.png", "crowns": true },
                        { "name": "mid", "res": 16, ... }, { "name": "far", "res": 100, ... }] },
  "instances": { "cellSize": 1000, "minX", "minY", "cellsX", "cellsY", "treeCount", "rockCount", "treeCells", "rockCells",
                 "shrubCount", "shrubCells" },              // shrub fields optional, DATA-020
  "treeSpecies": 3,                                        // optional: 3 (FEAT-233) tree ids 0..9, 2 (DATA-020) 0..7; absent = 0..2
  "vegetation": { "region": "east", "treeSpecies": { "hardwood": 0.82, ... },   // optional (FEAT-233): what the species rules
                  "farTreeSpecies": {...}, "evtUnknown": 0.0,                    // made of the forest, a log for pack_report.py;
                  "evtGroups": { "hardwood": 0.95, ... } },                     // the client ignores it
  "stands": { "res": 4, "size": 250, "zBase", "zScale": 32, "hStep": 0.25,  // optional, FEAT-074
              "cells": ["cx_cy", ...], "stems" },          // cells with an image; stems over the pack at full density
  "start": { "x", "y", "heading", "run", "lift", "label", "source" },  // default drop-in, heading in radians from north;
                                                           // gen_content.py (FEAT-175): source "generated", the top of the
                                                           // highest lift (`lift`) on `run`, `label` the menu's line
  "attract": { "generated": true },                       // optional (FEAT-175): the pack has attract/ (Main menu above)
  "generated": { "start": true, "shots": 5, "buildStart": {...} },  // optional (FEAT-175): gen_content.py ran on this build,
                                                           // what it found and the build's own start; a log, the client ignores it
  "treeline": 2700,                                       // optional, m (DATA-021): measured from the canopy; absent = 3,480 (Colorado);
                                                           // null = measured none (FEAT-234), see below
  "derived": { "rock.grey_sat": 0.093, "treeline": 2700, ... }, // optional (FEAT-175): values the build derived for this resort instead of
                                                           // copying Vail's (naip_calib.py thresholds, treeline); a log, the client ignores it.
                                                           // "relocated": [{ "name", "from", "to", "turnDeg", "featherM", "dzM" }] lists
                                                           // the areas moved next to the rest (FEAT-249, relocate.py), UTM metres;
                                                           // "source": "<slug>" on one cut from another place's raw data (FEAT-268)
  "tier": "bronze",                                       // optional (FEAT-225): the weakest layer's tier, gold / silver / bronze
  "sources": { "terrain": { "source": "Mapterhorn z16, 0.8 m", "tier": "silver" },   // optional (FEAT-225): what built each
               "trees": {...}, "surface": {...} },     // layer and its tier (pipeline/tiers.py); a log, the client ignores both
  "sun": { "azimuth": 160, "elevation": 32 },             // degrees, default lighting
  "attribution": ["..."]
}
```

`treeline` (DATA-021, FEAT-234) has three states. A number is the elevation where the canopy share by 25 m band falls
under half its peak (`pipeline/treeline.py`); the game puts its procedural treeline, its open valley floor (1,030 to
830 m under it) and the snow-ghost band (30 m under to 80 m over it) there. `null` means the build measured no
treeline: the box is forest from the bottom to the top (Boston Mills, 192 to 311 m; `treeline.forested_to_top`), so
the game draws no snow-ghost band and its procedural forest opens by slope and land cover only, not by elevation.
Absent means an older pack, or a box with no forest belt to measure; the game uses Colorado's 3,480 m. A game from
before FEAT-234 reads `null` as absent (`meta.treeline ?? 3480`), so `null` needed no format bump.

## formatVersion

FEAT-222. `meta.json` `formatVersion` is the pack format a build wrote: `FORMAT_VERSION` in `pipeline/packwriter.py`, which must equal `PACK_FORMAT` in the game's `game/src/pack/format.ts` (see [Contract](#contract)). `publish_pack.py` copies it into this repo's `catalog.json`; `get_pack.mjs` installs only a pack of the game's own format, and the resort picker shows an older one as "needs rebuild" (still loadable when it is on disk). Packs built before FEAT-222 have no field and count as 0.

**Bump rule** (FEAT-239):

1. Any change a current game can't read bumps `formatVersion`: a new required layer, a changed encoding, or a field the game now relies on. Optional layers the game already treats as absent don't need a bump.
2. It takes a PR here (`FORMAT_VERSION`, a line in the table below) and a PR in the game (`PACK_FORMAT` and the reader). The game's PR lands first or together: `tests/test_contract.py` fails here while this repo is ahead of the game's `main` ("land the game's format PR first"). To check the pair before either lands, point it at the game PR's checkout: `SBA_GAME_REPO=<game worktree> python -m pytest pipeline/tests/test_contract.py`, or `python pipeline/contract.py --game-repo <game worktree>`.
3. Every catalog pack on an older format shows "needs rebuild" in the resort picker, and `npm run get` refuses it, until it is rebuilt and republished (`publish_pack.py` refuses a pack that is not on this pipeline's format).

| formatVersion | Since | What |
|---|---|---|
| 0 | | Packs without the field (built before FEAT-222), whatever layers they have |
| 1 | FEAT-222, 2026-11-11 | The format at FEAT-222: `stands/` (FEAT-074), `treeSpecies` 2 (DATA-020), `cover` levels (FEAT-153), `treeline` when measured (DATA-021; `null` for a measured none since FEAT-234, read as absent by older games), `build` (FEAT-177) |

FEAT-233 (`treeSpecies` 3, ids 8 bare hardwood and 9 eastern hemlock, the optional `vegetation` log) stays on format 1:
every client since DATA-020 sends a species id past its table to 0 (`speciesFor`), so an older game loads a new pack and
draws the new ids as spruce, the conifer forest those packs showed before; western packs hold no new id at all.

Not a bump: the `coarse` height set (FEAT-229) is optional and a game before it ignores it.

## Contract

FEAT-239. Every value the pipeline and the game must agree on, with where each side keeps it. The layout and
encodings above are the rest of the contract; these are the numbers and shapes that are written down twice.
Lines are as of 2026-11-11 (the game at `51efba2`); search for the name if they have moved.

| Value | MapPacker (writes) | SnowboardAnywhere (reads) | Checked by |
|---|---|---|---|
| `formatVersion` | `pipeline/packwriter.py:15` `FORMAT_VERSION`, written to `meta.json` (`pipeline/build_pack.py:1056`) and `catalog.json` (`pipeline/publish_pack.py:149`, `:169`) | `game/src/pack/format.ts:7` `PACK_FORMAT`; `game/tools/get_pack.mjs:67` `formatProblem`; `game/src/ui/ResortPicker.ts:32`, `:42` ("needs rebuild") | `tests/test_contract.py` against the game's `main` |
| Species ids 0..9 (`treeSpecies` 3) | `pipeline/species.py:20` (ids), `:26` `TREE_SPECIES_VERSION` | `game/src/world/trees/species.ts:46` `SPECIES` (one row per id, in order), `:77` `speciesFor` (packs without `treeSpecies`: ids 0..2; an unknown id draws as 0); `game/src/pack/types.ts:106` | `tests/test_contract.py` (the ids are the rows of the crown radius table) |
| Drawn crown radius / height per id | `pipeline/cover.py:67` and `pipeline/stands.py:31` `CROWN_RATIO` (the crowns the game will draw, for the cover and the stem chance) | `game/src/world/trees/species.ts:47`-`58` `SPECIES[].radius` | `tests/test_contract.py`: must be equal |
| Record crown radius / height per id | `pipeline/species.py:29` `CROWN_K` (field 4 of `trees/*.bin`, the table under Instances) | `game/src/world/trees/species.ts:92` `crownRadius`: the drawn radius nudged by record / natural, clamped to 0.85..1.25 | not checked: it need not equal `SPECIES[].radius` |
| Default treeline (`treeline` absent; `null` is none, FEAT-234) | `pipeline/species.py:23` `COLORADO_TREELINE` (3,480 m, what the species bands were tuned for) | `game/src/pack/treeline.ts:4` `DEFAULT_TREELINE`; `game/src/pack/types.ts:111` | `tests/test_contract.py`: must be equal |
| `packs/index.json` `{"packs", "names"}` | `pipeline/packwriter.py:100` `index_packs` | `game/tools/get_pack.mjs:59` `writePackIndex` (rewrites it after an install); `game/src/resorts.ts:14` `PackIndex` | `tests/test_publish_pack.py` round trip through `get_pack.mjs` (needs the game checkout and node) |
| `catalog.json` | `pipeline/publish_pack.py:141` `catalog_entry`, `:156` `update_catalog` | `game/tools/get_pack.mjs:19` `CATALOG_URL`, `:75` `getPack`; `game/src/ui/ResortPicker.ts:42` | `tests/test_publish_pack.py` round trip |
| `terrain.coarse` (FEAT-229) | `pipeline/coarse_set.py`, `pipeline/build_pack.py` stage 1 | `game/src/pack/Pack.ts` `coarse`, `skipFine`; `game/src/terrain/Terrain.ts` `update` | not checked across repos |
| Terrarium heights | `pipeline/packwriter.py:17` `encode_terrarium` | `game/src/pack/HeightSet.ts:88` | not checked across repos |

`python pipeline/contract.py` prints the checked lines against the game's `main` (`--game-repo <dir>` for a
checkout). Add a line here, and to `contract.py` where it can be parsed, for any new value both sides hold.
