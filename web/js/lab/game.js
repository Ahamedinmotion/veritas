// VERITAS lab — 03 SPOT THE FAKE · "Humans vs AI".
// 10 random images per round; visitor calls REAL or AI-GENERATED (← / →); reveal shows the truth, the
// engine's call (ai_score > 50 → fake, same rule as scripts/build_samples.py) and a hint.
// Booth scoreboard + local top-10 live in localStorage.
// Kiosk: 60 s idle → attract screen; Shift+R twice (never while typing) → reset the booth scoreboard;
// the previous board is kept once in localStorage under 'veritas.game.v1.bak'.

import { $, esc, html, toast, pad, isTyping, MOCK, params } from './util.js';
import * as api from './api.js';

const ROUND = 10;
const IDLE_MS = (Number(params.get('idle')) || 60) * 1000; // ?idle=SECONDS overrides (testing)
const LS_KEY = 'veritas.game.v1';
const AI_THRESH = 50;   // engine "says AI" when ai_score > AI_THRESH (matches build_samples.py accuracy)

let root;
let items = null;
let G = null;            // current round
let state = 'loading';
let active = false;
let idleTimer = 0;
let lastShiftR = 0;
let lockUntil = 0;

/* ------------------------------------------------------------------ storage */
const blank = () => ({ players: 0, hc: 0, ht: 0, ac: 0, at: 0, top: [] });
function load() {
  try { const j = JSON.parse(localStorage.getItem(LS_KEY)); return j && typeof j === 'object' ? { ...blank(), ...j } : blank(); }
  catch { return blank(); }
}
function save(s) { try { localStorage.setItem(LS_KEY, JSON.stringify(s)); } catch { /* storage unavailable: keep in memory only */ } }
let stats = load();

/* ------------------------------------------------------------------ lifecycle */
export function init() {
  root = $('#game');
  root.tabIndex = -1; // focus target so arrow keys never stay on the tab bar (Windows focuses clicked links)
  window.addEventListener('keydown', onKey);
  for (const ev of ['pointerdown', 'wheel', 'touchstart']) window.addEventListener(ev, () => active && bumpIdle(), { passive: true });
  let lastMove = 0; // mouse movement also counts as activity (throttled)
  window.addEventListener('pointermove', () => { const t = performance.now(); if (active && t - lastMove > 500) { lastMove = t; bumpIdle(); } }, { passive: true });
  boot();
}
function grabFocus() {
  const a = document.activeElement;
  if (!a || a === document.body || a.closest?.('.tabs') || !root.contains(a)) root.focus({ preventScroll: true });
}
export function enter() { active = true; bumpIdle(); if (state === 'intro') renderIntro(); grabFocus(); }
export function leave() { active = false; clearTimeout(idleTimer); }

async function boot() {
  setState('loading');
  root.innerHTML = '<div class="g-loading"><span class="live-spin"></span><p class="eyebrow">Loading the exhibits…</p></div>';
  items = await api.gameItems();
  if (!items || !items.length) return renderMissing();
  items = items.filter((x) => x.label === 'real' || x.label === 'fake' || x.label === 'ai');
  items.forEach((x) => { if (x.label === 'ai') x.label = 'fake'; });
  if (!items.length) return renderMissing();
  renderIntro();
}

function setState(s) { state = s; root.dataset.state = s; }

function bumpIdle() {
  clearTimeout(idleTimer);
  if (!active) return;
  idleTimer = setTimeout(() => {
    if (!active) return;
    if (state === 'play' || state === 'end') { G = null; renderIntro(true); }
    else if (state === 'intro') root.querySelector('.g-intro')?.classList.add('is-idle');
  }, IDLE_MS);
}

/* ------------------------------------------------------------------ keys */
function onKey(e) {
  if (!active || document.body.dataset.view !== 'game') return;
  bumpIdle();
  if (e.key === 'Shift' || e.key === 'Control' || e.key === 'Alt' || e.key === 'Meta') return; // modifier alone
  // Typing a name must never trigger kiosk shortcuts (e.g. "SRIRAM" typed with Shift held).
  if (isTyping(e) || e.target?.closest?.('.g-name') || e.ctrlKey || e.metaKey || e.altKey) {
    lastShiftR = 0;
    if (state === 'end' && e.key === 'Enter' && e.target?.id === 'g-name') { e.preventDefault(); saveName(); }
    return;
  }
  if (e.shiftKey && (e.key === 'R' || e.key === 'r')) {
    const now = performance.now();
    if (now - lastShiftR < 1800) { resetBoard(); lastShiftR = 0; } else { lastShiftR = now; }
    return;
  }
  lastShiftR = 0;
  if (e.key === 'f' || e.key === 'F') return;
  if (state === 'intro') {
    if (['Enter', ' ', 'ArrowLeft', 'ArrowRight'].includes(e.key)) { e.preventDefault(); startRound(); }
    return;
  }
  if (state === 'play') {
    if (!G.revealed) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); answer('real'); }
      if (e.key === 'ArrowRight') { e.preventDefault(); answer('fake'); }
    } else if (performance.now() > lockUntil && ['Enter', ' ', 'ArrowRight', 'ArrowLeft', 'n', 'N'].includes(e.key)) {
      e.preventDefault(); next();
    }
    if (e.key === 'Escape') { G = null; renderIntro(); }
    return;
  }
  if (state === 'end') {
    if (e.key === 'Enter' && performance.now() > lockUntil) { e.preventDefault(); startRound(); }
    if (e.key === 'Escape') renderIntro();
  }
}

function resetBoard() {
  try { if (stats.players || stats.top.length) localStorage.setItem(`${LS_KEY}.bak`, JSON.stringify(stats)); } catch { /* ignore */ }
  stats = blank(); save(stats);
  toast('Booth scoreboard reset (previous board kept as a backup)', 'ok');
  if (state === 'intro') renderIntro();
  else if (state === 'end') { const slot = root.querySelector('.g-board-slot'); if (slot) slot.innerHTML = boardHTML(); }
}

/* ------------------------------------------------------------------ screens */
function renderMissing() {
  setState('missing');
  root.innerHTML = `<div class="g-missing">
    <p class="eyebrow"><span class="eyebrow-n">§ 03</span> Spot the fake</p>
    <h1 class="display">Game data <em>not installed.</em></h1>
    <p class="lede">The labelled images for “Humans vs AI” live in <code>web/samples/game/</code> with a <code>manifest.json</code>. Run the sample-builder script on the development machine, copy the folder across, then reload this page.</p>
    <p class="sec-note">Analyze and Live cam work without it.</p>
    <div class="g-missing-actions"><button class="btn btn-primary" type="button" data-act="retry">Check again</button></div>
  </div>`;
  root.querySelector('[data-act="retry"]').addEventListener('click', boot);
}

function pct(c, t) { return t ? Math.round((c / t) * 100) : null; }

function boardHTML(highlight = null) {
  const h = pct(stats.hc, stats.ht), a = pct(stats.ac, stats.at);
  const top = stats.top.slice(0, 10);
  return `<div class="g-board">
    <header class="sec-head"><h2 class="label"><span class="eyebrow-n">◆</span> Booth scoreboard</h2><span class="sec-note">${stats.players} player${stats.players === 1 ? '' : 's'} so far</span></header>
    <div class="g-vs">
      <div class="g-vs-side is-h"><span class="label">Humans</span><span class="g-vs-n ${h == null ? 'is-empty' : ''}">${h == null ? 'awaiting players' : h}<small>${h == null ? '' : '%'}</small></span></div>
      <span class="g-vs-x">vs</span>
      <div class="g-vs-side is-a"><span class="label">AI · VERITAS</span><span class="g-vs-n ${a == null ? 'is-empty' : ''}">${a == null ? 'awaiting players' : a}<small>${a == null ? '' : '%'}</small></span></div>
    </div>
    <div class="g-vs-bars" aria-hidden="true"><span class="b-h" style="--w:${h ?? 0}%"></span><span class="b-a" style="--w:${a ?? 0}%"></span></div>
    <p class="sec-note g-vs-note">correct calls across every round played at this booth</p>
    <h3 class="label g-top-h">Top 10</h3>
    ${top.length ? `<ol class="g-top">${top.map((t, i) => `<li class="${highlight && t.id === highlight ? 'is-me' : ''}"><span class="g-rk">${pad(i + 1)}</span><span class="g-nm">${esc(t.name)}</span><span class="g-sc">${t.score}<small>/${t.n}</small></span><span class="g-tm">${(t.ms / 1000).toFixed(0)} s</span></li>`).join('')}</ol>`
      : '<p class="g-top-empty">No names yet — be the first on the board.</p>'}
  </div>`;
}

function renderIntro(fromIdle = false) {
  setState('intro');
  G = null;
  const pics = shuffle(items.slice()).slice(0, 12);
  root.innerHTML = '';
  root.appendChild(html(`<div class="g-intro ${fromIdle ? 'is-idle' : ''}">
    <div class="g-mosaic" aria-hidden="true">${pics.map((p, i) => `<span style="--i:${i}"><img src="${esc(p.src)}" alt="" loading="lazy" decoding="async"></span>`).join('')}</div>
    <div class="g-intro-main">
      <p class="eyebrow"><span class="eyebrow-n">§ 03</span> Spot the fake <span class="eyebrow-sep">/</span> Humans vs AI</p>
      <h1 class="g-title">Real photo,<br>or <em>AI?</em></h1>
      <p class="lede">${ROUND} images. Some are photographs; some were generated by AI. Make the call on each — then see how VERITAS did on the very same ${ROUND}.</p>
      <div class="g-cta">
        <button class="btn btn-primary btn-xl" type="button" data-act="start">Start the challenge <kbd>Enter</kbd></button>
        <span class="g-keys"><kbd>←</kbd> Real <span class="dim">·</span> AI-generated <kbd>→</kbd></span>
      </div>
      <p class="g-attract">Press any arrow key to play</p>
    </div>
    ${boardHTML()}
  </div>`));
  root.querySelector('[data-act="start"]').addEventListener('click', startRound);
  root.querySelector('.g-mosaic').addEventListener('click', startRound);
  bumpIdle();
  if (active) grabFocus();
}

/* ------------------------------------------------------------------ round */
function shuffle(a) { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; }

function pickRound() {
  const real = shuffle(items.filter((x) => x.label === 'real'));
  const fake = shuffle(items.filter((x) => x.label === 'fake'));
  const n = Math.min(ROUND, items.length);
  const half = Math.floor(n / 2);
  let pick = [...real.slice(0, half), ...fake.slice(0, n - half)];
  if (pick.length < n) {
    const rest = shuffle(items.filter((x) => !pick.includes(x)));
    pick = pick.concat(rest.slice(0, n - pick.length));
  }
  return shuffle(pick);
}

function startRound() {
  G = { list: pickRound(), i: 0, answers: [], t0: performance.now(), revealed: false, saved: false };
  setState('play');
  root.innerHTML = '';
  root.appendChild(html(`<div class="g-play">
    <div class="g-stage-wrap">
      <header class="g-top-bar">
        <span class="g-count mono"></span>
        <ol class="g-pips" aria-hidden="true">${G.list.map(() => '<li></li>').join('')}</ol>
        <span class="g-score mono"></span>
      </header>
      <figure class="g-stage bracketed">
        <span class="corner tl"></span><span class="corner tr"></span><span class="corner bl"></span><span class="corner br"></span>
        <img class="g-img" alt="">
        <span class="g-stamp" aria-hidden="true"></span>
        <figcaption class="g-cap mono"></figcaption>
      </figure>
    </div>
    <aside class="g-side" aria-live="polite"></aside>
  </div>`));
  show();
  grabFocus();
}

function preload(src) { const im = new Image(); im.decoding = 'async'; im.src = src; return im; }

function show() {
  const it = G.list[G.i];
  G.revealed = false;
  const img = root.querySelector('.g-img');
  const stage = root.querySelector('.g-stage');
  stage.classList.remove('is-revealed', 'is-real', 'is-fake');
  stage.classList.add('is-loading');
  img.onload = () => stage.classList.remove('is-loading');
  img.onerror = () => { stage.classList.remove('is-loading'); root.querySelector('.g-cap').textContent = 'image missing'; };
  img.src = it.src;
  img.alt = `Exhibit ${G.i + 1} of ${G.list.length}`;
  if (G.list[G.i + 1]) preload(G.list[G.i + 1].src);
  root.querySelector('.g-cap').textContent = `EXHIBIT ${pad(G.i + 1)}`;
  root.querySelector('.g-stamp').textContent = '';
  root.querySelector('.g-count').innerHTML = `Exhibit <b>${pad(G.i + 1)}</b> / ${pad(G.list.length)}`;
  updatePips();
  const side = root.querySelector('.g-side');
  side.innerHTML = '';
  side.appendChild(html(`<div class="g-ask">
    <p class="eyebrow"><span class="eyebrow-n">Q${pad(G.i + 1)}</span> Your call</p>
    <h2 class="g-q">Is this a real photo — or <em>AI‑generated?</em></h2>
    <div class="g-choices">
      <button class="g-choice is-real" type="button" data-a="real"><span class="g-key">←</span><span class="g-ct">Real photo</span><span class="g-cs">taken by a camera</span></button>
      <button class="g-choice is-fake" type="button" data-a="fake"><span class="g-key">→</span><span class="g-ct">AI-generated</span><span class="g-cs">made by a model</span></button>
    </div>
    <p class="g-tip">Look at hands, text, hair edges, reflections and backgrounds.</p>
  </div>`));
  side.querySelectorAll('.g-choice').forEach((b) => b.addEventListener('click', () => answer(b.dataset.a)));
}

function aiCall(it) { return (Number(it.ai_score) || 0) > AI_THRESH ? 'fake' : 'real'; }
const unsure = (it) => { const s = Number(it.ai_score) || 0; return s >= 35 && s <= 65; };

function answer(choice) {
  if (!G || G.revealed) return;
  const it = G.list[G.i];
  const ai = aiCall(it);
  const rec = { you: choice, truth: it.label, ai, ok: choice === it.label, aiOk: ai === it.label };
  G.answers.push(rec);
  G.revealed = true;
  lockUntil = performance.now() + 900;
  const stage = root.querySelector('.g-stage');
  stage.classList.add('is-revealed', it.label === 'fake' ? 'is-fake' : 'is-real');
  const stamp = root.querySelector('.g-stamp');
  stamp.textContent = it.label === 'fake' ? 'AI-generated' : 'Real photo';
  updatePips();
  const last = G.i === G.list.length - 1;
  const side = root.querySelector('.g-side');
  side.innerHTML = '';
  side.appendChild(html(`<div class="g-reveal ${rec.ok ? 'is-ok' : 'is-no'}">
    <p class="eyebrow"><span class="eyebrow-n">Q${pad(G.i + 1)}</span> ${rec.ok ? 'Correct' : 'Incorrect'}</p>
    <h2 class="g-res">${rec.ok ? 'Correct.' : 'Not quite.'}</h2>
    <dl class="g-facts">
      <div><dt>Truth</dt><dd class="${it.label === 'fake' ? 'is-synthetic' : 'is-authentic'}">${it.label === 'fake' ? 'AI-generated' : 'Real photo'}</dd></div>
      <div><dt>You said</dt><dd>${choice === 'fake' ? 'AI-generated' : 'Real photo'} <span class="g-mark ${rec.ok ? 'ok' : 'no'}">${rec.ok ? '✓' : '✗'}</span></dd></div>
      <div><dt>VERITAS said</dt><dd>${ai === 'fake' ? 'AI-generated' : 'Real photo'} <span class="g-ai mono">score ${Math.round(Number(it.ai_score) || 0)}${unsure(it) ? ' · unsure zone' : ''}</span> <span class="g-mark ${rec.aiOk ? 'ok' : 'no'}">${rec.aiOk ? '✓' : '✗'}</span></dd></div>
      ${it.source ? `<div><dt>Source</dt><dd class="g-src">${esc(it.source)}</dd></div>` : ''}
    </dl>
    ${it.hint ? `<p class="g-hint"><span class="label">Tell-tale</span>${esc(it.hint)}</p>` : ''}
    <button class="btn btn-primary btn-xl g-next" type="button">${last ? 'See results' : 'Next exhibit'} <kbd>Enter</kbd></button>
  </div>`));
  side.querySelector('.g-next').addEventListener('click', next);
  setTimeout(() => side.querySelector('.g-next')?.focus({ preventScroll: true }), 50);
}

function next() {
  if (!G) return;
  if (G.i >= G.list.length - 1) return finish();
  G.i++;
  show();
}

function updatePips() {
  const pips = root.querySelectorAll('.g-pips li');
  pips.forEach((p, i) => {
    p.className = '';
    const a = G.answers[i];
    if (a) p.classList.add(a.ok ? 'ok' : 'no');
    else if (i === G.i) p.classList.add('cur');
  });
  const you = G.answers.filter((a) => a.ok).length, ai = G.answers.filter((a) => a.aiOk).length;
  root.querySelector('.g-score').innerHTML = `You <b>${you}</b> <span class="dim">·</span> VERITAS <b>${ai}</b>`;
}

/* ------------------------------------------------------------------ end */
function finish() {
  const n = G.answers.length;
  const you = G.answers.filter((a) => a.ok).length;
  const ai = G.answers.filter((a) => a.aiOk).length;
  G.ms = performance.now() - G.t0;
  stats.players += 1; stats.hc += you; stats.ht += n; stats.ac += ai; stats.at += n;
  save(stats);
  setState('end');
  lockUntil = performance.now() + 1200;
  const head = you > ai ? 'You beat the <em>machine.</em>' : you < ai ? 'The machine wins <em>this round.</em>' : 'Dead <em>heat.</em>';
  const sub = you > ai ? 'Human intuition still has an edge — but detectors improve every year.' : you < ai ? 'Modern fakes fool people. Forensic tools look at evidence our eyes can’t see.' : 'Neither side could separate every real photo from every fake.';
  root.innerHTML = '';
  root.appendChild(html(`<div class="g-end">
    <div class="g-end-main">
      <p class="eyebrow"><span class="eyebrow-n">§ 03</span> Results <span class="eyebrow-sep">/</span> ${(G.ms / 1000).toFixed(0)} s</p>
      <h1 class="g-end-h">${head}</h1>
      <p class="lede">${sub}</p>
      <div class="g-duel">
        <div class="g-duel-side is-h"><span class="label">You</span><span class="g-duel-n">${you}<small>/${n}</small></span></div>
        <div class="g-duel-side is-a"><span class="label">VERITAS</span><span class="g-duel-n">${ai}<small>/${n}</small></span></div>
      </div>
      <ol class="g-recap">${G.list.map((it, i) => { const a = G.answers[i]; return `<li class="${it.label === 'fake' ? 'is-fake' : 'is-real'}" style="--i:${i}">
        <span class="g-rthumb"><img src="${esc(it.src)}" alt=""></span>
        <span class="g-rtruth">${it.label === 'fake' ? 'AI' : 'Real'}</span>
        <span class="g-rmarks"><i class="${a.ok ? 'ok' : 'no'}" title="You">${a.ok ? '✓' : '✗'}</i><i class="${a.aiOk ? 'ok' : 'no'} ai" title="VERITAS">${a.aiOk ? '✓' : '✗'}</i></span></li>`; }).join('')}</ol>
      <p class="sec-note g-recap-key">top mark: you · bottom mark: VERITAS</p>
    </div>
    <div class="g-end-side">
      <form class="g-name" autocomplete="off">
        <label class="label" for="g-name">Put your name on the board <span class="dim">(optional)</span></label>
        <div class="g-name-row"><input id="g-name" name="name" maxlength="14" placeholder="YOUR NAME" spellcheck="false" autocomplete="off"><button class="btn btn-ghost" type="submit">Save</button></div>
      </form>
      <div class="g-board-slot">${boardHTML()}</div>
      <div class="g-end-actions">
        <button class="btn btn-primary btn-xl" type="button" data-act="again">Play again <kbd>Enter</kbd></button>
        <button class="btn btn-quiet" type="button" data-act="done">Done <kbd>Esc</kbd></button>
      </div>
    </div>
  </div>`));
  root.querySelector('.g-name').addEventListener('submit', (e) => { e.preventDefault(); saveName(); });
  root.querySelector('[data-act="again"]').addEventListener('click', startRound);
  root.querySelector('[data-act="done"]').addEventListener('click', () => renderIntro());
  root.querySelector('[data-act="again"]').focus({ preventScroll: true });
}

function saveName() {
  if (!G || G.saved) return;
  const input = $('#g-name');
  const name = (input?.value || '').replace(/[^\p{L}\p{N} ._-]/gu, '').trim().slice(0, 14);
  if (!name) { input?.focus(); toast('Type a name first (or just press Play again)', 'warn'); return; }
  const n = G.answers.length; const score = G.answers.filter((a) => a.ok).length;
  const entry = { id: Date.now().toString(36), name: name.toUpperCase(), score, n, ms: Math.round(G.ms), ts: Date.now() };
  stats.top.push(entry);
  stats.top.sort((a, b) => b.score / b.n - a.score / a.n || a.ms - b.ms || a.ts - b.ts);
  stats.top = stats.top.slice(0, 10);
  save(stats);
  G.saved = true;
  const rank = stats.top.findIndex((t) => t.id === entry.id);
  root.querySelector('.g-board-slot').innerHTML = boardHTML(entry.id);
  root.querySelector('.g-name').innerHTML = `<p class="g-saved">${rank >= 0 ? `Saved — you’re <b>#${rank + 1}</b> on the board.` : 'Saved — not quite top 10 this time.'}</p>`;
  root.querySelector('[data-act="again"]').focus({ preventScroll: true });
}

if (MOCK) window.__vxGame = { reset: resetBoard };
