// VERITAS lab — TEMPORARY Spot-the-Fake fixture, used only with ?mock=1 (real data: web/samples/game/manifest.json).
// Procedural placeholder scenes; labels are arbitrary and exist only to exercise the game UI.

import { rng } from './util.js';

const W = 960, H = 720;
const cv = () => { const c = document.createElement('canvas'); c.width = W; c.height = H; return c; };

function sky(g, top, bottom, R) {
  const s = g.createLinearGradient(0, 0, 0, H); s.addColorStop(0, top); s.addColorStop(1, bottom);
  g.fillStyle = s; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 40; i++) { g.fillStyle = `rgba(255,255,255,${R() * 0.05})`; g.beginPath(); g.arc(R() * W, R() * H * 0.5, R() * 60 + 10, 0, 7); g.fill(); }
}
function ridge(g, y, amp, color, R) {
  g.fillStyle = color; g.beginPath(); g.moveTo(0, H);
  for (let x = 0; x <= W; x += 16) g.lineTo(x, y + Math.sin(x / (80 + R() * 4)) * amp * 0.5 + Math.sin(x / 31) * amp * 0.25 + (R() - 0.5) * amp * 0.2);
  g.lineTo(W, H); g.fill();
}
const scenes = [
  (g, R) => { sky(g, '#f4a26b', '#5a3d6e', R); g.fillStyle = '#ffe2a8'; g.beginPath(); g.arc(W * 0.7, H * 0.42, 60, 0, 7); g.fill(); ridge(g, H * 0.55, 90, '#3a2b45', R); ridge(g, H * 0.7, 60, '#22182c', R); },
  (g, R) => { sky(g, '#0c1630', '#28304a', R); for (let i = 0; i < 26; i++) { const bw = 30 + R() * 50, bh = 120 + R() * 300, x = i * 38; g.fillStyle = `hsl(220,20%,${8 + R() * 8}%)`; g.fillRect(x, H - bh, bw, bh); for (let k = 0; k < 30; k++) { if (R() > 0.55) { g.fillStyle = 'rgba(255,210,130,.85)'; g.fillRect(x + 4 + (k % 3) * (bw / 3.2), H - bh + 8 + Math.floor(k / 3) * 16, 5, 7); } } } },
  (g, R) => { sky(g, '#9fd3ff', '#e9f5ff', R); g.fillStyle = '#1f6f9c'; g.fillRect(0, H * 0.58, W, H); for (let i = 0; i < 60; i++) { g.strokeStyle = `rgba(255,255,255,${0.2 + R() * 0.4})`; g.beginPath(); const y = H * 0.6 + R() * H * 0.4; g.moveTo(R() * W, y); g.lineTo(R() * W, y); g.stroke(); } g.fillStyle = '#e8d6a8'; g.fillRect(0, H * 0.86, W, H); },
  (g, R) => { sky(g, '#c9e3c0', '#e8efe1', R); for (let i = 0; i < 40; i++) { const x = R() * W, h = 200 + R() * 300; g.fillStyle = `hsl(${110 + R() * 30},35%,${18 + R() * 15}%)`; g.beginPath(); g.moveTo(x, H - h); g.lineTo(x - 40 - R() * 30, H); g.lineTo(x + 40 + R() * 30, H); g.fill(); } },
  (g, R) => { sky(g, '#f7d9a0', '#e7b36a', R); for (let k = 0; k < 4; k++) ridge(g, H * (0.45 + k * 0.12), 70, `hsl(32,${55 - k * 5}%,${62 - k * 9}%)`, R); },
  (g, R) => { g.fillStyle = '#2b2522'; g.fillRect(0, 0, W, H); g.fillStyle = '#5b4636'; g.fillRect(0, H * 0.62, W, H); const cols = ['#d94f3d', '#f2c14e', '#7fb069', '#e8e6df']; for (let i = 0; i < 6; i++) { const x = 160 + i * 120 + R() * 30, r = 40 + R() * 40; const gr = g.createRadialGradient(x - r / 3, H * 0.58 - r / 3, 4, x, H * 0.58, r); gr.addColorStop(0, '#fff'); gr.addColorStop(0.25, cols[i % 4]); gr.addColorStop(1, '#111'); g.fillStyle = gr; g.beginPath(); g.arc(x, H * 0.62 - r, r, 0, 7); g.fill(); } },
  (g, R) => { sky(g, '#1b1035', '#41285e', R); for (let i = 0; i < 260; i++) { g.fillStyle = `rgba(255,255,255,${R()})`; g.fillRect(R() * W, R() * H * 0.7, 1.5, 1.5); } ridge(g, H * 0.75, 50, '#0d0818', R); },
];

export async function gameItems() {
  await document.fonts?.ready;
  const items = [];
  for (let i = 0; i < 14; i++) {
    const R = rng(100 + i); const c = cv(); const g = c.getContext('2d');
    scenes[i % scenes.length](g, R);
    g.font = '500 22px "IBM Plex Mono", monospace'; g.fillStyle = 'rgba(255,255,255,.75)'; g.fillText(`MOCK ${String(i + 1).padStart(2, '0')}`, 20, H - 20);
    const label = i % 3 === 1 || i % 4 === 0 ? 'fake' : 'real';
    let ai = label === 'fake' ? 62 + Math.round(R() * 35) : 8 + Math.round(R() * 35);
    if (i === 5 || i === 9) ai = 100 - ai; // the engine gets a couple wrong
    items.push({ file: `mock-${i + 1}.jpg`, src: c.toDataURL('image/jpeg', 0.85), label, ai_score: ai,
      source: label === 'fake' ? 'Mock generator (placeholder)' : 'Mock camera (placeholder)',
      hint: label === 'fake' ? 'Mock hint: look for edges that melt into each other and textures that repeat.' : 'Mock hint: real scenes have consistent shadows and sensor noise everywhere.' });
  }
  return items;
}
