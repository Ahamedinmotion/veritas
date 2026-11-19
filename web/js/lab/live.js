// VERITAS lab — 02 LIVE CAM: webcam + MediaPipe FaceLandmarker (vendored, offline).
// 478-point mesh, eye aspect ratio + blink detection, head pose from the facial transformation matrix,
// a randomised liveness challenge (blinks + head turns in a random order, measured against the visitor's own
// resting pose) and "capture & analyze".

import { $, html, emit, clamp, pad, toast, reducedMotion, MOCK } from './util.js';
import { createLandmarker } from './facemesh.js';


// Eye landmark indices for EAR (p1..p6): corner, top, top, corner, bottom, bottom
const EYE_R = [33, 160, 158, 133, 153, 144];
const EYE_L = [362, 385, 387, 263, 373, 380];

let FL = null;            // FaceLandmarker class
let landmarker = null;
let loading = null;
let delegate = '—';
let stream = null;
let running = false;
let starting = false;
let wanted = false;       // tab is visible and wants the camera
let meshOn = true;
let vfc = 0, raf = 0, lastVideoTime = -1;
let els = {};
let cam0 = 0;
const fpsTimes = [];

// blink / EAR state
const E = { hist: [], base: 0.3, closed: false, closedAt: 0, blinks: [], count: 0, value: null, firstFace: 0, lastFace: 0 };
// head pose (degrees). yaw > 0: subject turned to THEIR left; pitch > 0: looking up; roll > 0: tilted clockwise on the mirrored screen
const P = { yaw: 0, pitch: 0, roll: 0, ok: false };
let LV = null; // liveness state
let noFaceSince = 0; // for the "step into frame" prompt
const IDLE_PAUSE_MS = 90000;

/* ------------------------------------------------------------------ lifecycle */
export function init() {
  els = {
    stage: $('#live-stage'), video: $('#live-video'), canvas: $('#live-canvas'), msg: $('#live-msg'), flash: $('#live-flash'),
    tc: $('#live-tc'), lv: $('#liveness'), ear: $('#ear-v'), graph: $('#ear-graph'), blinkN: $('#blink-n'), rate: $('#blink-rate'),
    rateMark: $('#rate-mark'), yaw: $('#pose-yaw'), pitch: $('#pose-pitch'), roll: $('#pose-roll'),
    faces: $('#t-faces'), fps: $('#t-fps'), points: $('#t-points'), deleg: $('#t-delegate'),
    btnCheck: $('#live-check'), btnCap: $('#live-capture'), btnMesh: $('#live-mesh'),
  };
  els.ctx = els.canvas.getContext('2d');
  els.btnMesh.addEventListener('click', () => {
    meshOn = !meshOn; els.btnMesh.setAttribute('aria-pressed', String(meshOn));
    els.btnMesh.textContent = meshOn ? 'Mesh on' : 'Mesh off';
  });
  els.btnCap.addEventListener('click', capture);
  els.btnCheck.addEventListener('click', () => (LV && !LV.done ? endLiveness() : startLiveness()));
  window.addEventListener('keydown', (e) => {
    if (document.body.dataset.view !== 'live' || e.ctrlKey || e.metaKey || e.altKey || e.target?.tagName === 'INPUT') return;
    if (e.key === 'l' || e.key === 'L') { e.preventDefault(); els.btnCheck.click(); }
    if (e.key === 'c' || e.key === 'C' || e.key === ' ') { e.preventDefault(); if (running) capture(); }
    if (e.key === 'm' || e.key === 'M') els.btnMesh.click();
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else if (wanted) start(); });
  drawGraph();
  resetStats();
}

export function enter() { wanted = true; start(); }
export function leave() { wanted = false; stop(); endLiveness(true); }

/* ------------------------------------------------------------------ MediaPipe */
async function loadLandmarker(prefer = 'GPU') {
  const r = await createLandmarker('VIDEO', {}, prefer);
  FL = r.FL; landmarker = r.lm; delegate = r.delegate;
  if (running) els.deleg.textContent = delegate; // shown only while the camera actually runs
  return landmarker;
}

/* ------------------------------------------------------------------ camera */
function msg(kind, title, body = '', action = null) {
  const m = els.msg;
  if (!kind) { m.classList.remove('is-on'); m.innerHTML = ''; return; }
  m.innerHTML = '';
  const box = html(`<div class="live-msg-box">${kind === 'busy' ? '<span class="live-spin" aria-hidden="true"></span>' : ''}
    <p class="eyebrow"><span class="eyebrow-n">§ 02</span> ${kind === 'busy' ? 'Starting up' : 'Camera'}</p>
    <h2>${title}</h2>${body ? `<p>${body}</p>` : ''}</div>`);
  if (action) {
    const b = html(`<button class="btn btn-primary" type="button">${action.label}</button>`);
    b.addEventListener('click', action.fn); box.appendChild(b);
  }
  m.appendChild(box); m.classList.add('is-on');
}

async function start() {
  if (running || starting) return;
  starting = true;
  els.stage.dataset.state = 'starting';
  msg('busy', 'Waking the <em>camera</em>…', 'If the browser asks, allow camera access. Nothing is recorded or uploaded.');
  const modelP = (loading ||= loadLandmarker().catch((e) => { loading = null; throw e; }));
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('no mediaDevices'), { name: 'NoAPI' });
    stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user', frameRate: { ideal: 30 } }, audio: false,
    });
    if (!wanted) { stopTracks(); starting = false; return; }
    els.video.srcObject = stream;
    await els.video.play();
  } catch (err) {
    starting = false; els.stage.dataset.state = 'error'; stopTracks();
    const n = err?.name;
    const booth = /^(localhost|127\.\d+\.\d+\.\d+|\[::1\])$/i.test(location.hostname);
    if (n === 'NotAllowedError' || n === 'SecurityError') msg('err', 'Camera access <em>blocked.</em>', booth
      ? 'Ask a team member to allow the camera for this page (camera icon in the address bar → Allow; press F to leave fullscreen first), then press Retry. If it still fails: Windows Settings → Privacy &amp; security → Camera → turn on camera access and “Let desktop apps access your camera”, and open the laptop’s camera shutter.'
      : 'Allow the camera for this page (the camera icon in the address bar, or the site settings of your browser), then press Retry. The face tracking runs in your browser: nothing is recorded or uploaded unless you press Capture &amp; analyze. Spot the fake works without a camera.', { label: 'Retry', fn: () => start() });
    else if (n === 'NotSupportedError' || n === 'TypeError') msg('err', 'Camera not <em>available</em> here.', 'This browser cannot open a camera on this page. Try Chrome, Edge or Safari over https://. Spot the fake and the Evidence locker still work.', { label: 'Retry', fn: () => start() });
    else if (n === 'NotFoundError' || n === 'OverconstrainedError') msg('err', 'No camera <em>found.</em>', 'Plug in a webcam (or enable the laptop camera), then press Retry.', { label: 'Retry', fn: () => start() });
    else if (n === 'NotReadableError' || n === 'AbortError') msg('err', 'Camera is <em>busy.</em>', 'Another app (Teams, Zoom, Camera) may be using it. Close that app, then press Retry. If it still fails: Windows Settings → Privacy &amp; security → Camera → turn on camera access and “Let desktop apps access your camera”, and open the laptop’s camera shutter.', { label: 'Retry', fn: () => start() });
    else if (n === 'NoAPI') msg('err', 'Camera not <em>available</em> here.', window.isSecureContext === false
      ? 'Browsers only allow the camera on secure pages. Open the lab through an https:// address (or on the booth laptop), in Chrome, Edge or Safari.'
      : 'This browser cannot open a camera. Try Chrome, Edge or Safari. Spot the fake and the Evidence locker still work.');
    else msg('err', 'Camera could not <em>start.</em>', String(err?.message || err), { label: 'Retry', fn: () => start() });
    return;
  }
  msg('busy', 'Loading the <em>face tracker</em>…', 'MediaPipe Face Landmarker · runs entirely in this browser');
  try { await modelP; } catch (e) {
    starting = false; els.stage.dataset.state = 'error';
    msg('err', 'Face tracker failed to <em>load.</em>', `The camera works, but the model in vendor/mediapipe could not start (${String(e?.message || e).slice(0, 120)}).`, { label: 'Retry', fn: () => { stop(); start(); } });
    return;
  }
  if (!wanted) { stop(); starting = false; return; }
  els.canvas.width = els.video.videoWidth || 1280;
  els.canvas.height = els.video.videoHeight || 720;
  msg(null);
  starting = false; running = true; cam0 = performance.now(); lastVideoTime = -1; noFaceSince = performance.now();
  els.stage.dataset.state = 'running';
  els.points.textContent = '478';
  els.deleg.textContent = delegate;
  schedule();
}

function stopTracks() { stream?.getTracks().forEach((t) => t.stop()); stream = null; }

function stop() {
  running = false;
  showNoFace(false);
  if (els.deleg) els.deleg.textContent = '—';
  if (vfc && els.video.cancelVideoFrameCallback) els.video.cancelVideoFrameCallback(vfc);
  cancelAnimationFrame(raf); vfc = 0; raf = 0;
  stopTracks();
  if (els.video) { els.video.pause?.(); els.video.srcObject = null; }
  if (els.stage && els.stage.dataset.state === 'running') els.stage.dataset.state = 'idle';
  els.ctx?.clearRect(0, 0, els.canvas.width, els.canvas.height);
}

function schedule() {
  if (!running) return;
  if (els.video.requestVideoFrameCallback) vfc = els.video.requestVideoFrameCallback(onFrame);
  else raf = requestAnimationFrame(onFrame);
}

let gpuFailures = 0;
function onFrame() {
  if (!running) return;
  const v = els.video;
  if (v.readyState >= 2 && v.currentTime !== lastVideoTime) {
    lastVideoTime = v.currentTime;
    const now = performance.now();
    let res = null;
    try { res = landmarker.detectForVideo(v, now); gpuFailures = 0; }
    catch (e) {
      if (delegate === 'GPU' && ++gpuFailures > 3) { // fall back to CPU at runtime
        running = false; landmarker?.close?.(); landmarker = null; loading = null; delegate = 'CPU';
        loading = loadLandmarker('CPU').then(() => { if (wanted && stream) { running = true; els.deleg.textContent = delegate; schedule(); } });
        return;
      }
    }
    if (res) process(res, now);
    fpsTimes.push(now); while (fpsTimes.length && now - fpsTimes[0] > 1000) fpsTimes.shift();
  }
  schedule();
}
/* ------------------------------------------------------------------ per-frame */
let uiTick = 0;
function process(res, now) {
  const faces = res.faceLandmarks || [];
  const W = els.canvas.width, H = els.canvas.height;
  const g = els.ctx;
  g.clearRect(0, 0, W, H);

  if (faces.length) {
    if (!E.firstFace || now - E.lastFace > 5000) { E.firstFace = now; E.blinks = []; }
    E.lastFace = now;
    const L = faces[0];
    // EAR in pixel space (aspect-correct)
    const ear = (earOf(L, EYE_R, W, H) + earOf(L, EYE_L, W, H)) / 2;
    E.value = ear;
    pose(res.facialTransformationMatrixes?.[0]);
    blink(ear, now);
    E.hist.push({ t: now, v: ear });
  } else {
    E.value = null; P.ok = false;
    E.hist.push({ t: now, v: null });
  }
  while (E.hist.length && now - E.hist[0].t > 10000) E.hist.shift();

  faces.forEach((L, i) => drawFace(g, L, W, H, i, faces.length));
  if (LV && !LV.done) stepLiveness(now, faces.length);
  if (faces.length) noFaceSince = 0; else if (!noFaceSince) noFaceSince = now;
  showNoFace(!faces.length && now - noFaceSince > 1200 && !(LV && !LV.done));
  // kiosk: nobody in front of the camera for 90 s → pause it (frees the CPU for analyses; the camera light goes off)
  if (!faces.length && noFaceSince && now - noFaceSince > IDLE_PAUSE_MS && !(LV && !LV.done)) {
    stop(); els.stage.dataset.state = 'error';
    msg('err', 'Camera <em>paused.</em>', 'Nobody was in view for a while, so the camera is resting.', { label: 'Wake', fn: () => start() });
    return;
  }

  // UI at ~15 Hz; graph every frame
  drawGraph(now);
  if (now - uiTick > 66) { uiTick = now; updateUI(now, faces.length); }
}

function showNoFace(on) {
  let el = els.stage?.querySelector('.live-noface');
  if (!on) { el?.remove(); return; }
  if (el) return;
  el = html('<div class="live-noface" role="status"><h2>Step into <em>frame.</em></h2><p>Look at the camera, about an arm’s length away.</p></div>');
  els.stage.appendChild(el);
}

function earOf(L, idx, W, H) {
  const p = idx.map((i) => [L[i].x * W, L[i].y * H]);
  const d = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  const h = d(p[0], p[3]);
  return h > 0 ? (d(p[1], p[5]) + d(p[2], p[4])) / (2 * h) : 0;
}

function pose(m) {
  if (!m?.data || m.data.length < 16) { P.ok = false; return; }
  const a = m.data; // column-major 4×4: r(i,j) = a[j*4 + i]
  const r00 = a[0], r10 = a[1], r20 = a[2], r21 = a[6], r22 = a[10];
  const deg = 180 / Math.PI;
  P.yaw = Math.asin(clamp(-r20, -1, 1)) * deg;      // + = subject turns to their left (nose to image-right)
  P.pitch = -Math.atan2(r21, r22) * deg;            // + = looking up
  P.roll = -Math.atan2(r10, r00) * deg;             // + = clockwise as seen in the mirror
  if (MOCK && window.__vxLive?.yawOffset) P.yaw += window.__vxLive.yawOffset; // automated checks only
  P.ok = true;
}

function blink(ear, now) {
  // Adaptive open-eye baseline: people's EAR differs, so we learn it.
  if (!E.closed && ear > E.base * 0.8) E.base = E.base * 0.96 + ear * 0.04;
  const lo = E.base * 0.7, hi = E.base * 0.82;
  const tooTurned = Math.abs(P.yaw) > 32 || Math.abs(P.pitch) > 28;
  if (!E.closed && ear < lo && !tooTurned) { E.closed = true; E.closedAt = now; }
  else if (E.closed && ear > hi) {
    E.closed = false;
    const dur = now - E.closedAt;
    if (dur >= 30 && dur <= 700) {
      E.count++; E.blinks.push(now);
      els.blinkN.textContent = E.count;
      els.blinkN.classList.remove('is-bump'); void els.blinkN.offsetWidth; els.blinkN.classList.add('is-bump');
    }
  }
}

function resetStats() {
  E.hist = []; E.blinks = []; E.count = 0; E.closed = false; E.firstFace = 0;
  els.blinkN.textContent = '0';
}

/* ------------------------------------------------------------------ drawing */
const COL = { mesh: 'rgba(170,205,255,0.30)', point: 'rgba(62,242,196,0.9)', oval: 'rgba(62,242,196,0.55)', eye: '#ffb020', iris: 'rgba(255,176,32,0.9)', bracket: '#3ef2c4' };

function strokeConn(g, L, conns, W, H) {
  g.beginPath();
  for (const c of conns) {
    const a = L[c.start], b = L[c.end];
    if (!a || !b) continue;
    g.moveTo(a.x * W, a.y * H); g.lineTo(b.x * W, b.y * H);
  }
  g.stroke();
}

function mirroredText(g, txt, x, y, align = 'left') {
  // canvas is mirrored by CSS; flip text back so it reads correctly
  g.save(); g.translate(x, y); g.scale(-1, 1); g.textAlign = align; g.fillText(txt, 0, 0); g.restore();
}

function drawFace(g, L, W, H, idx, n) {
  const s = Math.max(1, W / 1280);
  let x0 = 1, y0 = 1, x1 = 0, y1 = 0;
  for (let i = 0; i < 468; i++) { const p = L[i]; if (p.x < x0) x0 = p.x; if (p.x > x1) x1 = p.x; if (p.y < y0) y0 = p.y; if (p.y > y1) y1 = p.y; }
  if (meshOn) {
    g.lineWidth = 0.8 * s; g.strokeStyle = COL.mesh;
    strokeConn(g, L, FL.FACE_LANDMARKS_TESSELATION, W, H);
    g.lineWidth = 1.4 * s; g.strokeStyle = COL.oval;
    strokeConn(g, L, FL.FACE_LANDMARKS_FACE_OVAL, W, H);
    g.fillStyle = COL.point;
    const r = 2 * s;
    for (let i = 0; i < 468; i++) { const p = L[i]; g.fillRect(p.x * W - r / 2, p.y * H - r / 2, r, r); }
  }
  // eyes — what EAR measures
  g.lineWidth = 2 * s; g.strokeStyle = COL.eye;
  strokeConn(g, L, FL.FACE_LANDMARKS_LEFT_EYE, W, H);
  strokeConn(g, L, FL.FACE_LANDMARKS_RIGHT_EYE, W, H);
  if (meshOn) { g.lineWidth = 1.2 * s; g.strokeStyle = COL.iris; strokeConn(g, L, FL.FACE_LANDMARKS_LEFT_IRIS, W, H); strokeConn(g, L, FL.FACE_LANDMARKS_RIGHT_IRIS, W, H); }
  // EAR measurement struts on one eye (vertical pairs)
  if (idx === 0) {
    g.strokeStyle = 'rgba(255,176,32,0.7)'; g.lineWidth = 1 * s; g.setLineDash([3 * s, 3 * s]);
    for (const [a, b] of [[160, 144], [158, 153], [33, 133]]) { g.beginPath(); g.moveTo(L[a].x * W, L[a].y * H); g.lineTo(L[b].x * W, L[b].y * H); g.stroke(); }
    g.setLineDash([]);
  }
  // forensic brackets around the face
  const pxX0 = x0 * W - 18 * s, pxY0 = y0 * H - 24 * s, pxX1 = x1 * W + 18 * s, pxY1 = y1 * H + 14 * s;
  const len = Math.min(pxX1 - pxX0, pxY1 - pxY0) * 0.16;
  g.strokeStyle = n > 1 && idx > 0 ? 'rgba(232,230,223,0.8)' : COL.bracket; g.lineWidth = 2.5 * s;
  g.beginPath();
  g.moveTo(pxX0, pxY0 + len); g.lineTo(pxX0, pxY0); g.lineTo(pxX0 + len, pxY0);
  g.moveTo(pxX1 - len, pxY0); g.lineTo(pxX1, pxY0); g.lineTo(pxX1, pxY0 + len);
  g.moveTo(pxX0, pxY1 - len); g.lineTo(pxX0, pxY1); g.lineTo(pxX0 + len, pxY1);
  g.moveTo(pxX1 - len, pxY1); g.lineTo(pxX1, pxY1); g.lineTo(pxX1, pxY1 - len);
  g.stroke();
  // label (top-left on the mirrored screen = right edge in canvas space)
  g.font = `500 ${Math.round(15 * s)}px "IBM Plex Mono", monospace`;
  const label = `SUBJECT ${pad(idx + 1)} · LIVE`;
  g.fillStyle = 'rgba(4,6,10,0.75)';
  const tw = g.measureText(label).width;
  g.fillRect(pxX1 - tw - 14 * s, pxY0 - 28 * s, tw + 14 * s, 24 * s);
  g.fillStyle = COL.bracket;
  mirroredText(g, label, pxX1 - 7 * s, pxY0 - 11 * s, 'left');
  if (idx === 0 && E.value != null) {
    const et = `EAR ${E.value.toFixed(2)}`; const ew = g.measureText(et).width;
    g.fillStyle = 'rgba(4,6,10,0.75)'; g.fillRect(pxX0, pxY0 - 28 * s, ew + 14 * s, 24 * s);
    g.fillStyle = E.closed ? '#ffb020' : 'rgba(255,176,32,0.95)';
    mirroredText(g, et, pxX0 + 7 * s, pxY0 - 11 * s, 'right');
  }
}
const RATE_MIN_S = 30;
const fmtDeg = (v) => `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(0).padStart(2, '0')}°`;

function drawGraph(now = performance.now()) {
  const c = els.graph; if (!c) return;
  const dpr = Math.min(2, devicePixelRatio || 1);
  const Wc = c.clientWidth || 400, Hc = c.clientHeight || 120;
  if (c.width !== Math.round(Wc * dpr) || c.height !== Math.round(Hc * dpr)) { c.width = Math.round(Wc * dpr); c.height = Math.round(Hc * dpr); }
  const g = c.getContext('2d'); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, Wc, Hc);
  const span = 10000, ymax = 0.45;
  const X = (t) => Wc - ((now - t) / span) * Wc, Y = (v) => Hc - 6 - (clamp(v, 0, ymax) / ymax) * (Hc - 14);
  // grid
  g.strokeStyle = 'rgba(232,230,223,0.05)'; g.lineWidth = 1;
  for (let s = 0; s <= 10; s += 2) { const x = Math.round(Wc - (s / 10) * Wc) + 0.5; g.beginPath(); g.moveTo(x, 0); g.lineTo(x, Hc); g.stroke(); }
  // blink events
  for (const b of E.blinks) {
    if (now - b > span) continue;
    const x = X(b); g.fillStyle = 'rgba(255,176,32,0.16)'; g.fillRect(x - 5, 0, 10, Hc);
    g.fillStyle = '#ffb020'; g.fillRect(x - 0.5, 0, 1, 6);
  }
  // threshold
  if (E.hist.length) {
    const th = E.base * 0.7; g.strokeStyle = 'rgba(255,176,32,0.6)'; g.setLineDash([4, 4]);
    g.beginPath(); g.moveTo(0, Y(th)); g.lineTo(Wc, Y(th)); g.stroke(); g.setLineDash([]);
    g.fillStyle = 'rgba(255,176,32,0.9)'; g.font = '14px "IBM Plex Mono", monospace'; g.fillText('blink threshold', 6, Y(th) - 5);
  }
  // trace
  g.strokeStyle = '#3ef2c4'; g.lineWidth = 2; g.lineJoin = 'round'; g.beginPath();
  let pen = false;
  for (const p of E.hist) { if (p.v == null) { pen = false; continue; } const x = X(p.t), y = Y(p.v); if (!pen) { g.moveTo(x, y); pen = true; } else g.lineTo(x, y); }
  g.stroke();
  const last = E.hist[E.hist.length - 1];
  if (last?.v != null) { g.fillStyle = '#3ef2c4'; g.beginPath(); g.arc(X(last.t), Y(last.v), 3.5, 0, Math.PI * 2); g.fill(); }
  if (!E.hist.length) { g.fillStyle = 'rgba(232,230,223,0.5)'; g.font = '15px "IBM Plex Mono", monospace'; g.fillText('waiting for a face…', 10, Hc / 2 + 5); }
}

function updateUI(now, nFaces) {
  els.faces.textContent = nFaces;
  els.fps.textContent = fpsTimes.length > 1 ? Math.round(((fpsTimes.length - 1) * 1000) / (fpsTimes[fpsTimes.length - 1] - fpsTimes[0])) : '—';
  els.ear.textContent = E.value == null ? '—' : E.value.toFixed(3);
  const t = (now - cam0) / 1000;
  els.tc.textContent = `${pad(Math.floor(t / 3600))}:${pad(Math.floor((t / 60) % 60))}:${pad(Math.floor(t % 60))}`;
  // blink rate over the last 60 s of continuous face presence. People blink every 3–6 s, so anything shorter
  // than ~30 s is mostly noise: show "measuring" until then and only colour a low rate after that.
  if (E.firstFace && now - E.lastFace < 1500) {
    const winStart = Math.max(E.firstFace, now - 60000); const secs = (now - winStart) / 1000;
    if (secs >= RATE_MIN_S) {
      const n = E.blinks.filter((b) => b >= winStart).length; const rate = (n / secs) * 60;
      els.rate.textContent = rate.toFixed(0); els.rate.classList.remove('is-measuring');
      els.rate.style.color = rate < 8 ? 'var(--evidence)' : 'var(--bone)';
      els.rateMark.classList.add('is-on'); els.rateMark.style.left = `${clamp(rate / 40, 0, 1) * 100}%`;
    } else { els.rate.textContent = `measuring · ${Math.ceil(RATE_MIN_S - secs)} s`; els.rate.classList.add('is-measuring'); els.rate.style.color = 'var(--bone-faint)'; els.rateMark.classList.remove('is-on'); }
  } else { els.rate.textContent = '—'; els.rate.classList.remove('is-measuring'); els.rateMark.classList.remove('is-on'); }
  // pose
  const setPose = (el, v, k, sign) => {
    el.textContent = P.ok ? `${fmtDeg(v)}${k}` : '—';
    const dot = el.parentElement.querySelector('.pose-track i');
    dot.style.left = `${50 + clamp((sign * v) / 45, -1, 1) * 50}%`;
  };
  setPose(els.yaw, P.yaw, P.yaw >= 0 ? ' L' : ' R', -1);
  setPose(els.pitch, P.pitch, P.pitch >= 0 ? ' up' : ' dn', 1);
  setPose(els.roll, P.roll, '', 1);
}

/* ------------------------------------------------------------------ liveness
   Each run draws a fresh challenge: blink 2 or 3 times, turn left, turn right — in a random order.
   Turns are measured as a CHANGE of yaw from the visitor's own resting pose (captured when the check
   starts), so an off-axis webcam neither gives a step away nor makes it impossible. */
const NUM = ['', 'once', 'twice', 'three times'];
const TURN_DEG = 20;    // required change in yaw from the resting pose
const STEP_MS = 15000;
function makeSteps() {
  const blinks = 2 + Math.floor(Math.random() * 2);
  const steps = [
    { id: 'blink', n: blinks, label: `Blink ${NUM[blinks]}`, instr: `Blink <em>${NUM[blinks]}</em>`, sub: 'Natural blinks — the EAR graph will dip.' },
    { id: 'left', label: 'Turn left', instr: '<span class="lv-arrow l">←</span> Turn <em>left</em>', sub: 'Turn your head to your left, then hold.' },
    { id: 'right', label: 'Turn right', instr: 'Turn <em>right</em> <span class="lv-arrow r">→</span>', sub: 'Turn your head to your right, then hold.' },
  ];
  for (let i = steps.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [steps[i], steps[j]] = [steps[j], steps[i]]; }
  return steps;
}

function startLiveness() {
  if (!running) { toast('Start the camera first', 'warn'); return; }
  showNoFace(false);
  LV = { steps: makeSteps(), step: 0, t0: performance.now(), stepT0: performance.now(), blinkBase: E.count, hold: 0, done: false, rendered: -1,
    base: P.ok && Math.abs(P.yaw) < 30 ? P.yaw : null, baseN: P.ok ? 1 : 0 };
  els.btnCheck.innerHTML = '<span class="btn-ic">■</span>Stop check';
  renderLiveness();
}
function endLiveness(silent = false) {
  if (!LV) return;
  LV = null; els.lv.hidden = true; els.lv.innerHTML = '';
  els.stage.querySelector('.lv-pass')?.remove();
  els.btnCheck.innerHTML = '<span class="btn-ic">◎</span>Liveness check';
}

function renderLiveness(progress = 0, note = '') {
  const STEPS = LV.steps; const s = STEPS[LV.step];
  const C = 2 * Math.PI * 26;
  els.lv.hidden = false;
  if (LV.rendered !== LV.step) {
    LV.rendered = LV.step;
    els.lv.innerHTML = `<div class="lv-card ${LV.step ? 'is-next' : ''}">
      <div class="lv-head"><span class="label">Liveness check</span><span class="sec-note">step ${LV.step + 1} / ${STEPS.length} · random order</span></div>
      <ol class="lv-steps">${STEPS.map((x, i) => `<li class="lv-step ${i < LV.step ? 'is-done' : i === LV.step ? 'is-active' : ''}"><i>${i < LV.step ? '✓' : i + 1}</i>${x.label}</li>`).join('')}</ol>
      <div class="lv-now">
        <svg class="lv-ring" viewBox="0 0 60 60" aria-hidden="true"><circle class="bg" cx="30" cy="30" r="26"/><circle class="fg" cx="30" cy="30" r="26" style="stroke-dasharray:${C.toFixed(1)};stroke-dashoffset:${C.toFixed(1)}"/></svg>
        <div><div class="lv-instr">${s.instr}</div><div class="lv-sub">${s.sub}</div></div>
      </div>
      <p class="lv-note" aria-live="polite"></p>
      <p class="lv-why">Anti-spoofing: the steps and their order change every run, so a photo can’t do them and a pre-recorded video is unlikely to match.</p></div>`;
  }
  const fg = els.lv.querySelector('.lv-ring .fg'); if (fg) fg.style.strokeDashoffset = (C * (1 - progress)).toFixed(1);
  const n = els.lv.querySelector('.lv-note'); if (n) n.textContent = note;
}

let lvUi = 0;
function stepLiveness(now, nFaces) {
  const STEPS = LV.steps; const s = STEPS[LV.step];
  let progress = 0, note = '';
  // resting pose: average of the first few frames (only while nobody is mid-turn)
  if (nFaces === 1 && P.ok && LV.baseN < 8 && Math.abs(P.yaw) < 30 && (s.id === 'blink' || LV.baseN < 3)) {
    LV.base = LV.base == null ? P.yaw : (LV.base * LV.baseN + P.yaw) / (LV.baseN + 1); LV.baseN++;
  }
  if (nFaces === 0) note = 'face the camera';
  else if (nFaces > 1) note = 'one face at a time, please';
  else if (s.id === 'blink') progress = clamp((E.count - LV.blinkBase) / s.n, 0, 1);
  else if (LV.base == null || !P.ok) note = 'look at the camera';
  else {
    const d = P.yaw - LV.base;                 // + = turned to the subject's left
    const want = s.id === 'left' ? d : -d;
    progress = clamp(want / TURN_DEG, 0, 1);
    if (want > TURN_DEG) LV.hold += 1; else LV.hold = 0;
    if (LV.hold < 5 && progress >= 1) progress = 0.96;
  }
  if (progress >= 1) {
    LV.step++; LV.stepT0 = now; LV.hold = 0; LV.blinkBase = E.count;
    if (LV.step >= STEPS.length) return pass(now);
    renderLiveness(0); return;
  }
  if (now - LV.stepT0 > STEP_MS) return fail();
  const left = Math.ceil((STEP_MS - (now - LV.stepT0)) / 1000);
  if (!note && left <= 8) note = `${left} s left`;
  if (now - lvUi > 90) { lvUi = now; renderLiveness(progress, note); }
}

function pass(now) {
  LV.done = true;
  const secs = ((now - LV.t0) / 1000).toFixed(1);
  els.lv.hidden = true;
  const el = html(`<div class="lv-pass" role="status">
    <span class="lv-burst"></span><span class="lv-burst"></span><span class="lv-burst"></span>
    <div class="lv-pass-in"><span class="label">All steps done · ${secs} s</span><h2>Challenge passed.</h2>
    <p>A printed photo or a pre-recorded video can’t follow a random order like this. A real-time face-swap driven by a live person can, so banks combine challenges like this with other checks.</p></div></div>`);
  els.stage.querySelector('.lv-pass')?.remove();
  els.stage.appendChild(el);
  els.btnCheck.innerHTML = '<span class="btn-ic">◎</span>Run again';
  setTimeout(() => { if (LV?.done) { el.remove(); LV = null; els.btnCheck.innerHTML = '<span class="btn-ic">◎</span>Liveness check'; } }, 6500);
}
function fail() {
  const s = LV.steps[LV.step];
  LV.done = true; els.lv.hidden = true;
  const el = html(`<div class="lv-pass is-fail" role="status"><div class="lv-pass-in"><span class="label">Step timed out · ${s.label}</span><h2>Not verified.</h2><p>Make sure your whole face is in view and well lit, then try again.</p></div></div>`);
  els.stage.querySelector('.lv-pass')?.remove(); els.stage.appendChild(el);
  els.btnCheck.innerHTML = '<span class="btn-ic">◎</span>Try again';
  setTimeout(() => { if (LV?.done) { el.remove(); LV = null; els.btnCheck.innerHTML = '<span class="btn-ic">◎</span>Liveness check'; } }, 5000);
}

/* ------------------------------------------------------------------ capture */
async function capture() {
  if (!running) { toast('Camera is not running', 'warn'); return; }
  const v = els.video; const c = document.createElement('canvas');
  c.width = v.videoWidth; c.height = v.videoHeight;
  c.getContext('2d').drawImage(v, 0, 0); // un-mirrored: what the camera actually saw
  if (!reducedMotion()) { els.flash.classList.remove('is-on'); void els.flash.offsetWidth; els.flash.classList.add('is-on'); }
  const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.92));
  if (!blob) { toast('Could not capture a frame', 'warn'); return; }
  const d = new Date();
  const file = new File([blob], `live-capture-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}.jpg`, { type: 'image/jpeg' });
  setTimeout(() => emit('analyze-file', { file, meta: { origin: 'live', title: 'Live camera capture' } }), reducedMotion() ? 0 : 380);
}

// ?mock=1 only: lets the automated visual checks show the pass screen without a real person turning their head.
// yawOffset / blink() let a still test face exercise the turn and blink steps.
if (MOCK) window.__vxLive = { pass: () => { if (!LV) startLiveness(); if (LV) pass(performance.now()); }, yawOffset: 0, blink: () => { E.count++; E.blinks.push(performance.now()); } };
