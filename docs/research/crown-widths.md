# Crown widths by openness (FEAT-298)

What the lidar says about how wide a conifer's crown is for its height, and what the widths in `pipeline/widths.py`
are based on. Measured 2026-11-13 with `tools/crown_widths.py` on the raw 3DEP lidar: a canopy height grid at 1 m,
every visible top a tree (so the clumps the pack's crown detection merges are split), crowns grown from the tops by a
watershed, the footprint radius `sqrt(area / pi)` over the tree's height. Openness is the canopy cover within 10 m of
the top. Three segmentation settings each (smoothing 1 to 2 m, tops 2.5 to 4.5 m apart).

## Results

| place | points / m2 | trees | open-grown (cover10 < 0.25): r / h median | isolated (nearest top >= 15 m) | closed stands |
|---|---|---|---|---|---|
| Vail, Back Bowls sign, 600 m round it (3,340 m) | 0.93 | 2,000 to 4,700 | 0.13 to 0.15 (p10 0.09 to 0.11, p90 0.20 to 0.21) | 0.17 to 0.18 | 0.12 to 0.23, depends on the setting |
| Park City, closed stand at (724, 2032), 600 m (2,280 m) | 0.50 | 2,000 to 5,700 | 0.16 to 0.17 | 0.16 to 0.28 | 0.27 to 0.37: merged canopy, not single trees |
| Vail, front side above the village (2324, 3150) | 0.13 | | not usable: too few points to find crowns | | |

- Open-grown conifers are 0.15 to 0.17 x their height wide at both resorts, and the spread inside any group is about
  +-40 % (p10 to p90). This is what `OPEN_RATIO` (0.16) and `JITTER` (0.35) come from.
- The width of a tree inside a closed stand can't be resolved at these densities: the segmentation setting decides
  it. So a crowded tree keeps the species radius the game was tuned with (spruce 0.13, fir 0.10 x height).
- Crowded trees are mostly taller, not narrower in metres (Vail: 16 to 19 m in the open, 27 to 29 m in closed
  stands). The game's clump impostors draw the sparse classes shorter for this (`OPEN_H`, 0.65).
- The pack's detected crowns are usually clumps of about 3 tops (one crown per local maximum on sparse lidar); the
  record's crown radius was only the species formula. Measuring each crown's own footprint is a possible next step,
  reliable for open and isolated crowns only.

## The canopy cover

FEAT-298 holds the drawn canopy (the crowns plus the stems in expectation, at the species radii) where the stems can
give it back, and lets the crowns widen where there are no stems. Within 250 m / 600 m / 1.5 km of the Back Bowls sign
on Vail (read from the pack, and the same within 0.01 from the live game's trees):

| | 250 m | 600 m | 1.5 km |
|---|---|---|---|
| vail v4 as shipped (species radii) | 0.097 | 0.172 | 0.164 |
| with crown widths | 0.106 | 0.182 | 0.174 |
| lidar canopy 3 m or taller, 1 m grid | 0.163 | 0.168 | |
| lidar canopy, 1 m grid, gaps under 3 m closed | 0.227 | 0.276 | |
| lidar canopy, 2 m grid (the build's) | 0.252 | 0.298 | |

- Pack-wide the drawn crown area goes from 36.6 to 37.4 km2 (+2 %) and the stems from 2.38 M to 2.00 M; the detected
  crowns' drawn area is 1.20 times their area at the species radii.
- The lidar's canopy share depends on how it is measured (0.16 to 0.30 at the same place), so the build logs it
  beside the drawn cover rather than testing against it. The build's guard is the drawn cover after the widening
  against before it, round the config's `crown_cover_spots`.
- Today's drawn canopy round the sign is well under any of the lidar figures (about 0.1 against 0.16 to 0.25 within
  250 m). The FEAT-292 session's notes put the shipped canopy at 0.170 / 0.233 within 250 / 600 m; the same live
  read on today's vail v4 gives 0.094 / 0.172, so those figures do not describe this pack. Since BUG-120 the stems
  fill closed stands only, and the sparse stands are carried by their detected crowns alone.
