// VERITAS lab — 01 ANALYZE: intake (drop / click / paste / evidence locker), the examination sequence, report, history.

import { $, $$, esc, html, fileKind, fmtBytes, fmtElapsed, sha256Hex, shortHash, sleep, toast, on, emit,
  band, BAND_VAR, CATEGORY_LABEL, pad, reducedMotion, isTyping, MOCK, params } from './util.js';
import * as api from './api.js';
import { renderReport, stopMedia } from './report.js';

/* Pipeline shown while the engine works (names follow docs/ARCHITECTURE.md test ids).
   The engine runs these server-side and returns them together; the UI does not invent per-test progress. */
const PIPE = {
  image: [
    ['ai_generated', 'AI-Generated Image Detector', 'ai_model'], ['ai_face', 'AI Face Analysis', 'ai_model'],
    ['ela', 'Error Level Analysis', 'compression'], ['noise', 'Noise Residual Consistency', 'noise'],
    ['fft', 'Frequency Spectrum (FFT)', 'frequency'], ['jpeg_quant', 'JPEG Quantisation Tables', 'compression'],
    ['metadata', 'Metadata & Provenance', 'metadata'],
  ],
  video: [
    ['ai_face', 'AI Face Analysis (per-frame)', 'ai_model'], ['face_swap', 'Face-Swap Detector', 'ai_model'],
    ['ai_generated', 'AI-Generated Image Detector', 'ai_model'], ['blink', 'Blink Rate (Eye Aspect Ratio)', 'biometric'], ['landmark_jitter', 'Landmark Jitter', 'temporal'],
    ['temporal_flicker', 'Temporal Flicker', 'temporal'], ['metadata', 'Metadata & Provenance', 'metadata'],
  ],
  audio: [
    ['ai_voice', 'AI Voice Detector', 'ai_model'], ['spectral_cutoff', 'Spectral Cut-off', 'acoustic'],
    ['prosody', 'Prosody & Pitch', 'acoustic'], ['breath_silence', 'Breaths & Silence', 'acoustic'],
    ['spectrogram', 'Spectrogram', 'acoustic'],
  ],
};
// Booth laptop is CPU-only: keep the expectations generous (re-time on the Windows laptop if needed).
const TYPICAL = { image: 'usually under 15 s', video: 'usually under 1 min on CPU', audio: 'usually under 20 s' };
const SLOW_S = { image: 45, video: 120, audio: 45 };   // when to say "taking longer than usual"
const BUSY_RETRY_S = 6;                                  // auto-retry delay after HTTP 503 (engine busy)
const TRUTH_WORDS = { real: 'real', authentic: 'real', genuine: 'real', fake: 'fake', synthetic: 'fake', ai: 'fake', deepfake: 'fake', generated: 'fake' };

const S = {
  state: 'intake',
  job: null,          // { abort, timer, ... }
  history: [],        // { report, url, file, truth, thumb }
  intake: 0,
  engine: 'checking',
  current: null,
  cancelledAt: -1e9,  // when a job was cancelled while the engine was working on it
};

/* The scan panel owns per-job resources (object URL, listeners, a looping preview video, retry timer).
   releaseScan() frees them whenever the scan panel is replaced or left, so a long booth day doesn't leak. */
let scanJob = null;

let view, intakeEl, scanEl, reportEl;

/* ------------------------------------------------------------------ lifecycle */
export function init() {
  view = $('#view-analyze'); intakeEl = $('#intake'); scanEl = $('#scan'); reportEl = $('#report');
  S.intake = 1;
  bindIntake();
  loadLocker();
  on('engine', ({ state }) => { S.engine = state; });
  on('analyze-file', ({ file, meta }) => { emit('goto', 'analyze'); setTimeout(() => start(file, meta || {}), 30); });
  setState('intake');
  bindIdleReset();
  // warm the in-browser face pre-scan while the booth is idle
  const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 1));
  setTimeout(() => idle(() => import('./facemesh.js').then((m) => m.warm()).catch(() => {})), 2500);
}
export function enter() {
  if (S.state === 'report') reportEl.focus?.({ preventScroll: true });
}

/* Kiosk privacy: after a quiet spell (default 150 s, ?idle=SECONDS to change) forget every Live Cam capture - the
   thumbnails are visitors' faces - and return a finished report to the intake screen. Other cases stay in
   "This session" so a presenter can reopen them with one click. Never interrupts a running scan. */
function bindIdleReset() {
  const IDLE_MS = (Number(params.get('idle')) || 150) * 1000;
  let t = 0;
  const bump = () => {
    clearTimeout(t);
    t = setTimeout(() => {
      if (S.state === 'scanning') return bump();
      const before = S.history.length;
      S.history = S.history.filter((h) => {
        if (h.origin !== 'live') return true;
        if (h.url) URL.revokeObjectURL(h.url);
        return false;
      });
      if (S.state === 'report') newCase();
      else if (S.history.length !== before) renderHistory();
    }, IDLE_MS);
  };
  for (const ev of ['pointerdown', 'pointermove', 'keydown', 'wheel', 'touchstart']) window.addEventListener(ev, bump, { passive: true });
  bump();
}
export function leave() {}

function setState(s) {
  S.state = s;
  view.dataset.state = s;
  view.scrollTop = 0;
  window.scrollTo({ top: 0 });
  $('#history').hidden = s === 'scanning' || !S.history.length;
}

/* ------------------------------------------------------------------ intake */
function bindIntake() {
  const drop = $('#drop'); const input = $('#file-input');
  drop.addEventListener('click', () => input.click());
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
  input.addEventListener('change', () => { const f = input.files?.[0]; input.value = ''; if (f) start(f, { origin: 'upload' }); });

  // Drag anywhere over the Analyze view
  let depth = 0;
  const isFileDrag = (e) => Array.from(e.dataTransfer?.types || []).includes('Files');
  view.addEventListener('dragenter', (e) => { if (!isFileDrag(e)) return; e.preventDefault(); depth++; view.classList.add('is-dragging'); });
  view.addEventListener('dragover', (e) => { if (!isFileDrag(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; });
  view.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) view.classList.remove('is-dragging'); });
  view.addEventListener('drop', (e) => {
    if (!isFileDrag(e)) return;
    e.preventDefault(); depth = 0; view.classList.remove('is-dragging');
    const f = e.dataTransfer.files?.[0];
    if (f) start(f, { origin: 'drop' });
  });
  // Stop the browser from navigating away if a file is dropped elsewhere
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', (e) => e.preventDefault());

  window.addEventListener('paste', (e) => {
    if (document.body.dataset.view !== 'analyze' || isTyping(e)) return;
    const items = Array.from(e.clipboardData?.items || []);
    const it = items.find((i) => i.kind === 'file');
    const f = it?.getAsFile();
    if (!f) { toast('Nothing to paste — copy an image first', 'warn'); return; }
    const named = f.name && f.name !== 'image.png' ? f : new File([f], `pasted-${Date.now().toString(36)}.${(f.type.split('/')[1] || 'png').replace('jpeg', 'jpg')}`, { type: f.type });
    start(named, { origin: 'paste' });
  });

  window.addEventListener('keydown', (e) => {
    if (document.body.dataset.view !== 'analyze' || isTyping(e) || document.querySelector('.overlay:not([hidden])')) return;
    if (e.key === 'Escape' && S.state === 'scanning') { if (S.job) cancel(); else newCase(); }
    if ((e.key === 'n' || e.key === 'N') && S.state === 'report') newCase();
  });
}

async function loadLocker() {
  const box = $('#locker');
  box.innerHTML = '<p class="locker-empty">Opening the locker…</p>';
  const items = await api.lockerItems();
  // honesty: the exhibits were picked to show each test working (fakes it scored > 70, reals < 20); the manifest's
  // last exhibit is a deliberate miss. The story's Results chapter (06·2, 06·3) shows everything it gets wrong.
  const lc = $('#locker-count');
  lc.textContent = items.length ? `${items.length} exhibits · picked to show each test` : '';
  lc.title = 'Exhibits were chosen to show each test working; one is a fake VERITAS misses. For everything it gets wrong, see the story, Results 06·2 and 06·3 (video benchmark).';
  if (!items.length) {
    box.innerHTML = `<div class="locker-empty"><p><strong>No demo exhibits installed.</strong></p>
      <p>Put sample files and a <code>manifest.json</code> in <code>web/samples/lab/</code>, or drop your own file on the left.</p></div>`;
    return;
  }
  box.innerHTML = '';
  items.forEach((it, i) => {
    const letter = String.fromCharCode(65 + (i % 26)) + (i >= 26 ? Math.floor(i / 26) : '');
    const kind = it.kind || 'image';
    const truth = TRUTH_WORDS[String(it.label || '').toLowerCase()] || null;
    const thumb = it.thumb
      ? `<img src="${esc(it.thumb)}" alt="" loading="lazy">`
      : kind === 'image' ? `<img src="${esc(it.src)}" alt="" loading="lazy" decoding="async">`
      : kind === 'video' ? `<video src="${esc(it.src)}#t=0.8" muted preload="metadata" playsinline tabindex="-1"></video>`
      : waveGlyph(i);
    const tagLabel = !truth && it.label ? `<span class="lk-label">${esc(it.label)}</span>` : '';
    const card = html(`
      <button class="lk" type="button" role="listitem" data-kind="${esc(kind)}" style="--i:${i}">
        <span class="lk-thumb">${thumb}<span class="lk-kind">${kindIcon(kind)}${esc(kind)}</span></span>
        <span class="lk-body">
          <span class="lk-top"><span class="lk-ex">Exhibit ${esc(letter)}</span>
          ${truth ? '<span class="lk-seal" title="Ground truth stays sealed until the report">Sealed</span>' : ''}</span>
          <span class="lk-title">${esc(it.title || it.file)}</span>
          ${it.note ? `<span class="lk-note">${esc(it.note)}</span>` : ''}
          ${tagLabel}
        </span>
      </button>`);
    card.addEventListener('click', async () => {
      if (card.classList.contains('is-loading')) return;
      card.classList.add('is-loading');
      try {
        const f = await api.lockerFile(it);
        start(f, { origin: 'locker', truth, exhibit: letter, title: it.title });
      } catch (err) { toast(err.message || 'Could not open that exhibit', 'warn'); }
      finally { card.classList.remove('is-loading'); }
    });
    // Mute broken thumbs gracefully
    card.querySelector('img,video')?.addEventListener('error', (e) => { e.target.replaceWith(html(waveGlyph(i, true))); }, { once: true });
    box.appendChild(card);
  });
  // Scroll cue when the exhibits don't all fit (fade + hint at the bottom edge)
  const locker = box.closest('.locker');
  const cue = () => {
    const over = box.scrollHeight > box.clientHeight + 4;
    locker.classList.toggle('is-overflow', over);
    locker.classList.toggle('at-end', !over || box.scrollTop + box.clientHeight >= box.scrollHeight - 6);
  };
  box.addEventListener('scroll', cue, { passive: true });
  new ResizeObserver(cue).observe(box);
  requestAnimationFrame(cue);
}

function waveGlyph(seed, broken = false) {
  if (broken) return '<span class="lk-glyph" aria-hidden="true">no preview</span>';
  let d = ''; let s = seed * 9301 + 49297;
  for (let i = 0; i < 46; i++) {
    s = (s * 9301 + 49297) % 233280; const r = s / 233280;
    const env = Math.sin((i / 46) * Math.PI) * 0.8 + 0.2;
    const h = Math.max(2, r * 30 * env + 2);
    d += `<rect x="${i * 4 + 6}" y="${40 - h / 2}" width="2" height="${h}" rx="1"/>`;
  }
  return `<svg class="lk-wave" viewBox="0 0 196 80" preserveAspectRatio="xMidYMid meet" aria-hidden="true">${d}</svg>`;
}
export function kindIcon(k) {
  if (k === 'video') return '<svg class="kic" viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="3.5" width="9" height="9" rx="1" fill="none" stroke="currentColor"/><path d="M10.5 7l4-2.5v7l-4-2.5z" fill="currentColor"/></svg>';
  if (k === 'audio') return '<svg class="kic" viewBox="0 0 16 16" aria-hidden="true"><path d="M2 7v2M5 4v8M8 2v12M11 5v6M14 7v2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
  return '<svg class="kic" viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="11" rx="1" fill="none" stroke="currentColor"/><circle cx="5.5" cy="6.5" r="1.5" fill="currentColor"/><path d="M2 12l4-4 3 3 2-2 3.5 3.5" fill="none" stroke="currentColor"/></svg>';
}

function releaseScan() {
  const job = scanJob; scanJob = null;
  if (job) {
    for (const fn of job.cleanups.splice(0)) { try { fn(); } catch { /* ignore */ } }
    if (job.url && !S.history.some((h) => h.url === job.url)) URL.revokeObjectURL(job.url);
  }
  for (const m of scanEl.querySelectorAll('video, audio')) { try { m.pause(); m.removeAttribute('src'); m.load(); } catch { /* ignore */ } }
  scanEl.innerHTML = '';
}

/** An audio-only .webm/.ogg reports a video/* MIME type: look inside before choosing the endpoint. */
function probeAudioOnly(file) {
  return new Promise((resolve) => {
    const v = document.createElement('video'); const u = URL.createObjectURL(file);
    const done = (r) => { clearTimeout(t); v.removeAttribute('src'); v.load(); URL.revokeObjectURL(u); resolve(r); };
    const t = setTimeout(() => done(false), 2500);
    v.muted = true; v.preload = 'metadata';
    v.onloadedmetadata = () => done(!v.videoWidth && !v.videoHeight);
    v.onerror = () => done(false);
    v.src = u;
  });
}

/* ------------------------------------------------------------------ examination */
async function start(file, meta = {}) {
  const ext = (file.name || '').split('.').pop().toLowerCase();
  // iPhone HEIC/HEIF photos: the browser can't preview them, but the engine decodes them (pillow-heif) and returns a preview.
  let kind = fileKind(file);
  if (kind === 'video' && (ext === 'webm' || ext === 'ogg' || /webm|ogg/i.test(file.type || '')) && await probeAudioOnly(file)) kind = 'audio';
  if (!kind) {
    toast('That file type is not supported. Use an image (JPG/PNG/WEBP), video (MP4/MOV/WEBM) or audio (WAV/MP3/M4A/OGG).', 'warn', 5200);
    return;
  }
  if (file.size > 200 * 1024 * 1024) { toast('That file is over the engine’s 200 MB limit — please trim it first.', 'warn'); return; }
  if (S.job) cancel(true);
  closeOverlay();
  releaseScan();

  const url = URL.createObjectURL(file);
  const pipe = PIPE[kind];
  const t0 = performance.now();
  const job = { file, kind, url, meta, t0, aborted: false, lastLog: 0, cleanups: [] };
  S.job = job; scanJob = job;
  S.intake++;

  scanEl.appendChild(scanTemplate(file, kind, pipe, meta));
  setState('scanning');
  const $s = (sel) => scanEl.querySelector(sel);
  const log = (msg, cls = '') => {
    const t = (performance.now() - t0) / 1000;
    const line = html(`<p class="log-line ${cls}"><span class="log-t">${t.toFixed(2).padStart(5, '0')}</span><span class="log-m">${msg}</span></p>`);
    const box = $s('.scan-log'); if (!box) return; // the error panel replaced the log, or the scan was released
    box.appendChild(line); box.scrollTop = box.scrollHeight;
    while (box.children.length > 9) box.firstElementChild.remove();
  };

  // stage media
  mountStageMedia($s('.stage-media'), file, kind, url, (dims, el) => {
    const hud = $s('[data-hud="dims"]');
    if (dims && hud) { hud.textContent = dims; log(`decoded · ${esc(dims)}`); }
    if (kind === 'image' && el) preScan($s('.stage-media'), el, job, log);
  });

  // elapsed timer
  const elapsedEl = $s('.scan-elapsed'); const tcEl = $s('[data-hud="tc"]');
  job.cleanups.push(() => clearInterval(job.timer));
  job.timer = setInterval(() => {
    const t = (performance.now() - t0) / 1000;
    elapsedEl.textContent = fmtElapsed(t); tcEl.textContent = fmtElapsed(t);
    if (job.phase === 'engine') {
      const e = (performance.now() - job.engineT0) / 1000;
      if (e > 4 && !job.said4) { job.said4 = true; log(kind === 'video' ? 'decoding & sampling up to 48 frames…' : 'neural models are running on the CPU…', 'dim'); }
      if (e > 12 && !job.said12) { job.said12 = true; log(kind === 'video' ? 'still working — every sampled frame gets a face check' : 'still working — larger files take longer', 'dim'); }
      if (e > SLOW_S[kind] && !job.said30) { job.said30 = true; log('this is taking longer than usual · you can cancel with Esc', 'warn'); }
    }
  }, 100);

  log(`evidence received · <b>${esc(file.name || 'untitled')}</b> · ${esc(file.type || kind)} · ${fmtBytes(file.size)}`);
  if (meta.origin === 'locker') log(`from evidence locker · exhibit ${esc(meta.exhibit || '')}`, 'dim');
  if (meta.origin === 'live') log('frame captured from the live camera', 'dim');

  // Real client-side hash (shown, then cross-checked against the engine's)
  sha256Hex(file).then((h) => {
    if (job.aborted) return;
    job.sha = h;
    const el = $s('[data-k="sha"]');
    if (h && el) { el.textContent = shortHash(h, 12, 8); log(`sha-256 fingerprint · ${h.slice(0, 16)}… <span class="dim">(computed in this browser)</span>`); }
  });

  if (S.engine === 'offline' && !MOCK) log('engine status light is red — trying anyway', 'warn');
  if (performance.now() - S.cancelledAt < 120000) log('the engine may still be finishing the cancelled case · this one waits its turn', 'dim');
  log(`uploading to engine…`);
  const upBar = $s('.up-bar i'); const upPct = $s('.up-pct');
  const req = api.analyze(kind, file, {
    onUpload: (f) => {
      upBar.style.transform = `scaleX(${f})`; upPct.textContent = `${Math.round(f * 100)}%`;
      if (f >= 1 && !job.phase) {
        job.phase = 'engine'; job.engineT0 = performance.now();
        log(`upload complete · engine is running ${pipe.length} forensic tests`);
        scanEl.querySelector('.panel-scan-inner').classList.add('is-engine');
        $s('.pipe').classList.add('is-running');
        $$('.pipe-state', scanEl).forEach((x) => { x.textContent = 'Running'; });
      }
    },
  });
  job.abort = req.abort;

  let report;
  try {
    report = await req.promise;
  } catch (err) {
    if (job.aborted || err.cancelled) return;
    clearInterval(job.timer);
    S.job = null;
    showError(err, file, meta);
    return;
  }
  if (job.aborted) return;
  clearInterval(job.timer);
  job.phase = 'done';

  // Reveal real results on the pipeline rows
  const secs = ((report.elapsed_ms ?? (performance.now() - job.engineT0)) / 1000).toFixed(2);
  log(`report received · case <b>${esc(report.case_id || '—')}</b> · engine time ${secs} s`, 'ok');
  if (job.sha && report.file?.sha256 && report.file.sha256 !== job.sha) log('note: engine hash differs from browser hash', 'warn');
  await revealPipe(report, pipe);
  if (job.aborted) return;

  // Into the report
  const entry = { report, url, truth: meta.truth || null, origin: meta.origin, title: meta.title };
  entry.thumb = report.preview || null;
  S.history.unshift(entry);
  while (S.history.length > 12) { const old = S.history.pop(); if (old.url) URL.revokeObjectURL(old.url); }
  S.job = null;
  showReport(entry, true);
}

function scanTemplate(file, kind, pipe, meta) {
  const rows = pipe.map(([id, name, cat], i) => `
    <li class="pipe-row" data-id="${id}" style="--i:${i}">
      <span class="pipe-n">${pad(i + 1)}</span>
      <span class="pipe-name">${esc(name)}</span>
      <span class="pipe-cat">${esc(CATEGORY_LABEL[cat] || cat)}</span>
      <span class="pipe-state">Queued</span>
      <span class="pipe-bar"><i></i></span>
    </li>`).join('');
  return html(`
  <div class="panel-scan-inner" data-kind="${kind}">
    <div class="stage bracketed" data-kind="${kind}">
      <div class="stage-media"></div>
      <div class="stage-grid" aria-hidden="true"></div>
      <div class="stage-sweep" aria-hidden="true"><i></i></div>
      <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
      <span class="hud hud-tl">Exhibit · ${esc(kind)}${meta.exhibit ? ` ${esc(meta.exhibit)}` : ''}</span>
      <span class="hud hud-tr" data-hud="dims">—</span>
      <span class="hud hud-bl">${esc(file.name || 'untitled')}</span>
      <span class="hud hud-br" data-hud="tc">00:00.0</span>
      <span class="stage-reticle" aria-hidden="true"></span>
    </div>
    <div class="scan-side">
      <p class="eyebrow"><span class="eyebrow-n">§ 02</span> Examination in progress <span class="eyebrow-sep">/</span> Intake #${pad(S.intake, 4)}</p>
      <h2 class="scan-title">Examining the <em>${esc(kind === 'audio' ? 'recording' : kind === 'video' ? 'footage' : 'image')}</em><span class="dots" aria-hidden="true"><i>.</i><i>.</i><i>.</i></span></h2>
      <div class="scan-facts">
        <div class="fact"><span class="label">Elapsed</span><span class="scan-elapsed mono">00:00.0</span><span class="fact-note">${TYPICAL[kind]}</span></div>
        <div class="fact"><span class="label">Size</span><span class="mono fact-v">${fmtBytes(file.size)}</span><span class="fact-note">${esc((file.type || kind).toLowerCase())}</span></div>
        <div class="fact fact-wide"><span class="label">SHA-256</span><span class="mono fact-v" data-k="sha">hashing…</span><span class="fact-note">evidence fingerprint</span></div>
      </div>
      <div class="upload"><span class="label">Upload</span><span class="up-bar"><i></i></span><span class="up-pct mono">0%</span></div>
      <div class="pipe-head"><span class="label">Test battery</span><span class="fact-note">runs on the engine · results arrive together</span></div>
      <ol class="pipe">${rows}</ol>
      <div class="scan-log mono" role="log" aria-label="Examination log"></div>
      <div class="scan-actions"><button class="btn btn-quiet" type="button" data-act="cancel">Cancel <kbd>Esc</kbd></button></div>
    </div>
  </div>`);
}

function mountStageMedia(box, file, kind, url, onDims) {
  if (kind === 'image') {
    const im = new Image(); im.alt = 'Evidence under examination'; im.decoding = 'async';
    im.onload = () => onDims(`${im.naturalWidth} × ${im.naturalHeight}`, im);
    im.onerror = () => { box.innerHTML = '<p class="stage-na">Preview not available in this browser — the engine can still read it.</p>'; onDims(null); };
    im.src = url; box.appendChild(im);
  } else if (kind === 'video') {
    const v = document.createElement('video');
    v.muted = true; v.loop = true; v.playsInline = true; v.autoplay = true; v.src = url;
    v.onloadedmetadata = () => onDims(`${v.videoWidth} × ${v.videoHeight} · ${v.duration.toFixed(1)} s`);
    v.onerror = () => { box.innerHTML = '<p class="stage-na">This video format can’t be previewed here — the engine will decode it.</p>'; onDims(null); };
    box.appendChild(v); v.play?.().catch(() => {});
  } else {
    const c = document.createElement('canvas'); c.className = 'stage-wave'; box.appendChild(c);
    drawAudioPreview(c, file).then((d) => onDims(d)).catch(() => onDims(null));
  }
}

/* In-browser pre-scan: the vendored MediaPipe landmarker finds faces on the exhibit while the engine works.
   Real, local and fast — it only locates faces; the verdict still comes from the engine's tests. */
async function preScan(media, img, job, log) {
  let fm;
  try { fm = await import('./facemesh.js'); } catch { return; }
  const res = await fm.detectStill(img);
  if (!res || job.aborted || job.phase === 'done' || !img.isConnected) return;
  const { faces, FL } = res;
  if (!faces.length) { log('in-browser pre-scan · no face found — every test still runs', 'dim'); return; }
  log(`in-browser pre-scan · ${faces.length} face${faces.length > 1 ? 's' : ''} located · ${faces[0].length} landmarks`);
  const c = document.createElement('canvas'); c.className = 'stage-mesh'; c.setAttribute('aria-hidden', 'true');
  const s = Math.min(1, 1400 / Math.max(img.naturalWidth, img.naturalHeight));
  const W = (c.width = Math.round(img.naturalWidth * s)), H = (c.height = Math.round(img.naturalHeight * s));
  const place = () => {
    const m = media.getBoundingClientRect(), r = img.getBoundingClientRect();
    Object.assign(c.style, { left: `${r.left - m.left}px`, top: `${r.top - m.top}px`, width: `${r.width}px`, height: `${r.height}px` });
  };
  place(); media.appendChild(c);
  window.addEventListener('resize', place);
  job.cleanups.push(() => window.removeEventListener('resize', place));
  const g = c.getContext('2d'); const k = W / 900;
  const tess = FL.FACE_LANDMARKS_TESSELATION; const t0 = performance.now(); const dur = reducedMotion() ? 0 : 1400;
  const frame = (now) => {
    if (!c.isConnected) return;
    const p = dur ? Math.min(1, (now - t0) / dur) : 1;
    g.clearRect(0, 0, W, H);
    for (const L of faces) {
      const n = Math.floor(tess.length * p);
      g.lineWidth = Math.max(0.6, 0.8 * k); g.strokeStyle = 'rgba(170,205,255,0.35)'; g.beginPath();
      for (let i = 0; i < n; i++) { const a = L[tess[i].start], b = L[tess[i].end]; g.moveTo(a.x * W, a.y * H); g.lineTo(b.x * W, b.y * H); }
      g.stroke();
      if (p >= 1) {
        g.fillStyle = 'rgba(62,242,196,0.9)'; const r = Math.max(1.4, 2 * k);
        for (let i = 0; i < 468; i++) g.fillRect(L[i].x * W - r / 2, L[i].y * H - r / 2, r, r);
        g.lineWidth = Math.max(1.5, 2 * k); g.strokeStyle = '#ffb020';
        for (const set of [FL.FACE_LANDMARKS_LEFT_EYE, FL.FACE_LANDMARKS_RIGHT_EYE]) { g.beginPath(); for (const e of set) { g.moveTo(L[e.start].x * W, L[e.start].y * H); g.lineTo(L[e.end].x * W, L[e.end].y * H); } g.stroke(); }
        g.lineWidth = Math.max(1.2, 1.6 * k); g.strokeStyle = 'rgba(62,242,196,0.7)'; g.beginPath();
        for (const e of FL.FACE_LANDMARKS_FACE_OVAL) { g.moveTo(L[e.start].x * W, L[e.start].y * H); g.lineTo(L[e.end].x * W, L[e.end].y * H); }
        g.stroke();
      }
    }
    if (p < 1) requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

async function drawAudioPreview(canvas, file) {
  const AC = window.AudioContext || window.webkitAudioContext;
  const ac = new AC();
  try {
    const buf = await ac.decodeAudioData(await file.arrayBuffer());
    const data = buf.getChannelData(0);
    const W = 1200, H = 520; canvas.width = W; canvas.height = H;
    const g = canvas.getContext('2d'); const N = 300; const step = Math.floor(data.length / N);
    g.fillStyle = 'rgba(232,230,223,.75)';
    for (let i = 0; i < N; i++) {
      let m = 0; for (let j = 0; j < step; j += 4) m = Math.max(m, Math.abs(data[i * step + j] || 0));
      const h = Math.max(2, m * H * 0.8);
      g.fillRect(i * (W / N) + 1, (H - h) / 2, W / N - 2, h);
    }
    return `${buf.sampleRate} Hz · ${buf.duration.toFixed(1)} s`;
  } finally { ac.close?.(); }
}

async function revealPipe(report, pipe) {
  const list = scanEl.querySelector('.pipe');
  list.classList.remove('is-running');
  const tests = report.tests || [];
  const existing = new Set(pipe.map((p) => p[0]));
  // rows the engine didn't return disappear; extra tests are appended
  for (const row of $$('.pipe-row', list)) if (!tests.find((t) => t.id === row.dataset.id)) row.classList.add('is-gone');
  tests.forEach((t, i) => {
    if (!existing.has(t.id)) {
      list.appendChild(html(`<li class="pipe-row" data-id="${esc(t.id)}"><span class="pipe-n">${pad(list.children.length + 1)}</span><span class="pipe-name">${esc(t.name)}</span><span class="pipe-cat">${esc(CATEGORY_LABEL[t.category] || t.category || '')}</span><span class="pipe-state">Running</span><span class="pipe-bar"><i></i></span></li>`));
    }
  });
  const stagger = reducedMotion() ? 0 : 130;
  for (const t of tests) {
    const row = list.querySelector(`.pipe-row[data-id="${CSS.escape(t.id)}"]`);
    if (!row) continue;
    const st = row.querySelector('.pipe-state');
    // a one-sided test (the face-swap detector) below 50 is silent: grey, it neither flags nor clears the file
    const b = t.metrics && t.metrics.one_sided && t.score != null && t.score < 50 ? 'none' : band(t.score);
    row.dataset.band = b;
    row.querySelector('.pipe-name').textContent = t.name || row.querySelector('.pipe-name').textContent;
    if (t.status === 'skipped' || t.status === 'error') { row.classList.add('is-skipped'); st.textContent = t.status === 'error' ? 'Error' : 'Skipped'; }
    else if (t.score == null) { st.textContent = 'Visual'; row.classList.add('is-done'); }
    else {
      st.innerHTML = `<b style="color:${BAND_VAR[b]}">${Math.round(t.score)}</b>`;
      row.querySelector('.pipe-bar i').style.cssText = `transform:scaleX(${t.score / 100});background:${BAND_VAR[b]}`;
      row.classList.add('is-done');
    }
    await sleep(stagger);
  }
  await sleep(reducedMotion() ? 100 : 650);
}

function showError(err, file, meta) {
  // A reply without the engine's {error} body (404/501 from a plain file server, proxies…) means no engine is answering.
  const offline = err.offline || err.status === 0 || (!err.fromEngine && (S.engine === 'offline' || [404, 405, 501, 502, 504].includes(err.status)));
  const busy = !offline && err.status === 503;
  const tooBig = !offline && err.status === 413;
  if (offline && !err.offline) err.message = `No forensic engine answered (HTTP ${err.status}).`;
  const job = scanJob;
  const box = scanEl.querySelector('.scan-side');
  scanEl.querySelector('.panel-scan-inner').classList.add('is-error');
  const title = offline ? 'The engine is <em>not responding.</em>'
    : busy ? 'The engine is <em>busy.</em>'
    : tooBig ? 'That file is <em>too large.</em>'
    : 'The engine couldn’t <em>read this file.</em>';
  const help = offline ? '<p class="err-help">On the booth laptop, double-click <code>start_windows.bat</code> and wait until the engine light in the top-right turns green.</p>'
    : busy ? `<p class="err-help">It is still finishing the previous case. Trying again in <b class="err-count mono">${BUSY_RETRY_S}</b> s…</p>`
    : tooBig ? '<p class="err-help">Trim the clip or pick a smaller file (the limit is 200 MB).</p>'
    : '<p class="err-help">Try a different file, or a common format such as JPG, MP4 or WAV.</p>';
  box.innerHTML = `
    <div class="err">
      <p class="eyebrow"><span class="eyebrow-n">§ 02</span> ${busy ? 'Waiting for the engine' : 'Examination halted'}</p>
      <h2 class="err-title">${title}</h2>
      <p class="err-msg">${esc(err.message || 'Unknown error')}</p>
      ${help}
      <div class="err-actions">
        <button class="btn btn-primary" type="button" data-act="retry">${busy ? 'Retry now' : 'Try again'}</button>
        <button class="btn btn-ghost" type="button" data-act="new">Choose another file</button>
      </div>
    </div>`;
  box.querySelector('[data-act="retry"]').addEventListener('click', () => start(file, meta));
  box.querySelector('[data-act="new"]').addEventListener('click', () => newCase());
  box.querySelector('[data-act="retry"]').focus();
  if (busy && job) {
    let n = BUSY_RETRY_S; const out = box.querySelector('.err-count');
    const t = setInterval(() => {
      if (scanJob !== job) return clearInterval(t);
      n -= 1; if (out) out.textContent = String(Math.max(0, n));
      if (n <= 0) { clearInterval(t); start(file, meta); }
    }, 1000);
    job.cleanups.push(() => clearInterval(t));
  }
}

function cancel(silent = false) {
  const job = S.job; if (!job) return;
  if (job.phase === 'engine') S.cancelledAt = performance.now(); // the engine keeps working on it server-side
  job.aborted = true; clearInterval(job.timer); job.abort?.();
  S.job = null;
  releaseScan();
  if (!silent) { setState(S.current ? 'report' : 'intake'); toast('Examination cancelled'); if (!S.current) renderHistory(); }
}

/* ------------------------------------------------------------------ report + history */
let overlayMod = null;
async function openTest(entry, idx) {
  overlayMod ||= await import('./overlay.js');
  overlayMod.open(entry, idx);
}
function closeOverlay() { overlayMod?.close?.(); }

function showReport(entry, fresh = false) {
  S.current = entry;
  if (S.job) cancel(true);
  releaseScan();
  stopMedia();
  reportEl.innerHTML = '';
  reportEl.appendChild(renderReport(entry, { fresh, onNew: newCase, onOpenTest: (i) => openTest(entry, i) }));
  setState('report');
  renderHistory();
  reportEl.querySelector('.rp-new')?.focus({ preventScroll: true });
}

function newCase() {
  if (S.job) cancel(true);
  releaseScan();
  closeOverlay();
  S.current = null;
  stopMedia();
  reportEl.innerHTML = '';
  $('#intake-no').textContent = `Intake #${pad(S.intake, 4)}`;
  setState('intake');
  renderHistory();
  $('#drop').focus({ preventScroll: true });
}

function renderHistory() {
  const row = $('#history-row'); row.innerHTML = '';
  $('#history').hidden = S.state === 'scanning' || !S.history.length;
  S.history.forEach((h) => {
    const r = h.report; const v = (r.verdict || band(r.score));
    const kind = r.kind || 'image';
    const thumb = h.thumb ? `<img src="${esc(h.thumb)}" alt="">` : `<span class="hc-glyph">${kindIcon(kind)}</span>`;
    const b = html(`<button type="button" class="hc ${h === S.current ? 'is-current' : ''}" role="listitem" data-v="${esc(v)}" title="${esc(r.file?.name || '')}">
        <span class="hc-thumb">${thumb}</span>
        <span class="hc-body"><span class="hc-id">${esc(r.case_id || '—')}</span>
        <span class="hc-v"><i></i>${esc(v)} · ${Math.round(r.score ?? 0)}</span></span></button>`);
    b.addEventListener('click', () => showReport(h));
    row.appendChild(b);
  });
}
