// VERITAS lab — test detail overlay: large visual (heatmap blend slider over the original), the science, raw metrics.

import { $, esc, html, band, BAND_VAR, CATEGORY_LABEL, pad, loadImage } from './util.js';

let ov, state = null, lastFocus = null;

export function open(entry, idx) {
  ov ||= $('#overlay');
  if (!state) lastFocus = document.activeElement;
  state = { entry, idx, blend: state?.blend ?? 70 };
  render();
  ov.hidden = false;
  document.body.classList.add('has-overlay');
  requestAnimationFrame(() => ov.classList.add('is-open'));
  ov.querySelector('.ov-close')?.focus({ preventScroll: true });
  document.addEventListener('keydown', onKey, true);
}

export function close() {
  if (!ov || ov.hidden) return;
  ov.classList.remove('is-open');
  document.body.classList.remove('has-overlay');
  document.removeEventListener('keydown', onKey, true);
  setTimeout(() => { if (!ov.classList.contains('is-open')) { ov.hidden = true; ov.innerHTML = ''; } }, 220);
  state = null;
  lastFocus?.focus?.({ preventScroll: true });
}

function go(d) {
  const n = state.entry.report.tests.length;
  state.idx = (state.idx + d + n) % n;
  render();
  ov.querySelector(d > 0 ? '.ov-next' : '.ov-prev')?.focus({ preventScroll: true });
}

function onKey(e) {
  if (!state) return;
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); return; }
  const inRange = e.target?.type === 'range';
  if (!inRange && e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); go(1); }
  if (!inRange && e.key === 'ArrowLeft') { e.preventDefault(); e.stopPropagation(); go(-1); }
  if (e.key === 'Tab') { // focus trap
    const f = [...ov.querySelectorAll('button, input, [tabindex="0"]')].filter((x) => !x.disabled && x.offsetParent);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
}

function render() {
  const { entry, idx } = state; const r = entry.report; const tests = r.tests || [];
  const t = tests[idx]; if (!t) return close();
  const skipped = t.status === 'skipped' || t.status === 'error';
  const visualOnly = !skipped && t.score == null;
  const silent = !!(m0(t).one_sided && t.score != null && t.score < 50);   // one-sided test that did not fire
  const b = skipped || visualOnly || silent ? 'none' : band(t.score);
  const col = BAND_VAR[b];
  // Internal/debug fields go to the mono footer; the panel shows the measurements a judge can reason about.
  const HIDE = new Set(['ms', 'raw', 'model', 'detector', 'error', 'one_sided', 'z']);
  const m = t.metrics || {};
  const metrics = Object.entries(m).filter(([k, v]) => !HIDE.has(k) && v != null && v !== '');
  const hasProb = metrics.some(([k]) => isProb(k));
  const tech = [m.model && `model ${m.model}`, m.detector && `detector ${m.detector}`, m.ms != null && `${m.ms} ms`, m.error && `error: ${String(m.error).slice(0, 80)}`].filter(Boolean);
  const weightPct = t.weight != null ? `${Math.round(t.weight * 100)}%` : '—';
  const baseSrc = r.preview || null;

  ov.innerHTML = '';
  ov.appendChild(html(`
  <div class="ov-wrap" style="--c:${col}">
    <div class="ov-backdrop" data-close></div>
    <div class="ov-panel" data-band="${b}">
      <div class="ov-visual">
        <div class="ov-stage bracketed">
          <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
          <div class="ov-media"></div>
        </div>
        <div class="ov-blend" hidden>
          <span class="label">Original</span>
          <input type="range" min="0" max="100" step="1" value="${state.blend}" aria-label="Blend between original and heatmap" class="ov-range">
          <span class="label">${esc(visualWord(t))}</span>
          <span class="ov-blend-v mono">${state.blend}%</span>
          <span class="ov-snap">
            <button type="button" data-b="0">0</button><button type="button" data-b="50">50</button><button type="button" data-b="100">100</button>
          </span>
        </div>
      </div>

      <div class="ov-info">
        <p class="eyebrow"><span class="eyebrow-n">T·${pad(idx + 1)}</span> of ${pad(tests.length)} <span class="eyebrow-sep">/</span> ${esc(CATEGORY_LABEL[t.category] || t.category || '')}</p>
        <h2 class="ov-name" id="ov-title">${esc(t.name || t.id)}</h2>
        <div class="ov-score">
          <span class="ov-score-v">${skipped ? '—' : visualOnly ? 'Visual' : Math.round(t.score)}</span>
          <span class="ov-score-k">${skipped ? (t.status === 'error' ? 'test failed' : 'skipped · not applicable') : visualOnly ? 'evidence picture · not scored' : silent ? '/100 · below 50, so not counted (one-sided)' : '/100 synthetic likelihood'}</span>
          <span class="ov-bar"><i style="transform:scaleX(${skipped || visualOnly ? 0 : t.score / 100})"></i><b style="left:35%"></b><b style="left:65%"></b></span>
        </div>
        ${t.finding ? `<p class="ov-finding">${esc(t.finding)}</p>` : ''}
        ${t.explain ? `<h3 class="label ov-h">The science</h3><p class="ov-explain">${esc(t.explain)}</p>` : ''}
        ${metrics.length ? `<h3 class="label ov-h">Measurements</h3><dl class="ov-metrics">${metrics.map(([k, v]) => `<div><dt>${esc(metricName(k))}</dt><dd>${esc(isProb(k) && typeof v === 'number' ? fmtProb(v) : fmtVal(v))}</dd></div>`).join('')}</dl>
          ${hasProb ? '<p class="ov-mnote">“Raw P(fake)” is the network’s direct output. The score above is that output after calibration on our labelled test set, so the two numbers differ.</p>' : ''}` : ''}
        ${m.one_sided ? `<p class="ov-mnote ov-onesided"><b>One-sided test.</b> It counts toward the verdict only when it raises an alarm (score 50 or more); below 50 its weight is 0, because these networks were trained on face-swaps and call fully AI-generated faces “real”. 50 = the thresholds chosen on FaceForensics++ only: each network’s mean P(fake) over 8 frames is compared with its own threshold, the two are averaged, and the result is compared with the pair’s own FaceForensics++ threshold, which is lower. So the pair can fire even when each network on its own is slightly below its threshold.</p>` : ''}
        <p class="ov-foot mono">weight in verdict ${weightPct} · status ${esc(t.status || 'ok')} · id ${esc(t.id)}${tech.length ? ` · ${esc(tech.join(' · '))}` : ''}</p>
      </div>

      <button class="ov-close" type="button" aria-label="Close details (Esc)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5l14 14M19 5L5 19" stroke="currentColor" stroke-width="1.8"/></svg></button>
      <nav class="ov-nav" aria-label="Other tests">
        <button class="ov-prev btn btn-quiet" type="button"><span aria-hidden="true">←</span> Previous</button>
        <span class="ov-dots">${tests.map((x, i) => `<i class="${i === idx ? 'is-on' : ''}" style="--c:${BAND_VAR[x.status === 'skipped' || x.score == null || (m0(x).one_sided && x.score < 50) ? 'none' : band(x.score)]}"></i>`).join('')}</span>
        <button class="ov-next btn btn-quiet" type="button">Next <span aria-hidden="true">→</span></button>
      </nav>
    </div>
  </div>`));

  ov.querySelector('[data-close]').addEventListener('click', close);
  ov.querySelector('.ov-close').addEventListener('click', close);
  ov.querySelector('.ov-prev').addEventListener('click', () => go(-1));
  ov.querySelector('.ov-next').addEventListener('click', () => go(1));

  const media = ov.querySelector('.ov-media');
  if (t.visual) {
    mountVisual(media, t, baseSrc, r.kind);
  } else {
    media.appendChild(html(`<div class="ov-novis" style="--c:${col}">
      <span class="ov-novis-v">${skipped ? '—' : visualOnly ? '' : Math.round(t.score)}</span>
      <span class="label">${skipped ? 'Not run for this file' : 'This test reports numbers, not a picture'}</span></div>`));
  }
}

function m0(t) { return (t && t.metrics) || {}; }

function visualWord(t) {
  return { compression: 'Error map', noise: 'Noise residual', ai_model: 'Patch scores', frequency: 'Spectrum' }[t.category] || 'Heatmap';
}
const isProb = (k) => /^p_|(^|_)prob/.test(k);
function metricName(k) {
  if (isProb(k)) return k.replace(/^p_fake/, 'raw P(fake)').replace(/^p_/, 'raw P ').replace(/_/g, ' ');
  return k.replace(/_/g, ' ');
}
/** 0.004 -> "0.4 %", 0.73 -> "73 %" (probabilities shown as percentages, 1–2 significant figures) */
function fmtProb(v) {
  if (!(v >= 0 && v <= 1)) return fmtVal(v);
  const p = v * 100;
  if (p === 0) return '0 %';
  if (p < 0.1) return '< 0.1 %';
  if (p >= 99.5) return '> 99 %';
  return `${p < 10 ? p.toPrecision(1 + (p >= 1)) : Math.round(p)} %`;
}
function fmtVal(v) {
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : Math.abs(v) < 10 ? v.toFixed(3).replace(/0+$/, '').replace(/\.$/, '') : v.toFixed(1);
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (v && typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

async function mountVisual(media, t, baseSrc, kind) {
  const vis = await loadImage(t.visual).catch(() => null);
  if (!vis || !state) { media.innerHTML = '<p class="ev-na">Visual could not be decoded.</p>'; return; }
  let base = null;
  if (baseSrc && kind !== 'audio') base = await loadImage(baseSrc).catch(() => null);
  const ar = (im) => im.naturalWidth / im.naturalHeight;
  const blendable = base && Math.abs(ar(base) - ar(vis)) / ar(vis) < 0.03;
  if (!state) return;
  if (blendable) {
    const fig = html(`<figure class="ov-fig is-blend">
      <img class="ov-base" src="${esc(baseSrc)}" alt="Original">
      <img class="ov-heat" src="${esc(t.visual)}" alt="${esc(t.name)} visual" style="opacity:${state.blend / 100}">
    </figure>`);
    media.appendChild(fig);
    const blend = ov.querySelector('.ov-blend'); blend.hidden = false;
    const range = blend.querySelector('.ov-range'); const out = blend.querySelector('.ov-blend-v'); const heat = fig.querySelector('.ov-heat');
    const set = (v) => { state.blend = +v; range.value = v; heat.style.opacity = v / 100; out.textContent = `${v}%`; range.style.setProperty('--p', `${v}%`); };
    range.addEventListener('input', () => set(range.value));
    blend.querySelectorAll('[data-b]').forEach((b) => b.addEventListener('click', () => set(b.dataset.b)));
    set(state.blend);
  } else {
    media.appendChild(html(`<figure class="ov-fig"><img src="${esc(t.visual)}" alt="${esc(t.name)} visual"></figure>`));
  }
}
