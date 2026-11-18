import io, sys, json
import numpy as np
from PIL import Image
from scipy.ndimage import median_filter, uniform_filter, gaussian_filter
src, outdir = sys.argv[1], sys.argv[2]
rng = np.random.default_rng(7)
full = Image.open(src).convert('RGB')
FW, FH = full.size
W = 1600; H = round(FH * W / FW)
def jpeg(img_arr, q):
    b = io.BytesIO(); Image.fromarray(np.clip(img_arr + 0.5, 0, 255).astype(np.uint8)).save(b, 'JPEG', quality=q); b.seek(0)
    return np.asarray(Image.open(b).convert('RGB')).astype(np.float32)
# 1. the "camera" photo: downscale, add sensor-like noise, saved once at q=80 (its history)
base = np.asarray(full.resize((W, H), Image.LANCZOS)).astype(np.float32)
noise = rng.normal(0, 3.2, (H, W, 1)) + rng.normal(0, 1.2, (H, W, 3))
base = jpeg(base + noise, 80)
# 2. the forgery: palm copied from the high-res original, shrunk (which also smooths away its noise)
k = FW / 900
x0, y0, x1, y1 = int(392*k), int(2*k), int(500*k), int(150*k)
palm = full.crop((x0, y0, x1, y1))
sc = 0.30
palm = palm.resize((int(palm.width*sc), int(palm.height*sc)), Image.LANCZOS)
P = gaussian_filter(np.asarray(palm).astype(np.float32), (0.6, 0.6, 0))
ph, pw = P.shape[:2]
lum = P @ np.array([0.299, 0.587, 0.114], np.float32)
# patch mask: feathered rounded rectangle (forger pasted a patch including some sky)
yy, xx = np.mgrid[0:ph, 0:pw].astype(np.float32)
edge = np.minimum.reduce([xx, pw-1-xx, yy, (ph-1-yy)])
m = np.clip(edge / 14.0, 0, 1)
m = m * np.clip((ph - yy) / (ph*0.22), 0, 1)  # trunk fades into the bushes
kb = W / 900
px = int(772*kb) - pw//2; py = int(206*kb) - ph
# colour-match patch sky to destination sky
dst = base[py:py+ph, px:px+pw]
skyP = lum > np.percentile(lum, 60)
P = P + (dst[skyP].mean(0) - P[skyP].mean(0)) * 0.9
comp = base.copy()
comp[py:py+ph, px:px+pw] = dst*(1-m[...,None]) + P*m[...,None]
tam = jpeg(comp, 92)   # forger saves at high quality
# 3. ELA: resave at the photo's original quality and amplify the difference
rec = jpeg(tam, 80)
ela = np.abs(tam - rec).max(axis=2)
ela_s = gaussian_filter(ela, 1.5)
mask_full = np.zeros((H, W), bool); mask_full[py:py+ph, px:px+pw] = m > 0.6
leaf = np.zeros((H, W), bool); leaf[py:py+ph, px:px+pw] = (m > 0.6) & (lum < np.percentile(lum, 45))
# compare with the REAL palm (same texture)
rx0 = int(392*kb); ry0 = 0; rx1 = int(500*kb); ry1 = int(150*kb)
real_leaf = np.zeros((H, W), bool)
g0 = tam @ np.array([0.299, 0.587, 0.114], np.float32)
real_leaf[ry0:ry1, rx0:rx1] = g0[ry0:ry1, rx0:rx1] < np.percentile(g0[ry0:ry1, rx0:rx1], 45)
print('ELA pasted leaves', ela[leaf].mean(), 'real palm leaves', ela[real_leaf].mean(), 'ratio', ela[leaf].mean()/ela[real_leaf].mean())
def cmap(v):
    v = np.clip(v, 0, 1)
    stops = np.array([[0.0, 4,6,10],[0.22, 16,34,70],[0.5, 106,168,255],[0.78,255,176,32],[1.0,255,246,220]], np.float32)
    out = np.zeros(v.shape+(3,), np.float32)
    for i in range(len(stops)-1):
        a, b = stops[i], stops[i+1]
        sel = (v >= a[0]) & (v <= b[0])
        t = ((v - a[0]) / (b[0]-a[0]))[sel][:, None]
        out[sel] = a[1:]*(1-t) + b[1:]*t
    return out.astype(np.uint8)
norm = ela_s / np.percentile(ela_s, 99.6)
Image.fromarray(cmap(norm**0.75)).save(f'{outdir}/ela-map.webp', quality=86)
Image.fromarray(np.clip(tam+0.5,0,255).astype(np.uint8)).save(f'{outdir}/ela-photo.webp', quality=90)
# 4. noise residual r = I - median3x3(I), local RMS
g = tam @ np.array([0.299, 0.587, 0.114], np.float32)
r = g - median_filter(g, 3)
loc = np.sqrt(uniform_filter(r*r, 15))
# normalise so the camera noise of the open sky sits at 0.4 (mid blue): quieter regions go dark, texture saturates
sky_ref = np.median(loc[4:int(H*0.14), 4:int(W*0.7)])
nl = loc / (2.5 * sky_ref)
Image.fromarray(cmap(np.clip(nl,0,1))).save(f'{outdir}/noise-map.webp', quality=86)
Image.fromarray(np.clip(128 + r*9, 0, 255).astype(np.uint8)).save(f'{outdir}/noise-residual.webp', quality=82)
sky_patch = np.zeros((H, W), bool); sky_patch[py:py+ph, px:px+pw] = (m > 0.8) & (lum > np.percentile(lum, 70))
sky_ring = np.zeros((H, W), bool); sky_ring[max(0,py-40):py+ph, max(0,px-90):px] = True
print('noise sky in patch', loc[sky_patch].mean(), 'sky outside', loc[sky_ring].mean())
bb = dict(x=round(px/W,4), y=round(py/H,4), w=round(pw/W,4), h=round(ph/H,4))
json.dump({"width":W,"height":H,"splice":bb,
  "ela_ratio_vs_real_palm":round(float(ela[leaf].mean()/ela[real_leaf].mean()),2),
  "noise_ratio_sky":round(float(loc[sky_ring].mean()/max(1e-6,loc[sky_patch].mean())),2),
  "history":"camera photo + synthetic sensor noise, JPEG q80; palm pasted from high-res copy at 30% scale; saved JPEG q92; ELA resave q80"},
  open(f'{outdir}/ela-meta.json','w'), indent=1)
print(bb)
prev = [Image.fromarray(np.clip(tam+0.5,0,255).astype(np.uint8)), Image.open(f'{outdir}/ela-map.webp'), Image.open(f'{outdir}/noise-map.webp')]
out = Image.new('RGB', (800, 534*3))
for i, im in enumerate(prev): out.paste(im.convert('RGB').resize((800, 534)), (0, 534*i))
out.save(f'{outdir}/prev.png')
