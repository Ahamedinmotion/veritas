// VERITAS lab — talks to the local forensic engine (server/app.py) per docs/ARCHITECTURE.md.
// ?mock=1 swaps every call for canvas-generated fixtures in mock.js (contract-shaped).
// ?api=http://host:port lets a dev page on another port talk to the engine.

import { MOCK, params, fileKind } from './util.js';

const BASE = (params.get('api') || '').replace(/\/+$/, '');
let mockMod = null;
const mock = async () => (mockMod ||= await import('./mock.js'));

export const isMock = MOCK;

/** GET /api/health -> {ok, version, models, device} or throws. */
export async function health() {
  if (MOCK) return (await mock()).health();
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 4000);
  try {
    const r = await fetch(`${BASE}/api/health`, { cache: 'no-store', signal: ctl.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const j = await r.json();
    if (!j || j.ok === false) throw new Error('engine reported not ok');
    return j;
  } finally { clearTimeout(timer); }
}

/**
 * POST /api/analyze/{kind} with multipart field "file".
 * Returns { promise, abort }. onUpload(fraction 0..1) reports real upload progress.
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
  const promise = new Promise((resolve, reject) => {
    const fd = new FormData();
    fd.append('file', file, file.name || `evidence.${kind === 'image' ? 'jpg' : kind === 'video' ? 'mp4' : 'wav'}`);
    xhr.open('POST', `${BASE}/api/analyze/${kind}`);
    xhr.responseType = 'text';
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
        const err = new Error(msg); err.status = xhr.status; err.fromEngine = !!body?.error; reject(err);
      }
    };
    xhr.onerror = () => { const e = new Error('Could not reach the engine. Is start_windows.bat running?'); e.offline = true; reject(e); };
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

/** Evidence-locker items. ?mock=1 uses generated exhibits (add &samples=1 to try the real manifest first). */
export async function lockerItems() {
  if (MOCK && !params.has('samples')) return (await mock()).lockerItems();
  const real = await loadManifest('samples/lab/manifest.json');
  if (real?.length) {
    return real.filter((x) => x && x.file).map((x) => ({ ...x, kind: x.kind || fileKind({ name: x.file, type: '' }) || 'image', src: `samples/lab/${x.file}` }));
  }
  if (MOCK) return (await mock()).lockerItems();
  return [];
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
