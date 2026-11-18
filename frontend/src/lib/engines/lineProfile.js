// Line-profile panel: a spectral cross-section along a drawn segment (distance × band
// heat map) plus the intensity profile at the current band. Emits 'band'.

import { colorize, lut } from '../colormaps.js';
import { Emitter, fitCanvas, fmt, percentiles, ticks } from '../util.js';

export class LineProfile extends Emitter {
  constructor(canvas, store) {
    super();
    this.canvas = canvas;
    this.store = store;
    this.data = null; // {values: Float32Array (N*C), n, c}
    this._img = null;
    new ResizeObserver(() => this.draw()).observe(canvas);
    canvas.addEventListener('pointerdown', (e) => this._pick(e));
  }

  set(data) {
    this.data = data;
    this._img = null;
    this.draw();
  }

  _heat() {
    const s = this.store.state;
    const key = `${s.cmap}:${s.cmapRev}`;
    if (this._img?.key === key) return this._img.canvas;
    const { values, n, c } = this.data;
    // transpose to (C rows, N cols), flip so the first band is at the bottom
    const t = new Float32Array(n * c);
    for (let i = 0; i < n; i++) for (let b = 0; b < c; b++) t[(c - 1 - b) * n + i] = values[i * c + b];
    const [lo, hi] = percentiles(t, [2, 98]);
    const cv = document.createElement('canvas');
    cv.width = n; cv.height = c;
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(n, c);
    colorize(t, img.data, lo, hi, 1, lut(s.cmap, s.cmapRev));
    ctx.putImageData(img, 0, 0);
    this._img = { key, canvas: cv };
    return cv;
  }

  _layout(w, h) {
    const L = 58, R = 14, T = 10;
    const heatH = Math.max(40, (h - T - 26) * 0.62);
    const gap = 10;
    return { L, R, T, pw: w - L - R, heatH, plotT: T + heatH + gap, plotH: h - (T + heatH + gap) - 22 };
  }

  draw() {
    const { ctx, w, h } = fitCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    if (!this.data) return;
    const s = this.store.state, m = this.store.meta;
    const { values, n, c } = this.data;
    const G = this._layout(w, h);
    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue('--muted').trim(), line = css.getPropertyValue('--line').trim();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(this._heat(), G.L, G.T, G.pw, G.heatH);
    ctx.strokeStyle = line; ctx.strokeRect(G.L - 0.5, G.T - 0.5, G.pw + 1, G.heatH + 1);
    // y labels (bands)
    ctx.font = `10.5px ${css.getPropertyValue('--mono')}`; ctx.fillStyle = muted; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    const by = (b) => G.T + (1 - (b + 0.5) / c) * G.heatH;
    for (const b of ticks(0, c - 1, Math.max(2, Math.floor(G.heatH / 28)))) {
      const bi = Math.round(b);
      ctx.fillText(m.wavelengths ? fmt(m.axis[bi], 4) : `#${bi}`, G.L - 6, by(bi));
    }
    // current band marker
    const yb = by(s.band);
    ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(G.L - 4, Math.round(yb) + 0.5); ctx.lineTo(G.L + G.pw, Math.round(yb) + 0.5); ctx.stroke();

    // profile at current band
    const prof = new Array(n);
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < n; i++) { const v = values[i * c + s.band]; prof[i] = v; if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
    if (!(hi > lo)) { hi = lo + 1; }
    const py = (v) => G.plotT + (1 - (v - lo) / (hi - lo)) * G.plotH;
    const px = (i) => G.L + ((i + 0.5) / n) * G.pw;
    ctx.textAlign = 'right';
    for (const t of ticks(lo, hi, 3)) { ctx.fillStyle = muted; ctx.fillText(fmt(t, 3), G.L - 6, py(t)); ctx.strokeStyle = line; ctx.beginPath(); ctx.moveTo(G.L, Math.round(py(t)) + 0.5); ctx.lineTo(G.L + G.pw, Math.round(py(t)) + 0.5); ctx.stroke(); }
    ctx.strokeStyle = '#e5e9f0'; ctx.lineWidth = 1.5; ctx.beginPath();
    let pen = false;
    for (let i = 0; i < n; i++) { if (!Number.isFinite(prof[i])) { pen = false; continue; } pen ? ctx.lineTo(px(i), py(prof[i])) : ctx.moveTo(px(i), py(prof[i])); pen = true; }
    ctx.stroke();
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = muted;
    for (const t of ticks(0, n - 1, Math.max(2, Math.floor(G.pw / 80)))) ctx.fillText(`${Math.round(t)} px`, px(t), h - 16);
    ctx.textAlign = 'left';
    ctx.fillText(`A → B · ${n} px · profile at ${this.store.bandLabel(s.band, true)}`, G.L + 4, G.plotT - 2 + G.plotH + 4 > h ? G.T : G.plotT - 2);
  }

  _pick(e) {
    if (!this.data) return;
    const r = this.canvas.getBoundingClientRect();
    const G = this._layout(r.width, r.height);
    const y = e.clientY - r.top;
    if (y < G.T || y > G.T + G.heatH) return;
    const b = Math.floor((1 - (y - G.T) / G.heatH) * this.data.c);
    this.emit('band', Math.max(0, Math.min(this.data.c - 1, b)));
  }
}
