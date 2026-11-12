"""FEAT-225 (EPIC-15): Gold, Silver and Bronze tiers, one per layer, and the pack's tier (its weakest layer's).

    | Tier   | Terrain                       | Trees                                     | Surface masks   |
    |--------|-------------------------------|-------------------------------------------|-----------------|
    | Gold   | 1 m 3DEP                      | lidar crowns + LANDFIRE stands            | NAIP 1 m        |
    | Silver | 1 m 3DEP or Mapterhorn z15+   | stands from ETH 10 m canopy + WorldCover  | NAIP            |
    | Bronze | the best Mapterhorn zoom there| ETH + WorldCover stands                   | WorldCover 10 m |

Which source a layer uses is read from the config (`resort.py plan` writes it): `dem.source` "Mapterhorn" (with
`dem.zoom`) for the terrain, no `lidar` for stands from the ETH canopy height, no `naip` for masks from WorldCover.
`plan` records each layer's tier in `sources` (it may only lower one: a 1 m DEM or lidar over part of the box is
Silver); a config without it (the hand-written ones) gets the tiers of the sources it names.
`build_pack.py` writes what it used to `meta.json` (`tier`, `sources`) and `pack_report.py` shows it.
Pure functions, tested in tests/test_tiers.py.
"""
import math

RANK = {"gold": 0, "silver": 1, "bronze": 2}
LAYERS = ("terrain", "trees", "surface")
EARTH_M = 40075016.686        # web mercator circumference at the equator
TILE_PX = 512                 # Mapterhorn tiles are 512 x 512
SILVER_ZOOM = 15              # Mapterhorn from this zoom (about 1.6 m at 47 deg) is Silver terrain, coarser is Bronze
MAX_PROBE_ZOOM = 18
MAPTERHORN = "Mapterhorn"


def tier_of(layers):
    """the pack's tier is its weakest layer's (design section 4). `layers`: {layer: "gold"|"silver"|"bronze"}
    -> (tier, the layers that hold it there)"""
    worst = max(layers.values(), key=lambda t: RANK[t]) if layers else "bronze"
    return worst, sorted(k for k, t in layers.items() if t == worst and worst != "gold")


def tile_px_m(z, lat):
    """ground size (m) of one pixel of a 512 px web mercator tile at zoom z and latitude lat"""
    return EARTH_M * math.cos(math.radians(lat)) / (TILE_PX * 2 ** z)


def zoom_for(res_m, lat, native=MAX_PROBE_ZOOM):
    """the coarsest zoom whose pixels are no larger than res_m there, at most `native` (the finest Mapterhorn has)"""
    for z in range(0, native + 1):
        if tile_px_m(z, lat) <= res_m:
            return z
    return native


def terrain_tier(cfg):
    dem = cfg.get("dem") or {}
    if dem.get("source") == MAPTERHORN:
        return "silver" if dem.get("native_zoom", dem.get("zoom", 0)) >= SILVER_ZOOM else "bronze"
    return "gold"


def uses_mapterhorn(block):
    return (block or {}).get("source") == MAPTERHORN


def layer_sources(cfg):
    """{layer: {"source": what builds it, "tier": its tier}} from a config: the plan's `sources` tiers where it
    recorded them (a partial 1 m DEM or lidar is Silver), else the tier of the source the config names"""
    dem, lidar, naip = cfg.get("dem") or {}, cfg.get("lidar"), cfg.get("naip")
    lat = (cfg.get("lonlat_bbox") or [0, 0, 0, 0])
    lat = (lat[1] + lat[3]) / 2
    if uses_mapterhorn(dem):
        z = dem.get("zoom")
        terrain = f"Mapterhorn z{z}, {tile_px_m(z, lat):.1f} m" if z is not None else "Mapterhorn"
    else:
        terrain = "3DEP 1 m"
    out = {"terrain": {"source": terrain, "tier": terrain_tier(cfg)},
           "trees": {"source": "lidar crowns + stands" if lidar else "stands from ETH canopy height + WorldCover",
                     "tier": "gold" if lidar else "silver"},
           "surface": {"source": "NAIP" if naip else "WorldCover 10 m", "tier": "gold" if naip else "bronze"}}
    for k, v in (cfg.get("sources") or {}).items():      # the plan may only lower a tier, never raise it
        if k in out and isinstance(v, dict) and v.get("tier") in RANK and RANK[v["tier"]] > RANK[out[k]["tier"]]:
            out[k]["tier"] = v["tier"]
    return out


def summary(sources):
    """one line: "terrain Mapterhorn z16, 0.8 m (silver), trees ... (silver), surface WorldCover 10 m (bronze)" """
    return ", ".join(f"{k} {v['source']} ({v['tier']})" for k, v in sources.items())
