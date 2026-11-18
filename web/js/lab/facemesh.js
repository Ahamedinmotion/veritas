// VERITAS lab — shared MediaPipe Face Landmarker loader (vendored tasks-vision 1.2.3, fully offline).
// Used by the Live cam (VIDEO mode) and by the Analyze scan stage (IMAGE mode pre-scan of the exhibit).

const MP_BASE = new URL('../../vendor/mediapipe/', import.meta.url);
export const MODEL_URL = new URL('face_landmarker.task', MP_BASE).href;
export const WASM_URL = new URL('wasm', MP_BASE).href; // no trailing slash: the resolver appends /vision_wasm_internal.*

let modP = null, filesetP = null, imageLm = null;

// MediaPipe's WASM prints glog INFO/WARNING lines through console.error/warn. They are not errors;
// drop only those exact patterns so the booth console stays clean (real errors still pass through).
export function quietMediapipeLogs() {
  if (window.__vxQuiet) return; window.__vxQuiet = true;
  const noise = /^(INFO: |[IW]\d{4} \d\d:\d\d:\d\d|Graph successfully started running)/;
  for (const k of ['error', 'warn', 'log', 'info']) {
    const orig = console[k].bind(console);
    console[k] = (...a) => { if (typeof a[0] === 'string' && noise.test(a[0])) return; orig(...a); };
  }
}
// tasks-vision 1.2.3 contains a usage-telemetry uploader (fetch to *.googleapis.com). The booth is offline:
// answer such calls locally so nothing leaves the machine and no network errors appear.
export function guardTelemetry() {
  if (window.__vxGuard) return; window.__vxGuard = true;
  const orig = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = typeof input === 'string' ? input : input?.url || '';
    if (/^https?:\/\/[^/]*\.(googleapis|google|gstatic)\.com\//i.test(url)) return Promise.resolve(new Response('', { status: 204 }));
    return orig(input, init);
  };
}

export async function vision() {
  quietMediapipeLogs(); guardTelemetry();
  modP ||= import('../../vendor/mediapipe/vision_bundle.js');
  const mod = await modP;
  filesetP ||= mod.FilesetResolver.forVisionTasks(WASM_URL);
  return { mod, fileset: await filesetP };
}

/** Create a landmarker; tries the GPU delegate first, falls back to CPU. */
export async function createLandmarker(runningMode, extra = {}, prefer = 'GPU') {
  const { mod, fileset } = await vision();
  const opts = (d) => ({
    baseOptions: { modelAssetPath: MODEL_URL, delegate: d }, runningMode, numFaces: 2,
    outputFaceBlendshapes: false, outputFacialTransformationMatrixes: true,
    minFaceDetectionConfidence: 0.5, minFacePresenceConfidence: 0.5, minTrackingConfidence: 0.5, ...extra,
  });
  if (prefer === 'GPU') {
    try { return { lm: await mod.FaceLandmarker.createFromOptions(fileset, opts('GPU')), delegate: 'GPU', FL: mod.FaceLandmarker }; }
    catch { /* fall through to CPU */ }
  }
  return { lm: await mod.FaceLandmarker.createFromOptions(fileset, opts('CPU')), delegate: 'CPU', FL: mod.FaceLandmarker };
}

/** Detect faces on a still image element/canvas. Returns { faces: [landmarks], FL } or null on failure. */
export async function detectStill(source) {
  try {
    imageLm ||= createLandmarker('IMAGE', { numFaces: 4 }, 'CPU');
    const { lm, FL } = await imageLm;
    const r = lm.detect(source);
    return { faces: r.faceLandmarks || [], FL };
  } catch { return null; }
}

/** Pre-load the still-image landmarker when the page is idle, so the first pre-scan is instant. */
export function warm() {
  imageLm ||= createLandmarker('IMAGE', { numFaces: 4 }, 'CPU');
  imageLm.catch(() => { imageLm = null; });
}
