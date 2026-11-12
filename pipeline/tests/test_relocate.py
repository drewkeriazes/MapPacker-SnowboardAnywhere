"""FEAT-249: moving an area next to the rest of the resort (relocate.py)."""
import json, math, os, sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import paths      # noqa: E402
import relocate as rl   # noqa: E402

FRAME = [0.0, 0.0, 2000.0, 1000.0]
SRC = [1400.0, 300.0, 1800.0, 700.0]          # a 400 m square on the east side of the frame
MOVE = {"name": "Far", "from": SRC, "to": [500.0, 500.0], "turn_deg": 0, "feather_m": 50}


def rel(**kw):
    return rl.Relocation({"relocate": [dict(MOVE, **kw)]})


def test_dest_and_src_are_inverse_and_turn_is_clockwise():
    m = rl.Move(dict(MOVE, turn_deg=90))
    # a slope falling north (+y) from the patch centre falls east after a 90 degree clockwise turn
    x, y = m.dest_of(1600 + 0, 500 + 100)
    assert np.allclose([x, y], [500 + 100, 500])
    sx, sy = m.src_of(x, y)
    assert np.allclose([sx, sy], [1600, 600])
    assert m.facing(0) == 90 and m.facing(350) == 80
    xs, ys = np.random.default_rng(1).uniform(0, 2000, (2, 50))
    assert np.allclose(m.src_of(*m.dest_of(xs, ys)), [xs, ys])


def test_weight_is_one_inside_and_eases_to_zero_at_the_edge():
    m = rl.Move(MOVE)
    w = m.weight(np.array([500, 500, 500, 500, 500]), np.array([500, 320, 325, 300, 290]))
    assert w[0] == 1.0 and 0 < w[1] < w[2] < 1 and w[3] == 0 and w[4] == 0
    assert m.weight(500 - 200 + 50, 500) == 1.0       # feather_m in from the edge


def test_bad_specs_are_refused():
    with pytest.raises(ValueError):
        rl.Move(dict(MOVE, **{"from": [10, 10, 0, 20]}))
    with pytest.raises(ValueError):
        rl.Move(dict(MOVE, feather_m=250))           # two seams wider than the box
    with pytest.raises(ValueError):
        rl.Relocation({"relocate": [MOVE, MOVE]})


def test_select_picks_the_patch_inside_and_the_ground_outside():
    r = rel()
    x = np.array([500, 500, 100, 1600]); y = np.array([500, 340, 500, 500])
    sel = r.select(x, y)
    assert list(sel) == [0, sel[1], -1, -1]          # deep inside, in the seam (either side), outside, the source
    assert sel[1] in (0, -1)
    assert not rl.Relocation({})                     # no moves: falsy, and select is all ground
    assert (rl.Relocation({}).select(x, y) == -1).all()
    # the switch line is ragged but the same for every layer: asking twice, or one point alone, agrees
    gx, gy = np.meshgrid(np.arange(290, 711, 4.0), np.arange(290, 711, 4.0))
    s1 = r.select(gx, gy)
    assert (s1 == r.select(gx, gy)).all()
    assert all(r.select(gx[i:i + 1, j], gy[i:i + 1, j])[0] == s1[i, j] for i, j in ((3, 5), (10, 2), (50, 50)))
    band = (r.moves[0].weight(gx, gy) > 0.25) & (r.moves[0].weight(gx, gy) < 0.75)
    assert 0 < (s1[band] == 0).mean() < 1


def test_source_xy_reads_a_patch_at_its_own_place():
    r = rel()
    sx, sy = r.source_xy(np.array([500.0, 100.0]), np.array([500.0, 100.0]))
    assert np.allclose(sx, [1600, 100]) and np.allclose(sy, [500, 100])


def frame_dem():
    """1 m frame: flat 100 m ground with a 4 m step east of x 1000, and in the source square a hill (a cone,
    60 m at its centre) that falls to the north faster than to the south"""
    h, w = 1000, 2000
    X, Y = np.meshgrid(np.arange(w) + 0.5, 1000 - (np.arange(h) + 0.5))
    dem = np.where(X > 1000, 104.0, 100.0)
    d = np.hypot(X - 1600, np.where(Y > 500, (Y - 500) * 2, Y - 500))
    return np.where(d < 150, dem + 60 * (1 - d / 150), dem).astype(np.float32)


def test_compose_heights_pastes_the_hill_set_on_the_ground_there():
    dem = frame_dem()
    r = rel()
    m = r.moves[0]
    dz = rl.rim_dz(dem, FRAME, 1.0, m)
    assert dz == pytest.approx(-4.0)                 # the patch's rim is on the 104 m side, the ground there 100 m
    box = [0.0, 0.0, 1000.0, 1000.0]
    out = rl.compose_heights(dem, FRAME, 1.0, box, r, [dz])
    assert out.shape == (1000, 1000)
    assert out[500, 500] == pytest.approx(160.0, abs=1.0)        # the hill top, 64 m over its own ground - 4
    assert out[100, 100] == 100.0 and out[900, 900] == 100.0     # the ground outside the patch is untouched
    assert np.abs(out[480:520, 290:310] - 100).max() < 0.5       # the seam meets the ground
    # relief kept: 60 m from the top to the patch floor
    assert out[500, 500] - out[500, 330] == pytest.approx(60.0, abs=1.0)


def test_compose_heights_turns_the_patch():
    dem = frame_dem()
    r = rel(turn_deg=90)
    out = rl.compose_heights(dem, FRAME, 1.0, [0.0, 0.0, 1000.0, 1000.0], r, [rl.rim_dz(dem, FRAME, 1.0, r.moves[0])])
    # the steep side faced north; after a clockwise quarter turn it faces east: 50 m east of the top is lower than
    # 50 m west
    assert out[500, 550] < out[500, 450] - 10


def test_compose_classes_moves_classes_and_crops_without_moves():
    cls = np.zeros((2, 500, 1000), np.uint8)          # 2 bands at 2 m over the frame
    cls[0, 200:300, 750:850] = 7                      # the source square's middle (x 1500..1700, y 400..600)
    cls[1] = 3
    box = [0.0, 0.0, 1000.0, 1000.0]
    out = rl.compose_classes(cls, FRAME, 2.0, box, rel())
    assert out.shape == (2, 500, 500)
    assert (out[0, 200:300, 200:300] == 7).all()      # x 400..600, y 400..600
    assert out[0, 10, 10] == 0 and (out[1] == 3).all()
    plain = rl.compose_classes(cls, FRAME, 2.0, box, rl.Relocation({}))
    assert (plain == cls[:, :, :500]).all()
    with pytest.raises(ValueError):
        rl.crop(cls, FRAME, 2.0, [1.0, 0.0, 1001.0, 1000.0])   # not on the 2 m grid


class Flat:
    """a stand-in for the pyproj transformers: lon/lat are metres / 1000"""
    def __init__(self, k):
        self.k = k

    def transform(self, x, y):
        return np.asarray(x, np.float64) * self.k, np.asarray(y, np.float64) * self.k


TO_UTM, TO_LL = Flat(1000.0), Flat(0.001)


def ll(x, y):
    return {"lon": x / 1000, "lat": y / 1000}


def test_osm_moves_the_patch_and_clears_the_ground_it_covers():
    doc = {"elements": [
        {"type": "node", "id": 1, "lat": 0.5, "lon": 1.6, "tags": {"natural": "peak", "name": "Top"}},     # source
        {"type": "node", "id": 2, "lat": 0.5, "lon": 0.5, "tags": {"amenity": "bench"}},                   # covered
        {"type": "node", "id": 3, "lat": 0.9, "lon": 0.1, "tags": {"amenity": "bench"}},                   # stays
        {"type": "way", "id": 10, "tags": {"highway": "tertiary"}, "nodes": [1, 2, 3, 4, 5, 6],            # a road through
         "geometry": [ll(1100, 500), ll(1200, 500), ll(1500, 500), ll(1700, 500), ll(1900, 500), ll(1950, 500)],
         "bounds": {}},
        {"type": "way", "id": 11, "tags": {"building": "yes"},                                             # closed, source
         "geometry": [ll(1590, 490), ll(1610, 490), ll(1610, 510), ll(1590, 510), ll(1590, 490)]},
        {"type": "way", "id": 12, "tags": {"highway": "service"},                                          # under the patch
         "geometry": [ll(450, 450), ll(550, 550)]},
    ]}
    out, moved = rel().osm(doc, TO_UTM, TO_LL)
    els = {(e["id"], i): e for i, e in enumerate(out["elements"])}
    ids = [e["id"] for e in out["elements"]]
    assert 2 not in ids and 12 not in ids and 3 in ids
    peak = next(e for e in out["elements"] if e["id"] == 1)
    assert peak["lon"] == pytest.approx(0.5) and peak["lat"] == pytest.approx(0.5)
    roads = [e for e in out["elements"] if e["id"] == 10]
    assert len(roads) == 3                                   # west part, the moved middle, east part
    mid = next(r for r in roads if r["geometry"][0]["lon"] < 1)
    assert [p["lon"] for p in mid["geometry"]] == pytest.approx([0.4, 0.6]) and mid["nodes"] == [3, 4]
    assert all("bounds" not in r for r in roads)
    house = next(e for e in out["elements"] if e["id"] == 11)
    assert house["geometry"][0]["lon"] == pytest.approx(0.49)
    assert moved == {"Far": 3}
    assert len(els) == len(out["elements"])


def test_osm_whole_keeps_a_lift_in_one_piece():
    lift = {"type": "way", "id": 20, "tags": {"aerialway": "chair_lift"}, "nodes": [5, 6, 7],
            "geometry": [ll(1500, 500), ll(1600, 500), ll(1780, 500)]}   # the last node is in the seam
    out, _ = rel().osm({"elements": [lift]}, TO_UTM, TO_LL, whole=True)
    (e,) = out["elements"]
    assert e["nodes"] == [5, 6, 7] and [p["lon"] for p in e["geometry"]] == pytest.approx([0.4, 0.5, 0.68])
    assert rl.Relocation({}).osm({"elements": [lift]}, TO_UTM, TO_LL) == ({"elements": [lift]}, {})


def test_ride_buffer_drops_to_300_m_for_a_small_hill():
    assert rl.ride_buffer(800) == 300
    assert rl.ride_buffer(1476) == 400
    assert rl.ride_buffer(1999) == 600
    assert rl.ride_buffer(2500) == 800 and rl.ride_buffer(3500) == 1000 and rl.ride_buffer(2000) == 600


def test_ride_box_and_patches():
    box, buf, rb, diag = rl.ride_box([(1000, 1000), (1600, 1800)])
    assert buf == 300 and box == [700, 700, 1900, 2100] and diag == pytest.approx(1000)
    r = rel()
    assert rl.grow_to_patches([400, 400, 600, 600], r) == [300, 300, 700, 700]
    assert rl.grow_to_patches([0, 0, 650, 650], r) == [0, 0, 700, 700]
    assert r.check_inside(FRAME, [0, 0, 1000, 1000]) == []
    msgs = r.check_inside(FRAME, [0, 0, 600, 600])
    assert len(msgs) == 1 and "pasted patch" in msgs[0]
    assert any("pack_bbox" in s for s in r.check_inside([0, 0, 900, 900], [0, 0, 1000, 1000]))


def test_ride_points_takes_downhill_runs_and_real_lifts():
    ski = {"elements": [
        {"type": "way", "tags": {"piste:type": "downhill"}, "geometry": [ll(1, 1), ll(2, 2)]},
        {"type": "way", "tags": {"piste:type": "nordic"}, "geometry": [ll(9, 9), ll(9, 9)]},
        {"type": "way", "tags": {"aerialway": "chair_lift"}, "geometry": [ll(3, 3), ll(4, 4)]},
        {"type": "way", "tags": {"aerialway": "goods"}, "geometry": [ll(8, 8), ll(8, 8)]},
    ]}
    assert len(rl.ride_points(ski)) == 4
    assert len(rl.ride_points(ski, [0, 0, 0.0025, 0.0025])) == 2


def test_boston_mills_config():
    """Brandywine pasted next to Boston Mills: inside the fetched box, the patch inside the pack box"""
    cfg = json.load(open(paths.config_path("boston-mills"), encoding="utf-8"))
    r = rl.Relocation(cfg)
    assert [m.name for m in r.moves] == ["Brandywine"]
    assert r.check_inside(cfg["utm_bbox"], cfg["pack_bbox"]) == []
    fb, pb = cfg["utm_bbox"], cfg["pack_bbox"]
    assert (pb[2] - pb[0]) * (pb[3] - pb[1]) < 0.2 * (fb[2] - fb[0]) * (fb[3] - fb[1])
    ox, oy = cfg["origin"]
    assert pb[0] <= ox <= pb[2] and pb[1] <= oy <= pb[3]


# ------------------------------------------------------------------------------------------------ FEAT-268
# A sourced move cuts its area out of another place's raw data, its own frame far from this one's.

SRC_FRAME = [10000.0, 0.0, 11000.0, 1000.0]       # the source's fetched box, 8 km east of FRAME
FAR_SRC = [10300.0, 300.0, 10700.0, 700.0]
SOURCED = {"name": "Other hill", "source": "other", "from": FAR_SRC, "to": [1500.0, 500.0], "turn_deg": 0,
           "feather_m": 50}


def two(**kw):
    """an in-frame move (MOVE, pasted at 500, 500) and a sourced one (pasted at 1500, 500)"""
    return rl.Relocation({"relocate": [MOVE, dict(SOURCED, **kw)]}, {"other": SRC_FRAME})


def source_dem():
    """1 m source frame: flat 300 m ground with a 50 m cone at the source square's centre"""
    X, Y = np.meshgrid(SRC_FRAME[0] + np.arange(1000) + 0.5, 1000 - (np.arange(1000) + 0.5))
    d = np.hypot(X - 10500, Y - 500)
    return np.where(d < 150, 300 + 50 * (1 - d / 150), 300.0).astype(np.float32)


def test_a_sourced_move_is_checked_against_its_own_frame():
    r = two()
    assert r.moves[1].frame == SRC_FRAME and r.sourced == [1] and r.source_slugs() == ["other"]
    assert r.check_inside(FRAME, FRAME) == []                     # its from box is far outside FRAME: fine
    bad = two(**{"from": [10800.0, 300.0, 11200.0, 700.0]}).check_inside(FRAME, FRAME)
    assert len(bad) == 1 and "other's utm_bbox" in bad[0]
    unknown = rl.Relocation({"relocate": [SOURCED]})              # no frames given: not known, so refused
    assert "not known" in unknown.check_inside(FRAME, FRAME)[0]
    with pytest.raises(ValueError, match="has no config"):
        rl.Relocation({"relocate": [SOURCED]}, {})
    # an in-frame move outside FRAME is still refused as before
    assert any("utm_bbox" in s for s in rel(**{"from": [1800.0, 300.0, 2200.0, 700.0]}).check_inside(FRAME, FRAME))


def test_compose_heights_pastes_a_hill_from_the_source_dem():
    dem = frame_dem()
    r = two()
    srcs = {1: (source_dem(), SRC_FRAME)}
    dz = rl.rim_dz(dem, FRAME, 1.0, r.moves[1], srcs[1])
    assert dz == pytest.approx(-196.0)             # the source ground at 300 m onto this frame's 104 m east side
    dzs = [rl.rim_dz(dem, FRAME, 1.0, r.moves[0]), dz]
    out = rl.compose_heights(dem, FRAME, 1.0, FRAME, r, dzs, srcs)
    assert out[500, 1500] == pytest.approx(350 - 196, abs=1.0)    # the source cone's top, set on the ground here
    assert out[500, 500] == pytest.approx(160.0, abs=1.0)          # the in-frame patch reads this frame as before
    assert out[100, 1950] == 104.0                                 # ground outside both patches untouched
    assert np.abs(out[480:520, 1290:1310] - 104).max() < 0.5       # the seam meets the ground
    # no sources: the same heights as the in-frame move alone
    one = rl.Relocation({"relocate": [MOVE]})
    assert (rl.compose_heights(dem, FRAME, 1.0, FRAME, one, dzs[:1], {}) ==
            rl.compose_heights(dem, FRAME, 1.0, FRAME, one, dzs[:1])).all()


def test_compose_classes_from_a_source_grid_and_only_the_moves_asked():
    cls = np.zeros((500, 1000), np.uint8)
    cls[200:300, 750:850] = 7                        # the in-frame source square's middle
    other = np.full((500, 500), 9, np.uint8)         # the source grid, all class 9, at 2 m
    r = two()
    out = rl.compose_classes(cls, FRAME, 2.0, FRAME, r, {1: (other, SRC_FRAME)})
    assert (out[200:300, 200:300] == 7).all()        # in-frame patch at 400..600
    assert (out[200:300, 700:800] == 9).all()        # sourced patch at 1400..1600
    only = rl.compose_classes(cls, FRAME, 2.0, FRAME, r, {1: (other, SRC_FRAME)}, moves=[1])
    assert (only[200:300, 200:300] == 0).all() and (only[200:300, 700:800] == 9).all()
    # a source grid at another resolution (LANDFIRE clips each have their own 30 m grid)
    coarse = np.full((100, 100), 5, np.uint8)        # 10 m
    out10 = rl.compose_classes(cls, FRAME, 2.0, FRAME, r, {1: (coarse, SRC_FRAME, 10.0)}, moves=[1])
    assert (out10[200:300, 700:800] == 5).all()


def test_in_frame_drops_only_the_sourced_patches():
    r = two()
    x = np.array([500.0, 1500.0, 100.0]); y = np.array([500.0, 500.0, 900.0])
    sel = r.select(x, y)
    assert list(sel) == [0, 1, -1] and list(r.in_frame(sel)) == [0, -1, -1]
    sx, sy = r.source_xy(x, y, r.in_frame(sel))
    assert np.allclose(sx, [1600, 1500, 100])         # the sourced patch reads where it is drawn
    one = rel()
    s1 = one.select(x, y)
    assert one.in_frame(s1) is s1                     # no sourced move: unchanged
    assert np.allclose(one.source_xy(x, y, one.in_frame(s1)), one.source_xy(x, y))


def test_osm_source_doc_keeps_only_what_its_move_takes():
    src_doc = {"elements": [
        {"type": "node", "id": 1, "lat": 0.5, "lon": 10.5, "tags": {"natural": "peak"}},                   # in the patch
        {"type": "node", "id": 2, "lat": 0.9, "lon": 10.1, "tags": {"amenity": "bench"}},                  # outside it
        {"type": "way", "id": 10, "tags": {"highway": "tertiary"}, "nodes": [1, 2, 3, 4],                  # a road through
         "geometry": [ll(10100, 500), ll(10400, 500), ll(10600, 500), ll(10900, 500)]},
        {"type": "way", "id": 20, "tags": {"piste:type": "downhill"}, "nodes": [5, 6],
         "geometry": [ll(10450, 600), ll(10550, 400)]},
        {"type": "relation", "id": 30, "members": [{"geometry": [ll(10900, 900), ll(10950, 950)]}]},       # outside
        {"type": "relation", "id": 31, "members": []},
    ]}
    r = two()
    out, moved = r.osm(src_doc, TO_UTM, TO_LL, whole=False, source="other")
    ids = [e["id"] for e in out["elements"]]
    assert sorted(ids) == [1, 10, 20]
    peak = next(e for e in out["elements"] if e["id"] == 1)
    assert peak["lon"] == pytest.approx(1.5) and peak["lat"] == pytest.approx(0.5)
    (road,) = [e for e in out["elements"] if e["id"] == 10]   # only the piece inside the patch, moved
    assert [p["lon"] for p in road["geometry"]] == pytest.approx([1.4, 1.6]) and road["nodes"] == [2, 3]
    assert moved == {"Far": 0, "Other hill": 3}
    # this frame's doc: an element at the sourced patch's from coordinates is not moved (that is another place),
    # and the ground under the sourced patch is cleared
    main = {"elements": [{"type": "node", "id": 7, "lat": 0.5, "lon": 10.5},
                         {"type": "node", "id": 8, "lat": 0.5, "lon": 1.33},     # under the sourced patch only
                         {"type": "node", "id": 9, "lat": 0.9, "lon": 1.9}]}
    out2, moved2 = r.osm(main, TO_UTM, TO_LL)
    assert [e["id"] for e in out2["elements"]] == [7, 9] and out2["elements"][0]["lon"] == 10.5
    assert moved2 == {"Far": 0, "Other hill": 0}


def test_record_names_the_source_only_for_a_sourced_move():
    r = two()
    assert "source" not in r.moves[0].record()
    assert r.moves[1].record()["source"] == "other"


def test_merge_class_tables():
    a = [{"VALUE": "7", "EVT_NAME": "Oak"}, {"VALUE": "8", "EVT_NAME": "Maple"}]
    b = [{"VALUE": "8", "EVT_NAME": "Maple"}, {"VALUE": "9", "EVT_NAME": "Beech"}]
    assert [r["VALUE"] for r in rl.merge_class_tables(a, b)] == ["7", "8", "9"]
    with pytest.raises(ValueError, match="two LANDFIRE versions"):
        rl.merge_class_tables(a, [{"VALUE": "7", "EVT_NAME": "Pine"}])


def test_overlapping_patches_are_refused():
    assert two().overlaps() == []
    msgs = two(to=[700.0, 500.0]).check_inside(FRAME, FRAME)
    assert any("overlap" in s for s in msgs)


def test_source_configs_reads_each_source_once(tmp_path):
    for slug, crs in (("other", "EPSG:26917"), ("elsewhere", "EPSG:32613")):
        (tmp_path / slug).mkdir()
        (tmp_path / slug / f"{slug}.json").write_text(json.dumps({"slug": slug, "crs": crs, "utm_bbox": SRC_FRAME}))
    cfg = {"crs": "EPSG:26917", "relocate": [MOVE, SOURCED, dict(SOURCED, name="Again")]}
    assert list(rl.source_configs(cfg, str(tmp_path))) == ["other"]
    assert rl.source_configs({"relocate": [MOVE]}, str(tmp_path)) == {}
    with pytest.raises(ValueError, match="is in EPSG:32613"):
        rl.source_configs(dict(cfg, relocate=[dict(SOURCED, source="elsewhere")]), str(tmp_path))
    with pytest.raises(ValueError, match="no config"):
        rl.source_configs(dict(cfg, relocate=[dict(SOURCED, source="nowhere")]), str(tmp_path))


def test_ohio_hills_config():
    """FEAT-268: Mad River pasted north of Boston Mills, beside Brandywine, on boston-mills' raw data"""
    cfg = json.load(open(paths.config_path("ohio-hills"), encoding="utf-8"))
    bm = json.load(open(paths.config_path("boston-mills"), encoding="utf-8"))
    assert cfg["raw_from"] == "boston-mills"
    for k in ("origin", "utm_bbox", "crs", "lidar", "mid_ring", "far_ring"):
        assert cfg[k] == bm[k], k
    assert cfg["relocate"][0] == bm["relocate"][0]            # Brandywine as in the standalone pack
    srcs = rl.source_configs(cfg)
    assert list(srcs) == ["mad-river-mountain"]
    mr = srcs["mad-river-mountain"]
    assert mr["source_only"] is True and "far" not in mr["lidar"] and mr["landcover"] == {"enabled": False}
    r = rl.Relocation(cfg, {s: c["utm_bbox"] for s, c in srcs.items()})
    assert [m.name for m in r.moves] == ["Brandywine", "Mad River Mountain"]
    assert r.check_inside(cfg["utm_bbox"], cfg["pack_bbox"]) == []    # inside the frames, no overlap
    ox, oy = cfg["origin"]
    pb = cfg["pack_bbox"]
    assert pb[0] <= ox <= pb[2] and pb[1] <= oy <= pb[3]
    # Mad River's runs fall to the north-west (about 325 deg); turned -90 they fall south-west, to the valley floor
    # it shares with Boston Mills' base
    assert r.moves[1].facing(325) == pytest.approx(235)
