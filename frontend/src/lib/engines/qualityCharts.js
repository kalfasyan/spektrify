// Canvas charts for the data-quality dashboard (framework-free drawing + hit testing).

import { colorize, lut } from '../colormaps.js';
import { fitCanvas, fmt, ticks } from '../util.js';

export const METRICS = [
  { key: 'snr', label: 'SNR', sub: 'mean ÷ noise σ (from neighbour differences)', log: true, lowBad: true },
  { key: 'neighbor_corr', label: 'Neighbour r', sub: 'best correlation with an adjacent band', lowBad: true },
  { key: 'stripe', label: 'Striping', sub: 'strongest column artefact, in noise σ', log: true },
  { key: 'bad_frac', label: 'NaN / Inf', sub: 'fraction of invalid pixels', pct: true },
  { key: 'clip', label: 'Saturation', sub: 'fraction of pixels pinned at the max', pct: true },
  { key: 'mean', label: 'Mean ± σ', sub: 'band radiometry', band: true },
];

/** Stacked per-band metric charts. Returns the geometry needed for hit testing. */
export function drawMetrics(canvas, m, q, bandLabel) {
  const { ctx, w, h } = fitCanvas(canvas);
  ctx.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const muted = css.getPropertyValue('--muted').trim(), line = css.getPropertyValue('--line').trim(), text = css.getPropertyValue('--text-2').trim();
  const L = 110, R = 10, rowH = h / METRICS.length;
  const C = m.bands;
  const x = (b) => L + ((b + 0.5) / C) * (w - L - R);
  const flagged = new Set(q.flags.map((f) => f.band));
  ctx.font = `10.5px ${css.getPropertyValue('--mono')}`;
  METRICS.forEach((mt, r) => {
    const top = r * rowH + 6, bot = (r + 1) * rowH - 10;
    let vals = mt.band ? m.bandMean : q[mt.key];
    const lo2 = mt.band ? m.bandMean.map((v, i) => (v == null ? null : v - (m.bandStd[i] || 0))) : null;
    const hi2 = mt.band ? m.bandMean.map((v, i) => (v == null ? null : v + (m.bandStd[i] || 0))) : null;
    const all = [...vals, ...(lo2 || []), ...(hi2 || [])].filter((v) => v != null && Number.isFinite(v) && (!mt.log || v > 0));
    let lo = Math.min(...all), hi = Math.max(...all);
    if (mt.pct || mt.key === 'neighbor_corr') lo = Math.min(lo, 0);
    if (mt.key === 'neighbor_corr') hi = 1;
    if (!(hi > lo)) hi = lo + 1;
    const T = (v) => (mt.log ? Math.log10(Math.max(v, 1e-12)) : v);
    const [tl, th] = [T(lo), T(hi)];
    const y = (v) => bot - ((T(v) - tl) / (th - tl || 1)) * (bot - top);
    ctx.fillStyle = text; ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    ctx.font = '600 12px Inter, system-ui'; ctx.fillText(mt.label, 0, top);
    ctx.font = `10px ${css.getPropertyValue('--mono')}`; ctx.fillStyle = muted;
    ctx.fillText(mt.pct ? `${fmt(hi * 100, 3)}%` : fmt(hi, 3), 0, top + 17);
    ctx.fillText(mt.pct ? `${fmt(lo * 100, 3)}%` : fmt(lo, 3), 0, bot - 10);
    ctx.strokeStyle = line; ctx.beginPath(); ctx.moveTo(L, bot + 0.5); ctx.lineTo(w - R, bot + 0.5); ctx.stroke();
    for (const b of flagged) { ctx.fillStyle = 'rgba(255,93,108,.13)'; const bw = Math.max(2, (w - L - R) / C); ctx.fillRect(x(b) - bw / 2, top, bw, bot - top); }
    if (lo2) {
      ctx.fillStyle = 'rgba(90,169,255,.18)'; ctx.beginPath();
      for (let b = 0; b < C; b++) if (hi2[b] != null) ctx.lineTo(x(b), y(hi2[b]));
      for (let b = C - 1; b >= 0; b--) if (lo2[b] != null) ctx.lineTo(x(b), y(lo2[b]));
      ctx.fill();
    }
    if (C > 60 || !mt.pct) {
      ctx.strokeStyle = '#5aa9ff'; ctx.lineWidth = 1.5; ctx.beginPath();
      let pen = false;
      for (let b = 0; b < C; b++) { const v = vals[b]; if (v == null || !Number.isFinite(v) || (mt.log && v <= 0)) { pen = false; continue; } pen ? ctx.lineTo(x(b), y(v)) : ctx.moveTo(x(b), y(v)); pen = true; }
      ctx.stroke();
    }
    for (let b = 0; b < C; b++) {
      const v = vals[b];
      if (v == null || !Number.isFinite(v) || (mt.log && v <= 0)) continue;
      if (flagged.has(b) || C <= 60) { ctx.fillStyle = flagged.has(b) ? '#ff5d6c' : '#5aa9ff'; ctx.beginPath(); ctx.arc(x(b), y(v), flagged.has(b) ? 3 : 2, 0, Math.PI * 2); ctx.fill(); }
    }
  });
  // band axis
  ctx.fillStyle = muted; ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
  for (const t of ticks(0, C - 1, 8)) { const b = Math.round(t); ctx.fillText(m.wavelengths ? fmt(m.axis[b], 4) : `#${b}`, x(b), h); }
  return { L, R, rowH, C, w };
}

/** Band-to-band correlation heat map (diverging, −1…1). */
export function drawCorrelation(canvas, corr) {
  const C = Math.round(Math.sqrt(corr.length));
  const cv = document.createElement('canvas');
  cv.width = C; cv.height = C;
  const ctx2 = cv.getContext('2d');
  const img = ctx2.createImageData(C, C);
  colorize(corr, img.data, -1, 1, 1, lut('diverging'));
  ctx2.putImageData(img, 0, 0);
  const { ctx, w } = fitCanvas(canvas);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(cv, 0, 0, w, w);
}

/** |line-artefact score| image (bands bottom→top) for a stripes payload {data, meta}. */
export function drawLineMap(canvas, r, cmap = 'inferno') {
  const [C, N] = r.meta.shape;
  const abs = new Float32Array(C * N);
  for (let b = 0; b < C; b++) for (let i = 0; i < N; i++) abs[(C - 1 - b) * N + i] = Math.abs(r.data[b * N + i]);
  const cv = document.createElement('canvas');
  cv.width = N; cv.height = C;
  const c2 = cv.getContext('2d');
  const img = c2.createImageData(N, C);
  colorize(abs, img.data, 0, 12, 0.6, lut(cmap));
  c2.putImageData(img, 0, 0);
  const { ctx, w, h } = fitCanvas(canvas);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(cv, 0, 0, w, h);
}

/** Band index under the pointer for the metric chart (or null). */
export function metricHit(geom, canvas, e) {
  const r = canvas.getBoundingClientRect();
  const b = Math.floor(((e.clientX - r.left - geom.L) / (geom.w - geom.L - geom.R)) * geom.C);
  if (b < 0 || b >= geom.C) return null;
  return { band: b, metric: METRICS[Math.min(METRICS.length - 1, Math.max(0, Math.floor((e.clientY - r.top) / geom.rowH)))] };
}

/** Fractional (u, v) position of the pointer in a canvas. */
export function canvasUV(canvas, e) {
  const r = canvas.getBoundingClientRect();
  return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
}
