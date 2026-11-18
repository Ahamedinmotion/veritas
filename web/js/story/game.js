// Chapter 03 — inline "Can you tell?" challenge from samples/game/manifest.json (owned by the lab).
// Never invents data: if the manifest is missing, the cards stay sealed and point to the lab.
import { $, $$, loadFace } from './util.js';
import { facePath } from './demos/facepaths.js';

const LETTERS = ['A', 'B', 'C'];
const verdictColor = (s) => (s < 35 ? 'var(--authentic)' : s <= 65 ? 'var(--evidence)' : 'var(--synthetic)');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function srcFor(file) {
  const f = String(file).replace(/^\.?\//, '');
  if (/^[a-z]+:/i.test(f)) return null;               // never load remote URLs
  if (f.startsWith('samples/')) return f;
  return 'samples/game/' + f;
}

// ai_score is the engine's fused 0–100 score (scripts/build_samples.py). Accept a 0–1 fraction only if
// it is clearly one (non-integer below 1) — an integer 1 means "1 out of 100", not 100%.
function score100(v) {
  v = Number(v);
  if (!isFinite(v)) return null;
  return Math.round(!Number.isInteger(v) && v < 1 ? v * 100 : v);
}

// Three cards that tell the story: a GAN face (the 48.2% study's kind of fake), a real face, and an AI scene.
// Prefer files the engine judged decisively, so the reveal teaches rather than confuses. Order: fake, real, fake.
function pick(items) {
  const norm = items.map((it, i) => ({ ...it, _i: i, label: String(it.label).toLowerCase(), _s: score100(it.ai_score), _src: String(it.source || '') }));
  const real = norm.filter((x) => x.label === 'real'), fake = norm.filter((x) => x.label === 'fake');
  const best = (list, test, dir) => list.filter(test).sort((a, b) => (dir * ((a._s ?? 50) - (b._s ?? 50))) || a._i - b._i)[0];
  const ok = (x) => (x.label === 'fake' ? (x._s ?? 0) > 65 : (x._s ?? 100) < 35);
  const used = new Set();
  const take = (x) => { if (x) used.add(x); return x; };
  const free = (x) => !used.has(x);
  const ganFace = take(best(fake, (x) => ok(x) && /stylegan|gan face|person/i.test(x._src), -1) || best(fake, ok, -1) || fake[0]);
  const realFace = take(best(real, (x) => ok(x) && /ffhq|face/i.test(x._src), 1) || best(real, ok, 1) || real[0]);
  const scene = take(best(fake, (x) => free(x) && ok(x) && !/stylegan|face-swap|face swap/i.test(x._src), -1) || best(norm, (x) => free(x) && ok(x), -1));
  const out = [ganFace, realFace, scene].filter(Boolean);
  for (const x of norm) { if (out.length >= 3) break; if (!out.includes(x)) out.push(x); }
  return out.slice(0, 3);
}

export async function initGame() {
  const root = $('#game'), scoreEl = $('#game-score');
  let items = [];
  try {
    const r = await fetch('samples/game/manifest.json', { cache: 'no-store' });
    if (r.ok) {
      const m = await r.json();
      items = Array.isArray(m) ? m : m.items || m.samples || m.images || m.rounds || [];
    }
  } catch (e) { /* offline or not created yet */ }
  items = items.filter((it) => it && it.file && /^(real|fake)$/i.test(String(it.label || '')) && srcFor(it.file));
  const frame = root.closest('[data-stop]');
  if (!items.length) {
    // nothing to reveal: no in-frame presenter steps (avoids three "dead" clicks), re-measure the stops
    if (frame) { frame.dataset.steps = '0'; window.VX?.presenter?.compute(); }
    let mesh = '';
    try { mesh = facePath(await loadFace(), { size: 100, cx: 50, cy: 55, scale: 0.46 }); } catch (e) { /* no mesh */ }
    root.innerHTML = LETTERS.map((L) => `
      <article class="gcard gcard--sealed gcard--pending">
        <div class="gcard__img"><span class="gcard__tag mono">EXHIBIT 03-${L}</span><svg viewBox="0 0 100 110" aria-hidden="true"><path class="mesh mesh--evid" d="${mesh}"/></svg><i class="scanline"></i><div class="tape"><span>SEALED · OPEN IN LAB</span></div></div>
        <div class="gcard__bar mono"><span>REAL OR FAKE?</span><span>—</span></div>
      </article>`).join('');
    scoreEl.textContent = 'THE CHALLENGE IMAGES LIVE IN THE LAB · TRY TO BEAT A COIN TOSS';
    return () => {};
  }
  const chosen = pick(items);
  root.innerHTML = chosen.map((it, k) => {
    const score = it._s;
    const fake = it.label === 'fake';
    return `
    <article class="gcard ${fake ? 'is-fake' : 'is-real'}" data-k="${k}">
      <div class="gcard__img">
        <span class="gcard__tag mono">EXHIBIT 03-${LETTERS[k]}</span>
        <img src="${esc(srcFor(it.file))}" alt="Exhibit 03-${LETTERS[k]}: a photo to judge — real or AI-generated?" loading="lazy" decoding="async">
        <span class="stamp gcard__stamp ${fake ? 'stamp--synth' : 'stamp--auth'}">${fake ? 'SYNTHETIC' : 'AUTHENTIC'}</span>
      </div>
      <div class="gcard__bar mono"><span class="gcard__q">REAL OR FAKE?</span><div class="gcard__btns"><button type="button" data-guess="real">REAL</button><button type="button" data-guess="fake">FAKE</button></div></div>
      <div class="gcard__reveal">
        ${score == null ? '' : `<div class="gcard__score mono"><span>VERITAS SCORE</span><i><b style="background:${verdictColor(score)}" data-w="${score}"></b></i><em>${score}<small>/100</small></em></div>`}
        ${it.hint ? `<p class="gcard__hint">${esc(it.hint)}</p>` : ''}
      </div>
    </article>`;
  }).join('');
  const cards = $$('.gcard', root);
  let guessed = 0, correct = 0;
  const reveal = (card, guess) => {
    if (card.classList.contains('is-revealed')) return;
    card.classList.add('is-revealed');
    const fake = card.classList.contains('is-fake');
    $$('button', card).forEach((b) => { b.disabled = true; if (b.dataset.guess === guess) b.classList.add('is-picked'); });
    const q = $('.gcard__q', card);
    if (guess) {
      guessed++;
      const ok = (guess === 'fake') === fake;
      if (ok) correct++;
      q.innerHTML = ok ? '<span class="is-authentic">YOU: CORRECT</span>' : '<span class="is-synthetic">YOU: FOOLED</span>';
    } else q.textContent = fake ? 'ANSWER: FAKE' : 'ANSWER: REAL';
    const b = $('.gcard__score b', card);
    if (b) requestAnimationFrame(() => { b.style.width = b.dataset.w + '%'; });
    if (guessed) scoreEl.innerHTML = `YOUR SCORE <b>${correct} / ${guessed}</b> · IN ONE 2022 STUDY PEOPLE SCORED 48.2% ON GAN FACES · THE LAB HAS MORE ROUNDS`;
  };
  root.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-guess]');
    if (b) reveal(b.closest('.gcard'), b.dataset.guess);
  });
  return (step) => {
    cards.forEach((c, i) => { if (i < step) reveal(c, null); });
  };
}
