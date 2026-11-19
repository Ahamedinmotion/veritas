// VERITAS lab — bootstrap: tabs/router, engine status light, fullscreen, kiosk niceties.

import { $, $$, MOCK, isTyping, emit, on, pad, toast } from './util.js';
import * as engine from './engine.js';
import * as analyze from './analyze.js';

const VIEWS = ['analyze', 'live', 'game'];
const lazy = { live: () => import('./live.js'), game: () => import('./game.js') };
const mods = { analyze };
let current = null;

/* ------------------------------------------------------------------ router */
async function getMod(v) {
  if (!mods[v]) {
    const m = await lazy[v]();
    m.init?.();
    mods[v] = m;
  }
  return mods[v];
}

async function show(v) {
  if (v === current) return;
  const prev = current;
  current = v;
  document.body.dataset.view = v;
  for (const t of $$('.tab')) {
    const on = t.dataset.tab === v;
    t.classList.toggle('is-active', on);
    t.setAttribute('aria-selected', String(on));
    t.tabIndex = on ? 0 : -1;
  }
  for (const s of $$('.view')) s.hidden = s.id !== `view-${v}`;
  moveInk();
  updateBanner();
  if (prev && mods[prev]) mods[prev].leave?.();
  const m = await getMod(v);
  if (current === v) m.enter?.();
  document.title = `VERITAS · ${{ analyze: 'Analyze', live: 'Live cam', game: 'Spot the fake' }[v]}`;
}

function route() {
  const h = location.hash.replace('#', '').toLowerCase();
  show(VIEWS.includes(h) ? h : 'analyze');
}

function moveInk() {
  const ink = $('.tab-ink'); const a = $('.tab.is-active');
  if (!ink || !a) return;
  const nav = a.parentElement.getBoundingClientRect(); const r = a.getBoundingClientRect();
  ink.style.transform = `translateX(${r.left - nav.left}px)`;
  ink.style.width = `${r.width}px`;
}

/* ------------------------------------------------------------------ engine status
   The chip says which engine answers: this laptop, the online engine (a free shared server) or none (showcase mode:
   saved real reports). engine.js decides; this paints the chip and the banner under the header. */
let engineState = 'checking';
let wakeTick = 0;
const CHIP = {
  checking: ['Engine', 'Connecting…'],
  local: ['Engine', 'This laptop'],
  degraded: ['Engine', 'This laptop'],
  offline: ['Engine', 'Offline'],
  online: ['Engine', 'Online (free shared server)'],
  waking: ['Engine', 'Waking up…'],
  showcase: ['Showcase mode', 'Saved real reports'],
  mock: ['Engine', 'Mock data'],
};

function paintEngine(s) {
  engineState = s.state;
  const el = $('#engine');
  el.dataset.state = s.state;
  el.dataset.mode = s.mode;
  const [k, v] = CHIP[s.state] || CHIP.checking;
  $('#engine-k').textContent = k;
  $('#engine-v').textContent = v;
  const h = s.health;
  const models = h?.models || {};
  const vals = Object.values(models);
  if (s.state === 'degraded') $('#engine-v').textContent = `This laptop · ${vals.filter(Boolean).length}/${vals.length} models`;
  const modelList = Object.entries(models).map(([m, b]) => `${m} ${b ? '✓' : '✗'}`).join(', ') || 'n/a';
  el.title = {
    local: `The forensic engine is running on this laptop (VERITAS ${h?.version || ''}, CPU). Models: ${modelList}`,
    degraded: `The forensic engine is running on this laptop, but some models are missing. Models: ${modelList}`,
    offline: s.mode === 'online' ? 'The online engine is not answering right now. This page keeps checking.' : 'The forensic engine on this laptop is not answering. Double-click the VERITAS icon on the desktop.',
    online: `The online engine: VERITAS ${h?.version || ''} on a free shared server (CPU). Files are analysed in memory and not stored.`,
    waking: 'The free online engine sleeps when nobody uses it. Waking it usually takes under 2 minutes.',
    showcase: 'No forensic engine is reachable from this page. The Evidence-locker exhibits open real reports our engine saved earlier.',
    mock: 'Mock data (?mock=1): generated fixtures, not the engine.',
  }[s.state] || 'Looking for the forensic engine…';
  clearInterval(wakeTick);
  if (s.state === 'waking') { tickWake(); wakeTick = setInterval(tickWake, 1000); }
  updateBanner();
}

function tickWake() {
  const t = engine.wakeSeconds();
  const m = Math.floor(t / 60); const sec = Math.floor(t % 60);
  const clock = `${m}:${pad(sec)}`;
  $('#engine-v').textContent = `Waking up · ${clock}`;
  const bar = $('#banner .banner-prog i'); const out = $('#banner .banner-t');
  // honest progress: elapsed against the usual 2 minutes, never "done" until the engine actually answers
  if (bar) bar.style.transform = `scaleX(${Math.min(0.96, t / engine.WAKE_TYPICAL_S)})`;
  if (out) out.textContent = clock;
}

const BANNERS = {
  offline: () => `<span class="banner-dot" aria-hidden="true"></span><strong>Engine offline</strong>
    <span class="banner-x">Analysis is paused. Double-click the <b>VERITAS</b> icon on the desktop, then wait for the light to turn green. Live cam keeps working.</span>
    <button class="banner-retry" type="button" data-act="retry">Check again</button>`,
  offlineOnline: () => `<span class="banner-dot" aria-hidden="true"></span><strong>Engine not answering</strong>
    <span class="banner-x">The online engine may be restarting. This page keeps checking; the exhibits still open saved reports.</span>
    <button class="banner-retry" type="button" data-act="retry">Check again</button>`,
  waking: () => `<span class="banner-dot" aria-hidden="true"></span><strong>Waking up the online engine…</strong>
    <span class="banner-x">usually under 2 minutes · free servers sleep when nobody uses them</span>
    <span class="banner-prog" aria-hidden="true"><i></i></span><span class="banner-t mono">0:00</span>
    <button class="banner-retry" type="button" data-act="skip" title="Open the exhibits' saved reports now; the online engine keeps waking in the background">Use saved reports</button>`,
};

function updateBanner() {
  const b = $('#banner');
  const kind = current === 'game' ? null
    : engineState === 'waking' ? 'waking'
    : engineState === 'offline' ? (engine.mode() === 'online' ? 'offlineOnline' : 'offline')
    : null;
  if (b.dataset.kind !== (kind || '')) {
    b.dataset.kind = kind || '';
    b.innerHTML = kind ? BANNERS[kind]() : '';
    if (kind === 'waking') tickWake();
  }
  b.hidden = !kind;
  document.body.classList.toggle('has-banner', !b.hidden);
}

export const engineOnline = () => engine.ready();
/* ------------------------------------------------------------------ fullscreen + cursor */
function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen?.();
  else document.documentElement.requestFullscreen?.().catch(() => toast('Fullscreen was blocked by the browser', 'warn'));
}
let cursorTimer = 0;
function wakeCursor() {
  document.body.classList.remove('cursor-off');
  clearTimeout(cursorTimer);
  if (document.fullscreenElement) cursorTimer = setTimeout(() => document.body.classList.add('cursor-off'), 2500);
}

/* ------------------------------------------------------------------ clock */
function tick() {
  const d = new Date();
  $('#clock').textContent = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

/* ------------------------------------------------------------------ boot */
function boot() {
  if (MOCK) document.body.classList.add('is-mock');
  paintEngine(engine.snapshot());
  analyze.init();

  window.addEventListener('hashchange', route);
  window.addEventListener('resize', moveInk);
  for (const t of $$('.tab')) {
    // Windows/Edge leave focus on a clicked link; drop it so arrow keys reach the game (and don't switch tabs).
    t.addEventListener('click', (e) => { if (e.detail > 0) setTimeout(() => t.blur(), 0); });
    t.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      if (current === 'game') return; // in Spot the fake, ← / → are the answer keys
      e.preventDefault();
      const i = VIEWS.indexOf(t.dataset.tab) + (e.key === 'ArrowRight' ? 1 : -1);
      const v = VIEWS[(i + VIEWS.length) % VIEWS.length];
      location.hash = `#${v}`; $(`.tab[data-tab="${v}"]`).focus();
    });
  }

  $('#fs-btn').addEventListener('click', toggleFullscreen);
  $('#banner').addEventListener('click', (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'retry') engine.resolve();
    if (act === 'skip') engine.skipWaiting();
  });
  on('engine', paintEngine);
  on('engine-woke', () => toast('The online engine is awake: you can analyse your own files now', 'ok', 5000));
  on('engine-found', () => toast('The online engine is available again: you can analyse your own files now', 'ok', 5000));
  document.addEventListener('fullscreenchange', () => {
    document.body.classList.toggle('is-fullscreen', !!document.fullscreenElement);
    wakeCursor(); setTimeout(moveInk, 60);
  });
  ['mousemove', 'mousedown', 'touchstart'].forEach((ev) => window.addEventListener(ev, wakeCursor, { passive: true }));

  window.addEventListener('keydown', (e) => {
    if (isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (document.querySelector('.overlay:not([hidden])') && e.key !== 'f' && e.key !== 'F') return;
    if (e.key === 'f' || e.key === 'F') { if (!e.shiftKey) { e.preventDefault(); toggleFullscreen(); } return; }
    if (current !== 'game' && (e.key === '1' || e.key === '2' || e.key === '3')) {
      location.hash = `#${VIEWS[+e.key - 1]}`;
    }
  });

  on('goto', (v) => { if (VIEWS.includes(v)) location.hash = `#${v}`; });

  tick(); setInterval(tick, 1000);
  route();
  engine.resolve();
  document.fonts?.ready.then(() => { moveInk(); document.body.classList.remove('is-booting'); });
  setTimeout(() => document.body.classList.remove('is-booting'), 1500);
}

boot();
