// VERITAS lab — MOCK ENGINE. Loaded only with ?mock=1.
// Produces reports in the exact /api/analyze/* contract shape, with canvas-generated placeholder visuals,
// so the UI can be built and demoed without the Python engine. Nothing here is a real forensic result.

import { sleep, rng, clamp, sha256Hex, loadImage } from './util.js';

/* ------------------------------------------------------------------ canvas helpers */
const cv = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
const INFERNO = [[0, 0, 4], [31, 12, 72], [85, 15, 109], [136, 34, 106], [186, 54, 85], [227, 89, 51], [249, 140, 10], [249, 201, 50], [252, 255, 164]];
const MAGMA = [[0, 0, 4], [28, 16, 68], [79, 18, 123], [129, 37, 129], [181, 54, 122], [229, 80, 100], [251, 135, 97], [254, 194, 135], [252, 253, 191]];
function cmap(stops, t) {
  t = clamp(t, 0, 1) * (stops.length - 1);
  const i = Math.min(Math.floor(t), stops.length - 2), f = t - i, a = stops[i], b = stops[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}
/** Draw a scalar field fn(x01,y01) -> 0..1 at low res, colour-map, upscale smoothly. */
function field(w, h, lw, fn, stops = INFERNO) {
  const lh = Math.round(lw * h / w);
  const small = cv(lw, lh), sg = small.getContext('2d');
  const img = sg.createImageData(lw, lh);
  for (let y = 0; y < lh; y++) for (let x = 0; x < lw; x++) {
    const [r, g, b] = cmap(stops, fn(x / (lw - 1), y / (lh - 1)));
    const i = (y * lw + x) * 4; img.data[i] = r; img.data[i + 1] = g; img.data[i + 2] = b; img.data[i + 3] = 255;
  }
  sg.putImageData(img, 0, 0);
  const c = cv(w, h), g = c.getContext('2d');
  g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'high';
  g.drawImage(small, 0, 0, w, h);
  return c;
}
const gauss = (x, y, cx, cy, r) => Math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2 * r * r));
function valueNoise(seed) {
  const R = rng(seed); const G = 16; const grid = Array.from({ length: (G + 1) * (G + 1) }, R);
  return (x, y) => {
    const gx = x * G, gy = y * G, ix = Math.min(G - 1, Math.floor(gx)), iy = Math.min(G - 1, Math.floor(gy));
    const fx = gx - ix, fy = gy - iy, s = (t) => t * t * (3 - 2 * t);
    const v = (i, j) => grid[j * (G + 1) + i];
    const a = v(ix, iy) + (v(ix + 1, iy) - v(ix, iy)) * s(fx);
    const b = v(ix, iy + 1) + (v(ix + 1, iy + 1) - v(ix, iy + 1)) * s(fx);
    return a + (b - a) * s(fy);
  };
}
function watermark(g, w, h, text = 'MOCK DATA') {
  g.save(); g.font = `500 ${Math.round(w / 34)}px "IBM Plex Mono", monospace`; g.fillStyle = 'rgba(232,230,223,.55)';
  g.textAlign = 'right'; g.fillText(text, w - w / 40, h - w / 40); g.restore();
}

/** Anonymous "subject" silhouette — a deliberate placeholder, clearly not a real person. */
function portrait(w, h, seed = 3, tint = 0) {
  const R = rng(seed); const c = cv(w, h), g = c.getContext('2d');
  const bg = g.createLinearGradient(0, 0, 0, h);
  bg.addColorStop(0, tint ? '#2c2a34' : '#1d2a3a'); bg.addColorStop(1, '#080b11');
  g.fillStyle = bg; g.fillRect(0, 0, w, h);
  const key = g.createRadialGradient(w * 0.28, h * 0.22, 0, w * 0.28, h * 0.22, Math.max(w, h) * 0.75);
  key.addColorStop(0, tint ? 'rgba(255,190,140,.22)' : 'rgba(150,200,255,.18)'); key.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = key; g.fillRect(0, 0, w, h);
  // backdrop measurement lines (police line-up feel)
  g.strokeStyle = 'rgba(232,230,223,.07)'; g.lineWidth = Math.max(1, h / 500);
  for (let i = 1; i < 10; i++) { const y = (h * i) / 10; g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
  const cx = w * (0.5 + (R() - 0.5) * 0.02), hy = h * 0.4, hr = Math.min(w * 0.17, h * 0.2);
  const shape = new Path2D();
  shape.ellipse(cx, hy, hr * 0.84, hr * 1.08, 0, 0, Math.PI * 2);
  const body = new Path2D();
  body.moveTo(cx - hr * 0.36, hy + hr * 0.8); body.lineTo(cx - hr * 0.4, hy + hr * 1.35);
  body.bezierCurveTo(cx - hr * 1.9, hy + hr * 1.55, cx - hr * 2.6, hy + hr * 2.1, cx - hr * 2.9, h + 2);
  body.lineTo(cx + hr * 2.9, h + 2);
  body.bezierCurveTo(cx + hr * 2.6, hy + hr * 2.1, cx + hr * 1.9, hy + hr * 1.55, cx + hr * 0.4, hy + hr * 1.35);
  body.lineTo(cx + hr * 0.36, hy + hr * 0.8); body.closePath();
  const fill = g.createLinearGradient(cx - hr * 2, 0, cx + hr * 2, 0);
  fill.addColorStop(0, tint ? '#4a4048' : '#3b4a5c'); fill.addColorStop(0.55, '#1a222d'); fill.addColorStop(1, '#0d1118');
  g.fillStyle = fill; g.fill(body); g.fill(shape);
  // rim light on the lit side
  g.save(); g.beginPath(); g.rect(0, 0, cx - hr * 0.1, h); g.clip();
  g.strokeStyle = tint ? 'rgba(255,205,160,.55)' : 'rgba(190,225,255,.5)'; g.lineWidth = Math.max(1.5, w / 360);
  g.stroke(shape); g.stroke(body); g.restore();
  // subtle face-plane highlight
  const fh = g.createRadialGradient(cx - hr * 0.3, hy - hr * 0.2, 0, cx - hr * 0.3, hy - hr * 0.2, hr * 1.1);
  fh.addColorStop(0, 'rgba(255,255,255,.08)'); fh.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = fh; g.fill(shape);
  // film grain
  const id = g.getImageData(0, 0, w, h);
  for (let i = 0; i < id.data.length; i += 4) { const n = (R() - 0.5) * 12; id.data[i] += n; id.data[i + 1] += n; id.data[i + 2] += n; }
  g.putImageData(id, 0, 0);
  g.save(); g.font = `500 ${Math.round(Math.min(w, h) / 30)}px "IBM Plex Mono", monospace`; g.fillStyle = 'rgba(232,230,223,.45)';
  g.fillText(`SUBJECT ${String.fromCharCode(65 + (seed % 26))}`, Math.min(w, h) / 30, Math.min(w, h) / 30 * 2); g.restore();
  watermark(g, w, h, 'MOCK EXHIBIT');
  return c;
}

/** ELA-style residual from a source canvas: |p − blur(p)| amplified, hotter inside hot box. */
function elaFrom(src, hot = null, gain = 9) {
  const w = src.width, h = src.height, g0 = src.getContext('2d');
  const a = g0.getImageData(0, 0, w, h).data;
  const blur = cv(w, h), bg = blur.getContext('2d'); bg.filter = 'blur(1.4px)'; bg.drawImage(src, 0, 0);
  const b = bg.getImageData(0, 0, w, h).data;
  const out = cv(w, h), og = out.getContext('2d'); const id = og.createImageData(w, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4;
    let k = gain;
    if (hot) { const inside = x / w > hot[0] && x / w < hot[0] + hot[2] && y / h > hot[1] && y / h < hot[1] + hot[3]; k = inside ? gain * 2.6 : gain * 0.8; }
    id.data[i] = Math.min(255, Math.abs(a[i] - b[i]) * k);
    id.data[i + 1] = Math.min(255, Math.abs(a[i + 1] - b[i + 1]) * k);
    id.data[i + 2] = Math.min(255, Math.abs(a[i + 2] - b[i + 2]) * k);
    id.data[i + 3] = 255;
  }
  og.putImageData(id, 0, 0);
  return out;
}

function noiseResidual(w, h, seed, hot) {
  const R = rng(seed); const c = cv(w, h), g = c.getContext('2d'); const id = g.createImageData(w, h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const inside = hot && x / w > hot[0] && x / w < hot[0] + hot[2] && y / h > hot[1] && y / h < hot[1] + hot[3];
    const amp = inside ? 22 : 70;
    const v = 128 + (R() - 0.5) * amp + (R() - 0.5) * amp;
    const i = (y * w + x) * 4; id.data[i] = id.data[i + 1] = id.data[i + 2] = v; id.data[i + 3] = 255;
  }
  g.putImageData(id, 0, 0);
  return c;
}

function spectrum(n, seed, grid = true) {
  const N = valueNoise(seed);
  return field(n, n, 256, (x, y) => {
    const dx = x - 0.5, dy = y - 0.5, d = Math.hypot(dx, dy);
    let v = 0.95 / (1 + d * 18) + N(x, y) * 0.12;
    v += Math.exp(-Math.abs(dx) * 260) * 0.25 + Math.exp(-Math.abs(dy) * 260) * 0.25; // axis cross
    if (grid) for (let i = 1; i < 4; i++) for (let j = 0; j < 4; j++) {
      const px = 0.5 + Math.cos(j * Math.PI / 2) * i * 0.125, py = 0.5 + Math.sin(j * Math.PI / 2) * i * 0.125;
      v += gauss(x, y, px, py, 0.008) * 0.9;
      v += gauss(x, y, 0.5 + (i * 0.125) * (j % 2 ? 1 : -1), 0.5 + (i * 0.125) * (j > 1 ? 1 : -1), 0.007) * 0.7;
    }
    return clamp(Math.pow(v, 0.8), 0, 1);
  });
}

function heat(w, h, seed, spots) {
  const N = valueNoise(seed);
  return field(w, h, 96, (x, y) => {
    let v = N(x, y) * 0.22;
    for (const [cx, cy, r, a] of spots) v += gauss(x, y, cx, cy, r) * a;
    return v;
  });
}

function spectrogram(w, h, seed, cutoff = 1) {
  const R = rng(seed); const N = valueNoise(seed + 7);
  const syll = Array.from({ length: 14 }, (_, i) => [0.04 + i * 0.068 + R() * 0.02, 0.025 + R() * 0.02]);
  return field(w, h, 360, (x, y) => {
    const f = 1 - y; // 0 low .. 1 high
    if (f > cutoff) return 0.03 + N(x, y) * 0.03;
    let env = 0; for (const [c, r] of syll) env += Math.exp(-((x - c) ** 2) / (2 * r * r));
    env = Math.min(1, env);
    const f0 = 0.035 + 0.012 * Math.sin(x * 9) + 0.006 * Math.sin(x * 23);
    let harm = 0; for (let k = 1; k < 18; k++) harm += Math.exp(-((f - f0 * k) ** 2) / 0.00002) / (1 + k * 0.35);
    const formant = gauss(f, 0, 0.12, 0, 0.06) + gauss(f, 0, 0.3, 0, 0.08) * 0.6 + 0.15;
    const hiss = (f > 0.4 ? 0.12 : 0.05) * N((x * 3) % 1, (y * 3) % 1);
    return clamp(0.06 + env * (harm * formant * 1.3 + 0.1) + hiss, 0, 1);
  }, MAGMA);
}

function lineChart(w, h, values, { ymax = 1, thresh = null, color = '#3ef2c4', label = '', events = [] } = {}) {
  const c = cv(w, h), g = c.getContext('2d');
  g.fillStyle = '#0a0e15'; g.fillRect(0, 0, w, h);
  g.strokeStyle = 'rgba(232,230,223,.08)'; g.lineWidth = 1;
  for (let i = 1; i < 5; i++) { g.beginPath(); g.moveTo(0, (h * i) / 5); g.lineTo(w, (h * i) / 5); g.stroke(); }
  if (thresh != null) {
    g.strokeStyle = 'rgba(255,176,32,.8)'; g.setLineDash([6, 6]);
    const ty = h - (thresh / ymax) * h * 0.85 - h * 0.05; g.beginPath(); g.moveTo(0, ty); g.lineTo(w, ty); g.stroke(); g.setLineDash([]);
  }
  for (const e of events) { g.fillStyle = 'rgba(255,176,32,.18)'; g.fillRect(e * w - 6, 0, 12, h); }
  g.strokeStyle = color; g.lineWidth = 2.5; g.beginPath();
  values.forEach((v, i) => { const x = (i / (values.length - 1)) * w, y = h - (v / ymax) * h * 0.85 - h * 0.05; i ? g.lineTo(x, y) : g.moveTo(x, y); });
  g.stroke();
  g.font = '500 18px "IBM Plex Mono", monospace'; g.fillStyle = 'rgba(232,230,223,.7)'; g.fillText(label, 14, 28);
  watermark(g, w, h);
  return c;
}

const png = (c) => c.toDataURL('image/png');
const jpg = (c, q = 0.86) => c.toDataURL('image/jpeg', q);

/* ------------------------------------------------------------------ text */
const EXPLAIN = {
  face_swap: 'Two pretrained deepfake detectors (GenD and the DFDC challenge winner) each find the face in 8 frames and give the probability that it was swapped or re-animated; such detectors are trained to pick up blending seams and texture mismatches. One-sided: it can only raise an alarm.',
  ai_face: 'A vision network trained on thousands of real and face-swapped videos looks only at the cropped face. It learns blending seams, over-smoothed skin and lighting mismatches that people miss, and outputs the probability that the face is synthetic.',
  ai_generated: 'A classifier trained on photographs and on images from diffusion models and GANs. Generators leave statistical fingerprints across the whole picture — texture regularity, colour distribution — even when nothing looks wrong to the eye.',
  ela: 'Every JPEG save throws away a little detail. ELA re-saves the image at a known quality and maps the difference: regions with a different compression history, such as pasted or generated areas, glow brighter or darker than the rest.',
  noise: 'A camera sensor stamps every photo with a faint, uniform noise pattern. Subtracting a denoised copy isolates that residual. Generated or pasted regions often carry noise that is too smooth or statistically different from the rest of the frame.',
  fft: 'The 2-D Fourier transform turns an image into its spatial frequencies. Up-sampling layers in GANs and diffusion decoders leave a periodic grid that appears as bright, evenly spaced peaks; natural photos fall off smoothly from the centre.',
  jpeg_quant: 'JPEG stores an 8×8 quantisation table chosen by the software that saved it. Cameras and phones use characteristic tables; files from editors or generators often carry tables that match no camera, or show traces of double compression.',
  metadata: 'Photos from real cameras carry EXIF data: make, model, exposure, lens and time. Missing camera fields, editing-software tags or impossible values are not proof on their own, but they are evidence.',
  blink: 'People blink 15–20 times a minute, each blink lasting 100–400 ms. We track the eye aspect ratio on every sampled frame; early face swaps blinked far too rarely because their training photos mostly showed open eyes.',
  landmark_jitter: 'Facial landmarks are tracked from frame to frame. Real faces move smoothly; swaps that regenerate the face every frame make the landmarks jitter by a few pixels in ways skin and bone cannot.',
  temporal_flicker: 'We compare brightness and colour changes inside the face with those of the background between consecutive frames. Synthetic faces often shimmer independently of the scene lighting.',
  ai_voice: 'A neural network trained on genuine speech and on text-to-speech and voice-cloning output examines learned features of the waveform and returns the probability that the voice is synthetic.',
  spectral_cutoff: 'Many voice generators work at 16 or 22 kHz sample rates, which leaves a hard ceiling of energy at 8 or 11 kHz. A real microphone recording usually fades smoothly up to much higher frequencies.',
  prosody: 'Prosody is the music of speech: pitch contour, rhythm and stress. We track the fundamental frequency (F0) over time; cloned voices are often too even or change pitch in unnaturally regular steps.',
  breath_silence: 'Real speakers breathe, and pauses between phrases contain room noise. Synthetic speech often has digitally perfect silence and no breaths at all.',
  spectrogram: 'A spectrogram plots frequency (up) against time (across), with brightness for loudness. Horizontal bands are the harmonics of the voice; vertical striations are syllables. Analysts read it like a fingerprint.',
};

/* ------------------------------------------------------------------ public API */
export function health() {
  return Promise.resolve({ ok: true, version: '1.0.0-mock', models: { face_deepfake: true, ai_generated: true, audio_deepfake: true, face_swap: true }, device: 'mock' });
}

let caseNo = 41;
const caseId = () => `VX-20261121-${String(++caseNo).padStart(4, '0')}`;

function variantFor(name = '') {
  const n = name.toLowerCase();
  if (/real|street|voice-?note|capture|authentic|holiday/.test(n)) return 'authentic';
  if (/edit|susp|cropped/.test(n)) return 'suspicious';
  return 'synthetic';
}
const scale = (v, variant) => variant === 'authentic' ? Math.round(v * 0.24 + 4) : variant === 'suspicious' ? Math.round(v * 0.62 + 6) : v;

async function previewFromFile(file) {
  try {
    const url = URL.createObjectURL(file);
    const im = await loadImage(url);
    const s = Math.min(1, 960 / Math.max(im.naturalWidth, im.naturalHeight));
    const c = cv(Math.round(im.naturalWidth * s), Math.round(im.naturalHeight * s));
    c.getContext('2d').drawImage(im, 0, 0, c.width, c.height);
    URL.revokeObjectURL(url);
    return { canvas: c, w: im.naturalWidth, h: im.naturalHeight };
  } catch { return null; }
}

function verdictOf(score) { return score < 35 ? 'authentic' : score <= 65 ? 'suspicious' : 'synthetic'; }

async function buildImage(file, variant) {
  const fromFile = file.type?.startsWith('image/') ? await previewFromFile(file) : null;
  const base = fromFile?.canvas || portrait(720, 900, 3);
  const W = base.width, H = base.height;
  const faceBox = [0.34, 0.24, 0.32, 0.34];
  const sc = (v) => scale(v, variant);
  const tests = [
    { id: 'ai_face', name: 'AI Face Analysis', category: 'ai_model', score: sc(91), weight: 0.24, status: 'ok',
      finding: variant === 'authentic' ? 'Face texture and blending consistent with a real camera.' : 'Face region matches patterns of GAN-synthesised faces.',
      explain: EXPLAIN.ai_face, visual: png(heat(W, H, 11, [[0.5, 0.42, 0.1, variant === 'authentic' ? 0.25 : 0.95], [0.43, 0.4, 0.04, 0.4]])),
      metrics: { p_fake: +(sc(91) / 100).toFixed(2), faces: 1, input_px: '224×224', model: 'face-deepfake (mock)' } },
    { id: 'ai_generated', name: 'AI-Generated Image Detector', category: 'ai_model', score: sc(88), weight: 0.22, status: 'ok',
      finding: variant === 'authentic' ? 'Whole-image statistics look photographic.' : 'Whole-image statistics resemble diffusion-model output.',
      explain: EXPLAIN.ai_generated, visual: null, metrics: { p_ai: +(sc(88) / 100).toFixed(2), model: 'ai-image (mock)' } },
    { id: 'ela', name: 'Error Level Analysis', category: 'compression', score: sc(62), weight: 0.12, status: 'ok',
      finding: variant === 'authentic' ? 'Even error levels across the frame.' : 'Face recompresses differently from the background.',
      explain: EXPLAIN.ela, visual: png(elaFrom(base, variant === 'authentic' ? null : faceBox)), metrics: { mean_error: 6.2, max_error: 48, resave_quality: 90 } },
    { id: 'noise', name: 'Noise Residual Consistency', category: 'noise', score: sc(71), weight: 0.12, status: 'ok',
      finding: variant === 'authentic' ? 'Uniform sensor noise everywhere.' : 'Face is far smoother than the camera noise around it.',
      explain: EXPLAIN.noise, visual: png(noiseResidual(W, H, 5, variant === 'authentic' ? null : faceBox)), metrics: { residual_std_face: 1.8, residual_std_bg: 3.9, ratio: 0.46 } },
    { id: 'fft', name: 'Frequency Spectrum (FFT)', category: 'frequency', score: sc(79), weight: 0.12, status: 'ok',
      finding: variant === 'authentic' ? 'Spectrum falls off smoothly — no grid peaks.' : 'Periodic grid peaks typical of AI up-sampling.',
      explain: EXPLAIN.fft, visual: png(spectrum(512, 9, variant !== 'authentic')), metrics: { peak_ratio: variant === 'authentic' ? 1.1 : 3.4, grid_period_px: 8 } },
    { id: 'jpeg_quant', name: 'JPEG Quantisation Tables', category: 'compression', score: sc(44), weight: 0.08, status: 'ok',
      finding: 'Quantisation table matches generic library, not a camera.',
      explain: EXPLAIN.jpeg_quant, visual: null, metrics: { q_estimate: 92, double_compressed: 'no' } },
    { id: 'metadata', name: 'Metadata & provenance', category: 'metadata', score: sc(70), weight: 0.10, status: 'ok',
      finding: variant === 'authentic' ? 'Camera make, model and exposure present.' : 'No camera EXIF; file written by software.',
      explain: EXPLAIN.metadata, visual: null, metrics: { exif_fields: variant === 'authentic' ? 23 : 0 } },
  ];
  const score = fuse(tests);
  return {
    kind: 'image',
    file: { format: file.type?.includes('png') ? 'PNG' : 'JPEG', width: fromFile?.w || 1024, height: fromFile?.h || 1280, duration: null },
    verdict: verdictOf(score), score, confidence: variant === 'suspicious' ? 0.41 : 0.78,
    summary: variant === 'authentic'
      ? 'No test found meaningful signs of manipulation; camera metadata and sensor noise look genuine.'
      : variant === 'suspicious'
        ? 'Some tests flag the face region, but the evidence is mixed — treat this image with caution.'
        : 'Two neural detectors and the frequency spectrum agree: this face was most likely generated by AI.',
    preview: jpg(base), faces: [{ box: faceBox, score: tests[0].score }], tests,
    timeline: [], keyframes: [], waveform: [],
    metadata: variant === 'authentic'
      ? { exif: { Make: 'Mock Camera Co.', Model: 'MC-12', DateTimeOriginal: '2026:11:02 16:41:09', ExposureTime: '1/120', FNumber: 'f/1.8', ISOSpeedRatings: 160, FocalLength: '4.2 mm', Software: 'MC-12 firmware 3.1' }, flags: ['Camera: Mock Camera Co. MC-12', 'Captured 2026:11:02 16:41:09', 'Software: MC-12 firmware 3.1'] }
      : { exif: { Software: 'unknown', ColorSpace: 'sRGB' }, flags: ['No camera EXIF', 'Software: Adobe Photoshop 25.1', 'AI marker: Adobe Firefly (XMP)'] },
  };
}

function fuse(tests) {
  let s = 0, w = 0;
  for (const t of tests) if (t.status === 'ok' && t.score != null) { s += t.score * t.weight; w += t.weight; }
  return Math.round(w ? s / w : 50);
}

async function buildVideo(file, variant) {
  const R = rng(17); const dur = 18.4;
  const sc = (v) => scale(v, variant);
  // the face-swap detector only fires on swap-like clips; on the AI "talking photo" (a GAN face, no swap) and on real
  // video it stays silent, as the real engine does (it scores the locker's talking photo 0)
  const swapFires = variant !== 'authentic' && /swap|deepfake|reenact|lip/i.test(file.name || '');
  const timeline = Array.from({ length: 48 }, (_, i) => {
    const t = +(0.2 + (i * (dur - 0.4)) / 47).toFixed(2);
    let v = 46 + (R() - 0.5) * 18 + 10 * Math.sin(i / 5);
    if (i > 14 && i < 21) v += 34; if (i > 33 && i < 37) v += 40;
    const swap = swapFires ? clamp(Math.round(scale(v + 18, variant)), 0, 100) : 2 + ((i * 37) % 7);   // no R() here: keeps the AI-face trace identical
    return { t, score: clamp(Math.round(scale(v, variant)), 0, 100), ...(i % 6 === 3 ? { swap } : {}) };
  });
  const keyIdx = [17, 19, 35, 8];
  const keyframes = keyIdx.map((i, k) => {
    const c = portrait(480, 300, 21 + k, k % 2);
    return { t: timeline[i].t, score: timeline[i].score, thumb: jpg(c, 0.8) };
  });
  const poster = portrait(1280, 720, 21);
  const ear = Array.from({ length: 160 }, (_, i) => 0.3 + (R() - 0.5) * 0.02 - (Math.abs(i - 42) < 3 ? 0.17 : 0) - (Math.abs(i - 121) < 3 ? 0.16 : 0));
  const tests = [
    { id: 'ai_face', name: 'AI Face Analysis', category: 'ai_model', score: sc(74), weight: 0.3, status: 'ok',
      finding: 'Average over 48 frames; spikes at 5.9 s and 13.6 s.', explain: EXPLAIN.ai_face + ' For video, it runs on every sampled frame and we average.',
      visual: null, metrics: { frames: 48, mean_p_fake: +(sc(74) / 100).toFixed(2), max_p_fake: +(sc(93) / 100).toFixed(2) } },
    swapFires
      ? { id: 'face_swap', name: 'Face-Swap Detector', category: 'ai_model', score: sc(82), weight: 0.3, status: 'ok',
        finding: 'Face-swap traces: 6 of 8 face frames above threshold.', explain: EXPLAIN.face_swap, visual: null,
        metrics: { frames_scored: 8, networks_voting: 2, one_sided: true } }
      : { id: 'face_swap', name: 'Face-Swap Detector', category: 'ai_model', score: variant === 'authentic' ? 15 : 0, weight: 0, status: 'ok',
        finding: 'No face-swap traces found (this test only raises alarms).', explain: EXPLAIN.face_swap, visual: null,
        metrics: { frames_scored: 8, networks_voting: 2, one_sided: true } },
    { id: 'blink', name: 'Blink Rate (Eye Aspect Ratio)', category: 'biometric', score: sc(68), weight: 0.2, status: 'ok',
      finding: variant === 'authentic' ? '6 blinks in 18 s — a normal rate.' : 'Only 2 blinks in 18 s (expected 5–6).', explain: EXPLAIN.blink,
      visual: png(lineChart(900, 320, ear, { ymax: 0.4, thresh: 0.21, label: 'EAR · 18.4 s', events: [42 / 159, 121 / 159] })),
      metrics: { blinks: variant === 'authentic' ? 6 : 2, per_minute: variant === 'authentic' ? 19.6 : 6.5, ear_mean: 0.29 } },
    { id: 'landmark_jitter', name: 'Landmark Jitter', category: 'temporal', score: sc(61), weight: 0.2, status: 'ok',
      finding: 'Mouth and jaw landmarks jump between frames.', explain: EXPLAIN.landmark_jitter, visual: null,
      metrics: { jitter_px: 2.7, baseline_px: 1.1 } },
    { id: 'temporal_flicker', name: 'Temporal Flicker', category: 'temporal', score: sc(55), weight: 0.15, status: 'ok',
      finding: 'Face brightness flickers independently of scene.', explain: EXPLAIN.temporal_flicker, visual: null,
      metrics: { face_flicker: 0.034, bg_flicker: 0.011 } },
    { id: 'ai_generated', name: 'AI-Generated Image Detector', category: 'ai_model', score: sc(40), weight: 0.15, status: 'ok',
      finding: 'Background frames look photographic.', explain: EXPLAIN.ai_generated, visual: null, metrics: { p_ai: +(sc(40) / 100).toFixed(2) } },
    { id: 'jpeg_quant', name: 'JPEG Quantisation Tables', category: 'compression', score: null, weight: 0, status: 'skipped',
      finding: 'Not applicable to video streams.', explain: EXPLAIN.jpeg_quant, visual: null, metrics: {} },
  ];
  const score = fuse(tests);
  return {
    kind: 'video',
    file: { format: 'MP4 · H.264', width: 1280, height: 720, duration: dur },
    verdict: verdictOf(score), score, confidence: 0.66,
    summary: variant === 'authentic'
      ? 'Blinking, motion and texture are consistent across all 48 sampled frames.'
      : 'The face detector spikes in two segments and the speaker blinks far too rarely — consistent with a face swap.',
    preview: jpg(poster), faces: [{ box: [0.4, 0.16, 0.2, 0.5], score: sc(78) }], tests, timeline, keyframes, waveform: [],
    metadata: { exif: { Container: 'MP4', Codec: 'H.264 High', 'Frame rate': '30 fps', Encoder: 'Lavf60.3.100' }, flags: variant === 'authentic' ? ['Device tags: Mock Phone 12', 'Created 2026-11-02T16:41:09'] : ['Encoder: Lavf60.3.100', 'No container metadata'] },
  };
}

async function buildAudio(file, variant) {
  const R = rng(29); const N = 600;
  const waveform = Array.from({ length: N }, (_, i) => {
    const x = i / N; let env = 0;
    for (let k = 0; k < 11; k++) env += Math.exp(-((x - (0.05 + k * 0.085)) ** 2) / 0.0006);
    return clamp(0.02 + Math.min(1, env) * (0.5 + R() * 0.5), 0, 1);
  });
  const fake = variant !== 'authentic';
  const sc = (v) => scale(v, variant);
  const tests = [
    { id: 'ai_voice', name: 'AI Voice Detector', category: 'ai_model', score: sc(86), weight: 0.4, status: 'ok',
      finding: fake ? 'Voice embedding matches cloned-speech patterns.' : 'Voice features consistent with a live speaker.', explain: EXPLAIN.ai_voice, visual: null,
      metrics: { p_fake: +(sc(86) / 100).toFixed(2), window_s: 4, windows: 3 } },
    { id: 'spectral_cutoff', name: 'Spectral Cut-off', category: 'acoustic', score: sc(81), weight: 0.2, status: 'ok',
      finding: fake ? 'Hard energy ceiling at 8.0 kHz.' : 'Energy present up to 15.8 kHz — like a real mic.', explain: EXPLAIN.spectral_cutoff, visual: null,
      metrics: { cutoff_hz: fake ? 8000 : 15800, sample_rate: 44100 } },
    { id: 'prosody', name: 'Prosody & pitch', category: 'acoustic', score: sc(58), weight: 0.2, status: 'ok',
      finding: fake ? 'Pitch contour unusually flat (σ 11 Hz).' : 'Natural pitch variation (σ 34 Hz).', explain: EXPLAIN.prosody, visual: null,
      metrics: { f0_mean_hz: 168, f0_std_hz: fake ? 11 : 34 } },
    { id: 'breath_silence', name: 'Breaths & Silence', category: 'acoustic', score: sc(64), weight: 0.2, status: 'ok',
      finding: fake ? 'Pauses are digitally silent; no breaths.' : '3 breaths; pauses carry room noise.', explain: EXPLAIN.breath_silence, visual: null,
      metrics: { breaths: fake ? 0 : 3, silence_floor_db: fake ? -96 : -58 } },
    { id: 'spectrogram', name: 'Spectrogram', category: 'acoustic', score: null, weight: 0, status: 'ok',
      finding: 'Time–frequency picture of the clip.', explain: EXPLAIN.spectrogram, visual: png(spectrogram(1200, 360, 31, fake ? 0.36 : 0.93)), metrics: { fft: 1024, hop: 256 } },
  ];
  const score = fuse(tests);
  return {
    kind: 'audio',
    file: { format: 'WAV · PCM 16-bit', width: null, height: null, duration: 6.0 },
    verdict: verdictOf(score), score, confidence: 0.71,
    summary: fake
      ? 'The voice model and a hard 8 kHz spectral ceiling both point to a cloned or text-to-speech voice.'
      : 'Natural breathing, pitch variation and full-bandwidth audio are consistent with a real recording.',
    preview: null, faces: [], tests, timeline: [], keyframes: [], waveform,
    metadata: { exif: { Codec: 'PCM 16-bit', 'Sample rate': '44100 Hz', Channels: 1 }, flags: ['Sample rate 44.1 kHz'] },
  };
}

export async function analyze(kind, file, { onUpload, isAborted = () => false } = {}) {
  await document.fonts?.ready;
  const cancelled = () => { const e = new Error('cancelled'); e.cancelled = true; return e; };
  for (let i = 1; i <= 12; i++) { await sleep(45); if (isAborted()) throw cancelled(); onUpload?.(i / 12); }
  const t0 = performance.now();
  if (/error/i.test(file.name || '')) { await sleep(900); const e = new Error('Mock engine error: could not decode this file.'); e.status = 422; throw e; }
  const variant = variantFor(file.name);
  const rep = kind === 'video' ? await buildVideo(file, variant) : kind === 'audio' ? await buildAudio(file, variant) : await buildImage(file, variant);
  const target = { image: 2600, video: 6800, audio: 3600 }[kind] || 2500;
  const left = target - (performance.now() - t0);
  for (let waited = 0; waited < left; waited += 100) { await sleep(100); if (isAborted()) throw cancelled(); }
  const sha = await sha256Hex(file);
  return {
    kind: rep.kind,
    case_id: caseId(),
    elapsed_ms: Math.round(performance.now() - t0),
    file: { name: file.name || 'evidence', size: file.size || 0, sha256: sha || '0'.repeat(64), ...rep.file },
    verdict: rep.verdict, score: rep.score, confidence: rep.confidence, summary: rep.summary,
    preview: rep.preview, faces: rep.faces, tests: rep.tests,
    timeline: rep.timeline, keyframes: rep.keyframes, waveform: rep.waveform, metadata: rep.metadata,
  };
}

/* ------------------------------------------------------------------ mock locker */
function wavBlob(seconds = 6, sr = 16000, fake = true) {
  const n = seconds * sr; const buf = new ArrayBuffer(44 + n * 2); const v = new DataView(buf);
  const w = (o, s) => [...s].forEach((ch, i) => v.setUint8(o + i, ch.charCodeAt(0)));
  w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVE'); w(12, 'fmt '); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true);
  const R = rng(fake ? 3 : 4); let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / sr; const x = t / seconds;
    let env = 0; for (let k = 0; k < 11; k++) env += Math.exp(-((x - (0.05 + k * 0.085)) ** 2) / 0.0006);
    env = Math.min(1, env);
    const f0 = 150 + 25 * Math.sin(t * 2.1) + (fake ? 0 : 12 * Math.sin(t * 7.3));
    ph += (2 * Math.PI * f0) / sr;
    let s = 0; for (let h = 1; h < 9; h++) s += Math.sin(ph * h) / (h * 1.4);
    s = s * env * 0.32 + (fake ? 0 : (R() - 0.5) * 0.01);
    v.setInt16(44 + i * 2, clamp(s, -1, 1) * 32767, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

async function canvasFile(c, name) {
  const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.9));
  return new File([blob], name, { type: 'image/jpeg' });
}

function streetScene(w, h) {
  const c = cv(w, h), g = c.getContext('2d'); const R = rng(77);
  const sky = g.createLinearGradient(0, 0, 0, h); sky.addColorStop(0, '#5f7fa6'); sky.addColorStop(0.6, '#d9b38c'); sky.addColorStop(1, '#3a3530');
  g.fillStyle = sky; g.fillRect(0, 0, w, h);
  for (let i = 0; i < 14; i++) { const bw = w * (0.05 + R() * 0.08), bh = h * (0.2 + R() * 0.45), x = (i / 14) * w; g.fillStyle = `hsl(${210 + R() * 20},12%,${14 + R() * 12}%)`; g.fillRect(x, h * 0.75 - bh, bw, bh + h * 0.25); for (let k = 0; k < 18; k++) { g.fillStyle = R() > 0.6 ? 'rgba(255,214,140,.8)' : 'rgba(40,50,60,.6)'; g.fillRect(x + 4 + (k % 3) * bw / 3.2, h * 0.75 - bh + 8 + Math.floor(k / 3) * 18, bw / 5, 8); } }
  g.fillStyle = '#26221e'; g.fillRect(0, h * 0.8, w, h * 0.2);
  watermark(g, w, h, 'MOCK EXHIBIT');
  return c;
}

export async function lockerItems() {
  await document.fonts?.ready;
  const p1 = portrait(720, 900, 3), p2 = portrait(720, 900, 8, 1), st = streetScene(960, 640), vid = portrait(640, 360, 21);
  const thumb = (c) => jpg(c, 0.8);
  return [
    { file: 'mock-portrait.jpg', kind: 'image', label: 'fake', title: 'Studio portrait', note: 'Profile photo of a brand-new social account.', thumb: thumb(p1),
      mockFile: () => canvasFile(p1, 'mock-portrait.jpg') },
    { file: 'mock-street-real.jpg', kind: 'image', label: 'real', title: 'Street at dusk', note: 'Phone photo sent on a family chat.', thumb: thumb(st),
      mockFile: () => canvasFile(st, 'mock-street-real.jpg') },
    { file: 'mock-interview.mp4', kind: 'video', label: 'fake', title: 'Interview clip', note: '18-second clip forwarded on a group chat.', thumb: thumb(vid),
      mockFile: async () => new File([new Uint8Array(2048)], 'mock-interview.mp4', { type: 'video/mp4' }) },
    { file: 'mock-voicenote-real.wav', kind: 'audio', label: 'real', title: 'Voice note', note: 'A voice message recorded on a phone.',
      mockFile: async () => new File([wavBlob(6, 16000, false)], 'mock-voicenote-real.wav', { type: 'audio/wav' }) },
    { file: 'mock-urgent-call.wav', kind: 'audio', label: 'fake', title: '"Urgent" phone call', note: 'A caller asking for money, fast.',
      mockFile: async () => new File([wavBlob(6, 16000, true)], 'mock-urgent-call.wav', { type: 'audio/wav' }) },
    { file: 'mock-edited.jpg', kind: 'image', label: 'fake', title: 'Edited headshot', note: 'Cropped and re-saved several times.', thumb: thumb(p2),
      mockFile: () => canvasFile(p2, 'mock-edited.jpg') },
  ];
}
