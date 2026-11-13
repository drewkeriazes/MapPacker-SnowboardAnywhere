"""FEAT-298: measure per-tree crown width against openness from a resort's raw 3DEP lidar (docs/research/crown-widths.md).

python tools/crown_widths.py <raw_resort_dir> <crs> <originX> <originY> <x> <y> [radius_m]
  e.g. raw/park-city-mountain EPSG:26912 453600 4500500 724 2032 600
The centre is in the pack's local metres; reads raw/<slug>/ept (and ept_deep_pilot) *.laz.
"""
import laspy, glob, os, sys, numpy as np
from pyproj import Transformer
from scipy.interpolate import griddata, RegularGridInterpolator
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
R, CRS = sys.argv[1], sys.argv[2]; OX, OY, SX, SY = map(float, sys.argv[3:7]); RAD = int(sys.argv[7]) if len(sys.argv) > 7 else 600
X=[];Y=[];Z=[];C=[]
for sub in ['ept', 'ept_deep_pilot']:
    fs = glob.glob(os.path.join(R, sub, '*.laz'))
    if not fs: continue
    with laspy.open(fs[0]) as r0: crs_in = r0.header.parse_crs()
    t = Transformer.from_crs(crs_in or 'EPSG:3857', CRS, always_xy=True); ti = Transformer.from_crs(CRS, crs_in or 'EPSG:3857', always_xy=True)
    xs, ys = ti.transform([OX+SX-RAD, OX+SX+RAD, OX+SX-RAD, OX+SX+RAD], [OY+SY-RAD, OY+SY-RAD, OY+SY+RAD, OY+SY+RAD])
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    for f in fs:
        with laspy.open(f) as r:
            h = r.header
            if h.maxs[0] < bx0 or h.mins[0] > bx1 or h.maxs[1] < by0 or h.mins[1] > by1: continue
            p = r.read()
        x = np.asarray(p.x); y = np.asarray(p.y); m = (x >= bx0) & (x <= bx1) & (y >= by0) & (y <= by1)
        if not m.any(): continue
        xx, yy = t.transform(x[m], y[m]); X.append(xx - OX); Y.append(yy - OY); Z.append(np.asarray(p.z)[m]); C.append(np.asarray(p.classification)[m])
x = np.concatenate(X); y = np.concatenate(Y); z = np.concatenate(Z); c = np.concatenate(C)
k = (np.abs(x - SX) < RAD) & (np.abs(y - SY) < RAD); x, y, z, c = x[k], y[k], z[k], c[k]
g = c == 2
print(f'{len(x)} points, {len(x)/(2*RAD)**2:.2f}/m2, ground z median {np.median(z[g]):.0f} m')
CELL = 1.0; x0, y0 = SX-RAD, SY-RAD; n = int(2*RAD/CELL)
gx = np.arange(0, 2*RAD, 2.0) + x0 + 1; gy = np.arange(0, 2*RAD, 2.0) + y0 + 1
GX, GY = np.meshgrid(gx, gy)
dem = griddata((x[g], y[g]), z[g], (GX, GY), method='linear')
dem = np.where(np.isnan(dem), griddata((x[g], y[g]), z[g], (GX, GY), method='nearest'), dem)
hag = z - RegularGridInterpolator((gy, gx), dem, bounds_error=False, fill_value=None)((y, x))
veg = (~g) & (hag > 2) & (hag < 50)
ix = ((x[veg]-x0)/CELL).astype(int); iy = ((y[veg]-y0)/CELL).astype(int); ok = (ix>=0)&(ix<n)&(iy>=0)&(iy<n)
chm = np.zeros((n, n)); np.maximum.at(chm, (iy[ok], ix[ok]), hag[veg][ok])
chm = ndi.grey_closing(chm, size=3)
can = chm >= 3
yy, xx = np.mgrid[-RAD:RAD, -RAD:RAD] + 0.5; inner = np.hypot(yy, xx) < RAD - 20
print(f'canopy share (>= 3 m) {can[inner].mean():.3f}')
# canopy cover within 10 m (the model's openness input), as a disc
dy, dx = np.mgrid[-10:11, -10:11]; disc = (np.hypot(dy, dx) <= 10).astype(float); disc /= disc.sum()
cov10 = ndi.convolve(can.astype(float), disc, mode='nearest')
rows = []
for SIG, WIN, MINH in [(1.0, 5, 6), (1.5, 7, 6), (2.0, 9, 6)]:
    sm = ndi.gaussian_filter(chm, SIG)
    peaks = (sm == ndi.maximum_filter(sm, size=WIN)) & (sm >= MINH) & can
    mk, npk = ndi.label(peaks)
    markers = mk.astype(np.int32); markers[~ndi.binary_dilation(can, iterations=1)] = npk + 1
    inp = np.clip(255 - sm * 255 / max(1, sm.max()), 0, 255).astype(np.uint8)
    seg = ndi.watershed_ift(inp, markers); seg[~can] = 0
    ids = np.arange(1, npk + 1)
    area = ndi.sum(np.ones_like(seg), seg, ids); hmax = ndi.maximum(chm, seg, ids)
    cy_, cx_ = np.array(ndi.center_of_mass(peaks, mk, ids)).T
    px = x0 + (cx_ + .5); py = y0 + (cy_ + .5)
    ri, ci = np.clip(cy_.round().astype(int), 0, n-1), np.clip(cx_.round().astype(int), 0, n-1)
    inside = np.hypot(px - SX, py - SY) < RAD - 20
    dnn = cKDTree(np.c_[px, py]).query(np.c_[px, py], k=2)[0][:, 1]
    cov = cov10[ri, ci]
    r = np.sqrt(area / np.pi); h = hmax
    sel = inside & (area >= 3) & (h >= MINH)
    r, h, dnn, cov = r[sel], h[sel], dnn[sel], cov[sel]; rh = r / h
    print(f'\n== sigma {SIG}, tops {WIN/2:.1f} m apart: {len(r)} trees, h median {np.median(h):.1f} m')
    for lo, hi in [(0, .25), (.25, .5), (.5, .75), (.75, .9), (.9, 1.01)]:
        m = (cov >= lo) & (cov < hi)
        if m.sum() < 10: continue
        print(f'  cover10 {lo:.2f}-{hi:.2f}: {m.sum():5d}  r/h p10 {np.percentile(rh[m],10):.3f} p50 {np.median(rh[m]):.3f} p90 {np.percentile(rh[m],90):.3f}  h {np.median(h[m]):.1f} m')
    m = dnn >= 15
    if m.sum() >= 5: print(f'  isolated (nn >= 15 m): {m.sum():5d}  r/h p50 {np.median(rh[m]):.3f}')
    print(f'  corr(r/h, cover10) {np.corrcoef(cov, rh)[0,1]:.2f}')
