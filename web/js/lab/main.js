// VERITAS lab — bootstrap: tabs/router, engine status light, fullscreen, kiosk niceties.

import { $, $$, MOCK, isTyping, emit, on, pad, toast } from './util.js';
import * as api from './api.js';
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

/* ------------------------------------------------------------------ engine status */
let engineState = 'checking';
let healthTimer = 0;

function setEngine(state, h) {
  engineState = state;
  const el = $('#engine'); const v = $('#engine-v');
  el.dataset.state = state;
  if (state === 'online') {
    const models = h?.models || {};
    const vals = Object.values(models);
    const up = vals.filter(Boolean).length;
    const dev = String(h?.device || 'cpu').toUpperCase();
    if (MOCK) v.textContent = 'Mock data';
    else if (vals.length && up < vals.length) { el.dataset.state = 'degraded'; v.textContent = `Online · ${up}/${vals.length} models`; }
    else v.textContent = `Online · ${dev}`;
    el.title = `Forensic engine ${h?.version || ''} on ${dev}. Models: ${Object.entries(models).map(([k, b]) => `${k} ${b ? '✓' : '✗'}`).join(', ') || 'n/a'}`;
  } else if (state === 'offline') {
    v.textContent = 'Offline';
    el.title = 'Forensic engine not reachable. Run start_windows.bat.';
  } else v.textContent = 'Checking…';
  updateBanner();
  emit('engine', { state: el.dataset.state, health: h });
}

function updateBanner() {
  const b = $('#offline-banner');
  b.hidden = !(engineState === 'offline' && current !== 'game');
  document.body.classList.toggle('has-banner', !b.hidden);
}

async function checkHealth() {
  clearTimeout(healthTimer);
  try {
    const h = await api.health();
    setEngine('online', h);
    healthTimer = setTimeout(checkHealth, 15000);
  } catch {
    setEngine('offline');
    healthTimer = setTimeout(checkHealth, 5000);
  }
}
export const engineOnline = () => engineState === 'online';

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
  $('#banner-retry').addEventListener('click', () => { setEngine('checking'); checkHealth(); });
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
  checkHealth();
  document.fonts?.ready.then(() => { moveInk(); document.body.classList.remove('is-booting'); });
  setTimeout(() => document.body.classList.remove('is-booting'), 1500);
}

boot();
