// VERITAS story — small shared helpers.
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
export const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

export const C = {
  ink: '#04060a', ink1: '#0a0e15', ink2: '#111722', ink3: '#1a2230',
  bone: '#e8e6df', boneDim: '#a9a79f', boneFaint: '#6b6a64',
  auth: '#3ef2c4', synth: '#ff3b5c', evid: '#ffb020', scan: '#6aa8ff',
  line: 'rgba(232,230,223,0.10)', lineStrong: 'rgba(232,230,223,0.22)',
};
export const rgba = (hex, a) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
};

// Deterministic PRNG (mulberry32) so illustrations look the same every run.
export function rng(seed = 1) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
export function gauss(r) { // Box–Muller
  let u = 0, v = 0;
  while (u === 0) u = r();
  while (v === 0) v = r();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

// Size a canvas to its CSS box × devicePixelRatio (capped). Returns {ctx, w, h, dpr}.
export function fitCanvas(cv, maxDpr = 2) {
  const dpr = Math.min(maxDpr, window.devicePixelRatio || 1);
  const r = cv.getBoundingClientRect();
  const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  const ctx = cv.getContext('2d');
  return { ctx, w, h, dpr };
}

// Run fn(t, dt) on rAF only while `el` is on screen (and the tab is visible).
export function visibleLoop(el, fn, { margin = '80px' } = {}) {
  let on = false, raf = 0, last = 0, t0 = performance.now();
  const tick = (now) => {
    raf = 0;
    if (!on || document.hidden) return;
    const dt = Math.min(0.1, (now - (last || now)) / 1000);
    last = now;
    fn((now - t0) / 1000, dt);
    raf = requestAnimationFrame(tick);
  };
  const start = () => { if (!raf) { last = 0; raf = requestAnimationFrame(tick); } };
  new IntersectionObserver((es) => {
    for (const e of es) { on = e.isIntersecting; if (on) start(); }
  }, { rootMargin: margin }).observe(el);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && on) start(); });
  return { get active() { return on; } };
}

// Run once when an element first comes into view.
export function onceVisible(el, fn, threshold = 0.25) {
  const io = new IntersectionObserver((es) => {
    for (const e of es) if (e.isIntersecting) { io.disconnect(); fn(); }
  }, { threshold });
  io.observe(el);
}

let facePromise = null;
export function loadFace() {
  if (!facePromise) facePromise = fetch('assets/story/face.json').then((r) => { if (!r.ok) throw new Error('face.json ' + r.status); return r.json(); });
  return facePromise;
}

let photoPromise = null;
// Grayscale Float32 copy of the sample photo, resized to `size` square crop (cached per size).
const grayCache = new Map();
export function loadPhoto() {
  if (!photoPromise) photoPromise = new Promise((res, rej) => {
    const im = new Image();
    im.decoding = 'async';
    im.onload = () => res(im); im.onerror = rej;
    im.src = 'assets/story/forensics/backwaters.webp';
  });
  return photoPromise;
}
export async function photoGray(size, crop = { x: 0.08, y: 0.18, w: 0.62 }) {
  const key = size + JSON.stringify(crop);
  if (grayCache.has(key)) return grayCache.get(key);
  const im = await loadPhoto();
  const cv = document.createElement('canvas'); cv.width = cv.height = size;
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  const sw = im.naturalWidth * crop.w;
  ctx.drawImage(im, im.naturalWidth * crop.x, im.naturalHeight * crop.y, sw, sw, 0, 0, size, size);
  const d = ctx.getImageData(0, 0, size, size).data;
  const g = new Float32Array(size * size);
  for (let i = 0; i < g.length; i++) g[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2];
  grayCache.set(key, g);
  return g;
}

export function setRangeFill(input) {
  const v = (input.value - input.min) / (input.max - input.min || 1);
  input.style.setProperty('--fill', `${v * 100}%`);
}

// Simple segmented toggle wiring: returns setter.
export function segmented(root, onChange) {
  const btns = [...root.querySelectorAll('button[data-mode]')];
  const set = (mode, silent) => {
    btns.forEach((b) => { const on = b.dataset.mode === mode; b.classList.toggle('is-on', on); b.setAttribute('aria-checked', on); });
    if (!silent) onChange(mode);
  };
  btns.forEach((b) => b.addEventListener('click', () => set(b.dataset.mode)));
  return set;
}

export const pad = (n, l = 2) => String(n).padStart(l, '0');
