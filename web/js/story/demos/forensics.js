// Chapter 04 demos. Where possible these are REAL computations in the browser
// (ELA/noise maps precomputed by tools/make_ela.py; FFT and DCT computed live).
import { $, $$, C, rgba, rng, gauss, fitCanvas, visibleLoop, onceVisible, loadFace, loadPhoto, photoGray, clamp, lerp, smooth, segmented, reduceMotion } from '../util.js';
import { heat } from './forge.js';

const gsap = window.gsap;
const presenting = () => !!(window.VX && window.VX.presenting);

/* ─────────────── B · ELA before/after ─────────────── */
export async function initELA(frame) {
  const cmp = $('#ela-compare'), range = $('.compare__range', cmp), ratioEl = $('#ela-ratio');
  try {
    const meta = await fetch('assets/story/forensics/ela-meta.json').then((r) => r.json());
    ratioEl.textContent = meta.ela_ratio_vs_real_palm.toFixed(1);
    const b = meta.splice, box = $('#ela-box');
    Object.assign(box.style, { left: `${b.x * 100}%`, top: `${b.y * 100}%`, width: `${b.w * 100}%`, height: `${b.h * 100}%` });
  } catch (e) { /* keep defaults */ }
  const S = { v: 100 };
  let tw = null;
  const set = (v) => { S.v = v; range.value = v; cmp.style.setProperty('--pos', `${v}%`); };
  range.addEventListener('input', () => { tw && tw.kill(); set(+range.value); });
  const to = (v, d = 1.8) => { tw && tw.kill(); tw = gsap.to(S, { v, duration: reduceMotion ? 0.01 : d, ease: 'power2.inOut', onUpdate: () => set(S.v) }); return tw; };
  const step = (n) => {
    if (n === 0) { cmp.classList.remove('is-boxed'); to(100, 0.8); }
    if (n === 1) { cmp.classList.remove('is-boxed'); to(0, 2.2); }
    if (n === 2) { to(52, 1.2); setTimeout(() => cmp.classList.add('is-boxed'), 500); }
  };
  onceVisible(frame, () => {
    if (presenting()) return;
    setTimeout(() => { if (!presenting()) to(0, 2.4).then(() => setTimeout(() => { if (!presenting()) step(2); }, 900)); }, 2200);
  }, 0.5);
  return step;
}

/* ─────────────── C · Noise lens ─────────────── */
export async function initNoise(frame) {
  const lens = $('#noise-lens'), valEl = $('#noise-val'), verEl = $('#noise-verdict');
  // read the precomputed noise map back to estimate local noise under the lens
  const img = new Image(); img.src = 'assets/story/forensics/noise-map.webp';
  await img.decode().catch(() => {});
  const MW = 400, MH = Math.round(400 * 1067 / 1600);
  const cv = document.createElement('canvas'); cv.width = MW; cv.height = MH;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  cx.drawImage(img, 0, 0, MW, MH);
  const px = cx.getImageData(0, 0, MW, MH).data;
  // invert the colour map (same stops as make_ela.py) through a LUT
  const lut = Array.from({ length: 64 }, (_, i) => heatPy(i / 63));
  const level = new Float32Array(MW * MH);
  for (let i = 0; i < MW * MH; i++) {
    let best = 1e9, bi = 0;
    for (let k = 0; k < 64; k++) { const c = lut[k]; const d = (c[0] - px[i * 4]) ** 2 + (c[1] - px[i * 4 + 1]) ** 2 + (c[2] - px[i * 4 + 2]) ** 2; if (d < best) { best = d; bi = k; } }
    level[i] = bi / 63;
  }
  // Real noise analysis is done on FLAT pixels only: leaves, edges and texture light up any residual map,
  // so they are masked out (level > FLAT) and the median of what is left is compared with the sky's.
  const FLAT = 0.55;
  const sky = [];
  for (let y = 4; y < MH * 0.14; y++) for (let x = 4; x < MW * 0.7; x++) sky.push(level[y * MW + x]);
  sky.sort((a, b) => a - b);
  const ref = sky[Math.floor(sky.length / 2)] || 0.4;
  const S = { x: 0.15, y: 0.12 };
  let tw = null, idle = true;
  const R = 0.03; // probe radius (fraction of width) — drawn on screen as the inner dashed circle
  const read = () => {
    const vals = [];
    let n = 0;
    const cxp = S.x * MW, cyp = S.y * MH, rr = R * MW;
    for (let y = Math.max(0, Math.floor(cyp - rr)); y < Math.min(MH, cyp + rr); y++)
      for (let x = Math.max(0, Math.floor(cxp - rr)); x < Math.min(MW, cxp + rr); x++) {
        if ((x - cxp) ** 2 + (y - cyp) ** 2 > rr * rr) continue;
        n++;
        const v = level[y * MW + x];
        if (v <= FLAT) vals.push(v);
      }
    const flatFrac = n ? vals.length / n : 0;
    if (flatFrac < 0.3) {
      valEl.textContent = '—';
      verEl.textContent = 'MOSTLY TEXTURE — CAN’T JUDGE'; verEl.className = '';
      return;
    }
    vals.sort((a, b) => a - b);
    const ratio = vals[Math.floor(vals.length / 2)] / ref;
    valEl.textContent = `${ratio.toFixed(2)}× SKY`;
    let msg = 'CONSISTENT', cls = 'is-ok';
    if (ratio < 0.65) { msg = 'TOO QUIET — INCONSISTENT'; cls = 'is-hot'; }
    verEl.textContent = msg; verEl.className = cls;
  };
  const sizeLens = () => {
    lens.style.setProperty('--lr', `${Math.round(lens.clientWidth * 0.1)}px`);
    lens.style.setProperty('--pr', `${Math.round(lens.clientWidth * R)}px`);
  };
  sizeLens(); addEventListener('resize', sizeLens);
  const set = (x, y) => { S.x = x; S.y = y; lens.style.setProperty('--lx', `${x * 100}%`); lens.style.setProperty('--ly', `${y * 100}%`); read(); };
  lens.addEventListener('pointermove', (e) => {
    const r = lens.getBoundingClientRect();
    idle = false; tw && tw.kill();
    set(clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height));
  });
  lens.addEventListener('pointerleave', () => { idle = true; });
  set(S.x, S.y);
  const target = { x: 0.8525, y: 0.29 }; // the quiet gap under the pasted palm's fronds (inside the splice box)
  const goPalm = () => { idle = false; tw && tw.kill(); tw = gsap.to(S, { x: target.x, y: target.y, duration: reduceMotion ? 0.01 : 1.8, ease: 'power2.inOut', onUpdate: () => set(S.x, S.y) }); };
  visibleLoop(lens, (t) => {
    if (!idle || presenting()) return;
    // slow drift across the sky, passing the pasted palm
    set(0.5 + Math.sin(t * 0.32) * 0.4, 0.17 + Math.sin(t * 0.47) * 0.09);
  });
  return (n) => { if (n === 0) { idle = false; tw && tw.kill(); tw = gsap.to(S, { x: 0.15, y: 0.12, duration: 1, onUpdate: () => set(S.x, S.y) }); } else goPalm(); };
}
function heatPy(v) { // identical stops to tools/make_ela.py cmap()
  const s = [[0, 4, 6, 10], [0.22, 16, 34, 70], [0.5, 106, 168, 255], [0.78, 255, 176, 32], [1, 255, 246, 220]];
  for (let i = 0; i < s.length - 1; i++) if (v <= s[i + 1][0]) { const t = (v - s[i][0]) / (s[i + 1][0] - s[i][0]); return [0, 1, 2].map((k) => s[i][k + 1] + (s[i + 1][k + 1] - s[i][k + 1]) * t); }
  return [255, 246, 220];
}

/* ─────────────── D · FFT ─────────────── */
function fft1d(re, im, n) {
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) { let t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len, wr = Math.cos(ang), wi = Math.sin(ang), h = len >> 1;
    for (let i = 0; i < n; i += len) {
      let cr = 1, ci = 0;
      for (let j = 0; j < h; j++) {
        const a = i + j, b = a + h;
        const vr = re[b] * cr - im[b] * ci, vi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - vr; im[b] = im[a] - vi; re[a] += vr; im[a] += vi;
        const t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
      }
    }
  }
}
// log-magnitude spectrum, fft-shifted, of an N×N image (Hann-windowed)
export function spectrum(g, N) {
  const re = new Float64Array(N * N), im = new Float64Array(N * N);
  let mean = 0; for (let i = 0; i < N * N; i++) mean += g[i]; mean /= N * N;
  const win = new Float64Array(N); for (let i = 0; i < N; i++) win[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (N - 1));
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) re[y * N + x] = (g[y * N + x] - mean) * win[x] * win[y];
  const rr = new Float64Array(N), ri = new Float64Array(N);
  for (let y = 0; y < N; y++) { for (let x = 0; x < N; x++) { rr[x] = re[y * N + x]; ri[x] = im[y * N + x]; } fft1d(rr, ri, N); for (let x = 0; x < N; x++) { re[y * N + x] = rr[x]; im[y * N + x] = ri[x]; } }
  for (let x = 0; x < N; x++) { for (let y = 0; y < N; y++) { rr[y] = re[y * N + x]; ri[y] = im[y * N + x]; } fft1d(rr, ri, N); for (let y = 0; y < N; y++) { re[y * N + x] = rr[y]; im[y * N + x] = ri[y]; } }
  const out = new Float32Array(N * N), h = N >> 1;
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    const i = y * N + x, sx = (x + h) % N, sy = (y + h) % N;
    out[sy * N + sx] = Math.log1p(Math.hypot(re[i], im[i]));
  }
  return out;
}
function drawSpectrum(cv, sp, N, lo, hi) {
  const ctx = cv.getContext('2d');
  const img = ctx.createImageData(N, N);
  for (let i = 0; i < N * N; i++) {
    const v = clamp((sp[i] - lo) / (hi - lo));
    // neutral analysis palette: ink → scan blue → bone
    const a = v < 0.6 ? v / 0.6 : 1, b = v < 0.6 ? 0 : (v - 0.6) / 0.4;
    img.data[i * 4] = lerp(lerp(4, 106, a), 240, b);
    img.data[i * 4 + 1] = lerp(lerp(6, 168, a), 238, b);
    img.data[i * 4 + 2] = lerp(lerp(10, 255, a), 230, b);
    img.data[i * 4 + 3] = 255;
  }
  ctx.putImageData(img, 0, 0);
}
function drawGray(cv, g, N) {
  const ctx = cv.getContext('2d'); const img = ctx.createImageData(N, N);
  for (let i = 0; i < N * N; i++) { const v = clamp(g[i], 0, 255); img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 255; }
  ctx.putImageData(img, 0, 0);
}
// the "imprint" a stride-2 transposed convolution leaves when its kernel taps overlap unevenly
function tcImprint(N, layers = 2, k = [0.42, 1, 0.42]) {
  let n = N >> layers, cur = new Float32Array(n * n).fill(1);
  for (let l = 0; l < layers; l++) {
    const m = n * 2, z = new Float32Array(m * m), t = new Float32Array(m * m), o = new Float32Array(m * m);
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) z[(2 * y) * m + 2 * x] = cur[y * n + x];
    for (let y = 0; y < m; y++) for (let x = 0; x < m; x++) t[y * m + x] = k[0] * z[y * m + (x - 1 + m) % m] + k[1] * z[y * m + x] + k[2] * z[y * m + (x + 1) % m];
    for (let y = 0; y < m; y++) for (let x = 0; x < m; x++) o[y * m + x] = k[0] * t[((y - 1 + m) % m) * m + x] + k[1] * t[y * m + x] + k[2] * t[((y + 1) % m) * m + x];
    let mean = 0; for (let i = 0; i < m * m; i++) mean += o[i]; mean /= m * m;
    for (let i = 0; i < m * m; i++) o[i] /= mean;
    cur = o; n = m;
  }
  return cur;
}
function blur(g, N, s) {
  if (s <= 0.01) return g;
  const r = Math.ceil(s * 3), k = []; let sum = 0;
  for (let i = -r; i <= r; i++) { const v = Math.exp(-(i * i) / (2 * s * s)); k.push(v); sum += v; }
  for (let i = 0; i < k.length; i++) k[i] /= sum;
  const t = new Float32Array(N * N), o = new Float32Array(N * N);
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) { let a = 0; for (let i = -r; i <= r; i++) a += g[y * N + Math.min(N - 1, Math.max(0, x + i))] * k[i + r]; t[y * N + x] = a; }
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) { let a = 0; for (let i = -r; i <= r; i++) a += t[Math.min(N - 1, Math.max(0, y + i)) * N + x] * k[i + r]; o[y * N + x] = a; }
  return o;
}
function peakRatio(sp, N) {
  // diagonal N/4 positions only: off the axes, where natural photos have no special energy
  const h = N >> 1, q = N >> 2, pts = [[h + q, h + q], [h - q, h - q], [h + q, h - q], [h - q, h + q]];
  let pk = 0, bg = [];
  for (const [x, y] of pts) {
    let m = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) m = Math.max(m, sp[(y + dy) * N + x + dx]);
    pk += m;
    for (let dy = -7; dy <= 7; dy++) for (let dx = -7; dx <= 7; dx++) if (Math.abs(dx) > 3 || Math.abs(dy) > 3) bg.push(sp[(y + dy) * N + x + dx]);
  }
  bg.sort((a, b) => a - b);
  const med = bg[Math.floor(bg.length / 2)];
  return Math.exp(pk / pts.length - med); // log-magnitude difference → amplitude ratio
}

let ganTile = null;
async function tiles(N = 256) {
  const real = await photoGray(N, { x: 0.12, y: 0.12, w: 0.6 });
  if (!ganTile) {
    const P = tcImprint(N, 2, [0.47, 1, 0.47]);
    const soft = blur(real, N, 0.6);
    ganTile = new Float32Array(N * N);
    for (let i = 0; i < N * N; i++) ganTile[i] = soft[i] * P[i];
  }
  return { real, gan: ganTile };
}

export async function initFFT(frame) {
  const N = 256, fig = $('.fft', frame), imgCv = $('#fft-img'), spCv = $('#fft-spec'), read = $('#fft-read');
  const { real, gan } = await tiles(N);
  const spR = spectrum(real, N), spG = spectrum(gan, N);
  // shared display range so the two are comparable
  const all = Array.from(spR).sort((a, b) => a - b);
  const lo = all[Math.floor(all.length * 0.05)], hi = all[Math.floor(all.length * 0.9995)] + 0.6;
  const rR = peakRatio(spR, N), rG = peakRatio(spG, N);
  const peaks = $$('#fft-peaks i');
  const pos = [[75, 50], [25, 50], [50, 75], [50, 25], [75, 75], [25, 25], [75, 25], [25, 75]];
  peaks.forEach((p, i) => { p.style.left = pos[i][0] + '%'; p.style.top = pos[i][1] + '%'; p.style.transitionDelay = `${i * 60}ms`; });
  const show = (mode) => {
    const g = mode === 'gan';
    drawGray(imgCv, g ? gan : real, N);
    drawSpectrum(spCv, g ? spG : spR, N, lo, hi);
    fig.classList.toggle('is-gan', g);
    read.innerHTML = `DIAGONAL PEAKS AT f = N/4 vs BACKGROUND: <b>${(g ? rG : rR).toFixed(1)}×</b> &nbsp;·&nbsp; ${g ? '<span class="is-synthetic">PERIODIC ARTIFACT DETECTED</span>' : '<span class="is-authentic">SMOOTH NATURAL FALL-OFF</span>'}`;
  };
  const setMode = segmented($('.fft__toggle', frame), show);
  show('real');
  let auto = null;
  onceVisible(frame, () => {
    if (presenting()) return;
    let m = 'real';
    auto = setInterval(() => { if (presenting() || !frame.isConnected) return clearInterval(auto); m = m === 'real' ? 'gan' : 'real'; setMode(m); }, 3800);
  }, 0.5);
  $('.fft__toggle', frame).addEventListener('click', () => auto && clearInterval(auto));
  return (n) => { auto && clearInterval(auto); setMode(n ? 'gan' : 'real'); };
}

export async function initLimitBlur() {
  const N = 256, cv = $('#lim-fft'), range = $('#lim-range');
  if (!cv) return;
  const { real, gan } = await tiles(N);
  const spR = spectrum(real, N);
  const all = Array.from(spR).sort((a, b) => a - b);
  const lo = all[Math.floor(all.length * 0.05)], hi = all[Math.floor(all.length * 0.9995)] + 0.6;
  // Each slider value's spectrum is computed once and cached (blur + 256² FFT ≈ 15–40 ms on a slow CPU).
  const cache = new Map();
  const specFor = (v) => {
    if (cache.has(v)) return cache.get(v);
    const s = (v / 100) * 2.4;
    const g = blur(gan, N, s);
    const r = rng(5); // a little re-quantisation noise, like a re-save
    if (s > 0) for (let i = 0; i < g.length; i++) g[i] += (r() - 0.5) * s * 2;
    const sp = spectrum(g, N);
    cache.set(v, sp);
    return sp;
  };
  let pend = false, shown = -1;
  const draw = () => {
    pend = false;
    const v = +range.value;
    range.style.setProperty('--fill', `${v}%`);
    if (v === shown) return;
    shown = v;
    drawSpectrum(cv, specFor(v), N, lo, hi);
  };
  range.addEventListener('input', () => { if (!pend) { pend = true; requestAnimationFrame(draw); } });
  // Auto-sweep at 4 Hz, only while the card is on screen and nobody has touched the slider.
  let dir = 1, timer = null, touched = reduceMotion;
  const tick = () => {
    if (document.hidden) return;
    let v = +range.value + dir * 4;
    if (v >= 100 || v <= 0) dir *= -1;
    range.value = clamp(v, 0, 100); draw();
  };
  new IntersectionObserver((es) => {
    for (const e of es) {
      if (e.isIntersecting) { draw(); if (!touched && !timer) timer = setInterval(tick, 250); }
      else if (timer) { clearInterval(timer); timer = null; }
    }
  }, { threshold: 0.1 }).observe(cv);
  range.addEventListener('pointerdown', () => { touched = true; clearInterval(timer); timer = null; }, { once: true });
}

/* ─────────────── E · JPEG double quantisation ─────────────── */
const JPEG_Q = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99];
const qTable = (quality) => { const s = quality < 50 ? 5000 / quality : 200 - 2 * quality; return JPEG_Q.map((t) => Math.max(1, Math.floor((t * s + 50) / 100))); };

export async function initJPEG(frame) {
  const W = 768, H = 512, fig = $('.jpeg', frame);
  const im = await loadPhoto();
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  cx.drawImage(im, 0, 0, W, H);
  const d = cx.getImageData(0, 0, W, H).data;
  const g = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) g[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2] - 128;
  const cos = (k, x) => Math.cos(((2 * x + 1) * k * Math.PI) / 16);
  const Cc = (k) => (k === 0 ? Math.SQRT1_2 : 1);
  const coefs = [];
  for (let by = 0; by < H / 8; by++) for (let bx = 0; bx < W / 8; bx++) {
    let s = 0; // coefficient (u=0 rows, v=1 cols) = horizontal frequency 1
    for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) s += g[(by * 8 + y) * W + bx * 8 + x] * cos(1, x) * cos(0, y);
    coefs.push(0.25 * Cc(0) * Cc(1) * s);
  }
  // one textured block, full 8×8 DCT for the picture
  const blk = (() => { const bx = 30, by = 22, out = new Float32Array(64); for (let v = 0; v < 8; v++) for (let u = 0; u < 8; u++) { let s = 0; for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) s += g[(by * 8 + y) * W + bx * 8 + x] * cos(u, x) * cos(v, y); out[v * 8 + u] = 0.25 * Cc(u) * Cc(v) * s; } return out; })();
  const bctx = $('#jpeg-block').getContext('2d'); const bimg = bctx.createImageData(8, 8);
  let mx = 0; for (const v of blk) mx = Math.max(mx, Math.log1p(Math.abs(v)));
  blk.forEach((v, i) => { const [r, gg, b] = heat(Math.log1p(Math.abs(v)) / mx); bimg.data.set([r, gg, b, 255], i * 4); });
  bctx.putImageData(bimg, 0, 0);
  const qEl = $('#jpeg-q');
  const showQ = (quality) => { const t = qTable(quality); qEl.innerHTML = t.map((v, i) => `<span class="${i === 1 ? 'is-k' : ''}">${v}</span>`).join(''); };
  const hist = $('#jpeg-hist');
  const R = 22;
  const compute = (mode) => {
    const h = new Float32Array(2 * R + 1);
    for (const c of coefs) {
      let q;
      if (mode === 'single') q = Math.round(c / 3);
      else q = Math.round((Math.round(c / 5) * 5) / 3);
      if (q >= -R && q <= R) h[q + R]++;
    }
    return h;
  };
  const H1 = compute('single'), H2 = compute('double');
  const S = { k: 0 };
  const draw = () => {
    const { ctx, w, h } = fitCanvas(hist);
    ctx.clearRect(0, 0, w, h);
    const n = 2 * R + 1, bw = w / n, top = Math.max(...H1, ...H2) * 1.05;
    for (let i = 0; i < n; i++) {
      const v = lerp(H1[i], H2[i], S.k);
      const bh = Math.pow(v / top, 0.5) * (h - 26);
      const empty = S.k > 0.5 && H2[i] === 0;
      ctx.fillStyle = S.k > 0.5 ? (empty ? C.synth : rgba(C.evid, 0.9)) : rgba(C.scan, 0.9);
      if (empty) ctx.fillRect(i * bw + bw * 0.2, h - 26 - 3, bw * 0.6, 3);
      else ctx.fillRect(i * bw + bw * 0.18, h - 26 - bh, bw * 0.64, bh);
      if ((i - R) % 5 === 0) { ctx.fillStyle = C.boneFaint; ctx.font = `${Math.round(10 * (w / 700) + 4)}px "IBM Plex Mono", monospace`; ctx.textAlign = 'center'; ctx.fillText(String(i - R), i * bw + bw / 2, h - 8); }
    }
  };
  const show = (mode) => { showQ(mode === 'single' ? 85 : 78); gsap.to(S, { k: mode === 'single' ? 0 : 1, duration: reduceMotion ? 0.01 : 0.9, ease: 'power2.inOut', onUpdate: draw }); };
  const setMode = segmented($('.seg', fig), show);
  showQ(85); draw();
  addEventListener('resize', draw);
  onceVisible(frame, () => { draw(); if (!presenting()) setTimeout(() => !presenting() && setMode('double'), 2600); }, 0.4);
  return (n) => setMode(n ? 'double' : 'single');
}

/* ─────────────── F · Provenance chain ─────────────── */
export function initMeta(frame) {
  const chain = $('#c2pa-chain');
  let timer = null;
  onceVisible(frame, () => {
    if (presenting()) return;
    timer = setInterval(() => { if (presenting()) return clearInterval(timer); chain.classList.toggle('is-tampered'); }, 3400);
  }, 0.4);
  return (n) => { clearInterval(timer); chain.classList.toggle('is-tampered', n === 1); };
}

/* ─────────────── G · Blink / EAR ─────────────── */
export function initBlink(frame) {
  const fig = $('.blink', frame);
  const white = $('#eye-white'), clip = $('#eye-clip-path'), lid = $('#eye-lid');
  const v1 = $('#ear-v1'), v2 = $('#ear-v2'), hl = $('#ear-h'), ptsG = $('#eye-pts');
  const earNow = $('#ear-now'), earRate = $('#ear-rate'), chart = $('#ear-chart');
  const NS = 'http://www.w3.org/2000/svg';
  const dots = [];
  for (let i = 1; i <= 6; i++) {
    const c = document.createElementNS(NS, 'circle'); c.setAttribute('r', 7); c.setAttribute('class', `ear-pt ${i === 1 || i === 4 ? 'ear-pt--h' : 'ear-pt--v'}`);
    const t = document.createElementNS(NS, 'text'); t.setAttribute('class', 'ear-lab'); t.textContent = `p${i}`;
    ptsG.append(c, t); dots.push([c, t]);
  }
  const P1 = [110, 150], P4 = [490, 150], up = 74, lo = 40;
  let mode = 'real', hist = [], events = [], simT = 0, nextBlink = 1.2, blinkStart = -1;
  const r = rng(17);
  const gap = (rr) => (mode === 'real' ? 1.6 + rr() * 3.6 : 14 + rr() * 10); // ≈17 vs ≈3 blinks a minute
  const schedule = () => { nextBlink = simT + gap(r); };
  // pre-seed the last 60 s of (simulated) blinks so the per-minute rate is meaningful from the first frame
  const seed = () => { const rs = rng(mode === 'real' ? 41 : 43); events = []; for (let t = -60 + gap(rs); t < 0; t += gap(rs)) events.push(t); };
  const setMode = segmented($('.seg', fig), (m) => { mode = m; hist = []; simT = 0; blinkStart = -1; seed(); schedule(); });
  const closure = () => {
    if (blinkStart < 0) return 0;
    const u = simT - blinkStart;
    if (u < 0.09) return u / 0.09;
    if (u < 0.13) return 1;
    if (u < 0.32) return 1 - (u - 0.13) / 0.19;
    blinkStart = -1; return 0;
  };
  visibleLoop(fig, (t, dt) => {
    simT += dt;
    if (blinkStart < 0 && simT >= nextBlink) { blinkStart = simT; schedule(); }
    const c = closure();
    const o = 1 - c * 0.93;
    const p2 = [225, 150 - up * o + (1 - o) * 20], p3 = [375, 150 - up * o + (1 - o) * 20];
    const p6 = [225, 150 + lo - c * 4], p5 = [375, 150 + lo - c * 4];
    const upper = (pa, pb) => `C${pa[0]} ${pa[1] - 18 * o} ${pb[0]} ${pb[1] - 18 * o} `;
    const openUpper = `M${P1[0]} ${P1[1]} C225 ${150 - up - 18} 375 ${150 - up - 18} ${P4[0]} ${P4[1]}`;
    const eyePath = `M${P1[0]} ${P1[1]} ${upper(p2, p3)}${P4[0]} ${P4[1]} C${p5[0]} ${p5[1] + 14} ${p6[0]} ${p6[1] + 14} ${P1[0]} ${P1[1]}Z`;
    white.setAttribute('d', `M${P1[0]} ${P1[1]} C225 ${150 - up - 18} 375 ${150 - up - 18} ${P4[0]} ${P4[1]} C375 ${150 + lo + 14} 225 ${150 + lo + 14} ${P1[0]} ${P1[1]}Z`);
    clip.setAttribute('d', eyePath);
    lid.setAttribute('d', `${openUpper} C${p3[0]} ${p3[1] - 18 * o} ${p2[0]} ${p2[1] - 18 * o} ${P1[0]} ${P1[1]}Z`);
    const pts = [P1, p2, p3, P4, p5, p6];
    pts.forEach((p, i) => { dots[i][0].setAttribute('cx', p[0]); dots[i][0].setAttribute('cy', p[1]); dots[i][1].setAttribute('x', p[0] + (i === 0 ? -34 : i === 3 ? 14 : -10)); dots[i][1].setAttribute('y', p[1] + (i === 1 || i === 2 ? -16 : i === 4 || i === 5 ? 30 : 5)); });
    v1.setAttribute('x1', p2[0]); v1.setAttribute('y1', p2[1]); v1.setAttribute('x2', p6[0]); v1.setAttribute('y2', p6[1]);
    v2.setAttribute('x1', p3[0]); v2.setAttribute('y1', p3[1]); v2.setAttribute('x2', p5[0]); v2.setAttribute('y2', p5[1]);
    hl.setAttribute('x1', P1[0]); hl.setAttribute('y1', P1[1]); hl.setAttribute('x2', P4[0]); hl.setAttribute('y2', P4[1]);
    const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
    const ear = (dist(p2, p6) + dist(p3, p5)) / (2 * dist(P1, P4)) + (r() - 0.5) * 0.008;
    hist.push([simT, ear]);
    while (hist.length && hist[0][0] < simT - 10) hist.shift();
    const prev = hist.length > 1 ? hist[hist.length - 2][1] : ear;
    if (prev >= 0.21 && ear < 0.21) events.push(simT);
    while (events.length && events[0] < simT - 60) events.shift();
    earNow.textContent = ear.toFixed(2);
    const rate = events.length; // blinks in the last 60 s
    earRate.textContent = rate.toFixed(0);
    earRate.className = rate < 6 ? 'is-hot' : 'is-ok';
    // chart
    const { ctx, w, h } = fitCanvas(chart);
    ctx.clearRect(0, 0, w, h);
    const yv = (v) => h - 8 - (v / 0.4) * (h - 16);
    ctx.strokeStyle = rgba(C.evid, 0.8); ctx.setLineDash([5, 6]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, yv(0.21)); ctx.lineTo(w, yv(0.21)); ctx.stroke(); ctx.setLineDash([]);
    ctx.strokeStyle = mode === 'real' ? C.scan : C.scan; ctx.lineWidth = 2 * (w / 800) + 0.6;
    ctx.beginPath();
    hist.forEach(([tt, v], i) => { const x = w - ((simT - tt) / 10) * w; i ? ctx.lineTo(x, yv(v)) : ctx.moveTo(x, yv(v)); });
    ctx.stroke();
    ctx.fillStyle = C.synth;
    events.forEach((e) => { if (e > simT - 10) { const x = w - ((simT - e) / 10) * w; ctx.beginPath(); ctx.arc(x, yv(0.05), 4 * (w / 800) + 2, 0, 7); ctx.fill(); } });
  });
  seed(); schedule();
  return (n) => setMode(n ? 'fake' : 'real');
}

/* ─────────────── H · Landmark jitter ─────────────── */
export async function initJitter(frame) {
  const data = await loadFace();
  const V = data.vertices, E = data.edges, n = data.count;
  const inner = new Float32Array(n);
  for (let i = 0; i < n; i++) { const x = V[i * 3], y = V[i * 3 + 1]; const v = Math.pow(Math.abs(x / 0.66), 3) + Math.pow(Math.abs((y - 0.02) / 0.8), 3); inner[i] = clamp(1 - (v - 0.7) / 0.3); }
  const cells = [
    { cv: $('#jit-a'), g: $('#jit-ga'), v: $('#jit-va'), col: C.auth, amp: 0.0018, hist: [], noise: new Float32Array(n * 2), prev: new Float32Array(n * 2), seed: rng(1) },
    { cv: $('#jit-b'), g: $('#jit-gb'), v: $('#jit-vb'), col: C.synth, amp: 0.016, hist: [], noise: new Float32Array(n * 2), prev: new Float32Array(n * 2), seed: rng(2), flicker: true },
  ];
  // the engine reports jitter as a % of the distance between the eyes (outer eye corners 33 and 263)
  const EYE = Math.hypot(V[33 * 3] - V[263 * 3], V[33 * 3 + 1] - V[263 * 3 + 1]) || 0.6;
  let lastFrame = -1;
  visibleLoop($('.jit', frame), (t) => {
    const fi = Math.floor(t * 12); // 12 "video frames" per second
    const newFrame = fi !== lastFrame;
    lastFrame = fi;
    const yaw = Math.sin(t * 0.7) * 0.38, pitch = Math.sin(t * 0.5) * 0.08, cy = Math.cos(yaw), sy = Math.sin(yaw);
    for (const c of cells) {
      const { ctx, w, h } = fitCanvas(c.cv);
      const s = Math.min(w, h) * 0.42;
      if (newFrame) {
        let J = 0;
        for (let i = 0; i < n; i++) {
          const a = c.amp * (c.flicker ? 0.25 + inner[i] : 1);
          const nx = gauss(c.seed) * a, ny = gauss(c.seed) * a;
          J += Math.hypot(nx - c.noise[i * 2], ny - c.noise[i * 2 + 1]);
          c.prev[i * 2] = c.noise[i * 2]; c.prev[i * 2 + 1] = c.noise[i * 2 + 1];
          c.noise[i * 2] = nx; c.noise[i * 2 + 1] = ny;
        }
        const Jpx = (J / n) * s;
        c.hist.push(Jpx); if (c.hist.length > 90) c.hist.shift();
        c.v.textContent = ((J / n) / EYE * 100).toFixed(2);
      }
      ctx.clearRect(0, 0, w, h);
      const proj = (i) => {
        const x = V[i * 3] + c.noise[i * 2], y = V[i * 3 + 1] + c.noise[i * 2 + 1], z = V[i * 3 + 2];
        const X = x * cy + z * sy, Z = -x * sy + z * cy;
        const Y = y * Math.cos(pitch) - Z * Math.sin(pitch);
        return [w / 2 + X * s, h / 2 - Y * s];
      };
      const P = new Float32Array(n * 2);
      for (let i = 0; i < n; i++) { const [a, b] = proj(i); P[i * 2] = a; P[i * 2 + 1] = b; }
      if (c.flicker) { // temporal flicker: the swapped inner face's tone changes frame to frame
        const f = 0.05 + 0.07 * Math.abs(Math.sin(fi * 2.3));
        ctx.fillStyle = rgba(C.synth, f);
        ctx.beginPath(); ctx.ellipse(w / 2 + Math.sin(yaw) * s * 0.3, h / 2 - s * 0.02, s * 0.5, s * 0.66, 0, 0, 7); ctx.fill();
      }
      ctx.strokeStyle = rgba(c.col, 0.38); ctx.lineWidth = Math.max(1, w / 700);
      ctx.beginPath();
      for (let k = 0; k < E.length; k += 2) { const a = E[k], b = E[k + 1]; ctx.moveTo(P[a * 2], P[a * 2 + 1]); ctx.lineTo(P[b * 2], P[b * 2 + 1]); }
      ctx.stroke();
      ctx.fillStyle = c.col;
      const ps = Math.max(1.5, w / 300);
      for (let i = 0; i < n; i++) ctx.fillRect(P[i * 2] - ps / 2, P[i * 2 + 1] - ps / 2, ps, ps);
      // sparkline
      const gg = fitCanvas(c.g);
      gg.ctx.clearRect(0, 0, gg.w, gg.h);
      gg.ctx.strokeStyle = c.col; gg.ctx.lineWidth = Math.max(1.2, gg.w / 400);
      gg.ctx.beginPath();
      const maxJ = 4;
      c.hist.forEach((v, i) => { const x = (i / 89) * gg.w, y = gg.h - 3 - clamp(v / maxJ) * (gg.h - 6); i ? gg.ctx.lineTo(x, y) : gg.ctx.moveTo(x, y); });
      gg.ctx.stroke();
    }
  });
}

/* ─────────────── I · Spectrogram ─────────────── */
export function initSpectro(frame) {
  const fig = $('.spec', frame), cv = $('#spec-canvas'), flag = $('#spec-flag');
  const GW = 420, GH = 220;
  const build = (fake) => {
    const r = rng(fake ? 31 : 30);
    const off = document.createElement('canvas'); off.width = GW; off.height = GH;
    const ctx = off.getContext('2d'); const img = ctx.createImageData(GW, GH);
    const E = new Float32Array(GW * GH);
    const f0s = new Float32Array(GW);
    const fmax = 16000;
    for (let x = 0; x < GW; x++) {
      const tN = x / GW;
      const env = speech(tN);
      const voiced = env > 0.08;
      const f0 = fake ? 165 + 12 * Math.sin(tN * 7) : 150 + 55 * Math.sin(tN * 5.3) + 30 * Math.sin(tN * 13.1 + 1) + 18 * Math.sin(tN * 29);
      f0s[x] = voiced ? f0 : 0;
      const F = [520 + 220 * Math.sin(tN * 23), 1500 + 500 * Math.sin(tN * 11 + 2), 2600 + 200 * Math.sin(tN * 7)];
      if (voiced) for (let k = 1; k * f0 < fmax; k++) {
        const f = k * f0;
        const form = Math.exp(-(((f - F[0]) / 260) ** 2)) + 0.75 * Math.exp(-(((f - F[1]) / 380) ** 2)) + 0.45 * Math.exp(-(((f - F[2]) / 500) ** 2)) + 0.05;
        const tilt = Math.exp(-f / 4200);
        const a = env * form * tilt;
        const yc = GH - (f / fmax) * GH;
        for (let dy = -2; dy <= 2; dy++) { const y = Math.round(yc + dy); if (y >= 0 && y < GH) E[y * GW + x] += a * Math.exp(-(dy * dy) / 1.4); }
      }
      // fricatives ("s", "sh") and breaths: broadband high-frequency energy
      const fric = Math.max(0, Math.sin(tN * 37 + 0.6)) ** 18 * 0.9;
      const breath = !fake && ((tN > 0.475 && tN < 0.56) || tN < 0.035 || tN > 0.97) ? 0.32 : 0;
      for (let y = 0; y < GH; y++) {
        const f = (1 - y / GH) * fmax;
        let v = E[y * GW + x];
        v += fric * Math.exp(-(((f - 7000) / 3800) ** 2)) * (0.6 + 0.4 * r());
        v += breath * (0.4 + 0.6 * r()) * Math.exp(-f / 9000) * (f > 600 ? 1 : 0.3);
        v += (fake ? 0.004 : 0.03) * r() * Math.exp(-f / 12000); // mic hiss
        if (fake && f > 8000) v *= 0.0006; // vocoder ceiling: nothing above fs/2
        E[y * GW + x] = v;
      }
    }
    for (let i = 0; i < GW * GH; i++) {
      const v = clamp((Math.log10(E[i] + 1e-4) + 3.2) / 3.4);
      const [R, G, B] = heat(v);
      img.data[i * 4] = R; img.data[i * 4 + 1] = G; img.data[i * 4 + 2] = B; img.data[i * 4 + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    return { off, f0s };
  };
  const speech = (x) => {
    const pause = Math.abs(x - 0.52) < 0.045 || x < 0.04 || x > 0.965;
    if (pause) return 0;
    const syl = Math.sin(x * Math.PI * 2 * 4.6) * 0.5 + 0.5;
    return 0.25 + 0.75 * Math.pow(syl, 1.3);
  };
  const cache = { real: build(false), fake: build(true) };
  let mode = 'real';
  const setMode = segmented($('.seg', fig), (m) => {
    mode = m; fig.classList.toggle('is-fake', m === 'fake');
    flag.textContent = m === 'fake' ? 'BREATHS: 0 · F0 RANGE: NARROW · ENERGY STOPS AT 8 kHz' : 'BREATHS: 3 · F0 RANGE: WIDE · ENERGY UP TO 16 kHz';
  });
  setMode('real', true);
  flag.textContent = 'BREATHS: 3 · F0 RANGE: WIDE · ENERGY UP TO 16 kHz';
  visibleLoop(cv, (t) => {
    const { ctx, w, h } = fitCanvas(cv);
    const { off, f0s } = cache[mode];
    ctx.imageSmoothingEnabled = true;
    ctx.drawImage(off, 0, 0, w, h);
    // F0 contour overlay on its own scale (80–300 Hz mapped to the lower 40%)
    ctx.strokeStyle = C.evid; ctx.lineWidth = Math.max(1.5, w / 380);
    ctx.beginPath(); let pen = false;
    for (let x = 0; x < GW; x++) {
      const f = f0s[x];
      if (!f) { pen = false; continue; }
      const X = (x / GW) * w, Y = h * 0.96 - ((f - 80) / 220) * h * 0.4;
      pen ? ctx.lineTo(X, Y) : ctx.moveTo(X, Y); pen = true;
    }
    ctx.stroke();
    ctx.font = `${Math.round(Math.max(10, w / 70))}px "IBM Plex Mono", monospace`;
    const lab = 'F0 CONTOUR · 80–300 Hz SCALE', fs = Math.round(Math.max(10, w / 70));
    ctx.fillStyle = 'rgba(4,6,10,0.75)'; ctx.fillRect(8, h - fs * 2.1, ctx.measureText(lab).width + 16, fs * 1.7);
    ctx.fillStyle = C.evid; ctx.fillText(lab, 16, h - fs * 0.85);
    // playhead
    const px = ((t % 5) / 5) * w;
    ctx.fillStyle = rgba(C.bone, 0.75); ctx.fillRect(px, 0, Math.max(1, w / 900), h);
  });
  onceVisible(frame, () => { if (!presenting()) setTimeout(() => !presenting() && setMode('fake'), 3200); }, 0.4);
  return (n) => setMode(n ? 'fake' : 'real');
}
