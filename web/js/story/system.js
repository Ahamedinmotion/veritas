// Chapter 05 — the VERITAS pipeline, revealed in five states (pinned + scrubbed, or stepped).
import { $, $$ } from './util.js';

// REAL engine output for one clip: the Wav2Lip lip-sync we made from Google DFD actor 07 (web/data/results.json
// video.clips; actor 07 is in neither face-swap network's training data). The seven tests and base weights are the
// engine's real VIDEO pipeline (server/config.py DEFAULT_WEIGHTS["video"]); score + confidence come from the
// line-for-line port of server/fusion.py below (one-sided face-swap test included).
// Checked against the Python engine: these inputs -> score 70, confidence 0.49 (the engine reported 70; 14 before
// the face-swap detector was added). Teaching point: the AI-face model said "real" (9); the face-swap detector (95)
// carried the verdict. Blink and jitter sat at their floors.
const VIDEO = [
  { id: 'ai_face', name: 'AI-face model', ai: true, s: 9, w: 0.40 },
  { id: 'face_swap', name: 'Face-swap model', ai: true, s: 95, w: 1.25, oneSided: true },
  { id: 'ai_generated', name: 'AI-image model', ai: true, s: 14, w: 0.20 },
  { id: 'blink', name: 'Blink rate', s: 15, w: 0.14 },
  { id: 'landmark_jitter', name: 'Landmark jitter', s: 12, w: 0.10 },
  { id: 'temporal_flicker', name: 'Skin flicker', s: 35, w: 0.10 },
  { id: 'metadata', name: 'Container metadata', s: 40, w: 0.06 },
];
const GAIN = 1, BIAS = 0; // video has no fitted calibration in server/calibration.json → gain 1, bias 0
const T_SUS = 35, T_SYN = 65, AMPLIFY = 2;
const color = (s) => (s < T_SUS ? 'var(--authentic)' : s <= T_SYN ? 'var(--evidence)' : 'var(--synthetic)');

// Port of server/fusion.py fuse(): log-odds weighted mean, classic-test amplification, calibrated sigmoid; a
// one-sided test only votes at 50 or more, and can only raise the score (max of with / without it).
export function fuse(tests, gain = GAIN, bias = BIAS) {
  const logit = (s) => { const p = Math.min(0.985, Math.max(0.015, s / 100)); return Math.log(p / (1 - p)); };
  let active = tests.filter((t) => t.s != null && t.w > 0 && !(t.oneSided && t.s < 50)).map((t) => ({ ...t, eff: !t.ai && t.s > T_SYN ? t.w * (1 + (AMPLIFY * (t.s - T_SYN)) / (100 - T_SYN)) : t.w }));
  if (!active.length) return { score: 50, confidence: 0 };
  const combine = (items) => {
    const tot = items.reduce((a, t) => a + t.eff, 0);
    const Z = items.reduce((a, t) => a + (t.eff / tot) * logit(t.s), 0);
    return { score: Math.min(100, Math.max(0, 100 / (1 + Math.exp(-(gain * Z + bias))))), tot };
  };
  let { score, tot } = combine(active);
  const rest = active.filter((t) => !t.oneSided);
  if (rest.length && rest.length < active.length) {
    const r = combine(rest);
    if (r.score > score) ({ score, tot } = r), (active = rest);
  }
  const agree = 1 - active.reduce((a, t) => a + (Math.round((t.eff / tot) * 1000) / 1000) * Math.abs(t.s - score) / 100, 0);
  const decis = Math.abs(score - 50) / 50;
  let conf = (0.45 * agree + 0.55 * decis) * (active.length < 3 ? 0.75 : 1);
  conf = Math.min(0.99, Math.max(0.05, conf));
  return { score: Math.round(score), confidence: Math.round(conf * 100) / 100, weights: active.map((t) => t.eff / tot) };
}

export function initSystem() {
  const stage = $('#system-stage'), pipe = $('#pipe'), wires = $('#pipe-wires');
  const row = (d) => `<li class="${d.s == null ? 'is-skip' : ''}" data-s="${d.s ?? ''}"><span>${d.name}${d.ai ? ' <i class="det__ai">AI</i>' : ''}</span><i><b style="background:${d.s == null ? 'transparent' : color(d.s)}"></b></i><em>${d.s == null ? '—' : d.s}</em></li>`;
  $('#det-video').innerHTML = VIDEO.map(row).join('');
  const { score: fused, confidence } = fuse(VIDEO);
  const nTests = VIDEO.filter((d) => d.s != null).length;
  const cols = $$('.pipe__col', pipe);
  const gauge = $('#gauge'), needle = $('#gauge-needle'), gVal = $('#gauge-val'), gVer = $('#gauge-verdict');
  const NS = 'http://www.w3.org/2000/svg';
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  // wires between columns (recomputed on resize)
  const layout = () => {
    const pr = pipe.getBoundingClientRect();
    if (!pr.width) return;
    wires.setAttribute('viewBox', `0 0 ${pr.width} ${pr.height}`);
    wires.innerHTML = '';
    const R = (el) => { const r = el.getBoundingClientRect(); return { l: r.left - pr.left, r: r.right - pr.left, t: r.top - pr.top, b: r.bottom - pr.top, cy: (r.top + r.bottom) / 2 - pr.top }; };
    const add = (x1, y1, x2, y2, stage, pulse) => {
      const p = document.createElementNS(NS, 'path');
      const mx = (x1 + x2) / 2;
      p.setAttribute('d', `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`);
      p.dataset.stage = stage; p.id = `pw-${wires.childElementCount}`;
      wires.appendChild(p);
      if (pulse && !reduce) {
        const c = document.createElementNS(NS, 'circle'); c.setAttribute('r', 3); c.dataset.stage = stage;
        const am = document.createElementNS(NS, 'animateMotion'); am.setAttribute('dur', `${1.4 + Math.random() * 0.8}s`); am.setAttribute('repeatCount', 'indefinite'); am.setAttribute('begin', `${(Math.random() * 1.2).toFixed(2)}s`);
        const mp = document.createElementNS(NS, 'mpath'); mp.setAttribute('href', '#' + p.id);
        am.appendChild(mp); c.appendChild(am); wires.appendChild(c);
      }
    };
    const [c1, c2, c3, c4, c5] = cols.map(R);
    const sel = $('.pipe__files li.is-sel', cols[0]) || $('.pipe__files li', cols[0]);
    $$('.pipe__files li', cols[0]).forEach((li) => { const r = R(li); add(c1.r, r.cy, c2.l, c2.cy, 2, li === sel); });
    const dets = $$('#det-video li', cols[2]);
    dets.forEach((li, i) => { const r = R(li); add(c2.r, c2.cy, c3.l, r.cy, 3, i % 3 === 0); });
    dets.forEach((li, i) => { const r = R(li); add(c3.r, r.cy, c4.l, c4.cy, 4, i % 3 === 1); });
    add(c4.r, c4.cy, c5.l, c5.cy, 5, true);
    apply(state, true);
  };
  let state = -1;
  const apply = (n, force) => {
    if (n === state && !force) return;
    state = n;
    stage.dataset.state = n;
    cols.forEach((c) => { const s = +c.dataset.s; c.classList.toggle('is-lit', s <= n); c.classList.toggle('is-current', s === n); });
    $$('path, circle', wires).forEach((p) => p.classList.toggle('is-lit', +p.dataset.stage <= n));
    $$('.det li', pipe).forEach((li, i) => {
      const b = $('b', li);
      b.style.transitionDelay = n >= 3 ? `${i * 70}ms` : '0ms';
      b.style.transform = n >= 3 && li.dataset.s ? `scaleX(${li.dataset.s / 100})` : 'scaleX(0)';
    });
    if (n >= 5) {
      needle.style.transform = `rotate(${-90 + (fused / 100) * 180}deg)`;
      gVal.textContent = fused;
      gVer.textContent = `${fused > T_SYN ? 'SYNTHETIC' : fused >= T_SUS ? 'SUSPICIOUS' : 'AUTHENTIC'} · CONFIDENCE ${confidence.toFixed(2)}`;
      gauge.classList.toggle('is-synthetic', fused > T_SYN);
    } else {
      needle.style.transform = 'rotate(-90deg)';
      gVal.textContent = '0'; gVer.textContent = n >= 4 ? `FUSING ${nTests} TESTS…` : 'AWAITING EVIDENCE'; gauge.classList.remove('is-synthetic');
    }
  };
  apply(0);
  let raf = 0;
  addEventListener('resize', () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(layout); });
  return { layout, apply, fused, stepper: (_step, stop) => apply(stop ? stop.sub : 0) };
}
