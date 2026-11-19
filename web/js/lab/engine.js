// VERITAS lab — which forensic engine answers this page.
//   1. same origin  api/health   the booth laptop (http://localhost) or the Hugging Face Space that serves this site
//   2. window.VERITAS_CONFIG.onlineApi   the online engine, cross-origin (a free Space may need 1-3 min to wake up)
//   3. neither  ->  SHOWCASE mode: the Evidence-locker exhibits open real reports our engine saved earlier
// ?api=URL tries only that engine; ?showcase=1 forces showcase mode; ?mock=1 keeps the canvas fixtures (mock.js).

import { MOCK, params, emit, sleep } from './util.js';
import * as api from './api.js';

const CFG = (typeof window !== 'undefined' && window.VERITAS_CONFIG) || {};
/* The online engine's limits (contract shared with server/online.py; the engine's /api/health may send its own). */
export const ONLINE_LIMITS = {
  image: { max_mb: 15, max_seconds: null },
  audio: { max_mb: 20, max_seconds: 60 },
  video: { max_mb: 40, max_seconds: 30 },
};
export const WAKE_TYPICAL_S = 120;   // "usually under 2 minutes"
const WAKE_GIVE_UP_S = 300;          // then showcase mode (and keep checking quietly in the background)
const BG_RETRY_MS = 60000;           // showcase: look for the online engine again every minute

/** Booth: the page itself comes from the engine on this computer. */
const ON_LOCALHOST = /^(localhost|127\.\d+\.\d+\.\d+|\[::1\])$/i.test(location.hostname);

const E = {
  mode: 'checking',   // checking | local | online | waking | showcase | mock
  ok: false,          // the chosen engine answered its last health check
  health: null,
  base: '',           // '' same origin, else the online engine's origin
  remote: '',         // configured online engine (for background re-checks)
  wakeT0: 0,
  why: '',            // showcase: forced | none | asleep | down
};
let pollTimer = 0; let bgTimer = 0; let fails = 0; let run = 0;
const waiters = new Set();

export const snapshot = () => ({ ...E, state: state(), limits: limits() });
/** Header chip state: checking | local | degraded | offline | online | waking | showcase | mock */
export function state() {
  if (E.mode === 'local' || (E.mode === 'online' && !E.base)) {
    if (!E.ok) return 'offline';
    const vals = Object.values(E.health?.models || {});
    if (vals.length && vals.filter(Boolean).length < vals.length) return 'degraded';
    return E.mode === 'online' ? 'online' : 'local';
  }
  if (E.mode === 'online') return E.ok ? 'online' : 'waking';
  return E.mode;
}
export const mode = () => E.mode;
/** True when a file can be sent for analysis right now. */
export const ready = () => (E.mode === 'local' || E.mode === 'online' || E.mode === 'mock') && E.ok;
export const isOnline = () => E.mode === 'online';
export const isShowcase = () => E.mode === 'showcase';
/** Limits to enforce in the browser (online engine only; the booth keeps its 200 MB limit). */
export function limits() {
  if (E.mode === 'waking') return ONLINE_LIMITS;
  if (E.mode !== 'online') return null;
  const L = E.health?.online?.limits;
  return L && typeof L === 'object' ? { ...ONLINE_LIMITS, ...L } : ONLINE_LIMITS;
}
export const wakeSeconds = () => (E.mode === 'waking' && E.wakeT0 ? (performance.now() - E.wakeT0) / 1000 : 0);

function publish() {
  const s = snapshot();
  emit('engine', s);
  if (ready() || E.mode === 'showcase') { for (const w of waiters) w(ready()); waiters.clear(); }
}

/** Resolves true once an engine is ready, false if the lab settles in showcase mode. */
export function whenReady() {
  if (ready()) return Promise.resolve(true);
  if (E.mode === 'showcase') return Promise.resolve(false);
  return new Promise((res) => waiters.add(res));
}

const isOnlineHealth = (h) => !!(h && (h.online || h.mode === 'online' || h.hosted));

function use(base, health, mode) {
  clearTimeout(bgTimer); clearTimeout(pollTimer);
  api.setBase(base);
  Object.assign(E, { mode, ok: true, health, base, why: '', wakeT0: 0 });
  fails = 0;
  publish();
  schedulePoll();
}

function showcase(why) {
  clearTimeout(pollTimer);
  Object.assign(E, { mode: 'showcase', ok: false, why, wakeT0: 0 });
  publish();
  clearTimeout(bgTimer);
  if (E.remote && why !== 'forced') bgTimer = setTimeout(backgroundCheck, BG_RETRY_MS);
}

async function backgroundCheck() {
  if (E.mode !== 'showcase' || !E.remote) return;
  const p = await api.probe(E.remote, 15000);   // asking also wakes a sleeping Space
  if (E.mode !== 'showcase') return;
  if (p.kind === 'ok') { use(E.remote, p.health, 'online'); emit('engine-found', snapshot()); return; }
  bgTimer = setTimeout(backgroundCheck, BG_RETRY_MS);
}

/* Keep watching the chosen engine. Booth: every 15 s (5 s while it is down), like before.
   Online: every 30 s with a long timeout - a busy shared server answers slowly - and only after two misses in a row
   does the lab go back to "waking up". */
function schedulePoll() {
  clearTimeout(pollTimer);
  const remote = !!E.base;
  pollTimer = setTimeout(async () => {
    const my = run;
    const p = await api.probe(E.base, remote ? 15000 : 4000);
    if (my !== run || !(E.mode === 'local' || E.mode === 'online')) return;
    if (p.kind === 'ok') {
      fails = 0;
      const was = E.ok; E.ok = true; E.health = p.health;
      if (!was) publish(); else emit('engine', snapshot());
    } else if (remote) {
      fails += 1;
      if (fails >= 2) { wake(E.base, my); return; }
    } else {
      fails += 1;
      if (E.ok) { E.ok = false; publish(); }
    }
    schedulePoll();
  }, remote ? 30000 : E.ok ? 15000 : 5000);
}

/** Ask a (possibly sleeping) online engine until it answers, or give up into showcase mode. */
async function wake(base, my = run) {
  E.remote = base;
  let p = await api.probe(base, 12000);
  if (my !== run) return;
  if (p.kind === 'ok') { use(base, p.health, 'online'); return; }
  if (p.kind !== 'waking') { showcase(p.kind === 'down' ? 'down' : 'none'); return; }
  api.setBase(base);
  Object.assign(E, { mode: 'waking', ok: false, base, wakeT0: performance.now() });
  publish();
  while (my === run && (performance.now() - E.wakeT0) / 1000 < WAKE_GIVE_UP_S) {
    await sleep(5000);
    if (my !== run) return;
    p = await api.probe(base, 20000);
    if (my !== run) return;
    if (p.kind === 'ok') { use(base, p.health, 'online'); emit('engine-woke', snapshot()); return; }
  }
  if (my === run) showcase('asleep');
}

/** Work out which engine to use. Safe to call again (the "Check again" buttons). */
export async function resolve() {
  const my = ++run;
  clearTimeout(pollTimer); clearTimeout(bgTimer);
  if (MOCK) { Object.assign(E, { mode: 'mock', ok: true, health: (await api.probe('', 4000)).health }); publish(); return; }
  if (params.get('showcase') === '1') { showcase('forced'); return; }
  E.mode = 'checking'; E.ok = false; publish();

  const explicit = api.explicitApi();
  if (explicit) { await wake(explicit, my); return; }

  // 1. same origin
  const so = await api.probe('', 5000);
  if (my !== run) return;
  if (so.kind === 'ok') { use('', so.health, isOnlineHealth(so.health) ? 'online' : 'local'); return; }
  if (ON_LOCALHOST && so.kind !== 'none') {
    // the booth: this page came from the engine on this laptop, so it is restarting or was closed - keep asking it
    api.setBase(''); Object.assign(E, { mode: 'local', ok: false, health: null, base: '' }); publish(); schedulePoll(); return;
  }
  // 2. the online engine
  const remote = api.cleanBase(CFG.onlineApi);
  if (remote && remote !== location.origin) { await wake(remote, my); return; }
  // 3. showcase
  showcase('none');
}

/** Stop waiting for a sleeping engine and use the saved reports now (it keeps being checked in the background). */
export function skipWaiting() {
  if (E.mode !== 'waking') return;
  run++;
  showcase('asleep');
}
