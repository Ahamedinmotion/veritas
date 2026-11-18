// VERITAS — signature hero: the MediaPipe canonical face mesh as a living point cloud.
// State (S) is driven by scroll from main.js: fracture, scan sweep, authentic/synthetic split.
import { loadFace, rng, clamp, lerp, reduceMotion } from './util.js';

const HEX = { bone: 0xd9d6ce, auth: 0x3ef2c4, synth: 0xff3b5c, scan: 0x6aa8ff, ink: 0x04060a };

// Face-swap region: inner face (brows → mouth, cheek to cheek) is "synthetic" in Exhibit A.
function innerWeight(x, y, z) {
  const v = Math.pow(Math.abs(x / 0.66), 3) + Math.pow(Math.abs((y - 0.02) / 0.8), 3);
  const w = 1 - smoothstep(0.72, 1.02, v);
  return z < -0.15 ? 0 : w;
}
function smoothstep(a, b, v) { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); }

// Build all per-point attributes once: landmarks + surface samples + shards.
function buildCloud(data, samples = 7200) {
  const r = rng(468);
  const V = data.vertices, Nn = data.normals, T = data.triangles;
  const nV = data.count, nT = T.length / 3;
  // triangle centroids + areas
  const cen = new Float32Array(nT * 3), area = new Float32Array(nT);
  let total = 0;
  for (let t = 0; t < nT; t++) {
    const a = T[t * 3], b = T[t * 3 + 1], c = T[t * 3 + 2];
    for (let k = 0; k < 3; k++) cen[t * 3 + k] = (V[a * 3 + k] + V[b * 3 + k] + V[c * 3 + k]) / 3;
    const ux = V[b * 3] - V[a * 3], uy = V[b * 3 + 1] - V[a * 3 + 1], uz = V[b * 3 + 2] - V[a * 3 + 2];
    const wx = V[c * 3] - V[a * 3], wy = V[c * 3 + 1] - V[a * 3 + 1], wz = V[c * 3 + 2] - V[a * 3 + 2];
    const cx = uy * wz - uz * wy, cy = uz * wx - ux * wz, cz = ux * wy - uy * wx;
    area[t] = 0.5 * Math.hypot(cx, cy, cz); total += area[t];
  }
  // shards: farthest-point seeds over centroids, then Voronoi assignment
  const K = 46, seeds = [Math.floor(r() * nT)];
  const dmin = new Float32Array(nT).fill(1e9);
  while (seeds.length < K) {
    const s = seeds[seeds.length - 1];
    let best = 0, bi = 0;
    for (let t = 0; t < nT; t++) {
      const dx = cen[t * 3] - cen[s * 3], dy = cen[t * 3 + 1] - cen[s * 3 + 1], dz = cen[t * 3 + 2] - cen[s * 3 + 2];
      dmin[t] = Math.min(dmin[t], dx * dx + dy * dy + dz * dz);
      if (dmin[t] > best) { best = dmin[t]; bi = t; }
    }
    seeds.push(bi);
  }
  const triShard = new Int16Array(nT);
  for (let t = 0; t < nT; t++) {
    let best = 1e9, bi = 0;
    for (let k = 0; k < K; k++) {
      const s = seeds[k];
      const dx = cen[t * 3] - cen[s * 3], dy = cen[t * 3 + 1] - cen[s * 3 + 1], dz = cen[t * 3 + 2] - cen[s * 3 + 2];
      const d = dx * dx + dy * dy + dz * dz;
      if (d < best) { best = d; bi = k; }
    }
    triShard[t] = bi;
  }
  const shC = new Float32Array(K * 3), shN = new Float32Array(K), shR = new Float32Array(K);
  for (let t = 0; t < nT; t++) { const k = triShard[t]; shC[k * 3] += cen[t * 3]; shC[k * 3 + 1] += cen[t * 3 + 1]; shC[k * 3 + 2] += cen[t * 3 + 2]; shN[k]++; }
  for (let k = 0; k < K; k++) { shC[k * 3] /= shN[k] || 1; shC[k * 3 + 1] /= shN[k] || 1; shC[k * 3 + 2] /= shN[k] || 1; shR[k] = r(); }
  const vertShard = new Int16Array(nV).fill(-1);
  for (let t = 0; t < nT; t++) for (let j = 0; j < 3; j++) { const v = T[t * 3 + j]; if (vertShard[v] < 0) vertShard[v] = triShard[t]; }

  // allocate
  const counts = new Int32Array(nT);
  let nS = 0;
  for (let t = 0; t < nT; t++) { counts[t] = Math.round((area[t] / total) * samples); nS += counts[t]; }
  const N = nV + nS;
  const pos = new Float32Array(N * 3), dir = new Float32Array(N * 3), shard = new Float32Array(N * 4), rnd = new Float32Array(N * 4), inner = new Float32Array(N), size = new Float32Array(N);
  const put = (i, x, y, z, nx, ny, nz, k, s) => {
    pos[i * 3] = x; pos[i * 3 + 1] = y; pos[i * 3 + 2] = z;
    dir[i * 3] = nx; dir[i * 3 + 1] = ny; dir[i * 3 + 2] = nz;
    shard[i * 4] = shC[k * 3]; shard[i * 4 + 1] = shC[k * 3 + 1]; shard[i * 4 + 2] = shC[k * 3 + 2]; shard[i * 4 + 3] = shR[k];
    rnd[i * 4] = r(); rnd[i * 4 + 1] = r(); rnd[i * 4 + 2] = r(); rnd[i * 4 + 3] = r();
    inner[i] = innerWeight(x, y, z); size[i] = s;
  };
  for (let v = 0; v < nV; v++) put(v, V[v * 3], V[v * 3 + 1], V[v * 3 + 2], Nn[v * 3], Nn[v * 3 + 1], Nn[v * 3 + 2], Math.max(0, vertShard[v]), 1);
  let i = nV;
  for (let t = 0; t < nT; t++) {
    const a = T[t * 3], b = T[t * 3 + 1], c = T[t * 3 + 2];
    for (let n = 0; n < counts[t]; n++) {
      let u = r(), w = r();
      if (u + w > 1) { u = 1 - u; w = 1 - w; }
      const q = 1 - u - w;
      const p = (k, A) => A[a * 3 + k] * q + A[b * 3 + k] * u + A[c * 3 + k] * w;
      put(i++, p(0, V), p(1, V), p(2, V), p(0, Nn), p(1, Nn), p(2, Nn), triShard[t], r() < 0.08 ? 0.32 : 0);
    }
  }
  return { N, nV, pos, dir, shard, rnd, inner, size, edges: data.edges };
}

const COMMON = /* glsl */`
attribute vec3 aDir; attribute vec4 aShard; attribute vec4 aRand; attribute float aInner; attribute float aSize;
uniform float uTime, uFracture, uScanY, uScanOn, uClassify, uFinale, uOpacity, uDim;
uniform vec3 cBone, cAuth, cSynth, cScan;
varying vec3 vColor; varying float vAlpha;
vec3 rotAxis(vec3 p, vec3 a, float ang){ float c = cos(ang), s = sin(ang); return p*c + cross(a,p)*s + a*dot(a,p)*(1.0-c); }
vec3 displace(vec3 p){
  p += aDir * sin(uTime*1.6 + aRand.x*40.0) * 0.006;
  float f = uFracture;
  if (f > 0.0001) {
    float k = f * (0.5 + aShard.w * 0.65);
    vec3 c = aShard.xyz;
    vec3 axis = normalize(aRand.yzw - 0.5 + 0.001);
    p = c + rotAxis(p - c, axis, k * (aShard.w - 0.5) * 1.5);
    vec3 o = normalize(vec3(c.x * 1.2, c.y * 0.9, c.z + 0.9));
    p += o * k * 0.62;
    p += (aRand.yzw - 0.5) * k * 0.3 * (1.0 - aSize);
  }
  return p;
}
float colorize(vec3 p0){
  float d = p0.y - uScanY;
  float band = exp(-d*d*240.0) * uScanOn;
  float passed = smoothstep(uScanY - 0.03, uScanY + 0.06, p0.y) * uClassify;
  vec3 judged = mix(cAuth, cSynth, aInner);
  vec3 col = mix(cBone, judged, passed);
  col = mix(col, cAuth, uFinale);
  col += cScan * band * 1.4;
  vColor = col;
  float a = mix(0.30, 1.0, aSize);
  a *= 1.0 - uDim * 0.55;
  vAlpha = a * uOpacity * (1.0 + band * 1.6);
  return band;
}`;

const PTS_VS = COMMON + /* glsl */`
uniform float uSize, uPR;
void main(){
  vec3 p = displace(position);
  float band = colorize(position);
  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * mix(0.62, 1.55, aSize) * uPR * (1.0 + band * 0.9) / -mv.z;
}`;
const PTS_FS = /* glsl */`
varying vec3 vColor; varying float vAlpha;
void main(){
  vec2 c = gl_PointCoord - 0.5; float r = length(c);
  if (r > 0.5) discard;
  float a = smoothstep(0.5, 0.0, r); a *= a;
  gl_FragColor = vec4(vColor, a * vAlpha);
}`;
const LN_VS = COMMON + /* glsl */`
void main(){ vec3 p = displace(position); colorize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0); }`;
const LN_FS = /* glsl */`
uniform float uLine; varying vec3 vColor; varying float vAlpha;
void main(){ gl_FragColor = vec4(vColor, vAlpha * uLine); }`;
const BG_FS = /* glsl */`
varying vec2 vUv; uniform float uTime, uOpacity, uFinale; uniform vec3 cScan, cAuth;
void main(){
  vec2 p = vUv * 2.0 - 1.0;
  float r = length(p);
  float a = atan(p.y, p.x);
  vec3 tint = mix(cScan, cAuth, uFinale);
  float glow = exp(-r * r * 3.2) * 0.07;
  float ring1 = smoothstep(0.004, 0.0, abs(r - 0.82)) * 0.10;
  float ring2 = smoothstep(0.003, 0.0, abs(r - 0.9)) * 0.05;
  float ticks = step(0.985, fract((a + uTime * 0.04) * 72.0 / 6.2831853)) * smoothstep(0.012, 0.0, abs(r - 0.86)) * 0.35;
  float major = step(0.988, fract((a - uTime * 0.025) * 12.0 / 6.2831853)) * smoothstep(0.022, 0.0, abs(r - 0.94)) * 0.5;
  float cross = (smoothstep(0.0025, 0.0, abs(p.x)) + smoothstep(0.0025, 0.0, abs(p.y))) * step(0.9, r) * step(r, 1.0) * 0.18;
  gl_FragColor = vec4(tint, (glow + ring1 + ring2 + ticks + major + cross) * uOpacity);
}`;
const SCAN_VS = /* glsl */`varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
const SCAN_FS = /* glsl */`
varying vec2 vUv; uniform float uOn; uniform vec3 cScan;
void main(){
  float d = vUv.y - 0.5;
  float line = exp(-d*d*9000.0);
  float glow = exp(-abs(d)*26.0) * 0.22;
  float trail = d > 0.0 ? exp(-d*7.0) * 0.10 : 0.0;
  float edge = smoothstep(0.0, 0.18, vUv.x) * smoothstep(1.0, 0.82, vUv.x);
  float ticks = step(0.94, fract(vUv.x * 48.0)) * exp(-abs(d)*60.0) * 0.6;
  gl_FragColor = vec4(cScan, (line + glow + trail + ticks) * edge * uOn);
}`;

export function createFace(canvas, { labels = [], onTelemetry } = {}) {
  const S = { opacity: 0, x: 0.22, y: 0, scale: 1, fracture: 0, scanY: 1.5, scanOn: 0, classify: 0, finale: 0, spin: 0, dim: 0, labels: 0, line: 1 };
  const api = { state: S, ready: null, ok: false, setActive: () => {}, mode: 'none' };
  let resolveReady;
  api.ready = new Promise((r) => (resolveReady = r));

  init().catch((err) => { console.warn('[veritas] face hero unavailable:', err); resolveReady(false); });
  return api;

  async function init() {
    const [THREE, data] = await Promise.all([import('three'), loadFace()]);
    const cloud = buildCloud(data);
    // share of the scanned surface (above the scan plane) that lies in the swapped inner face
    api.stats = (scanY) => {
      let sc = 0, fl = 0;
      for (let i = 0; i < cloud.N; i++) if (cloud.pos[i * 3 + 1] > scanY) { sc++; if (cloud.inner[i] > 0.5) fl++; }
      return { scanned: sc / cloud.N, flagged: sc ? fl / sc : 0 };
    };
    let renderer;
    try {
      const test = document.createElement('canvas');
      if (!(test.getContext('webgl2') || test.getContext('webgl'))) throw new Error('no webgl');
      renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, powerPreference: 'high-performance' });
    } catch (e) {
      document.documentElement.classList.add('no-webgl');
      start2D(cloud);
      return;
    }
    api.mode = 'webgl';
    const raw = (hex) => new THREE.Color().setHex(hex, THREE.LinearSRGBColorSpace);
    renderer.setClearColor(HEX.ink, 1);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
    camera.position.set(0, 0, 7.2);
    const group = new THREE.Group();
    scene.add(group);

    const uniforms = {
      uTime: { value: 0 }, uFracture: { value: 0 }, uScanY: { value: 1.5 }, uScanOn: { value: 0 }, uClassify: { value: 0 },
      uFinale: { value: 0 }, uOpacity: { value: 0 }, uDim: { value: 0 }, uSize: { value: 28 }, uPR: { value: 1 }, uLine: { value: 0.16 },
      // raw sRGB components straight into the shader (custom shaders skip colour management)
      cBone: { value: raw(HEX.bone) }, cAuth: { value: raw(HEX.auth) }, cSynth: { value: raw(HEX.synth) }, cScan: { value: raw(HEX.scan) },
    };

    const attr = (g, n) => {
      g.setAttribute('position', new THREE.BufferAttribute(cloud.pos.subarray(0, n * 3), 3));
      g.setAttribute('aDir', new THREE.BufferAttribute(cloud.dir.subarray(0, n * 3), 3));
      g.setAttribute('aShard', new THREE.BufferAttribute(cloud.shard.subarray(0, n * 4), 4));
      g.setAttribute('aRand', new THREE.BufferAttribute(cloud.rnd.subarray(0, n * 4), 4));
      g.setAttribute('aInner', new THREE.BufferAttribute(cloud.inner.subarray(0, n), 1));
      g.setAttribute('aSize', new THREE.BufferAttribute(cloud.size.subarray(0, n), 1));
      return g;
    };
    const pg = attr(new THREE.BufferGeometry(), cloud.N);
    const pm = new THREE.ShaderMaterial({ uniforms, vertexShader: PTS_VS, fragmentShader: PTS_FS, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending });
    const points = new THREE.Points(pg, pm);
    const lg = attr(new THREE.BufferGeometry(), cloud.nV);
    lg.setIndex(cloud.edges);
    const lm = new THREE.ShaderMaterial({ uniforms, vertexShader: LN_VS, fragmentShader: LN_FS, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending });
    const lines = new THREE.LineSegments(lg, lm);
    group.add(lines, points);

    const bgU = { uTime: uniforms.uTime, uOpacity: { value: 0 }, uFinale: uniforms.uFinale, cScan: uniforms.cScan, cAuth: uniforms.cAuth };
    const backdrop = new THREE.Mesh(new THREE.PlaneGeometry(3.3, 3.3), new THREE.ShaderMaterial({ uniforms: bgU, vertexShader: SCAN_VS, fragmentShader: BG_FS, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }));
    backdrop.renderOrder = -1;
    scene.add(backdrop);
    const scanU = { uOn: { value: 0 }, cScan: uniforms.cScan };
    const scan = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 1.0), new THREE.ShaderMaterial({ uniforms: scanU, vertexShader: SCAN_VS, fragmentShader: SCAN_FS, transparent: true, depthWrite: false, depthTest: false, blending: THREE.AdditiveBlending }));
    scene.add(scan);

    // pointer parallax
    const ptr = { x: 0, y: 0, tx: 0, ty: 0 };
    addEventListener('pointermove', (e) => { ptr.tx = (e.clientX / innerWidth) * 2 - 1; ptr.ty = (e.clientY / innerHeight) * 2 - 1; }, { passive: true });

    let W = 0, H = 0, visH = 1, visW = 1;
    const resize = () => {
      W = innerWidth; H = innerHeight;
      const pr = Math.min(window.devicePixelRatio || 1, W * H > 2.2e6 ? 1.25 : 1.6);
      renderer.setPixelRatio(pr);
      renderer.setSize(W, H, false);
      camera.aspect = W / H; camera.updateProjectionMatrix();
      visH = 2 * camera.position.z * Math.tan((camera.fov * Math.PI) / 360);
      visW = visH * camera.aspect;
      uniforms.uPR.value = pr;
      uniforms.uSize.value = 30 * (H / 1080) * (W < 800 ? 1.3 : 1);
    };
    resize();
    addEventListener('resize', resize);

    const lmIdx = labels.map((el) => +el.dataset.lm);
    const tmp = new THREE.Vector3();
    let active = false, raf = 0, t0 = performance.now(), lastTele = 0;
    const rotState = { yaw: 0, pitch: 0 };

    const frame = (now) => {
      raf = 0;
      if (!active || document.hidden) return;
      const t = (now - t0) / 1000;
      ptr.x += (ptr.tx - ptr.x) * 0.05; ptr.y += (ptr.ty - ptr.y) * 0.05;
      const still = reduceMotion ? 0 : 1;
      rotState.yaw = (Math.sin(t * 0.23) * 0.42 + Math.sin(t * 0.07) * 0.12) * still + ptr.x * 0.32 + S.spin;
      rotState.pitch = (Math.sin(t * 0.17) * 0.07) * still + ptr.y * 0.14 - 0.04;
      group.rotation.set(rotState.pitch, rotState.yaw, 0);
      const sc = S.scale * (W < 800 ? 0.9 : 1);
      group.scale.setScalar(sc);
      group.position.set(S.x * visW, S.y * visH, 0);
      scan.position.set(group.position.x, group.position.y + S.scanY * sc, 0.6);
      backdrop.position.set(group.position.x, group.position.y, -1.2);
      backdrop.scale.setScalar(sc);
      bgU.uOpacity.value = S.opacity * (1 - S.fracture * 0.6) * (1 - S.dim * 0.5);
      scan.scale.setScalar(sc);
      uniforms.uTime.value = t;
      uniforms.uFracture.value = S.fracture;
      uniforms.uScanY.value = S.scanY;
      uniforms.uScanOn.value = S.scanOn;
      uniforms.uClassify.value = S.classify;
      uniforms.uFinale.value = S.finale;
      uniforms.uOpacity.value = S.opacity;
      uniforms.uDim.value = S.dim;
      uniforms.uLine.value = 0.16 * S.line * (1 - S.fracture * 0.5);
      scanU.uOn.value = S.scanOn * S.opacity;
      renderer.render(scene, camera);

      if (labels.length) {
        const lo = S.labels * S.opacity;
        group.updateMatrixWorld();
        for (let i = 0; i < labels.length; i++) {
          const el = labels[i], k = lmIdx[i];
          if (lo < 0.01) { if (el._o !== 0) { el.style.opacity = 0; el._o = 0; } continue; }
          tmp.set(cloud.pos[k * 3], cloud.pos[k * 3 + 1], cloud.pos[k * 3 + 2]).applyMatrix4(group.matrixWorld).project(camera);
          const sx = (tmp.x * 0.5 + 0.5) * W, sy = (-tmp.y * 0.5 + 0.5) * H;
          const left = cloud.pos[k * 3] < -0.05 || k === 152 && false;
          if (el._left !== left) { el.classList.toggle('is-left', left); el._left = left; }
          const w = el._w || (el._w = el.offsetWidth);
          el.style.transform = `translate(${(left ? sx - w + 3.5 : sx - 3.5).toFixed(1)}px, ${(sy - 7).toFixed(1)}px)`;
          el.style.opacity = lo.toFixed(3); el._o = lo;
        }
      }
      if (onTelemetry && now - lastTele > 100) {
        lastTele = now;
        onTelemetry({ yaw: (rotState.yaw * 180) / Math.PI, pitch: (-rotState.pitch * 180) / Math.PI });
      }
      raf = requestAnimationFrame(frame);
    };
    api.setActive = (on) => {
      if (on === active) return;
      active = on;
      canvas.classList.toggle('is-on', on);
      if (on && !raf) raf = requestAnimationFrame(frame);
    };
    document.addEventListener('visibilitychange', () => { if (!document.hidden && active && !raf) raf = requestAnimationFrame(frame); });
    api.ok = true;
    renderer.compile(scene, camera);
    resolveReady(true);
  }

  // Canvas-2D fallback (no WebGL): same data, simple projection.
  function start2D(cloud) {
    api.mode = '2d';
    const cv = document.getElementById('face-2d');
    if (!cv) { resolveReady(false); return; }
    const ctx = cv.getContext('2d');
    let active = false, raf = 0, t0 = performance.now();
    const step = Math.max(1, Math.floor(cloud.N / 3000));
    const frame = (now) => {
      raf = 0;
      if (!active) return;
      const t = (now - t0) / 1000;
      const dpr = Math.min(1.5, devicePixelRatio || 1);
      const w = cv.clientWidth * dpr, h = cv.clientHeight * dpr;
      if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
      ctx.fillStyle = '#04060a'; ctx.fillRect(0, 0, w, h);
      const yaw = (reduceMotion ? 0 : Math.sin(t * 0.23) * 0.42) + S.spin, cy = Math.cos(yaw), sy = Math.sin(yaw);
      const sc = h * 0.27 * S.scale, ox = w * (0.5 + S.x), oy = h * (0.5 - S.y);
      for (let i = 0; i < cloud.N; i += (i < cloud.nV ? 1 : step)) {
        let x = cloud.pos[i * 3], y = cloud.pos[i * 3 + 1], z = cloud.pos[i * 3 + 2];
        const f = S.fracture * (0.5 + cloud.shard[i * 4 + 3] * 0.65) * 0.62;
        x += cloud.shard[i * 4] * f * 1.25; y += cloud.shard[i * 4 + 1] * f * 0.85; z += f * 0.5;
        const X = x * cy + z * sy, Z = -x * sy + z * cy;
        const persp = 7.2 / (7.2 - Z);
        const passed = (cloud.pos[i * 3 + 1] > S.scanY ? 1 : 0) * S.classify;
        const inner = cloud.inner[i];
        let col = passed > 0.5 ? (inner > 0.5 ? '255,59,92' : '62,242,196') : '217,214,206';
        if (S.finale > 0.5) col = '62,242,196';
        const a = (i < cloud.nV ? 0.9 : 0.35) * S.opacity;
        ctx.fillStyle = `rgba(${col},${a})`;
        const s = (i < cloud.nV ? 2.2 : 1.2) * dpr;
        ctx.fillRect(ox + X * sc * persp - s / 2, oy - y * sc * persp - s / 2, s, s);
      }
      if (S.scanOn > 0.01) {
        const yy = oy - S.scanY * sc;
        ctx.fillStyle = `rgba(106,168,255,${0.8 * S.scanOn})`; ctx.fillRect(ox - sc * 1.4, yy, sc * 2.8, 1.5 * dpr);
      }
      raf = requestAnimationFrame(frame);
    };
    api.setActive = (on) => { active = on; cv.style.opacity = on ? 1 : 0; if (on && !raf) raf = requestAnimationFrame(frame); };
    api.ok = true;
    resolveReady(true);
  }
}
