// Turn MediaPipe contour edge lists into SVG path data, with optional "identity" warps
// so the diagrams can show abstract, non-identifiable person A / person B faces.
const GROUPS = ['face_oval', 'left_eye', 'right_eye', 'left_eyebrow', 'right_eyebrow', 'lips', 'nose'];

export function warpPoint(x, y, z, w = {}) {
  const { sx = 1, sy = 1, eye = 1, brow = 0, smile = 0, jaw = 1 } = w;
  let X = x * sx, Y = y * sy;
  if (y < -0.35) X *= jaw;                                   // jaw width
  const inEye = Math.abs(Math.abs(x) - 0.36) < 0.2 && Math.abs(y - 0.36) < 0.12;
  if (inEye) { const cx = Math.sign(x) * 0.36 * sx; X = cx + (X - cx) * eye; Y = 0.36 * sy + (Y - 0.36 * sy) * eye; }
  if (y > 0.5 && y < 0.8 && Math.abs(x) > 0.1) Y += brow;   // raised brows
  if (smile && y < -0.3 && y > -0.62 && Math.abs(x) > 0.08) Y += smile * Math.min(1, (Math.abs(x) - 0.08) / 0.2);
  return [X, Y];
}

export function facePath(data, { size = 80, cx = 40, cy = 42, scale = 0.44, warp = {} } = {}) {
  const V = data.vertices;
  const s = size * scale;
  let d = '';
  for (const g of GROUPS) {
    const e = data.contours[g];
    if (!e) continue;
    for (let i = 0; i < e.length; i += 2) {
      const a = e[i], b = e[i + 1];
      const [x1, y1] = warpPoint(V[a * 3], V[a * 3 + 1], V[a * 3 + 2], warp);
      const [x2, y2] = warpPoint(V[b * 3], V[b * 3 + 1], V[b * 3 + 2], warp);
      d += `M${(cx + x1 * s).toFixed(1)} ${(cy - y1 * s).toFixed(1)}L${(cx + x2 * s).toFixed(1)} ${(cy - y2 * s).toFixed(1)}`;
    }
  }
  return d;
}

export const IDENT = {
  A: { sx: 1.07, sy: 0.98, eye: 1.12, jaw: 1.06 },
  B: { sx: 0.9, sy: 1.06, eye: 0.88, brow: 0.05, jaw: 0.86 },
};
