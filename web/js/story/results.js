// Chapter 06 — renders OUR experiment from data/results.json (written by scripts/evaluate.py).
// Frame 1: the image experiment (held-out test only). Frame 2: voice + video + the honest caveats.
// If the file is missing or invalid it shows a "results pending" state. It never fabricates numbers:
// every figure on screen is read from the JSON or derived from it (n from the confusion matrix, etc.).
// Testing only: ?results=example loads data/results.example.json and stamps it EXAMPLE DATA.
import { $, $$, onceVisible, reduceMotion } from './util.js';

const gsap = window.gsap;
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => (typeof v === 'number' && isFinite(v) ? v : null);
const pct = (v) => (v == null ? null : v <= 1 ? v * 100 : v);
const fmtPct = (v, d = 1) => (v == null ? '—' : `${pct(v).toFixed(d)}%`);

// group ids written by scripts/evaluate.py → words a judge understands
const GROUPS = {
  gan_face: 'GAN faces', diffusion: 'AI scenes', diffusion_people: 'AI people', face_swap: 'Face-swaps',
  face: 'Real faces', scene: 'Real scenes', scene_people: 'Real people', phone: 'Phone photos',
};
const groupName = (g) => GROUPS[g] || String(g || '').replace(/_/g, ' ');
// test ids → short labels that fit one line in the per-test bar chart
const TESTS = {
  ai_generated: 'AI-image (pretrained)', ai_face: 'AI-face (pretrained)', ela: 'Error level (ELA)', noise: 'Noise residual',
  fft: 'Frequency (FFT)', jpeg_quant: 'JPEG tables', metadata: 'Metadata', ai_voice: 'AI-voice model',
  spectral_cutoff: 'Spectral cut-off', prosody: 'Pitch (prosody)', breath_silence: 'Breaths & silence',
  blink: 'Blink rate', landmark_jitter: 'Landmark jitter', temporal_flicker: 'Skin flicker',
};

// Exact (Clopper-Pearson) 95% interval for k successes out of n, by bisection on the binomial tail.
function binomTail(k, n, p, upper) { // upper: P(X >= k), else P(X <= k)
  let lp = 0, sum = 0;
  const lc = (i) => { let v = 0; for (let j = 1; j <= i; j++) v += Math.log((n - i + j) / j); return v; };
  for (let i = upper ? k : 0; upper ? i <= n : i <= k; i++) {
    lp = lc(i) + (i ? i * Math.log(p) : 0) + (n - i ? (n - i) * Math.log(1 - p) : 0);
    sum += Math.exp(lp);
  }
  return sum;
}
function ci95(k, n) {
  if (!n) return null;
  const solve = (f) => { let a = 0, b = 1; for (let i = 0; i < 60; i++) { const m = (a + b) / 2; if (f(m)) b = m; else a = m; } return (a + b) / 2; };
  const lo = k === 0 ? 0 : solve((p) => binomTail(k, n, p, true) >= 0.025);
  const hi = k === n ? 1 : solve((p) => binomTail(k, n, p, false) <= 0.025);
  return [lo, hi];
}
const rng = (c, d = 0) => (c ? `${(c[0] * 100).toFixed(0)}–${(c[1] * 100).toFixed(d)}%` : '—');

function cmCounts(cf) {
  const tp = num(cf?.tp), fp = num(cf?.fp), tn = num(cf?.tn), fn = num(cf?.fn);
  if ([tp, fp, tn, fn].some((v) => v == null)) return null;
  return { tp, fp, tn, fn, n: tp + fp + tn + fn, real: tn + fp, fake: tp + fn };
}

export async function initResults() {
  const body = $('#results-body'), ds = $('#res-dataset');
  const frame2 = $('#results-more'), body2 = $('#results-body2'), ds2 = $('#res-dataset2');
  const example = new URLSearchParams(location.search).get('results') === 'example';
  const url = example ? 'data/results.example.json' : 'data/results.json';
  let R = null;
  try {
    const r = await fetch(url, { cache: 'no-store' });
    if (r.ok) R = await r.json();
  } catch (e) { /* missing */ }
  const m = R && R.metrics;
  if (!R || !m || num(m.accuracy) == null) { pending(body, ds); hideFrame(frame2); return; }

  if (example) $$('.frame--results').forEach((f) => f.classList.add('is-example'));

  /* ───────── Frame 1 · images ───────── */
  const cm = cmCounts(R.confusion);
  const d = R.dataset || {};
  const det = R.image_details || {};
  const split = String(d.split || '');
  const q = (split.match(/JPEG\s*q\s*(\d+)/i) || [])[1];
  const laundered = det.condition === 'laundered' || /launder/i.test(split);
  const heldReal = cm ? cm.real : num(d.held_out_real), heldFake = cm ? cm.fake : num(d.held_out_fake);
  const total = (num(d.real) || 0) + (num(d.fake) || 0);
  ds.innerHTML = `
    <span class="scope__k">IMAGES · HELD-OUT TEST</span>
    <b class="scope__n">n = ${cm ? cm.n : '—'}</b>
    <span>${heldReal ?? '—'} real · ${heldFake ?? '—'} fake${total && cm && total > cm.n ? ` <i>(of ${total} images; the rest tuned the system)</i>` : ''}</span>
    ${laundered ? `<span class="scope__cond">re-saved as JPEG${q ? ` q${esc(q)}` : ''} · metadata stripped</span>` : ''}`;

  const tiles = [
    ['ACCURACY', pct(num(m.accuracy)), '%', 1, true, 'correct calls'],
    ['PRECISION', pct(num(m.precision)), '%', 1, false, cm ? `${cm.fp} of ${cm.real} false alarms` : 'flags that were right'],
    ['RECALL', pct(num(m.recall)), '%', 1, false, 'fakes caught'],
    ['F1 SCORE', pct(num(m.f1)), '%', 1, false, 'balance of the two'],
    ['ROC AUC', num(m.auc), '', 3, true, '1.000 = perfect ranking'],
    ['TIME / IMAGE', num(m.mean_latency_ms) == null ? null : m.mean_latency_ms / 1000, 's', 2, false, 'CPU, our dev laptop'],
  ];
  const roc = cleanRoc(R.roc);
  const tests = Array.isArray(R.per_test) ? R.per_test.filter((t) => num(t.auc) != null).map((t) => ({ ...t, name: TESTS[t.id] || t.name })).sort((a, b) => b.auc - a.auc) : [];
  const groups = Array.isArray(det.by_group) ? det.by_group.filter((g) => num(g.n) && num(g.flagged_pct) != null) : [];
  const flagged = (g) => Math.round((g.n * g.flagged_pct) / 100);
  const gFake = groups.filter((g) => g.label === 'fake'), gReal = groups.filter((g) => g.label === 'real');
  const chip = (g, bad) => `<li class="${bad ? 'is-bad' : ''}"><span>${esc(groupName(g.group))}</span><b>${flagged(g)}/${g.n}</b></li>`;
  // the out-of-distribution false-alarm check: stills of real people from research videos (not in the held-out set)
  const xv = det.external_video_stills && det.external_video_stills.real_as_photo;
  const xvChip = xv && num(xv.n) ? `<li class="${xv.flagged ? 'is-bad' : ''}"><span>Real video stills*</span><b>${xv.flagged}/${xv.n}</b></li>` : '';
  // the AI-image network's authors trained it on FFHQ + COCO: our 'face', 'scene', 'scene_people' real photos
  const inTrain = gReal.filter((g) => g.group !== 'phone').reduce((a, g) => a + g.n, 0);
  const ciAcc = cm ? ci95(cm.tp + cm.tn, cm.n) : null, ciFa = cm ? ci95(cm.fp, cm.real) : null;

  body.innerHTML = `
  <div class="res">
    <div class="res__metrics">
      ${tiles.map(([k, v, u, dec, key, desc]) => `<div class="metric ${key ? 'metric--key' : ''}"><span>${k}</span><b>${v == null ? '—' : `<span data-to="${v}" data-dec="${dec}">${(0).toFixed(dec)}</span>${u ? `<small>${u}</small>` : ''}`}</b><em>${desc}</em></div>`).join('')}
    </div>
    <div class="panel">
      <div class="panel__k"><span>CONFUSION MATRIX</span><b>${cm ? `n = ${cm.n}` : ''}</b></div>
      ${cm ? confusion(cm) : '<p class="mono">NO CONFUSION DATA</p>'}
    </div>
    <div class="panel roc">
      <div class="panel__k"><span>ROC CURVE</span><b>${num(m.auc) != null ? `AUC ${m.auc.toFixed(3)}` : ''}</b></div>
      ${rocSVG(roc, num(m.auc))}
    </div>
    <div class="panel">
      <div class="panel__k"><span>EACH TEST ALONE · AUC</span><b>0.5 = CHANCE</b></div>
      ${aucBars(tests.slice(0, 8), false, true)}
    </div>
    ${groups.length ? `<div class="res__groups">
      ${gFake.length ? `<div><span class="res__gk">FAKES FLAGGED</span><ul>${gFake.map((g) => chip(g, g.flagged_pct < 90)).join('')}</ul></div>` : ''}
      ${gReal.length ? `<div><span class="res__gk">REAL PHOTOS WRONGLY FLAGGED</span><ul>${gReal.map((g) => chip(g, g.flagged_pct > 0)).join('')}${xvChip}</ul></div>` : ''}
    </div>` : ''}
    <p class="res__method"><span class="m-long">Score above 50 = “synthetic”. No number was fitted on these files, but we looked at earlier runs while improving the system.${cm ? ` 95% ranges: accuracy ${rng(ciAcc)}, false-alarm rate ${rng(ciFa, 0)}.` : ''}
      <b>Caveat:</b> the pretrained AI-image network was trained on FFHQ and COCO photos${inTrain && cm ? `, the source of ${inTrain} of our ${cm.real} real test photos` : ''}, so “0 false alarms” is optimistic.${xvChip ? ` *Stills of real people from research videos.` : ''}</span><span class="m-short">${cm ? `95% ranges: accuracy ${rng(ciAcc)}, false alarms ${rng(ciFa, 0)}. ` : ''}<b>Caveat:</b> the pretrained network was trained on FFHQ/COCO${inTrain && cm ? ` (${inTrain} of our ${cm.real} real photos)` : ''}, so “0 false alarms” is optimistic.</span></p>
  </div>`;
  onceVisible(body, () => animate(body), 0.2);

  /* ───────── Frame 2 · voice, video, caveats ───────── */
  const A = R.audio && R.audio.metrics ? R.audio : null;
  const V = R.video && Array.isArray(R.video.clips) && R.video.clips.length ? R.video : null;
  if (!A && !V) { hideFrame(frame2); return; }
  const acm = A ? cmCounts(A.confusion) : null;
  const gen = A && Array.isArray(A.generalisation) ? A.generalisation.filter((g) => num(g.auc) != null) : [];
  const nImg = total || (cm ? cm.n : 0);
  const ad = (A && A.dataset) || {};
  const nAud = (num(ad.real) || 0) + (num(ad.fake) || 0) || (acm ? acm.n : 0);
  const onePt = cm && cm.n ? 100 / cm.n : null;
  ds2.innerHTML = `<span class="scope__k">SMALL, SCHOOL-SCALE TEST</span><span>${nImg ? `${nImg} images` : ''}${nAud ? ` · ${nAud} voice clips` : ''}${V ? ` · ${V.clips.length} videos` : ''}</span>${onePt ? `<span class="scope__cond">one image changing class moves accuracy ≈ ${onePt.toFixed(1)} points</span>` : ''}`;

  // Voice: lead with the 10 outside clips (fakes caught / reals cleared), then the leave-one-dataset-out
  // stress test; the same-datasets held-out number is shown last, as the optimistic reference it is.
  const X = A && A.external && Array.isArray(A.external.clips) && A.external.clips.length ? A.external : null;
  const fa = A && Array.isArray(A.generalisation) ? A.generalisation.filter((g) => num(g.auc) == null && num(g.false_alarm_rate) != null) : [];
  const panels = [];
  if (X) {
    const xc = X.clips.filter((c) => num(c.score) != null);
    const xf = xc.filter((c) => c.label === 'fake'), xr = xc.filter((c) => c.label !== 'fake');
    const caught = xf.filter((c) => c.score > 50).length, cleared = xr.filter((c) => c.score <= 50).length;
    const synth = xf.filter((c) => c.score > 65).length;
    panels.push(`<div class="panel panel--voice">
      <div class="panel__k"><span>VOICE · ${xc.length} OUTSIDE CLIPS</span><b>SPOT CHECK</b></div>
      <div class="vstat vstat--two">
        <div><span>FAKES CAUGHT</span><b class="is-synthetic"><span data-to="${caught}" data-dec="0">0</span><small>/${xf.length}</small></b></div>
        <div><span>REAL CLEARED</span><b class="is-authentic"><span data-to="${cleared}" data-dec="0">0</span><small>/${xr.length}</small></b></div>
      </div>
      ${clipRows(xc)}
      <p class="panel__note">${num(X.auc) != null ? `AUC ${X.auc.toFixed(2)}, but from only ${xr.length} real and ${xf.length} fake clips. ` : ''}New generators (F5-TTS, Chatterbox, WaveGlow, ASVspoof A10); speaker 260 (4 clips) and HiFi-GAN-type vocoders were in our tuning set. In the lab ${synth ? `only ${synth}` : 'none'} of the ${xf.length} fakes gets a “synthetic” verdict.</p>
    </div>`);
  }
  if (A) {
    const am = A.metrics;
    panels.push(`<div class="panel panel--gen">
      <div class="panel__k"><span>VOICE STRESS TEST · LEAVE A DATASET OUT</span><b>AUC</b></div>
      <p class="panel__lead">Tune without one whole dataset, then test on it. 0.5 = guessing.</p>
      ${aucBars([
        ...(num(am.auc) != null ? [{ name: `Same datasets, new speakers${num(am.accuracy) != null ? ` · ${fmtPct(am.accuracy)}` : ''}`, auc: am.auc, n: acm ? acm.n : null, ref: true }] : []),
        ...gen.map((g) => ({ name: `Left out: ${shortFamily(g.unseen_family)}`, auc: g.auc, n: g.n })),
      ], true)}
      ${fa.map((g) => `<p class="res__alarm"><b>${Math.round(pct(g.false_alarm_rate))}%</b><span>of real voices from <em>${esc(shortFamily(g.unseen_family).replace(/\s*\(real only\)/i, ''))}</em> were wrongly flagged when that dataset was left out${num(g.n) ? ` · n = ${g.n}` : ''}</span></p>`).join('')}
      <p class="panel__note is-warn">Voices, generators and microphones it has never heard are the hardest problem in deepfake detection.</p>
    </div>`);
  }
  if (V) {
    const vc = V.clips.filter((c) => num(c.score) != null);
    const vf = vc.filter((c) => c.label === 'fake'), vr = vc.filter((c) => c.label !== 'fake');
    const vCaught = vf.filter((c) => c.score > 50).length, vCleared = vr.filter((c) => c.score <= 50).length;
    const vSynth = vf.filter((c) => c.score > 65);
    const missed = vf.filter((c) => c.score <= 50).sort((a, b) => a.score - b.score);
    const gan = groups.find((g) => g.group === 'gan_face');
    panels.push(`<div class="panel panel--video">
      <div class="panel__k"><span>VIDEO · ${vc.length} RESEARCH CLIPS</span><b>SPOT CHECK</b></div>
      <div class="vstat vstat--two">
        <div><span>FAKES CAUGHT</span><b class="is-synthetic"><span data-to="${vCaught}" data-dec="0">0</span><small>/${vf.length}</small></b></div>
        <div><span>REAL CLEARED</span><b class="is-authentic"><span data-to="${vCleared}" data-dec="0">0</span><small>/${vr.length}</small></b></div>
      </div>
      ${clipRows(vc)}
      <p class="panel__note is-warn">In the lab ${vSynth.length === 1 ? `only one clip (${esc(clipLabel(vSynth[0]))}) gets` : `${vSynth.length} of ${vf.length} get`} a “synthetic” verdict. It missed ${missed.map((c) => `${esc(clipLabel(c))} (${Math.round(c.score)})`).join(', ')}. None of these is a fully AI-generated face${gan ? ` (it caught ${flagged(gan)}/${gan.n} GAN faces in photos)` : ''}.${num(V.mean_latency_ms) ? ` About ${(V.mean_latency_ms / 1000).toFixed(1)} s per clip.` : ''}</p>
    </div>`);
  }
  body2.innerHTML = `<div class="res res--more" style="--cols:${panels.length}">${panels.join('')}</div>
    ${R.generated && !example ? `<p class="res__run mono">RUN ${esc(fmtDate(R.generated))} · FULL METHOD, SOURCES &amp; NOTES IN data/results.json AND docs/</p>` : ''}`;
  onceVisible(body2, () => animate(body2), 0.2);
}

function hideFrame(f) {
  if (!f) return;
  f.hidden = true;
  f.removeAttribute('data-stop');
}

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const shortFamily = (s) => String(s || '').split(' (')[0];
function fmtDate(iso) {
  const dt = new Date(iso);
  if (isNaN(dt)) return String(iso).toUpperCase();
  return dt.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase();
}

function cleanRoc(roc) {
  return Array.isArray(roc) ? roc.filter((p) => Array.isArray(p) && p.length >= 2).map((p) => [+p[0], +p[1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]) : [];
}

function aucBars(list, warn = false, wide = false) {
  if (!list.length) return '<p class="mono">NO PER-TEST DATA</p>';
  const col = (a) => (a >= 0.8 ? 'var(--authentic)' : a >= 0.65 ? 'var(--scan)' : a >= 0.5 ? 'var(--evidence)' : 'var(--synthetic)');
  return `<div class="bars ${warn ? 'bars--gen' : ''} ${wide ? 'bars--wide' : ''}">${list.map((t) => `<div class="hbar ${t.ref ? 'is-ref' : ''}"><span>${esc(t.name || t.id)}${t.n && warn ? ` <i>· n = ${t.n}</i>` : ''}</span><i><b style="width:${Math.max(0.01, Math.min(1, t.auc)) * 100}%; background:${col(t.auc)}"></b></i><em>${t.auc.toFixed(2)}</em></div>`).join('')}</div>`;
}

// Short, human labels for the outside test clips. File names are never shown (some research clips depict celebrities).
const CLIP_LABELS = [
  [/^ljspeech_real/i, 'Real · LJSpeech'], [/^librispeech_real/i, 'Real · LibriSpeech'], [/^asvspoof\d*_la_bonafide/i, 'Real · ASVspoof'],
  [/^wavefake_hifigan/i, 'Vocoder · HiFi-GAN'], [/^wavefake_waveglow/i, 'Vocoder · WaveGlow'], [/^f5tts_clone/i, 'Clone · F5-TTS'],
  [/^chatterbox_clone/i, 'Clone · Chatterbox'], [/^asvspoof\d*_la_(a\d+)/i, 'TTS · ASVspoof $1'],
  [/^ffpp_original/i, 'Real · FF++'], [/^ffpp_deepfakes/i, 'Face-swap · FF++'], [/^ffpp_face2face/i, 'Reenact · Face2Face'],
  [/^ffpp_neuraltextures/i, 'Reenact · NeuralTex'], [/^dfd_original/i, 'Real · DFD'], [/^dfd_faceswap/i, 'Face-swap · DFD'],
  [/^celebdf_real/i, 'Real · Celeb-DF'], [/^celebdf_synthesis/i, 'Face-swap · Celeb-DF'], [/^wav2lip/i, 'Lip-sync · Wav2Lip'],
];
function clipLabel(c) {
  const f = String(c.file || '');
  for (const [re, lab] of CLIP_LABELS) { const m = f.match(re); if (m) return lab.replace('$1', (m[1] || '').toUpperCase()); }
  const g = String(c.group || '').replace(/^real recording$/i, '');
  return `${c.label === 'fake' ? 'Fake' : 'Real'}${g ? ` · ${g}` : ''}`;
}

// drawn marks: the mono font has no ✓/✗ glyphs (the fallback looks like a square-root sign)
const MARK_OK = '<svg class="mk" viewBox="0 0 12 12" aria-hidden="true"><path d="M1.5 6.5l3 3 6-7"/></svg>';
const MARK_NO = '<svg class="mk" viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 2.5l7 7M9.5 2.5l-7 7"/></svg>';

function clipRows(clips) {
  // one row per clip: bar = fused score 0–100, colour = what it really is, dashed line = the 50 cut-off
  const order = [...clips].sort((a, b) => (a.label === b.label ? (a.label === 'fake' ? b.score - a.score : a.score - b.score) : a.label === 'real' ? -1 : 1));
  return `<div class="clips" role="list">
    ${order.map((c) => {
      const fake = c.label === 'fake', ok = (c.score > 50) === fake, sc = Math.max(0, Math.min(100, c.score));
      return `<div class="clip ${fake ? 'is-fake' : 'is-real'} ${ok ? 'is-ok' : 'is-wrong'}" role="listitem" aria-label="${esc(clipLabel(c))}: score ${Math.round(c.score)}, ${ok ? 'correct' : 'wrong'}">
        <span>${esc(clipLabel(c))}</span><i><b style="width:${Math.max(1, sc)}%"></b></i><em>${Math.round(c.score)}</em><strong>${ok ? MARK_OK : MARK_NO}</strong></div>`;
    }).join('')}
    <div class="clip clip--ax mono" aria-hidden="true"><span></span><i><s>0</s><s>50</s><s>100</s></i><em></em><strong></strong></div>
  </div>
  <div class="vscale__leg clips__leg mono"><span><i class="sw sw--auth"></i>REAL</span><span><i class="sw sw--synth"></i>FAKE</span><span class="is-ok">${MARK_OK} CORRECT</span><span class="is-wrong">${MARK_NO} WRONG</span></div>`;
}

function confusion(c, small = false) {
  const mx = Math.max(1, c.tp, c.fp, c.tn, c.fn);
  const cell = (v, kind, lab) => `<div class="cm__c cm__c--${kind}" style="--a:${(0.25 + 0.75 * v / mx).toFixed(2)}"><b data-to="${v}" data-dec="0">0</b><span>${lab}</span></div>`;
  return `<div class="cm ${small ? 'cm--sm' : ''}">
    <span></span><span class="cm__h">FLAGGED FAKE</span><span class="cm__h">CALLED REAL</span>
    <span class="cm__h cm__h--row">REALLY FAKE</span>${cell(c.tp, 'tp', 'CAUGHT')}${cell(c.fn, 'err', 'MISSED')}
    <span class="cm__h cm__h--row">REALLY REAL</span>${cell(c.fp, 'err', 'FALSE ALARM')}${cell(c.tn, 'tn', 'CLEARED')}
  </div>`;
}

function rocSVG(pts, auc) {
  const W = 300, H = 220, L = 30, B = 26, T = 6, Rr = 8;
  const x = (v) => L + v * (W - L - Rr), y = (v) => H - B - v * (H - B - T);
  if (pts.length < 2) return '<p class="mono">NO ROC DATA</p>';
  const P = [[0, 0], ...pts, [1, 1]];
  const d = P.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join('');
  const area = `${d}L${x(1)} ${y(0)}L${x(0)} ${y(0)}Z`;
  const grid = [0.25, 0.5, 0.75].map((g) => `<line class="grid" x1="${x(g)}" y1="${y(0)}" x2="${x(g)}" y2="${y(1)}"/><line class="grid" x1="${x(0)}" y1="${y(g)}" x2="${x(1)}" y2="${y(g)}"/>`).join('');
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="ROC curve${auc != null ? `, area under curve ${auc.toFixed(3)}` : ''}">
    ${grid}
    <line class="ax" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(0)}"/><line class="ax" x1="${x(0)}" y1="${y(0)}" x2="${x(0)}" y2="${y(1)}"/>
    <line class="chance" x1="${x(0)}" y1="${y(0)}" x2="${x(1)}" y2="${y(1)}"/>
    <path class="area" d="${area}"/>
    <path class="curve" d="${d}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>
    <text x="${x(0.5)}" y="${H - 4}" text-anchor="middle">FALSE ALARM RATE</text>
    <text x="9" y="${y(0.5)}" text-anchor="middle" transform="rotate(-90 9 ${y(0.5)})">FAKES CAUGHT</text>
    <text x="${x(0.6)}" y="${y(0.5)}" class="t-chance">CHANCE</text>
    ${auc != null ? `<text class="auc" x="${x(0.42)}" y="${y(0.2)}">AUC ${auc.toFixed(3)}</text>` : ''}
  </svg>`;
}

function animate(root) {
  const d = reduceMotion ? 0.01 : 1;
  $$('[data-to]', root).forEach((el) => {
    const o = { v: 0 }, to = +el.dataset.to, dec = +el.dataset.dec;
    gsap.to(o, { v: to, duration: 1.8 * d, ease: 'expo.out', onUpdate: () => { el.textContent = o.v.toFixed(dec); }, onComplete: () => { el.textContent = to.toFixed(dec); } });
  });
  const curve = $('.curve', root);
  if (curve) gsap.to(curve, { strokeDashoffset: 0, duration: 2.2 * d, ease: 'power2.inOut', delay: 0.3 });
  if ($('.area', root)) gsap.from($$('.area', root), { opacity: 0, duration: 1.2 * d, delay: 1.4 * d });
  if ($('.hbar i b', root)) gsap.from($$('.hbar i b', root), { scaleX: 0, transformOrigin: 'left', duration: 1.4 * d, ease: 'expo.out', stagger: 0.06 * d, delay: 0.2 });
  if ($('.clip i b', root)) gsap.from($$('.clip i b', root), { scaleX: 0, transformOrigin: 'left', duration: 1.2 * d, ease: 'expo.out', stagger: 0.05 * d, delay: 0.3 });
}

function pending(body, ds) {
  ds.innerHTML = '<span class="scope__k">AWAITING</span><span>data/results.json</span>';
  body.innerHTML = `
  <div class="pending">
    <div class="pending__seal">RESULTS<br>PENDING</div>
    <div>
      <h3>The experiment is <em>still running.</em></h3>
      <p>We are testing VERITAS on a labelled set of real and AI-generated images, videos and voice clips. When the evaluation script writes <span class="mono">data/results.json</span>, this chapter fills in automatically — accuracy, confusion matrix, ROC curve and every test’s individual score. We don’t show numbers we haven’t measured.</p>
      <ul><li>ACCURACY</li><li>PRECISION · RECALL · F1</li><li>ROC AUC</li><li>CONFUSION MATRIX</li><li>PER-TEST AUC</li><li>TIME PER FILE</li></ul>
    </div>
  </div>`;
}
