// VERITAS lab — talks to a forensic engine (server/app.py) per docs/ARCHITECTURE.md.
// Which engine answers (this laptop, the online engine or none = showcase mode) is decided in engine.js;
// it calls setBase('') for the same origin or setBase('https://…hf.space') for the online engine.
// ?mock=1 swaps every call for canvas-generated fixtures in mock.js (contract-shaped).
// ?api=http://host:port lets a dev page on another port talk to an engine.

import { MOCK, params, fileKind } from './util.js';

let mockMod = null;
const mock = async () => (mockMod ||= await import('./mock.js'));

export const isMock = MOCK;

/* ------------------------------------------------------------------ engine base URL */
let BASE = '';                        // '' = same origin; else an absolute origin without trailing slash
let REMOTE = false;                   // the engine is another site (the online engine): longer timeouts
export function setBase(base) { BASE = cleanBase(base); REMOTE = !!BASE; }
export const getBase = () => BASE;
/** 'https://x.hf.space/' -> 'https://x.hf.space'; anything that is not http(s) -> '' */
export function cleanBase(u) {
  const s = String(u || '').trim().replace(/\/+$/, '');
  return /^https?:\/\/[^\s/]+/i.test(s) ? s : '';
}
/** Same origin uses a RELATIVE url, so the lab also works under a sub-path (e.g. /veritas/lab.html). */
export const apiUrl = (path, base = BASE) => (base ? `${base}/api/${path}` : `api/${path}`);
export const explicitApi = () => cleanBase(params.get('api'));

/**
 * One health probe. Never throws. Returns { kind, health?, status? } where kind is
 *  'ok'      an engine answered and is ready
 *  'waking'  something is there but not ready (HTTP 502/503/504, a "starting" page, models still loading, slow answer)
 *  'none'    definitely no engine here (static host: web/api/health stand-in, 404, an HTML page)
 *  'down'    nothing answered at all (connection refused, offline, DNS)
 */
export async function probe(base = BASE, ms = 4000) {
  if (MOCK) return { kind: 'ok', health: await (await mock()).health() };
  const url = apiUrl('health', base);
  if (base) {
    // Is anything there at all? Asked without CORS first, so a server that answers without CORS headers (a free
    // host's "waking up" page) is not an error, and a dead address costs one failed request, not two.
    const c0 = new AbortController(); const t0 = setTimeout(() => c0.abort(), Math.min(ms, 10000));
    try { await fetch(url, { mode: 'no-cors', cache: 'no-store', signal: c0.signal, credentials: 'omit' }); }
    catch (e) { return { kind: e?.name === 'AbortError' ? 'waking' : 'down', status: 0 }; }
    finally { clearTimeout(t0); }
  }
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms);
  try {
    const r = await fetch(url, { cache: 'no-store', signal: ctl.signal, credentials: 'omit' });
    let j = null;
    try { j = await r.json(); } catch { /* not JSON */ }
    if (r.ok && j && typeof j === 'object') {
      if (j.static) return { kind: 'none', status: r.status };     // web/api/health on a static host
      if (j.ok === true) return { kind: 'ok', health: j };
      if (j.ok === false) return { kind: 'waking', health: j, status: r.status };
      return { kind: 'none', status: r.status };
    }
    if ([502, 503, 504].includes(r.status)) return { kind: 'waking', status: r.status };
    if (r.ok && base) return { kind: 'waking', status: r.status }; // a remote host's HTML "starting" page
    return { kind: 'none', status: r.status };
  } catch (e) {
    if (e?.name === 'AbortError') return { kind: base ? 'waking' : 'down', status: 0 };
    // cross-origin: the server answered (see above) but without CORS headers -> a host page while the engine starts
    return { kind: base ? 'waking' : 'down', status: 0 };
  } finally { clearTimeout(timer); }
}

/** GET /api/health -> {ok, version, models, device} or throws. Kept for callers that want the old contract. */
export async function health() {
  const p = await probe(BASE, REMOTE ? 15000 : 4000);
  if (p.kind !== 'ok') throw new Error(`engine ${p.kind}`);
  return p.health;
}

/**
 * POST /api/analyze/{kind} with multipart field "file".
 * Returns { promise, abort }. onUpload(fraction 0..1) reports real upload progress.
 * Errors carry: status, fromEngine (the engine sent {error}), offline (nothing answered), busy + retryAfter (HTTP 503).
 */
export function analyze(kind, file, { onUpload } = {}) {
  if (MOCK) {
    let aborted = false; let rejectFn;
    const promise = new Promise((resolve, reject) => {
      rejectFn = reject;
      mock().then((m) => m.analyze(kind, file, { onUpload, isAborted: () => aborted })).then(resolve, reject);
    });
    return { promise, abort() { aborted = true; const e = new Error('cancelled'); e.cancelled = true; rejectFn?.(e); } };
  }
  const xhr = new XMLHttpRequest();
  const remote = REMOTE;
  const promise = new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('file', file, file.name || `evidence.${kind === 'image' ? 'jpg' : kind === 'video' ? 'mp4' : 'wav'}`);
    xhr.open('POST', apiUrl(`analyze/${kind}`));
    xhr.responseType = 'text';
    if (remote) xhr.timeout = 8 * 60 * 1000;  // a shared free server: never wait forever
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) onUpload?.(e.loaded / e.total); };
    xhr.upload.onload = () => onUpload?.(1);
    xhr.onload = () => {
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* not JSON */ }
      if (xhr.status >= 200 && xhr.status < 300 && body && typeof body === 'object' && !body.error) {
        resolve(body);
      } else {
        const msg = body?.error || body?.detail?.toString?.() ||
          (xhr.status === 404 ? 'The engine does not offer this analysis (404). Is it the right version?' :
           xhr.status === 413 ? 'That file is too large for the engine.' :
           `The engine returned an error (HTTP ${xhr.status}).`);
        const err = new Error(msg); err.status = xhr.status; err.fromEngine = !!body?.error;
        if (xhr.status === 503) { err.busy = true; err.retryAfter = Number(body?.retry_after || xhr.getResponseHeader('Retry-After')) || 0; }
        reject(err);
      }
    };
    xhr.onerror = () => {
      const e = new Error(remote ? 'Could not reach the online engine. It may be restarting or asleep.' : 'Could not reach the engine on this laptop.');
      e.offline = true; reject(e);
    };
    xhr.ontimeout = () => { const e = new Error('The online engine took too long to answer.'); e.offline = true; reject(e); };
    xhr.onabort = () => { const e = new Error('cancelled'); e.cancelled = true; reject(e); };
    xhr.send(fd);
  });
  return { promise, abort: () => xhr.abort() };
}

/** Fetch a JSON manifest; returns null if missing / invalid. */
export async function loadManifest(url) {
  try {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) return null;
    const j = await r.json();
    return Array.isArray(j) ? j : Array.isArray(j?.items) ? j.items : null;
  } catch { return null; }
}

/** Evidence-locker items. ?mock=1 uses generated exhibits (add &samples=1 to try the real manifest first).
 *  Each real exhibit has a saved engine report at samples/lab/reports/<file>.json (showcase mode). */
export async function lockerItems() {
  if (MOCK && !params.has('samples')) return (await mock()).lockerItems();
  const real = await loadManifest('samples/lab/manifest.json');
  if (real?.length) {
    return real.filter((x) => x && x.file).map((x) => ({
      ...x, kind: x.kind || fileKind({ name: x.file, type: '' }) || 'image', src: `samples/lab/${x.file}`,
      report: `samples/lab/reports/${x.file.split('/').pop()}.json`,
    }));
  }
  if (MOCK) return (await mock()).lockerItems();
  return [];
}

/** The engine's saved report for a locker exhibit (showcase mode). Throws if it is missing. */
export async function lockerReport(item) {
  if (!item.report) throw new Error('This exhibit has no saved report');
  const r = await fetch(item.report);
  if (!r.ok) throw new Error(`Saved report not found (${r.status})`);
  const j = await r.json();
  if (!j || typeof j !== 'object' || !Array.isArray(j.tests)) throw new Error('Saved report is not readable');
  return j;
}

/** Turn a locker item into a File ready for upload. */
export async function lockerFile(item) {
  if (item.mockFile) return item.mockFile();
  const r = await fetch(item.src);
  if (!r.ok) throw new Error(`Could not open exhibit file (${r.status})`);
  const blob = await r.blob();
  const name = item.file.split('/').pop();
  return new File([blob], name, { type: blob.type || '' });
}

/** Spot-the-fake data. Returns { items, base } or null. */
export async function gameItems() {
  if (MOCK && !params.has('samples')) return (await import('./mock-game.js')).gameItems();
  const real = await loadManifest('samples/game/manifest.json');
  if (real?.length) return real.filter((x) => x && x.file).map((x) => ({ ...x, src: `samples/game/${x.file}` }));
  if (MOCK) return (await import('./mock-game.js')).gameItems();
  return null;
}
