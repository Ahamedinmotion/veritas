// VERITAS lab — CASE REPORT rendering (verdict, gauge, evidence with face brackets, video timeline,
// audio waveform/spectrogram, test cards, metadata).

import { esc, html, band, BAND_VAR, VERDICT_WORD, CATEGORY_LABEL, normVerdict, fmtBytes, fmtClock,
  shortHash, pad, tween, clamp, reducedMotion } from './util.js';

const KIND_WORD = { image: 'Image', video: 'Video', audio: 'Audio' };
const MEDIA = new Set();
const OBSERVERS = new Set();
/** Pause and release every player (and resize observer) created by previous reports. */
export function stopMedia() {
  for (const m of MEDIA) { try { m.pause(); m.removeAttribute('src'); m.load(); } catch { /* ignore */ } }
  MEDIA.clear();
  for (const o of OBSERVERS) o.disconnect();
  OBSERVERS.clear();
}
function observe(el, fn) { const o = new ResizeObserver(fn); o.observe(el); OBSERVERS.add(o); return o; }

/* ------------------------------------------------------------------ metadata flags
   The engine's metadata.flags mixes neutral facts ("Camera: Google Pixel 6", "Encoder: Lavf…") with real
   red flags ("No camera EXIF", "AI marker: …"). Flags may also arrive as { text, level } objects
   (level: info | warn | alert). Plain strings are classified here so that amber/red keep their meaning. */
const EDIT_SW = /photoshop|\bgimp\b|snapseed|picsart|canva|facetune|faceapp|pixlr|affinity|paint\.net|photopea|lightroom|capture one|luminar|meitu|remini/i;
function classifyFlag(text) {
  if (/^ai marker/i.test(text)) return 'alert';
  if (/^(no camera exif|no container metadata|exif present but no camera)/i.test(text)) return 'warn';
  if (/^software:/i.test(text)) return EDIT_SW.test(text) ? 'warn' : 'info';
  if (/^(camera:|captured|created|device tags:|gps location|c2pa|encoder:|text chunks:|sample rate|only the first|live webcam capture)/i.test(text)) return 'info';
  return 'warn'; // unknown strings keep the contract's original meaning: a red flag
}
export function normFlags(r, entry = {}) {
  return (r.metadata?.flags || []).map((x) => {
    let text = typeof x === 'string' ? x : String(x?.text ?? '');
    let level = typeof x === 'object' && ['info', 'warn', 'alert'].includes(x?.level) ? x.level : classifyFlag(text);
    if (entry.origin === 'live' && /^no camera exif/i.test(text)) { level = 'info'; text += ' · normal for a webcam capture'; }
    return { text, level };
  }).filter((f) => f.text);
}
const flagLi = (f) => `<li class="etag" data-level="${f.level}">${esc(f.text)}</li>`;

export function renderReport(entry, { fresh = false, onNew, onOpenTest } = {}) {
  const r = entry.report;
  const kind = r.kind || 'image';
  const score = clamp(Math.round(r.score ?? 0), 0, 100);
  const verdict = normVerdict(r.verdict, score);
  const tests = Array.isArray(r.tests) ? r.tests : [];
  const f = r.file || {};
  const flags = normFlags(r, entry);
  const redFlags = flags.filter((x) => x.level !== 'info');
  const conf = r.confidence == null ? null : clamp(r.confidence, 0, 1);

  // a one-sided test (the face-swap detector) below 50 is silent: it neither flags nor clears the file
  const ok = tests.filter((t) => t.status !== 'skipped' && t.status !== 'error' && t.score != null && !isSilent(t));
  const tally = {
    flag: ok.filter((t) => t.score > 65).length,
    mid: ok.filter((t) => t.score >= 35 && t.score <= 65).length,
    clear: ok.filter((t) => t.score < 35).length,
    skip: tests.filter((t) => t.status === 'skipped' || t.status === 'error').length,
  };

  const dims = f.width && f.height ? `${f.width}×${f.height}` : '';
  const dur = f.duration ? `${(+f.duration).toFixed(1)} s` : '';
  const fmtLine = [f.format, dims, dur, fmtBytes(f.size)].filter(Boolean).join(' · ');
  const elapsed = r.elapsed_ms != null ? `${(r.elapsed_ms / 1000).toFixed(2)} s` : '—';

  let truthHtml = '';
  if (entry.truth) {
    const said = verdict === 'synthetic' ? 'fake' : verdict === 'authentic' ? 'real' : 'unsure';
    const agree = said === entry.truth;
    truthHtml = `<div class="truth" data-agree="${said === 'unsure' ? 'unsure' : agree}">
      <span class="label">Ground truth</span><span class="truth-v">${entry.truth === 'fake' ? 'Fake' : 'Real'}</span>
      <span class="truth-x">${said === 'unsure' ? 'VERITAS was unsure on this one' : agree ? 'VERITAS got it right' : 'VERITAS got this one wrong — no detector is perfect'}</span></div>`;
  }

  const el = html(`
  <div class="rp ${fresh ? 'is-fresh' : ''}" data-verdict="${verdict}" data-kind="${kind}" style="--v:${BAND_VAR[verdict]}">
    <header class="rp-bar">
      <div class="rp-case"><span class="label">Case file</span><span class="rp-case-id">${esc(r.case_id || '—')}</span></div>
      <dl class="rp-meta">
        <div><dt>Exhibit</dt><dd class="rp-name" title="${esc(f.name || '')}">${esc(entry.title || f.name || 'untitled')}</dd></div>
        <div><dt>${esc(KIND_WORD[kind] || kind)}</dt><dd>${esc(fmtLine || '—')}</dd></div>
        <div><dt>SHA-256</dt><dd title="${esc(f.sha256 || '')}">${esc(shortHash(f.sha256, 8, 6))}</dd></div>
        <div><dt>Analysed in</dt><dd>${esc(elapsed)}</dd></div>
      </dl>
      <button class="btn btn-primary rp-new" type="button"><span class="btn-ic">＋</span>New case <kbd>N</kbd></button>
    </header>
    ${entry.saved ? savedRibbon(entry.saved) : ''}

    <div class="rp-body">
      <section class="rp-left" aria-label="Evidence">
        <div class="rp-evidence"></div>
      </section>

      <section class="rp-right">
        <div class="verdict">
          <div class="verdict-gauge">${gaugeSVG()}</div>
          <div class="verdict-main">
            <p class="eyebrow"><span class="eyebrow-n">§ 03</span> Verdict</p>
            <h2 class="verdict-word"><span>${VERDICT_WORD[verdict]}</span></h2>
            <p class="verdict-summary">${esc(r.summary || '')}</p>
          </div>
          <div class="verdict-stats">
            <div class="vs"><span class="label">Synthetic likelihood</span><span class="vs-v"><b class="vs-score">0</b><small>/100</small></span></div>
            <div class="vs"><span class="label">Confidence</span><span class="vs-v"><b>${conf == null ? '—' : Math.round(conf * 100) + '%'}</b></span>
              <span class="conf-bar" aria-hidden="true"><i style="--c:${conf ?? 0}"></i></span></div>
            <div class="vs vs-tally"><span class="label">Tests</span>
              <span class="tally">
                <span class="t-flag" title="Flag synthetic (&gt;65)"><i></i>${tally.flag} flag</span>
                <span class="t-mid" title="Inconclusive (35–65)"><i></i>${tally.mid} unsure</span>
                <span class="t-clear" title="Look authentic (&lt;35)"><i></i>${tally.clear} clear</span>
                ${tally.skip ? `<span class="t-skip"><i></i>${tally.skip} skipped</span>` : ''}
              </span></div>
          </div>
          ${redFlags.length || truthHtml ? `<div class="verdict-foot">
            ${redFlags.length ? `<ul class="flags flags-v" aria-label="Metadata warnings">${redFlags.map(flagLi).join('')}</ul>` : ''}
            ${truthHtml}</div>` : ''}
        </div>

        <div class="tests">
          <header class="sec-head"><h3 class="label"><span class="eyebrow-n">§ 04</span> Test battery</h3><span class="sec-note">${tests.length} tests · select a card for the science</span></header>
          <ol class="tests-grid">${tests.map((t, i) => testCard(t, i, tests.length)).join('')}</ol>
        </div>
      </section>
    </div>

    ${metaSection(r, flags)}
  </div>`);

  // Evidence column per kind
  const ev = el.querySelector('.rp-evidence');
  if (kind === 'video') ev.appendChild(videoEvidence(entry));
  else if (kind === 'audio') ev.appendChild(audioEvidence(entry));
  else ev.appendChild(imageEvidence(r));

  // Wire actions
  el.querySelector('.rp-new').addEventListener('click', () => onNew?.());
  el.querySelectorAll('.tc').forEach((c) => c.addEventListener('click', () => onOpenTest?.(+c.dataset.i)));

  // Animate gauge + number
  const g = el.querySelector('.gauge');
  const scoreEl = el.querySelector('.vs-score');
  // While the needle sweeps it takes each band's colour; at rest it shows the engine's verdict colour
  // (the engine decides on the unrounded score, so 65 can legitimately be "synthetic").
  const setG = (v, done = false) => { setGauge(g, v, verdict, done); scoreEl.textContent = Math.round(v); };
  if (fresh && !reducedMotion()) {
    setG(0);
    setTimeout(() => tween(1500, (e) => setG(score * e, e >= 1)), 380);
  } else setG(score, true);
  return el;
}

/* Showcase mode: this report was opened from a file the real engine wrote earlier (web/samples/lab/reports/). */
function savedRibbon(sv) {
  const d = sv.saved_at ? new Date(sv.saved_at) : null;
  const when = d && !isNaN(d) ? d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  return `<p class="rp-saved" role="note"><span class="rp-saved-k">Saved report from our engine</span>
    <span class="rp-saved-x">The real report VERITAS wrote for this exhibit${when ? `, recorded ${esc(when)}` : ''}${sv.where ? ` on ${esc(sv.where)}` : ''}, opened from a file.
    Analysing your own files needs the engine: the booth laptop or the online engine.</span></p>`;
}

/* ------------------------------------------------------------------ gauge */
const GA = { cx: 120, cy: 120, r: 92, a0: 135, a1: 405 };
const polar = (a, r) => [GA.cx + r * Math.cos((a * Math.PI) / 180), GA.cy + r * Math.sin((a * Math.PI) / 180)];
const arcPath = (v0, v1, r) => {
  const a = GA.a0 + (GA.a1 - GA.a0) * (v0 / 100), b = GA.a0 + (GA.a1 - GA.a0) * (v1 / 100);
  const [x0, y0] = polar(a, r), [x1, y1] = polar(b, r);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${b - a > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
};
function gaugeSVG() {
  let ticks = '';
  for (let v = 0; v <= 100; v += 5) {
    const a = GA.a0 + (GA.a1 - GA.a0) * (v / 100); const major = v % 25 === 0;
    const [x0, y0] = polar(a, major ? 70 : 74), [x1, y1] = polar(a, 79);
    ticks += `<line x1="${x0.toFixed(1)}" y1="${y0.toFixed(1)}" x2="${x1.toFixed(1)}" y2="${y1.toFixed(1)}" class="${major ? 'tk-maj' : 'tk'}"/>`;
  }
  const lbl = (v, txt) => { const a = GA.a0 + (GA.a1 - GA.a0) * (v / 100); const [x, y] = polar(a, 120); return `<text x="${x.toFixed(1)}" y="${(y + 6).toFixed(1)}" class="g-lbl">${txt}</text>`; };
  const L = (Math.PI * GA.r * (GA.a1 - GA.a0)) / 180;
  return `<svg class="gauge" viewBox="0 0 240 240" role="img" aria-label="Synthetic likelihood gauge">
    <path d="${arcPath(0, 100, GA.r)}" class="g-track"/>
    <path d="${arcPath(0, 35, 104)}" class="g-zone z-a"/>
    <path d="${arcPath(35, 65, 104)}" class="g-zone z-s"/>
    <path d="${arcPath(65, 100, 104)}" class="g-zone z-f"/>
    ${ticks}
    ${lbl(0, '0')}${lbl(35, '35')}${lbl(65, '65')}${lbl(100, '100')}
    <path d="${arcPath(0, 100, GA.r)}" class="g-val" style="stroke-dasharray:${L.toFixed(1)};stroke-dashoffset:${L.toFixed(1)}" data-len="${L.toFixed(1)}"/>
    <g class="g-needle"><circle r="7" class="g-dot"/><circle r="3" class="g-dot-in"/></g>
    <text x="120" y="122" class="g-num">0</text>
    <text x="120" y="156" class="g-sub">of 100</text>
  </svg>`;
}
function setGauge(svg, v, verdict, done = false) {
  const val = svg.querySelector('.g-val'); const L = +val.dataset.len;
  val.style.strokeDashoffset = (L * (1 - v / 100)).toFixed(1);
  const b = band(v);
  const col = BAND_VAR[done || b === 'none' ? verdict : b];
  val.style.stroke = col;
  const a = GA.a0 + (GA.a1 - GA.a0) * (v / 100); const [x, y] = polar(a, GA.r);
  const n = svg.querySelector('.g-needle'); n.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
  n.style.color = col;
  svg.querySelector('.g-num').textContent = Math.round(v);
}

/* ------------------------------------------------------------------ test cards */
const PIC_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1.5" y="2.5" width="13" height="11" rx="1" fill="none" stroke="currentColor"/><circle cx="5.5" cy="6.5" r="1.5" fill="currentColor"/><path d="M2 12l4-4 3 3 2-2 3.5 3.5" fill="none" stroke="currentColor"/></svg>';
/** One-sided tests (metrics.one_sided) only vote when they raise an alarm; below 50 they are shown in neutral grey. */
export const isSilent = (t) => !!(t && t.metrics && t.metrics.one_sided && t.score != null && t.score < 50);

function testCard(t, i, n) {
  const skipped = t.status === 'skipped' || t.status === 'error';
  const visualOnly = !skipped && t.score == null;
  const b = skipped || visualOnly || isSilent(t) ? 'none' : band(t.score);
  const sc = skipped ? '—' : visualOnly ? '' : Math.round(t.score);
  return `<li class="tc-li"><button type="button" class="tc ${skipped ? 'is-skipped' : ''} ${visualOnly ? 'is-visual' : ''}" data-i="${i}" data-band="${b}" style="--i:${i};--c:${BAND_VAR[b]};--s:${skipped || visualOnly ? 0 : t.score / 100}"
      aria-label="${esc(`${t.name}: ${skipped ? t.status : visualOnly ? 'visual' : `score ${sc} of 100`}. ${t.finding || ''}. Open details.`)}">
    <span class="tc-top"><span class="tc-n">T·${pad(i + 1)}</span><span class="tc-cat">${esc(CATEGORY_LABEL[t.category] || t.category || '')}</span>
      ${t.visual && !skipped ? `<span class="tc-pic" title="Opens with an evidence picture">${PIC_ICON}</span>` : ''}
      <span class="tc-score">${visualOnly ? '<span class="tc-vis">Visual</span>' : esc(sc)}</span></span>
    <span class="tc-name" title="${esc(t.name || t.id)}">${esc(t.name || t.id)}</span>
    <span class="tc-bar"><i></i></span>
    <span class="tc-find">${esc(skipped ? (t.finding || (t.status === 'error' ? 'This test failed to run.' : 'Not applicable to this file.')) : t.finding || '')}</span>
    <span class="tc-more" aria-hidden="true">Details →</span>
  </button></li>`;
}

/* ------------------------------------------------------------------ evidence: image */
function facesHTML(faces, what = '') {
  return (faces || []).map((fc, i) => {
    const [x, y, w, h] = (fc.box || [0, 0, 0, 0]).map(Number);
    const b = band(fc.score);
    return `<span class="face" style="left:${x * 100}%;top:${y * 100}%;width:${w * 100}%;height:${h * 100}%;--c:${BAND_VAR[b]};--i:${i}">
      <i class="fb tl"></i><i class="fb tr"></i><i class="fb bl"></i><i class="fb br"></i>
      <span class="face-tag">Face ${pad(i + 1)}${fc.score != null ? ` · ${what}<b>${Math.round(fc.score)}</b>` : ''}</span></span>`;
  }).join('');
}

function imageEvidence(r) {
  const faces = r.faces || [];
  return html(`<div class="ev ev-image">
    <div class="ev-head"><span class="label">Exhibit · image</span><span class="sec-note">${faces.length ? `${faces.length} face${faces.length > 1 ? 's' : ''} located · per-face synthetic score` : 'no faces located'}</span></div>
    <div class="ev-frame bracketed">
      <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
      ${r.preview ? `<figure class="ev-fig"><img src="${esc(r.preview)}" alt="The analysed image">${facesHTML(faces)}</figure>` : '<p class="ev-na">No preview returned by the engine.</p>'}
    </div>
  </div>`);
}

/* ------------------------------------------------------------------ evidence: video */
function videoEvidence(entry) {
  const r = entry.report; const f = r.file || {};
  const tl = (r.timeline || []).filter((p) => p && p.t != null && p.score != null);
  const kf = r.keyframes || [];
  const hasSwap = tl.some((p) => p.swap != null);
  const swSilentR = isSilent((r.tests || []).find((t) => t.id === 'face_swap'));
  const dur = +f.duration || (tl.length ? tl[tl.length - 1].t : 0) || 1;
  const box = html(`<div class="ev ev-video">
    <div class="ev-head"><span class="label">Exhibit · video</span><span class="sec-note">${tl.length} sampled frames${f.duration ? ` · ${(+f.duration).toFixed(1)} s` : ''}</span></div>
    <div class="ev-frame bracketed">
      <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
      <figure class="ev-fig ev-fig-video">
        <span class="ev-vbox">${r.preview ? `<img class="ev-poster" src="${esc(r.preview)}" alt="Poster frame">` : ''}${r.preview ? facesHTML(r.faces, 'face test ') : ''}</span>
      </figure>
      <button class="ev-play" type="button" aria-label="Play video"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor"/></svg></button>
    </div>
    <div class="tl-wrap">
      <div class="ev-head"><span class="label">${hasSwap ? 'Per-frame scores' : 'Face model · frame by frame'}</span><span class="sec-note">click to seek</span></div>
      ${hasSwap ? `<p class="tl-leg"><span class="tl-leg-line"><i></i>AI-face model · every sampled frame</span><span class="tl-leg-sw"><i></i>Face-swap detector · 8 frames${swSilentR ? ' · silent, so grey' : ''}</span></p>` : ''}
      <div class="tline" role="slider" tabindex="0" aria-label="Video timeline" aria-valuemin="0" aria-valuemax="${dur.toFixed(1)}" aria-valuenow="0"></div>
      <p class="tl-note">${hasSwap ? 'Two tests score single frames: the AI-face model (line) and the face-swap detector (diamonds).' : 'One test (the AI-face model) scored on each sampled frame.'} The verdict weighs all ${(r.tests || []).length || 6} tests together, so single frames can spike without the video being fake.</p>
    </div>
    ${kf.length ? `<div class="kf-wrap"><div class="ev-head"><span class="label">${kf.some((k) => k.by === 'face_swap') ? 'Most suspicious frames' : 'Frames the face model rated highest'}</span></div>
      <ol class="kf">${kf.map((k, i) => `<li><button type="button" class="kf-b" data-t="${+k.t}" style="--c:${k.by === 'face_swap' && swSilentR ? BAND_VAR.none : BAND_VAR[band(k.score)]}" title="${esc(KF_BY[k.by] || '')}">
        ${k.thumb ? `<img src="${esc(k.thumb)}" alt="">` : ''}<span class="kf-t">${fmtTenths(+k.t)}</span><span class="kf-s">${Math.round(k.score)}</span><span class="kf-n">K${i + 1}${k.by === 'face_swap' ? ' · swap' : ''}</span></button></li>`).join('')}</ol></div>` : ''}
  </div>`);

  const fig = box.querySelector('.ev-fig');
  const playBtn = box.querySelector('.ev-play');
  const tlEl = box.querySelector(".tline");
  let video = null; let playable = false;
  if (entry.url) {
    video = document.createElement('video');
    video.className = 'ev-video-el'; video.src = entry.url; video.playsInline = true; video.preload = 'auto'; video.muted = false;
    video.addEventListener('loadeddata', () => { playable = true; fig.classList.add('has-video'); });
    video.addEventListener('error', () => { playable = false; video.remove(); playBtn.hidden = true; });
    fig.prepend(video); MEDIA.add(video);
  } else playBtn.hidden = true;

  const draw = drawTimeline(tlEl, tl, kf, dur, r);
  const setPlayhead = () => { if (video) { draw.playhead(video.currentTime); tlEl.setAttribute('aria-valuenow', video.currentTime.toFixed(1)); } };
  let raf = 0;
  const loop = () => { setPlayhead(); if (video && !video.paused) raf = requestAnimationFrame(loop); };
  const seek = (t) => {
    if (!video || !playable) return;
    video.currentTime = clamp(t, 0, video.duration || dur);
    fig.classList.add('is-playing-vid');
    setPlayhead();
  };
  if (video) {
    video.addEventListener('play', () => { fig.classList.add('is-playing-vid'); playBtn.classList.add('is-hidden'); loop(); });
    video.addEventListener('pause', () => { playBtn.classList.remove('is-hidden'); cancelAnimationFrame(raf); setPlayhead(); });
    video.addEventListener('seeked', setPlayhead);
    video.addEventListener('click', () => (video.paused ? video.play() : video.pause()));
  }
  playBtn.addEventListener('click', () => { if (video && playable) video.play(); });
  tlEl.addEventListener('pointerdown', (e) => {
    const rect = tlEl.getBoundingClientRect(); const t = draw.timeAt(e.clientX - rect.left);
    if (t != null) seek(t);
  });
  tlEl.addEventListener('keydown', (e) => {
    if (!video) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); seek(video.currentTime + 1); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); seek(video.currentTime - 1); }
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); video.paused ? video.play() : video.pause(); }
  });
  box.querySelectorAll('.kf-b').forEach((b) => b.addEventListener('click', () => {
    seek(+b.dataset.t); video?.pause();
    draw.flash(+b.dataset.t);
  }));
  return box;
}

const KF_BY = { face_swap: 'Rated by the face-swap detector', ai_face: 'Rated by the AI-face model', ai_generated: 'Rated by the AI-frame detector' };

/** 3.96 -> "0:04.0" (round once, then split) */
function fmtTenths(t) {
  const r = Math.round((+t || 0) * 10) / 10;
  return `${fmtClock(Math.floor(r))}.${Math.round((r % 1) * 10) % 10}`;
}

function drawTimeline(host, pts, kf, dur, r) {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg'); svg.classList.add('tl-svg');
  host.appendChild(svg);
  let geom = null; let playT = 0;
  const pad = { l: 46, r: 14, t: 20, b: 28 };
  const render = () => {
    const W = Math.max(300, host.clientWidth), H = Math.max(120, host.clientHeight || 170);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('width', W); svg.setAttribute('height', H);
    const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
    const X = (t) => pad.l + (t / dur) * iw, Y = (s) => pad.t + ih - (s / 100) * ih;
    geom = { X, iw, W };
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)} ${Y(p.score).toFixed(1)}`).join('');
    const sw = pts.filter((p) => p.swap != null);
    // silent face-swap test (< 50): its diamonds are grey, so they never seem to vouch for the face
    const swSilent = isSilent((r.tests || []).find((t) => t.id === 'face_swap'));
    const swFill = (v) => (swSilent ? 'var(--bone-dim)' : BAND_VAR[band(v)]);
    const area = pts.length ? `${line}L${X(pts[pts.length - 1].t).toFixed(1)} ${Y(0)}L${X(pts[0].t).toFixed(1)} ${Y(0)}Z` : '';
    let xt = ''; const step = dur > 40 ? 10 : dur > 16 ? 4 : dur > 8 ? 2 : 1;
    for (let t = 0; t <= dur + 0.001; t += step) xt += `<text x="${X(t).toFixed(1)}" y="${H - 7}" class="tl-x">${fmtClock(t)}</text><line x1="${X(t).toFixed(1)}" x2="${X(t).toFixed(1)}" y1="${pad.t}" y2="${pad.t + ih}" class="tl-grid"/>`;
    // The trace is ONE test's raw per-frame output, so it is drawn in the neutral analysis colour, not the verdict's.
    const vcol = 'var(--scan)';
    svg.innerHTML = `
      <defs><linearGradient id="tlg" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${vcol}" stop-opacity=".35"/><stop offset="1" stop-color="${vcol}" stop-opacity="0"/></linearGradient></defs>
      <rect x="${pad.l}" y="${Y(100)}" width="${iw}" height="${Y(65) - Y(100)}" class="tl-band b-f"/>
      <rect x="${pad.l}" y="${Y(65)}" width="${iw}" height="${Y(35) - Y(65)}" class="tl-band b-s"/>
      <rect x="${pad.l}" y="${Y(35)}" width="${iw}" height="${Y(0) - Y(35)}" class="tl-band b-a"/>
      ${xt}
      <line x1="${pad.l}" x2="${pad.l + iw}" y1="${Y(65)}" y2="${Y(65)}" class="tl-th th-f"/>
      <line x1="${pad.l}" x2="${pad.l + iw}" y1="${Y(35)}" y2="${Y(35)}" class="tl-th th-a"/>
      <text x="${pad.l - 8}" y="${Y(100) + 5}" class="tl-y">100</text><text x="${pad.l - 8}" y="${Y(65) + 5}" class="tl-y">65</text>
      <text x="${pad.l - 8}" y="${Y(35) + 5}" class="tl-y">35</text><text x="${pad.l - 8}" y="${Y(0) + 5}" class="tl-y">0</text>
      ${kf.map((k, i) => `<g class="tl-kf" data-t="${k.t}"><line x1="${X(k.t)}" x2="${X(k.t)}" y1="${pad.t}" y2="${pad.t + ih}"/><text x="${X(k.t)}" y="${pad.t - 5}">K${i + 1}</text></g>`).join('')}
      <path d="${area}" fill="url(#tlg)" class="tl-area"/>
      <path d="${line}" class="tl-line" style="stroke:${vcol}"/>
      ${pts.map((p) => `<circle cx="${X(p.t).toFixed(1)}" cy="${Y(p.score).toFixed(1)}" r="3.2" class="tl-pt" style="fill:${BAND_VAR[band(p.score)]}"><title>${p.t.toFixed(1)} s · AI-face ${Math.round(p.score)}</title></circle>`).join('')}
      ${sw.length > 1 ? `<path d="${sw.map((p, i) => `${i ? 'L' : 'M'}${X(p.t).toFixed(1)} ${Y(p.swap).toFixed(1)}`).join('')}" class="tl-swline"/>` : ''}
      ${sw.map((p) => `<path d="M${X(p.t).toFixed(1)} ${(Y(p.swap) - 5).toFixed(1)}l5 5l-5 5l-5 -5z" class="tl-sw" style="fill:${swFill(p.swap)}"><title>${p.t.toFixed(1)} s · face-swap ${Math.round(p.swap)}${swSilent ? ' (test silent: below 50 overall)' : ''}</title></path>`).join('')}
      <g class="tl-ph" transform="translate(${X(playT)} 0)"><line y1="${pad.t - 4}" y2="${pad.t + ih + 2}"/><rect x="-4" y="${pad.t - 8}" width="8" height="8" rx="1"/></g>`;
    if (!pts.length) svg.insertAdjacentHTML('beforeend', `<text x="${W / 2}" y="${H / 2}" class="tl-empty">No per-frame scores returned</text>`);
  };
  render();
  let lastW = 0, lastH = 0, sized = false;
  observe(host, () => {
    const W = host.clientWidth, H = host.clientHeight;
    if (!W || (W === lastW && H === lastH)) return;
    if (sized) svg.classList.add('no-anim'); // later resizes redraw without replaying the intro animation
    render(); sized = true; lastW = W; lastH = H;
  });
  return {
    timeAt: (px) => (geom ? clamp(((px - pad.l) / geom.iw) * dur, 0, dur) : null),
    playhead: (t) => { playT = t; const ph = svg.querySelector('.tl-ph'); if (ph && geom) ph.setAttribute('transform', `translate(${geom.X(t).toFixed(1)} 0)`); },
    flash: (t) => { const g = [...svg.querySelectorAll('.tl-kf')].find((x) => Math.abs(+x.dataset.t - t) < 0.01); g?.classList.remove('is-flash'); void g?.getBBox?.(); g?.classList.add('is-flash'); },
  };
}

/* ------------------------------------------------------------------ evidence: audio */
function audioEvidence(entry) {
  const r = entry.report; const f = r.file || {};
  const wf = (r.waveform || []).map(Number).filter((x) => isFinite(x));
  const spec = (r.tests || []).find((t) => t.id === 'spectrogram' && t.visual);
  const box = html(`<div class="ev ev-audio">
    <div class="ev-head"><span class="label">Exhibit · audio</span><span class="sec-note">${esc([f.format, f.duration ? `${(+f.duration).toFixed(1)} s` : ''].filter(Boolean).join(' · '))}</span></div>
    <div class="au bracketed">
      <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
      <div class="au-top">
        <button class="au-play" type="button" aria-label="Play recording"><svg viewBox="0 0 24 24" aria-hidden="true"><path class="i-play" d="M8 5v14l11-7z"/><path class="i-pause" d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg></button>
        <div class="au-time mono"><span class="au-cur">0:00</span> <span class="dim">/ <span class="au-dur">${fmtClock(+f.duration || 0)}</span></span></div>
        <span class="sec-note">waveform · peak amplitude</span>
      </div>
      <canvas class="au-wave" aria-label="Waveform; click to seek"></canvas>
    </div>
    ${spec ? `<figure class="au-spec">
      <div class="ev-head"><span class="label">Spectrogram</span><span class="sec-note">frequency ↑ · time →</span></div>
      <div class="au-spec-img"><img src="${esc(spec.visual)}" alt="Spectrogram of the recording"></div>
    </figure>` : ''}
  </div>`);
  const canvas = box.querySelector('.au-wave');
  const audio = entry.url ? new Audio(entry.url) : null;
  const playBtn = box.querySelector('.au-play');
  let progress = 0;
  const draw = () => {
    const dpr = Math.min(2, devicePixelRatio || 1);
    const W = canvas.clientWidth || 600, H = canvas.clientHeight || 160;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    const g = canvas.getContext('2d'); g.scale(dpr, dpr); g.clearRect(0, 0, W, H);
    const N = wf.length || 1; const bw = W / N;
    g.fillStyle = 'rgba(232,230,223,.07)'; g.fillRect(0, H / 2 - 0.5, W, 1);
    for (let i = 0; i < wf.length; i++) {
      const x = i * bw; const h = Math.max(1.5, clamp(wf[i], 0, 1) * (H - 12));
      g.fillStyle = i / N <= progress ? '#6aa8ff' : 'rgba(232,230,223,.62)';
      g.fillRect(x + bw * 0.18, (H - h) / 2, Math.max(1, bw * 0.64), h);
    }
    if (!wf.length) { g.fillStyle = 'rgba(232,230,223,.5)'; g.font = '14px "IBM Plex Mono"'; g.fillText('No waveform returned', 12, H / 2); }
    if (progress > 0) { g.fillStyle = '#e8e6df'; g.fillRect(progress * W - 1, 0, 2, H); }
  };
  requestAnimationFrame(draw);
  observe(canvas, draw);
  if (audio) {
    let raf = 0;
    const tick = () => { progress = audio.duration ? audio.currentTime / audio.duration : 0; box.querySelector('.au-cur').textContent = fmtClock(audio.currentTime); draw(); if (!audio.paused) raf = requestAnimationFrame(tick); };
    audio.addEventListener('loadedmetadata', () => { box.querySelector('.au-dur').textContent = fmtClock(audio.duration); });
    audio.addEventListener('play', () => { playBtn.classList.add('is-playing'); tick(); });
    audio.addEventListener('pause', () => { playBtn.classList.remove('is-playing'); cancelAnimationFrame(raf); tick(); });
    audio.addEventListener('ended', () => { progress = 0; draw(); });
    audio.addEventListener('error', () => { playBtn.disabled = true; playBtn.title = 'This recording cannot be played in the browser'; });
    playBtn.addEventListener('click', () => (audio.paused ? audio.play() : audio.pause()));
    canvas.addEventListener('pointerdown', (e) => {
      if (!audio.duration) return;
      const rect = canvas.getBoundingClientRect(); audio.currentTime = clamp((e.clientX - rect.left) / rect.width, 0, 1) * audio.duration; tick();
    });
    MEDIA.add(audio);
  } else playBtn.disabled = true;
  return box;
}

/* ------------------------------------------------------------------ metadata */
function metaSection(r, flags) {
  const exif = r.metadata?.exif || {};
  const entries = Object.entries(exif).filter(([, v]) => v != null && v !== '');
  const val = (v) => (typeof v === 'object' ? JSON.stringify(v) : String(v));
  return `<section class="rp-meta-sec" aria-label="Metadata">
    <header class="sec-head"><h3 class="label"><span class="eyebrow-n">§ 05</span> Metadata &amp; provenance</h3><span class="sec-note">${entries.length} field${entries.length === 1 ? '' : 's'} found</span></header>
    <div class="meta-grid">
      ${entries.length ? `<table class="exif"><tbody>${entries.slice(0, 40).map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(val(v).slice(0, 120))}</td></tr>`).join('')}</tbody></table>`
        : '<p class="meta-empty">No metadata fields were found in this file. Real camera photos usually carry dozens; screenshots, re-saved and AI-generated files often carry none.</p>'}
      <div class="meta-flags"><span class="label">What the metadata says</span>
        ${flags.length ? `<ul class="flags">${flags.map(flagLi).join('')}</ul>
        ${new Set(flags.map((x) => x.level)).size > 1 ? '<p class="flag-key"><span data-level="info">fact</span><span data-level="warn">warning</span><span data-level="alert">AI marker</span></p>' : ''}` : ''}
        ${flags.some((x) => x.level !== 'info') ? '' : '<p class="meta-empty">No metadata red flags.</p>'}</div>
    </div>
  </section>`;
}
