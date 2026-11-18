// VERITAS lab — small shared helpers (no dependencies).

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export const params = new URLSearchParams(location.search);
export const MOCK = params.has('mock') && params.get('mock') !== '0';

export const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);

/** Parse an HTML string into a single element (or fragment if several roots). */
export function html(str) {
  const t = document.createElement('template');
  t.innerHTML = str.trim();
  return t.content.childElementCount === 1 ? t.content.firstElementChild : t.content;
}

export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const lerp = (a, b, t) => a + (b - a) * t;
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const pad = (n, w = 2) => String(n).padStart(w, '0');

export function fmtBytes(n) {
  if (n == null || isNaN(n)) return '—';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(2)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

/** 7.3 -> "00:07.3" */
export function fmtElapsed(sec) {
  const m = Math.floor(sec / 60);
  const s = sec - m * 60;
  return `${pad(m)}:${s.toFixed(1).padStart(4, '0')}`;
}

/** 83.2 -> "1:23" */
export function fmtClock(sec) {
  if (!isFinite(sec)) return '0:00';
  const m = Math.floor(sec / 60);
  return `${m}:${pad(Math.floor(sec % 60))}`;
}

/* ---------- Verdict language ---------- */
// score < 35 authentic, 35–65 suspicious, > 65 synthetic (docs/ARCHITECTURE.md)
export function band(score) {
  if (score == null || isNaN(score)) return 'none';
  if (score < 35) return 'authentic';
  if (score <= 65) return 'suspicious';
  return 'synthetic';
}
export const BAND_VAR = {
  authentic: 'var(--authentic)',
  suspicious: 'var(--evidence)',
  synthetic: 'var(--synthetic)',
  none: 'var(--bone-faint)',
};
export const VERDICT_WORD = { authentic: 'Authentic', suspicious: 'Suspicious', synthetic: 'Synthetic' };
export function normVerdict(v, score) {
  const s = String(v || '').toLowerCase();
  if (s === 'authentic' || s === 'suspicious' || s === 'synthetic') return s;
  const b = band(score);
  return b === 'none' ? 'suspicious' : b;
}

export const CATEGORY_LABEL = {
  compression: 'Compression',
  noise: 'Noise',
  frequency: 'Frequency',
  metadata: 'Metadata',
  ai_model: 'Neural net',
  biometric: 'Biometric',
  temporal: 'Temporal',
  acoustic: 'Acoustic',
};

/* ---------- Files ---------- */
const EXT_KIND = {
  jpg: 'image', jpeg: 'image', png: 'image', webp: 'image', gif: 'image', bmp: 'image', tif: 'image', tiff: 'image', heic: 'image', heif: 'image', avif: 'image',
  mp4: 'video', mov: 'video', m4v: 'video', webm: 'video', mkv: 'video', avi: 'video',
  wav: 'audio', mp3: 'audio', m4a: 'audio', ogg: 'audio', oga: 'audio', flac: 'audio', aac: 'audio', opus: 'audio',
};
export function fileKind(file) {
  const t = (file.type || '').split('/')[0];
  const ext = (file.name || '').split('.').pop().toLowerCase();
  // .webm can be audio-only; trust MIME first
  if (t === 'image' || t === 'video' || t === 'audio') return t;
  return EXT_KIND[ext] || null;
}

export async function sha256Hex(blob) {
  try {
    if (!crypto?.subtle) return null;
    const buf = await blob.arrayBuffer();
    const h = await crypto.subtle.digest('SHA-256', buf);
    return Array.from(new Uint8Array(h), (b) => b.toString(16).padStart(2, '0')).join('');
  } catch { return null; }
}

export const shortHash = (h, a = 10, b = 6) => (h ? `${h.slice(0, a)}…${h.slice(-b)}` : '—');

export function loadImage(src) {
  return new Promise((resolve, reject) => {
    const im = new Image();
    im.decoding = 'async';
    im.onload = () => resolve(im);
    im.onerror = () => reject(new Error('image failed to load'));
    im.src = src;
  });
}

/* ---------- Animation helpers ---------- */
export const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
export const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

/** rAF tween: calls fn(eased 0..1). Returns a cancel function. */
export function tween(dur, fn, ease = easeOutExpo) {
  if (reducedMotion()) { fn(1); return () => {}; }
  let raf = 0; const t0 = performance.now();
  const step = (now) => {
    const t = clamp((now - t0) / dur, 0, 1);
    fn(ease(t));
    if (t < 1) raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}

/* ---------- Toast ---------- */
let toastTimer = 0;
export function toast(msg, kind = 'info', ms = 3200) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.dataset.kind = kind;
  t.classList.add('is-on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('is-on'), ms);
}

/** True when focus is in a text field (so global hotkeys should stand down). */
export function isTyping(e) {
  const el = e?.target || document.activeElement;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' && !['range', 'checkbox', 'radio', 'button'].includes(el.type) || tag === 'TEXTAREA' || el.isContentEditable;
}

/** Simple event bus between lab modules. */
const bus = new EventTarget();
export const on = (type, fn) => bus.addEventListener(type, (e) => fn(e.detail));
export const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));

/** Deterministic PRNG for mock visuals. */
export function rng(seed = 1) {
  let s = seed >>> 0 || 1;
  return () => { s ^= s << 13; s ^= s >>> 17; s ^= s << 5; return ((s >>> 0) % 1e9) / 1e9; };
}
