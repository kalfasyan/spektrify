// Small shared helpers: API access, DOM, formatting, events.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
    else if (k === 'html') e.innerHTML = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}

// ---------------------------------------------------------------- events
export class Emitter {
  constructor() { this._h = new Map(); }
  on(ev, fn) { (this._h.get(ev) || this._h.set(ev, new Set()).get(ev)).add(fn); return () => this.off(ev, fn); }
  off(ev, fn) { this._h.get(ev)?.delete(fn); }
  emit(ev, ...args) { for (const fn of [...(this._h.get(ev) || [])]) fn(...args); }
}

// ---------------------------------------------------------------- formatting
export function fmt(v, digits = 4) {
  if (v == null || Number.isNaN(v)) return 'NaN';
  if (!Number.isFinite(v)) return v > 0 ? '+Inf' : '-Inf';
  const a = Math.abs(v);
  if (a !== 0 && (a < 1e-3 || a >= 1e6)) return v.toExponential(Math.max(1, digits - 2));
  if (Number.isInteger(v) && a < 1e6) return String(v);
  return Number(v.toPrecision(digits)).toString();
}
export function fmtBytes(n) {
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i ? 1 : 0)} ${u[i]}`;
}
export const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

// ---------------------------------------------------------------- canvas
export function fitCanvas(canvas, w = canvas.clientWidth, h = canvas.clientHeight) {
  const dpr = window.devicePixelRatio || 1;
  const W = Math.max(1, Math.round(w * dpr)), H = Math.max(1, Math.round(h * dpr));
  if (canvas.width !== W || canvas.height !== H) { canvas.width = W; canvas.height = H; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h, dpr };
}

/** "Nice" tick values covering [lo, hi]. */
export function ticks(lo, hi, target = 6) {
  if (!(hi > lo)) return [lo];
  const span = hi - lo;
  const raw = span / target;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= target) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

// ---------------------------------------------------------------- stats on typed arrays
/** Percentiles of finite values via a strided sample + sort (fast, ≤ ~200k samples). */
export function percentiles(arr, ps, maxSamples = 200000) {
  const step = Math.max(1, Math.floor(arr.length / maxSamples));
  const s = [];
  for (let i = 0; i < arr.length; i += step) { const v = arr[i]; if (Number.isFinite(v)) s.push(v); }
  if (!s.length) return ps.map(() => 0);
  const f = Float64Array.from(s).sort();
  return ps.map((p) => {
    const x = (p / 100) * (f.length - 1);
    const i = Math.floor(x), t = x - i;
    return f[i] + (f[Math.min(i + 1, f.length - 1)] - f[i]) * t;
  });
}

export function histogram(arr, lo, hi, bins = 128, maxSamples = 400000) {
  const h = new Float64Array(bins);
  const step = Math.max(1, Math.floor(arr.length / maxSamples));
  const k = bins / (hi - lo || 1);
  for (let i = 0; i < arr.length; i += step) {
    const v = arr[i];
    if (!Number.isFinite(v)) continue;
    const b = Math.floor((v - lo) * k);
    if (b >= 0 && b < bins) h[b]++;
    else if (b === bins && v === hi) h[bins - 1]++;
  }
  return h;
}

// ---------------------------------------------------------------- misc
export function download(name, blobOrText, type = 'text/plain') {
  const blob = blobOrText instanceof Blob ? blobOrText : new Blob([blobOrText], { type });
  const a = el('a', { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
}

export function throttleRAF(fn) {
  let pending = false, lastArgs;
  return (...args) => {
    lastArgs = args;
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => { pending = false; fn(...lastArgs); });
  };
}

/** Approximate colour of a wavelength (nm) for visual cues; NIR fades to deep red/grey. */
export function wavelengthColor(nm) {
  let r = 0, g = 0, b = 0;
  if (nm >= 380 && nm < 440) { r = -(nm - 440) / 60; b = 1; }
  else if (nm < 490) { g = (nm - 440) / 50; b = 1; }
  else if (nm < 510) { g = 1; b = -(nm - 510) / 20; }
  else if (nm < 580) { r = (nm - 510) / 70; g = 1; }
  else if (nm < 645) { r = 1; g = -(nm - 645) / 65; }
  else if (nm <= 780) { r = 1; }
  let f = 1;
  if (nm < 380) return [110, 70, 160];
  if (nm < 420) f = 0.3 + 0.7 * (nm - 380) / 40;
  else if (nm > 700 && nm <= 780) f = 0.3 + 0.7 * (780 - nm) / 80;
  if (nm > 780) { const t = Math.min(1, (nm - 780) / 600); return [Math.round(120 - 50 * t), Math.round(40 + 20 * t), Math.round(50 + 30 * t)]; }
  return [r, g, b].map((c) => Math.round(255 * Math.pow(c * f, 0.8)));
}

// Categorical palette for pins / regions (distinct on dark backgrounds).
export const PALETTE = ['#ff6b6b', '#4dabf7', '#51cf66', '#fcc419', '#cc5de8', '#ff922b', '#20c997', '#f06595', '#94d82d', '#748ffc', '#ffa8a8', '#66d9e8'];
