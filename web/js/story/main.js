// VERITAS — THE STORY. Page choreography: loader → hero face → chapters → lab.
// Scroll (Lenis + ScrollTrigger) drives everything; presenter.js adds clicker/keyboard steps.
import { $, $$, clamp, lerp, smooth, pad, reduceMotion } from './util.js';
import { createFace } from './face-hero.js';
import { createPresenter } from './presenter.js';
import { initGAN, initSwap, initDiffusion, initVoice, initThreatWave } from './demos/forge.js';
import { initELA, initNoise, initFFT, initLimitBlur, initJPEG, initMeta, initBlink, initJitter, initSpectro } from './demos/forensics.js';
import { initGame } from './game.js';
import { initSystem } from './system.js';
import { initResults } from './results.js';

const { gsap, ScrollTrigger, SplitText, Lenis } = window;
gsap.registerPlugin(ScrollTrigger, SplitText);
ScrollTrigger.config({ ignoreMobileResize: true });
const root = document.documentElement;
root.classList.add('js');
if (reduceMotion) root.classList.add('reduce');
window.VX = { presenting: false, booting: true };
const initialHash = location.hash && location.hash.length > 1 ? location.hash : '';
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

/* ───────── Smooth scroll ───────── */
let lenis = null;
if (!reduceMotion && Lenis) {
  lenis = new Lenis({ lerp: 0.1, wheelMultiplier: 0.9, smoothWheel: true, autoRaf: false });
  lenis.on('scroll', ScrollTrigger.update);
  gsap.ticker.add((t) => lenis.raf(t * 1000));
  gsap.ticker.lagSmoothing(0);
  lenis.stop();
}
window.VX.lenis = lenis;

/* ───────── Face ───────── */
const labels = $$('#face-labels .flabel');
const tmYaw = $('#tm-yaw'), tmPitch = $('#tm-pitch'), tmScan = $('#tm-scan'), tmSyn = $('#tm-syn');
const sign = (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1).padStart(4, '0') + '°';
const face = createFace($('#face-gl'), {
  labels,
  onTelemetry: ({ yaw, pitch }) => { tmYaw.textContent = sign(yaw); tmPitch.textContent = sign(pitch); },
});
window.VX.face = face;

/* ───────── Loader ───────── */
const pre = { v: 0 };
const barEl = $('#loader-bar'), pctEl = $('#loader-pct'), msgEl = $('#loader-msg');
const msgs = ['INDEXING 468 LANDMARKS', 'CALIBRATING SCAN PLANE', 'LOADING EVIDENCE', 'CASE FILE READY'];
const drawPre = () => {
  barEl.style.transform = `scaleX(${pre.v / 100})`;
  pctEl.textContent = String(Math.round(pre.v)).padStart(3, '0');
  msgEl.textContent = msgs[Math.min(msgs.length - 1, Math.floor(pre.v / 26))];
};
gsap.to(pre, { v: 86, duration: reduceMotion ? 0.1 : 1.5, ease: 'power2.out', onUpdate: drawPre });
const settle = (p, ms) => Promise.race([p, new Promise((r) => setTimeout(r, ms))]);
Promise.all([
  settle(document.fonts ? document.fonts.ready : Promise.resolve(), 3000),
  settle(face.ready, 4000),
  new Promise((r) => setTimeout(r, reduceMotion ? 0 : 1200)),
]).then(() => {
  build();
  gsap.to(pre, { v: 100, duration: 0.4, ease: 'power1.in', onUpdate: drawPre, onComplete: enter });
});

/* ───────── Hero state (animated by the pinned timeline) ───────── */
const H = { intro: 0, x: 0.2, y: 0.035, scale: 1, fracture: 0, scanY: 1.3, scanOn: 0, classify: 0, spin: 0, labels: 0, line: 1 };
let pThreatIn = null, pFinale = null, presenter = null, heroST = null, syncCh = () => {};

function enter() {
  document.body.classList.remove('is-loading');
  const tl = gsap.timeline({ defaults: { ease: 'expo.out' } });
  tl.to('#loader .loader__inner', { y: -30, autoAlpha: 0, duration: 0.5, ease: 'power2.in' })
    .to('#loader', { autoAlpha: 0, duration: 0.8, ease: 'power2.inOut' }, '-=0.1')
    .set('#loader', { display: 'none' });
  tl.to(H, { intro: 1, duration: reduceMotion ? 0.01 : 2.2, ease: 'power2.out' }, 0.4);
  if (!reduceMotion) {
    tl.fromTo('.hero__title .char', { yPercent: 118, rotate: 5 }, { yPercent: 0, rotate: 0, duration: 1.6, stagger: 0.026 }, 0.55)
      .fromTo('.hero__beat--1 .kicker, .hero__lede', { autoAlpha: 0, y: 22 }, { autoAlpha: 1, y: 0, duration: 1.1, stagger: 0.12 }, 1.0)
      .fromTo('.hero__meta, .telemetry, .hero__cue', { autoAlpha: 0 }, { autoAlpha: 1, duration: 1.2, stagger: 0.1 }, 1.1)
      .fromTo('.hud, .rail, .viewfinder, .step-hint', { autoAlpha: 0 }, { autoAlpha: 1, duration: 1.2, clearProps: 'opacity,visibility' }, 1.2);
  }
  if (lenis) lenis.start();
  ScrollTrigger.refresh();
  if (lenis) lenis.resize();
  setTimeout(() => {
    if (initialHash && presenter) presenter.jumpToHash(initialHash);
    else if (lenis) lenis.scrollTo(0, { immediate: true, force: true });
    else window.scrollTo(0, 0);
    setTimeout(() => { syncCh(); window.VX.booting = false; }, 400);
  }, 80);
}

/* ───────── Build all scroll choreography ───────── */
function build() {
  const steppers = new Map();

  // reduced motion: SMIL <animateMotion> ignores the CSS media query, so drop the moving pulses
  if (reduceMotion) $$('svg animateMotion').forEach((a) => a.parentElement && a.parentElement.remove());
  // credits: hide a placeholder line such as "[School Name]" until the team fills it in
  $$('[data-placeholder]').forEach((el) => { if (/^\s*\[.*\]\s*$/.test(el.textContent)) el.hidden = true; });
  const reg = (el, p) => Promise.resolve(p).then((fn) => { if (typeof fn === 'function') steppers.set(el, fn); }).catch((e) => console.warn('[veritas] demo failed', e));

  /* Hero: pinned scrub through four beats */
  if (!reduceMotion) SplitText.create('.hero__title .l', { type: 'chars', charsClass: 'char' });
  const beats = $$('.hero__beat');
  const tl = gsap.timeline({ defaults: { ease: 'power2.inOut' } });
  tl.to('.hero__title .l', { yPercent: -40, autoAlpha: 0, stagger: 0.08, duration: 0.9 }, 0.2)
    .to('.hero__beat--1 .kicker, .hero__lede', { autoAlpha: 0, y: -20, duration: 0.7 }, 0.2)
    .to('.hero__cue', { autoAlpha: 0, duration: 0.4 }, 0)
    .to(H, { scale: 1.16, x: 0.21, duration: 1.6 }, 0.2)
    .fromTo(beats[1], { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.8, ease: 'power3.out' }, 1.3)
    .to(H, { labels: 1, duration: 0.6 }, 1.5)
    .to({}, { duration: 1.4 }, 2.1)
    .to(beats[1], { autoAlpha: 0, y: -40, duration: 0.6 }, 3.6)
    .to(H, { labels: 0, duration: 0.4 }, 3.6)
    .to(H, { fracture: 1, spin: 0.55, duration: 1.7, ease: 'power2.out' }, 3.8)
    .fromTo(beats[2], { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.8, ease: 'power3.out' }, 4.4)
    .to({}, { duration: 1 }, 5.2)
    .to(H, { fracture: 0, spin: 0, duration: 1.3, ease: 'power3.inOut' }, 6.1)
    .to(beats[2], { autoAlpha: 0, y: -40, duration: 0.6 }, 6.1)
    .set(H, { classify: 1 }, 7.0)
    .to(H, { scanOn: 1, duration: 0.25, ease: 'none' }, 7.0)
    .fromTo(H, { scanY: 1.25 }, { scanY: -1.22, duration: 2.0, ease: 'none' }, 7.0)
    .to(H, { scanOn: 0, duration: 0.3, ease: 'none' }, 9.0)
    .fromTo(beats[3], { autoAlpha: 0, y: 40 }, { autoAlpha: 1, y: 0, duration: 0.8, ease: 'power3.out' }, 7.6)
    .to({}, { duration: 0.6 }, 9.3);
  heroST = ScrollTrigger.create({ trigger: '#hero-stage', start: 'top top', end: () => `+=${innerHeight * (reduceMotion ? 0.01 : 3.4)}`, pin: true, scrub: reduceMotion ? true : 0.7, animation: tl, invalidateOnRefresh: true });
  if (reduceMotion) tl.progress(1);


  /* Threat */
  initThreatWave();
  ScrollTrigger.create({ trigger: '.casefile', start: 'top 72%', once: true, onEnter: () => $$('.redact').forEach((r, i) => setTimeout(() => r.classList.add('is-open'), (reduceMotion ? 0 : 350) + i * 300)) });

  /* Forge */
  reg($('#gan'), initGAN($('#gan')));
  reg($('#swap'), initSwap($('#swap')));
  reg($('#diffusion'), initDiffusion($('#diffusion')));
  reg($('#voice'), initVoice($('#voice')));

  /* Challenge */
  reg($('#challenge .frame'), initGame());

  /* Forensics */
  reg($('#ex-ela'), initELA($('#ex-ela')));
  reg($('#ex-noise'), initNoise($('#ex-noise')));
  reg($('#ex-fft'), initFFT($('#ex-fft')));
  reg($('#ex-jpeg'), initJPEG($('#ex-jpeg')));
  reg($('#ex-meta'), initMeta($('#ex-meta')));
  reg($('#ex-blink'), initBlink($('#ex-blink')));
  reg($('#ex-jitter'), initJitter($('#ex-jitter')));
  reg($('#ex-audio'), initSpectro($('#ex-audio')));
  initLimitBlur();

  /* System: pinned, five states */
  const sys = initSystem();
  const sysStage = $('#system-stage');
  let sysST = null;
  if (innerWidth > 800 && !reduceMotion) {
    sysST = ScrollTrigger.create({
      trigger: sysStage, start: 'top top', end: () => `+=${innerHeight * 2.6}`, pin: true, invalidateOnRefresh: true,
      onUpdate: (self) => sys.apply(Math.round(self.progress * 5)),
      onRefresh: () => requestAnimationFrame(sys.layout),
    });
  } else {
    ScrollTrigger.create({ trigger: sysStage, start: 'top 60%', once: true, onEnter: () => sys.apply(5) });
  }
  steppers.set(sysStage, sys.stepper);

  /* Face visibility probes — created after every pin so their positions include pin spacing */
  pThreatIn = ScrollTrigger.create({ trigger: '#threat', start: 'top bottom', end: 'top 30%' });
  pFinale = ScrollTrigger.create({ trigger: '#lab', start: 'top 90%', end: 'top 20%' });
  requestAnimationFrame(sys.layout);

  /* Results */
  initResults().then(() => ScrollTrigger.refresh());

  /* Generic reveals */
  if (!reduceMotion) {
    SplitText.create('[data-split]', {
      type: 'lines', mask: 'lines', linesClass: 'split-line', autoSplit: true,
      onSplit: (self) => gsap.from(self.lines, { yPercent: 108, duration: 1.2, ease: 'expo.out', stagger: 0.1, scrollTrigger: { trigger: self.elements[0], start: 'top 88%' } }),
    });
    gsap.set('.reveal', { autoAlpha: 0, y: 36 });
    ScrollTrigger.batch('.reveal', {
      start: 'top 92%', once: true,
      onEnter: (els) => gsap.to(els, { y: 0, autoAlpha: 1, duration: 1, ease: 'power3.out', stagger: 0.08, overwrite: true }),
    });
    $$('.frame--demo').forEach((fr) => {
      const viz = $('.col--viz', fr), txt = $$('.col--text > *', fr);
      gsap.from(txt, { autoAlpha: 0, y: 26, duration: 0.9, ease: 'power3.out', stagger: 0.06, scrollTrigger: { trigger: fr, start: 'top 70%' } });
      if (viz) gsap.from(viz, { autoAlpha: 0, y: 40, scale: 0.98, duration: 1.2, ease: 'expo.out', scrollTrigger: { trigger: fr, start: 'top 70%' } });
    });
    $$('.eyebrow').forEach((el) => {
      if (el.closest('.frame--demo') || el.closest('.hero')) return;
      gsap.from(el, { autoAlpha: 0, x: -18, duration: 0.9, ease: 'power3.out', scrollTrigger: { trigger: el, start: 'top 92%' } });
    });
    gsap.from('.pipe__col', { y: 30, duration: 1, ease: 'power3.out', stagger: 0.08, scrollTrigger: { trigger: '#system', start: 'top 70%' } });
  }

  /* Counters */
  $$('[data-count]').forEach((el) => {
    const end = parseFloat(el.dataset.count), dec = +(el.dataset.decimals || 0), suf = el.dataset.suffix || '';
    const fmt = (v) => (dec ? v.toFixed(dec) : Math.round(v).toLocaleString('en-US')) + suf;
    if (reduceMotion) { el.textContent = fmt(end); return; }
    const o = { v: 0 };
    el.textContent = fmt(0);
    gsap.to(o, { v: end, duration: 2.2, ease: 'expo.out', onUpdate: () => { el.textContent = fmt(o.v); }, scrollTrigger: { trigger: el, start: 'top 90%', once: true } });
  });

  /* Chapters → rail + HUD + hash */
  const railLinks = $$('#rail a');
  const hudNum = $('#hud-num'), hudName = $('#hud-name');
  let curCh = -1;
  const setCh = (n, sec) => {
    if (n === curCh) return;
    curCh = n;
    railLinks.forEach((a) => a.classList.toggle('is-active', +a.dataset.go === n));
    hudNum.textContent = pad(n); hudName.textContent = sec.dataset.title;
    const h = n === 0 ? location.pathname + location.search : `#${sec.id}`;
    if (!window.VX.booting) history.replaceState(null, '', h);
  };
  $$('section.ch').forEach((sec) => {
    ScrollTrigger.create({ trigger: sec, start: 'top 50%', end: 'bottom 50%', onToggle: (s) => s.isActive && setCh(+sec.dataset.ch, sec) });
  });
  const secs = $$('section.ch');
  syncCh = () => {
    const mid = window.scrollY + innerHeight / 2;
    let n = 0, el = secs[0];
    secs.forEach((sec) => { if (sec.getBoundingClientRect().top + window.scrollY <= mid) { n = +sec.dataset.ch; el = sec; } });
    setCh(n, el);
  };
  syncCh();
  const fill = $('#rail-fill');

  /* Per-frame composition: face state + rail + timecode */
  const tc = $('#hud-tc');
  const t0 = performance.now();
  let lastTc = 0, lastScan = '', lastSyn = '', lastFill = -1;
  // scrollHeight forces layout: measure it only when the layout changes, never per frame
  let maxScroll = 1;
  const measure = () => { maxScroll = Math.max(1, document.documentElement.scrollHeight - innerHeight); };
  measure();
  ScrollTrigger.addEventListener('refresh', measure);
  addEventListener('resize', measure);
  gsap.ticker.add(() => {
    const f = Math.round(clamp(window.scrollY / maxScroll) * 1000) / 1000;
    if (f !== lastFill) { lastFill = f; fill.style.transform = `scaleY(${f})`; }
    const now = performance.now();
    if (now - lastTc > 100) {
      lastTc = now;
      const s = (now - t0) / 1000;
      tc.textContent = `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(Math.floor(s) % 60)}:${pad(Math.floor((s % 1) * 25))}`;
    }
    if (!face.ok) return;
    const F = face.state;
    const heroVis = H.intro * (1 - smooth(0, 1, pThreatIn.progress));
    const finVis = smooth(0, 1, pFinale.progress);
    if (finVis > heroVis) {
      F.opacity = finVis * 0.95; F.finale = 1; F.x = innerWidth < 800 ? 0 : 0.24; F.y = 0.02; F.scale = 1.32; F.dim = 0.25;
      F.fracture = 0; F.scanOn = 0; F.classify = 0; F.spin = 0; F.labels = 0;
    } else {
      F.opacity = heroVis; F.finale = 0; F.x = innerWidth < 800 ? 0 : H.x; F.y = innerWidth < 800 ? 0.24 : H.y; F.scale = innerWidth < 800 ? H.scale * 0.8 : H.scale; F.dim = 0;
      F.fracture = H.fracture; F.scanOn = H.scanOn; F.scanY = H.scanY; F.classify = H.classify; F.spin = H.spin; F.labels = H.labels;
    }
    face.setActive(F.opacity > 0.004);
    // telemetry
    let scan = 'STANDBY', syn = '—';
    if (H.classify > 0.5 && heroVis > 0.01) {
      const p = clamp((1.25 - H.scanY) / 2.47);
      scan = p >= 0.999 ? 'COMPLETE' : `SCANNING ${Math.round(p * 100)}%`;
      const st = face.stats ? face.stats(H.scanY) : null;
      if (st && st.scanned > 0.02) syn = `${Math.round(st.flagged * 100)}% OF SCANNED`;
    }
    if (scan !== lastScan) { tmScan.textContent = scan; tmScan.classList.toggle('is-live', scan !== 'STANDBY'); lastScan = scan; }
    if (syn !== lastSyn) { tmSyn.textContent = syn; tmSyn.classList.toggle('is-hot', syn !== '—'); lastSyn = syn; }
  });

  /* Presenter */
  presenter = createPresenter({ lenis, ScrollTrigger, pins: { 'hero-stage': heroST, ...(sysST ? { 'system-stage': sysST } : {}) }, steppers });
  window.VX.presenter = presenter;
  presenter.compute();
  if (lenis) ScrollTrigger.addEventListener('refresh', () => lenis.resize());

  // images/fonts can shift layout a hair; re-measure once everything has settled
  addEventListener('load', () => ScrollTrigger.refresh());
}
