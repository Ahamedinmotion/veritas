// Chapter 02 demos: GAN training (face from noise), autoencoder swap faces, diffusion forward process, voice-clone pipeline.
import { $, $$, C, rgba, rng, gauss, fitCanvas, visibleLoop, onceVisible, loadFace, loadPhoto, clamp, smooth, setRangeFill, reduceMotion } from '../util.js';
import { facePath, IDENT } from './facepaths.js';

const gsap = window.gsap;
const presenting = () => !!(window.VX && window.VX.presenting);

/* ─────────────── GAN ─────────────── */
export async function initGAN(frame) {
  const cv = $('#gan-canvas'), range = $('#gan-range');
  const stepEl = $('#gan-step'), dEl = $('#gan-d'), dBar = $('#gan-dbar');
  const data = await loadFace();
  $('#gan-real-path').setAttribute('d', facePath(data, { size: 100, cx: 50, cy: 52, scale: 0.42 }));
  const V = data.vertices, n = data.count;
  const r = rng(7);
  const start = new Float32Array(n * 2);
  for (let i = 0; i < n; i++) { start[i * 2] = (r() * 2 - 1) * 1.05; start[i * 2 + 1] = (r() * 2 - 1) * 1.05; }
  const S = { p: 0 };
  let tween = null;
  const set = (p) => {
    S.p = p;
    range.value = Math.round(p * 1000); setRangeFill(range);
    const steps = Math.round(p * 10000);
    stepEl.textContent = steps.toLocaleString('en-US');
    const d = 0.02 + 0.48 * smooth(0.08, 0.92, p);
    dEl.textContent = d.toFixed(2);
    dBar.style.width = `${d * 100}%`;
  };
  range.addEventListener('input', () => { tween && tween.kill(); set(range.value / 1000); });
  set(0);
  const play = () => { tween && tween.kill(); set(0); tween = gsap.to(S, { p: 1, duration: reduceMotion ? 0.01 : 6.5, ease: 'power1.inOut', onUpdate: () => set(S.p) }); };
  const r2 = rng(99);
  visibleLoop(cv, (t) => {
    const { ctx, w, h } = fitCanvas(cv);
    ctx.clearRect(0, 0, w, h);
    const q = smooth(0, 1, S.p), sig = (1 - q) * 0.22 + 0.012;
    const s = w * 0.42;
    ctx.fillStyle = C.synth;
    for (let i = 0; i < n; i++) {
      const tx = V[i * 3], ty = V[i * 3 + 1];
      const x = start[i * 2] + (tx - start[i * 2]) * q + gauss(r2) * sig * 0.4;
      const y = start[i * 2 + 1] + (ty - start[i * 2 + 1]) * q + gauss(r2) * sig * 0.4;
      ctx.globalAlpha = 0.55 + 0.45 * q;
      ctx.fillRect(w / 2 + x * s - 1, h / 2 - y * s * 0.98 - 1, 1.8 * (w / 100), 1.8 * (w / 100));
    }
    ctx.globalAlpha = 1;
  });
  onceVisible(frame, () => { if (!presenting()) setTimeout(play, 500); }, 0.4);
  return (step) => { if (step === 0) { tween && tween.kill(); set(0); } else play(); };
}

/* ─────────────── Autoencoder swap ─────────────── */
export async function initSwap(frame) {
  const data = await loadFace();
  const fig = $('.swap', frame);
  $$('.face-a', fig).forEach((p) => p.setAttribute('d', facePath(data, { size: 80, cx: 40, cy: 42, scale: 0.44, warp: p.classList.contains('face-a--smile') ? { ...IDENT.A, smile: 0.12 } : IDENT.A })));
  $$('.face-b', fig).forEach((p) => {
    const big = p.classList.contains('face-b--smile');
    p.setAttribute('d', facePath(data, big ? { size: 120, cx: 72, cy: 60, scale: 0.42, warp: { ...IDENT.B, smile: 0.12 } } : { size: 80, cx: 40, cy: 42, scale: 0.44, warp: IDENT.B }));
  });
  return (step) => { fig.classList.toggle('is-dim', step === 0); };
}

/* ─────────────── Diffusion (forward process on a real photo) ─────────────── */
export async function initDiffusion(frame) {
  const cv = $('#diff-canvas'), range = $('#diff-range'), playBtn = $('#diff-play');
  const tEl = $('#diff-t'), abEl = $('#diff-ab'), sigEl = $('#diff-sig'), noiEl = $('#diff-noi'), bar = $('#diff-sigbar');
  const W = 480, H = 320;
  cv.width = W; cv.height = H;
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  const im = await loadPhoto();
  const off = document.createElement('canvas'); off.width = W; off.height = H;
  const octx = off.getContext('2d', { willReadFrequently: true });
  octx.drawImage(im, 0, 0, W, H);
  const src = octx.getImageData(0, 0, W, H).data;
  const x0 = new Float32Array(W * H * 3), eps = new Float32Array(W * H * 3);
  const r = rng(2020);
  for (let i = 0, j = 0; i < W * H; i++) for (let c = 0; c < 3; c++, j++) { x0[j] = src[i * 4 + c] / 127.5 - 1; eps[j] = gauss(r); }
  // DDPM linear schedule
  const T = 1000, ab = new Float64Array(T + 1);
  ab[0] = 1;
  for (let t = 1; t <= T; t++) { const beta = 1e-4 + (0.02 - 1e-4) * ((t - 1) / (T - 1)); ab[t] = ab[t - 1] * (1 - beta); }
  const out = ctx.createImageData(W, H);
  const S = { t: 0 };
  let tween = null, lastT = -1;
  const render = (t) => {
    t = Math.round(clamp(t, 0, T));
    range.value = t; setRangeFill(range);
    if (t === lastT) return;
    lastT = t;
    const a = Math.sqrt(ab[t]), b = Math.sqrt(1 - ab[t]);
    const o = out.data;
    for (let i = 0, j = 0; i < W * H; i++) {
      o[i * 4] = (a * x0[j] + b * eps[j++] + 1) * 127.5;
      o[i * 4 + 1] = (a * x0[j] + b * eps[j++] + 1) * 127.5;
      o[i * 4 + 2] = (a * x0[j] + b * eps[j++] + 1) * 127.5;
      o[i * 4 + 3] = 255;
    }
    ctx.putImageData(out, 0, 0);
    tEl.textContent = t;
    abEl.textContent = ab[t].toFixed(3);
    sigEl.textContent = Math.round(ab[t] * 100);
    noiEl.textContent = Math.round((1 - ab[t]) * 100);
    bar.style.width = `${ab[t] * 100}%`;
  };
  render(0);
  range.addEventListener('input', () => { tween && tween.kill(); S.t = +range.value; render(S.t); });
  const to = (t, dur, ease = 'power2.inOut') => { tween && tween.kill(); tween = gsap.to(S, { t, duration: reduceMotion ? 0.01 : dur, ease, onUpdate: () => render(S.t) }); return tween; };
  const generate = () => { S.t = 1000; render(1000); to(0, 4.6, 'power1.out'); };
  playBtn.addEventListener('click', generate);
  onceVisible(frame, () => { if (!presenting()) { to(1000, 3.2).then(() => setTimeout(() => !presenting() && generate(), 700)); } }, 0.45);
  return (step) => { if (step === 0) to(1000, 2.6); else generate(); };
}

/* ─────────────── Voice clone pipeline ─────────────── */
function speechEnv(x, seed) { // 0..1 time → syllabic envelope
  const syl = Math.sin(x * Math.PI * 2 * 4.2 + seed) * 0.5 + 0.5;
  const words = Math.sin(x * Math.PI * 2 * 1.1 + seed * 0.7) * 0.5 + 0.5;
  const gap = smooth(0.0, 0.06, x) * smooth(1, 0.94, x) * (Math.abs(x - 0.52) < 0.04 ? 0.15 : 1);
  return Math.pow(syl, 1.6) * (0.35 + 0.65 * words) * gap;
}
function drawWave(cv, color, progress = 1, seed = 1, mono = false) {
  const { ctx, w, h } = fitCanvas(cv);
  ctx.clearRect(0, 0, w, h);
  const r = rng(seed), bars = Math.floor(w / 5);
  const bw = Math.max(1.5, (w / bars) * 0.55);
  for (let i = 0; i < bars; i++) {
    const x = i / bars;
    const a = (0.08 + 0.92 * speechEnv(x, seed)) * (0.6 + 0.4 * r());
    const on = x <= progress;
    ctx.fillStyle = on ? color : rgba(C.bone, 0.12);
    const bh = Math.max(2, a * h * 0.9);
    ctx.fillRect(i * (w / bars), (h - bh) / 2, bw, bh);
  }
  if (!mono && progress < 1) { ctx.fillStyle = C.bone; ctx.fillRect(progress * w, 0, 1.5, h); }
}
function melCol(ctx, x, colW, h, tN, seed) {
  // procedural mel-spectrogram column: harmonic stack shaped by moving formants
  const env = speechEnv(tN, seed);
  const img = ctx.createImageData(1, h);
  const f1 = 0.1 + 0.05 * Math.sin(tN * 30 + seed), f2 = 0.3 + 0.12 * Math.sin(tN * 17 + seed * 2), f3 = 0.55 + 0.05 * Math.sin(tN * 9);
  for (let y = 0; y < h; y++) {
    const m = 1 - y / h; // mel position 0 (low) .. 1 (high)
    const harm = Math.pow(Math.abs(Math.cos(m * Math.PI * (18 + 6 * Math.sin(tN * 6)))), 6);
    const form = Math.exp(-((m - f1) ** 2) / 0.003) + 0.8 * Math.exp(-((m - f2) ** 2) / 0.006) + 0.5 * Math.exp(-((m - f3) ** 2) / 0.008);
    let v = env * (0.15 + 0.85 * harm) * (0.25 + form) * (1 - m * 0.6) + 0.02;
    v = clamp(v * 1.4);
    const [R, G, B] = heat(v);
    img.data[y * 4] = R; img.data[y * 4 + 1] = G; img.data[y * 4 + 2] = B; img.data[y * 4 + 3] = 255;
  }
  for (let k = 0; k < colW; k++) ctx.putImageData(img, x + k, 0);
}
export function heat(v) { // ink → scan blue → amber → bone
  const s = [[0, 4, 6, 10], [0.3, 22, 48, 96], [0.55, 106, 168, 255], [0.8, 255, 176, 32], [1, 255, 246, 220]];
  for (let i = 0; i < s.length - 1; i++) {
    if (v <= s[i + 1][0]) { const t = (v - s[i][0]) / (s[i + 1][0] - s[i][0]); return [s[i][1] + (s[i + 1][1] - s[i][1]) * t, s[i][2] + (s[i + 1][2] - s[i][2]) * t, s[i][3] + (s[i + 1][3] - s[i][3]) * t]; }
  }
  return [255, 246, 220];
}

export function initVoice(frame) {
  const sample = $('#vox-sample'), mel = $('#vox-mel'), outW = $('#vox-out'), emb = $('#vox-emb'), txt = $('#vox-text');
  const full = txt.textContent;
  const r = rng(11);
  emb.innerHTML = Array.from({ length: 16 }, () => `<i style="height:${(18 + r() * 82).toFixed(0)}%"></i>`).join('');
  const bars = $$('i', emb);
  let tl = null;
  const S = { sample: 0, emb: 0, text: 0, mel: 0, out: 0 };
  let melDrawn = 0;
  const draw = () => {
    drawWave(sample, C.auth, S.sample, 3);
    bars.forEach((b, i) => { b.style.transform = `scaleY(${clamp(S.emb * 16 - i * 0.6)})`; });
    const n = Math.round(full.length * S.text);
    txt.innerHTML = full.slice(0, n) + (S.text > 0 && S.text < 1 ? '<span class="caret"></span>' : '');
    const { ctx, w, h } = fitCanvas(mel);
    const target = Math.floor(S.mel * w);
    if (target < melDrawn) { ctx.fillStyle = C.ink; ctx.fillRect(0, 0, w, h); melDrawn = 0; }
    for (let x = melDrawn; x < target; x += 2) melCol(ctx, x, 2, h, x / w, 5);
    melDrawn = Math.max(melDrawn, target - (target % 2));
    drawWave(outW, C.synth, S.out, 5);
  };
  const run = () => {
    tl && tl.kill();
    Object.assign(S, { sample: 0, emb: 0, text: 0, mel: 0, out: 0 });
    const { ctx, w, h } = fitCanvas(mel); ctx.fillStyle = C.ink; ctx.fillRect(0, 0, w, h); melDrawn = 0;
    const d = reduceMotion ? 0.01 : 1;
    tl = gsap.timeline({ onUpdate: draw })
      .to(S, { sample: 1, duration: 1.6 * d, ease: 'none' })
      .to(S, { emb: 1, duration: 0.9 * d, ease: 'power2.out' })
      .to(S, { text: 1, duration: 1.6 * d, ease: 'none' }, '-=0.2')
      .to(S, { mel: 1, duration: 2.2 * d, ease: 'none' })
      .to(S, { out: 1, duration: 1.8 * d, ease: 'none' });
  };
  draw();
  addEventListener('resize', () => { melDrawn = 0; draw(); });
  onceVisible(frame, () => { if (!presenting()) run(); else { Object.assign(S, { sample: 1, emb: 1, text: 1, mel: 1, out: 1 }); draw(); } }, 0.4);
  return (step) => { if (step === 1) run(); };
}

/* ─────────────── Threat: 3-second sample ─────────────── */
export function initThreatWave() {
  const cv = $('#threat-wave');
  if (!cv) return;
  visibleLoop(cv, (t) => {
    const p = (t % 4.2) / 3.2;
    drawWave(cv, C.scan, Math.min(1, p), 8, p >= 1);
  });
}
