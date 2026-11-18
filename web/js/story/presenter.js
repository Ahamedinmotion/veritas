// VERITAS — presenter mode. Clickers send PageUp/PageDown; keyboards use arrows/space.
// "Stops" are scroll positions (frame tops, or progress points inside pinned stages);
// frames with data-steps also get in-place steps that advance a demo without scrolling.
import { $, $$, pad } from './util.js';

export function createPresenter({ lenis, ScrollTrigger, pins = {}, steppers = new Map() }) {
  let stops = [];
  let cur = 0;
  let moving = false;
  let presenting = false;
  const hint = $('#step-count');
  const keys = $('#keys');

  function absTop(el) { return el.getBoundingClientRect().top + window.scrollY; }

  function compute() {
    // remember where we are, so a resize / fullscreen / late layout change can't strand us between frames
    const prev = stops[cur];
    const wasAligned = prev && Math.abs(window.scrollY - prev.y) < 8;
    const list = [];
    $$('section.ch').forEach((sec) => {
      const ch = +sec.dataset.ch;
      const stage = sec.querySelector('[data-stops]');
      if (stage && pins[stage.id]) {
        const st = pins[stage.id];
        stage.dataset.stops.split(',').map(Number).forEach((p, i) => {
          list.push({ y: Math.round(st.start + p * (st.end - st.start)), ch, el: stage, step: 0, sub: i });
        });
      } else if (stage) {
        list.push({ y: Math.round(absTop(stage)), ch, el: stage, step: 0, sub: 0 });
      }
      $$('[data-stop]', sec).forEach((el) => {
        if (!el.getClientRects().length) return; // hidden frame (e.g. no data yet)
        const y = Math.round(absTop(el));
        const n = +(el.dataset.steps || 0);
        for (let s = 0; s <= n; s++) list.push({ y, ch, el, step: s, sub: 0 });
      });
    });
    list.sort((a, b) => a.y - b.y || a.step - b.step);
    stops = list;
    const i = prev ? stops.findIndex((s) => s.el === prev.el && s.step === prev.step && s.sub === prev.sub) : -1;
    if (i >= 0 && (wasAligned || presenting || moving)) {
      cur = i;
      updateHint();
      // ScrollTrigger restores its own scroll position at the very end of a refresh, after this event,
      // so re-snap on the next frames (and re-aim an animation that was heading for the old position)
      const target = stops[i];
      const snap = () => {
        if (stops[cur] !== target) return;
        if (moving) { scrollToY(target.y); return; }
        if (Math.abs(window.scrollY - target.y) > 2) {
          if (lenis) { lenis.resize && lenis.resize(); lenis.scrollTo(target.y, { immediate: true, force: true }); } else window.scrollTo(0, target.y);
        }
      };
      requestAnimationFrame(() => requestAnimationFrame(snap));
      return;
    }
    syncToScroll();
  }

  function syncToScroll() {
    const y = window.scrollY;
    const c = stops[cur];
    if (c && Math.abs(c.y - y) < 8) { updateHint(); return; } // still on the current stop (incl. its steps)
    let idx = 0;
    for (let i = 0; i < stops.length; i++) if (stops[i].y <= y + 6 && stops[i].step === 0) idx = i;
    cur = idx;
    updateHint();
  }

  function updateHint() {
    if (hint && stops.length) hint.textContent = `${pad(cur + 1)} / ${pad(stops.length)}`;
  }

  function scrollToY(y, done) {
    const dist = Math.abs(window.scrollY - y);
    if (dist < 3) { done && done(); return; }
    moving = true;
    const duration = Math.min(1.9, Math.max(0.9, 0.7 + dist / (innerHeight * 2.4)));
    const finish = () => { moving = false; done && done(); };
    if (lenis) lenis.resize && lenis.resize();
    if (lenis) lenis.scrollTo(y, { duration, easing: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2), lock: true, force: true, onComplete: finish });
    else { window.scrollTo(0, y); setTimeout(finish, 50); }
  }

  function applyStep(stop) {
    const fn = steppers.get(stop.el);
    if (fn) fn(stop.step, stop);
  }

  function go(i) {
    if (!stops.length) compute();
    i = Math.max(0, Math.min(stops.length - 1, i));
    const from = stops[cur];
    const to = stops[i];
    cur = i;
    updateHint();
    if (from && to.el === from.el && to.y === from.y) { applyStep(to); return; }
    // entering a frame: set its step state (0 when arriving fresh, N when arriving backwards)
    applyStep(to);
    scrollToY(to.y);
  }

  const next = () => { presenting = true; window.VX && (window.VX.presenting = true); go(cur + 1); };
  const prev = () => { presenting = true; window.VX && (window.VX.presenting = true); go(cur - 1); };
  const chapter = (n) => {
    presenting = true; window.VX && (window.VX.presenting = true);
    const i = stops.findIndex((s) => s.ch === n && s.step === 0);
    if (i >= 0) go(i);
  };

  // ── keyboard ──
  addEventListener('keydown', (e) => {
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    const typing = t && (t.tagName === 'INPUT' && t.type !== 'range' && t.type !== 'button' || t.tagName === 'TEXTAREA' || t.isContentEditable);
    const onRange = t && t.tagName === 'INPUT' && t.type === 'range';
    const k = e.key;
    if (typing && k !== 'PageDown' && k !== 'PageUp') return;
    wake();
    if (k === 'PageDown' || (k === 'ArrowRight' && !onRange) || (k === ' ' && !e.shiftKey)) { e.preventDefault(); if (t && t.blur && t !== document.body) t.blur(); next(); }
    else if (k === 'PageUp' || (k === 'ArrowLeft' && !onRange) || (k === ' ' && e.shiftKey)) { e.preventDefault(); prev(); }
    else if (k === 'Home') { e.preventDefault(); chapter(0); }
    else if (k === 'End') { e.preventDefault(); presenting = true; window.VX && (window.VX.presenting = true); go(stops.length - 1); }
    else if (/^[0-8]$/.test(k)) { e.preventDefault(); chapter(+k); }
    else if (k === 'f' || k === 'F') { e.preventDefault(); toggleFullscreen(); }
    else if (k === '?' || k === 'h' || k === 'H') { e.preventDefault(); keys.hidden = !keys.hidden; }
    else if (k === 'Escape') { keys.hidden = true; }
  });

  function toggleFullscreen() {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen?.().catch(() => {});
    else document.exitFullscreen?.();
  }
  document.addEventListener('fullscreenchange', () => {
    document.body.classList.toggle('is-fullscreen', !!document.fullscreenElement);
    wake(); // a clicker-only presenter never moves the mouse: start the idle-cursor timer now
    setTimeout(() => ScrollTrigger.refresh(), 300);
  });

  // ── idle cursor (fullscreen only) ──
  let idleT = 0;
  function wake() {
    document.body.classList.remove('is-idle');
    clearTimeout(idleT);
    idleT = setTimeout(() => { if (document.fullscreenElement) document.body.classList.add('is-idle'); }, 2600);
  }
  addEventListener('pointermove', wake, { passive: true });
  addEventListener('pointerdown', wake, { passive: true });

  // ── manual scrolling re-syncs the step counter ──
  // (a resize moves scrollY by itself before ScrollTrigger re-measures: don't treat that as the user scrolling)
  let st = 0, resizedAt = -1e9;
  addEventListener('resize', () => { resizedAt = performance.now(); clearTimeout(st); });
  addEventListener('scroll', () => {
    if (moving || performance.now() - resizedAt < 900) return;
    clearTimeout(st);
    st = setTimeout(syncToScroll, 140);
  }, { passive: true });

  ScrollTrigger.addEventListener('refresh', compute);

  // rail + in-page anchor links go through the same smooth scroller
  document.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const id = a.getAttribute('href').slice(1);
    const el = id && document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    const sec = el.closest('section.ch');
    if (el === sec) { chapter(+sec.dataset.ch); history.replaceState(null, '', '#' + id); return; }
    if (el.closest('.refs')) { scrollToY(absTop(el) - innerHeight * 0.3); el.classList.add('is-target'); history.replaceState(null, '', '#' + id); return; }
    const i = stops.findIndex((s) => s.el === el && s.step === 0);
    if (i >= 0) go(i); else scrollToY(absTop(el));
  });

  return {
    compute, next, prev, chapter, go,
    get presenting() { return presenting; },
    get state() { return { cur, stops: stops.map((s) => ({ y: s.y, ch: s.ch, step: s.step, sub: s.sub, id: s.el.id })) }; },
    jumpToHash(hash, immediate = true) {
      const el = hash && document.getElementById(hash.replace('#', ''));
      if (!el) return;
      compute();
      const sec = el.closest('section.ch');
      let i = el === sec ? stops.findIndex((s) => s.ch === +sec.dataset.ch && s.step === 0) : stops.findIndex((s) => s.el === el && s.step === 0);
      if (i < 0) { // an element inside a frame (e.g. #ref-7 in the credits): open the frame that contains it
        for (let k = 0; k < stops.length; k++) if (stops[k].step === 0 && stops[k].el.contains(el)) i = k;
      }
      if (i < 0) return;
      cur = i;
      const y = stops[i].y;
      if (lenis) { lenis.resize && lenis.resize(); lenis.scrollTo(y, { immediate, force: true }); } else window.scrollTo(0, y);
      updateHint();
    },
  };
}
