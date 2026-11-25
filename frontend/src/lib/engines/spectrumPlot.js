// Spectrum plot on a 2-D canvas: curves, ±σ envelopes, current-band cursor, RGB markers and a
// wavelength colour strip. Click / drag selects a band; hovering shows every curve's value.
// Emits: 'band' (index).

import { Emitter, TOUCH, fitCanvas, fmt, nearestIndex, ticks, wavelengthColor } from '../util.js';

const PAD = { l: 58, r: 14, t: 12, b: 34 };

export class SpectrumPlot extends Emitter {
  constructor(canvas, tip) {
    super();
    this.canvas = canvas;
    this.tip = tip;
    this.data = null;
    this.hoverIdx = null;
    this._raf = 0;
    new ResizeObserver(() => this.redraw()).observe(canvas);
    this._bind();
  }

  /**
   * data: {axis, unit, wavelengths: bool, band, rgb?: [r,g,b], flagged?: Set,
   *        series: [{id, label, color, values, env?: [lo, hi], dashed?, width?, faint?}],
   *        log: bool, yLabel}
   */
  update(data) { this.data = data; this.redraw(); }

  redraw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._draw(); });
  }

  _geom() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    const d = this.data;
    const ax = d.axis;
    const xmin = ax.reduce((a, b) => Math.min(a, b)), xmax = ax.reduce((a, b) => Math.max(a, b));
    const pw = w - PAD.l - PAD.r, ph = h - PAD.t - PAD.b;
    const span = xmax - xmin || 1;
    const px = (x) => PAD.l + ((x - xmin) / span) * pw;
    return { w, h, xmin, xmax, pw, ph, px };
  }

  _yRange() {
    const d = this.data;
    let lo = Infinity, hi = -Infinity;
    const consider = (arr) => { if (!arr) return; for (const v of arr) if (v != null && Number.isFinite(v) && (!d.log || v > 0)) { if (v < lo) lo = v; if (v > hi) hi = v; } };
    for (const s of d.series) { consider(s.values); if (s.env) { consider(s.env[0]); consider(s.env[1]); } }
    if (!Number.isFinite(lo)) { lo = 0; hi = 1; }
    if (d.log) { lo = Math.log10(lo); hi = Math.log10(hi); }
    if (hi - lo < 1e-12) { const c = (hi + lo) / 2; lo = c - (Math.abs(c) * 0.05 || 0.5); hi = c + (Math.abs(c) * 0.05 || 0.5); }
    const m = (hi - lo) * 0.06;
    return [lo - m, hi + m];
  }

  _draw() {
    const { ctx, w, h } = fitCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    const d = this.data;
    if (!d || !d.axis?.length) return;
    const G = this._geom();
    const [ylo, yhi] = this._yRange();
    const py = (v) => { const t = d.log ? Math.log10(v) : v; return PAD.t + (1 - (t - ylo) / (yhi - ylo)) * G.ph; };
    const css = getComputedStyle(document.documentElement);
    const muted = css.getPropertyValue('--muted').trim(), line = css.getPropertyValue('--line').trim();

    // grid + y ticks
    ctx.font = `10.5px ${css.getPropertyValue('--mono')}`;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    for (const t of ticks(ylo, yhi, Math.max(2, Math.floor(G.ph / 34)))) {
      const y = PAD.t + (1 - (t - ylo) / (yhi - ylo)) * G.ph;
      ctx.strokeStyle = line; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(PAD.l, Math.round(y) + 0.5); ctx.lineTo(w - PAD.r, Math.round(y) + 0.5); ctx.stroke();
      ctx.fillStyle = muted;
      ctx.fillText(d.log ? fmt(10 ** t, 3) : fmt(t, 4), PAD.l - 6, y);
    }
    // flagged bands
    if (d.flagged?.size) {
      ctx.fillStyle = 'rgba(255, 93, 108, .10)';
      const step = G.pw / Math.max(1, d.axis.length - 1);
      for (const b of d.flagged) ctx.fillRect(G.px(d.axis[b]) - Math.max(1.5, step / 2), PAD.t, Math.max(3, step), G.ph);
    }
    // x ticks + colour strip
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const t of ticks(G.xmin, G.xmax, Math.max(2, Math.floor(G.pw / 70)))) {
      const x = G.px(t);
      ctx.strokeStyle = line;
      ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, PAD.t); ctx.lineTo(Math.round(x) + 0.5, PAD.t + G.ph); ctx.stroke();
      ctx.fillStyle = muted;
      ctx.fillText(fmt(t, 4), x, h - PAD.b + 12);
    }
    if (d.wavelengths) {
      const y0 = PAD.t + G.ph + 3;
      for (let x = 0; x < G.pw; x += 2) {
        const nm = G.xmin + (x / G.pw) * (G.xmax - G.xmin);
        const [r, g, b] = wavelengthColor(nm);
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(PAD.l + x, y0, 2, 5);
      }
    }
    ctx.textAlign = 'left'; ctx.fillStyle = muted;
    ctx.fillText(d.unit ? `λ (${d.unit})` : 'band', w - PAD.r - 46, h - 12);
    if (d.yLabel) { ctx.save(); ctx.translate(11, PAD.t + G.ph / 2); ctx.rotate(-Math.PI / 2); ctx.textAlign = 'center'; ctx.fillText(d.yLabel, 0, 0); ctx.restore(); }

    // RGB markers
    if (d.rgb) {
      ['#ff5d5d', '#3ddc97', '#5aa9ff'].forEach((c, k) => {
        const x = G.px(d.axis[d.rgb[k]]);
        ctx.strokeStyle = c; ctx.lineWidth = 2; ctx.globalAlpha = 0.85;
        ctx.beginPath(); ctx.moveTo(x, PAD.t); ctx.lineTo(x, PAD.t + G.ph); ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.fillStyle = c; ctx.beginPath(); ctx.moveTo(x - 5, PAD.t); ctx.lineTo(x + 5, PAD.t); ctx.lineTo(x, PAD.t + 7); ctx.fill();
      });
    }

    ctx.save();
    ctx.beginPath(); ctx.rect(PAD.l, PAD.t - 2, G.pw, G.ph + 4); ctx.clip();
    // envelopes
    for (const s of d.series) {
      if (!s.env) continue;
      const [lo, hi] = s.env;
      ctx.fillStyle = s.color + '2e';
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < d.axis.length; i++) if (hi[i] != null && (!d.log || hi[i] > 0)) { const x = G.px(d.axis[i]), y = py(hi[i]); started ? ctx.lineTo(x, y) : ctx.moveTo(x, y); started = true; }
      for (let i = d.axis.length - 1; i >= 0; i--) if (lo[i] != null && (!d.log || lo[i] > 0)) ctx.lineTo(G.px(d.axis[i]), py(lo[i]));
      ctx.closePath(); ctx.fill();
    }
    // curves
    for (const s of d.series) {
      if (!s.values) continue;
      ctx.strokeStyle = s.color;
      ctx.lineWidth = s.width || 1.7;
      ctx.globalAlpha = s.faint ? 0.6 : 1;
      ctx.setLineDash(s.dashed ? [5, 4] : []);
      ctx.lineJoin = 'round';
      ctx.beginPath();
      let pen = false;
      for (let i = 0; i < d.axis.length; i++) {
        const v = s.values[i];
        if (v == null || !Number.isFinite(v) || (d.log && v <= 0)) { pen = false; continue; }
        const x = G.px(d.axis[i]), y = py(v);
        pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        pen = true;
      }
      ctx.stroke();
      if (d.axis.length <= 40 && !s.dashed) {
        ctx.fillStyle = s.color;
        for (let i = 0; i < d.axis.length; i++) { const v = s.values[i]; if (v != null && Number.isFinite(v) && (!d.log || v > 0)) { ctx.beginPath(); ctx.arc(G.px(d.axis[i]), py(v), 2.2, 0, Math.PI * 2); ctx.fill(); } }
      }
    }
    ctx.setLineDash([]); ctx.globalAlpha = 1;
    ctx.restore();

    // current band cursor
    if (d.band != null) {
      const x = G.px(d.axis[d.band]);
      ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, PAD.t); ctx.lineTo(Math.round(x) + 0.5, PAD.t + G.ph); ctx.stroke();
      ctx.fillStyle = '#fff';
      ctx.beginPath(); ctx.moveTo(x - 5, PAD.t + G.ph + 9); ctx.lineTo(x + 5, PAD.t + G.ph + 9); ctx.lineTo(x, PAD.t + G.ph + 2); ctx.fill();
    }
    // hover cursor
    if (this.hoverIdx != null && this.hoverIdx !== d.band) {
      const x = G.px(d.axis[this.hoverIdx]);
      ctx.strokeStyle = 'rgba(255,255,255,.3)'; ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, PAD.t); ctx.lineTo(Math.round(x) + 0.5, PAD.t + G.ph); ctx.stroke();
      ctx.setLineDash([]);
      for (const s of d.series) {
        const v = s.values?.[this.hoverIdx];
        if (v == null || !Number.isFinite(v) || (d.log && v <= 0)) continue;
        ctx.fillStyle = s.color; ctx.strokeStyle = '#0b0e13'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, py(v), 3.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      }
    }
    // empty hint
    if (!d.series.some((s) => s.values)) {
      ctx.fillStyle = muted; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.font = '12px Inter, system-ui';
      ctx.fillText(TOUCH ? 'Tap the image to see a spectrum' : 'Hover the image to see a spectrum · click to pin it', PAD.l + G.pw / 2, PAD.t + G.ph / 2);
    }
  }

  _idxAt(clientX) {
    const d = this.data;
    if (!d) return null;
    const r = this.canvas.getBoundingClientRect();
    const G = this._geom();
    const x = clientX - r.left;
    const val = G.xmin + ((x - PAD.l) / G.pw) * (G.xmax - G.xmin);
    return nearestIndex(d.axis, val);
  }

  _bind() {
    const c = this.canvas;
    let dragging = false;
    c.addEventListener('pointerdown', (e) => { if (!this.data) return; dragging = true; c.setPointerCapture(e.pointerId); this.emit('band', this._idxAt(e.clientX)); });
    c.addEventListener('pointermove', (e) => {
      if (!this.data) return;
      const i = this._idxAt(e.clientX);
      if (dragging) this.emit('band', i);
      if (i !== this.hoverIdx) { this.hoverIdx = i; this.redraw(); }
      this._showTip(e, i);
    });
    c.addEventListener('pointerup', () => (dragging = false));
    c.addEventListener('pointerleave', () => { this.hoverIdx = null; this.tip.hidden = true; this.redraw(); });
  }

  _showTip(e, i) {
    const d = this.data;
    const rows = d.series.filter((s) => s.values && !s.noTip);
    if (!rows.length) { this.tip.hidden = true; return; }
    const head = `#${i}${d.wavelengths ? ` · ${fmt(d.axis[i], 5)} ${d.unit}` : ''}`;
    this.tip.innerHTML = `<div class="h">${head}</div>` + rows.map((s) => `<div class="r"><span class="sw" style="background:${s.color}"></span><span>${s.label}</span><span style="margin-left:auto">${fmt(s.values[i], 5)}</span></div>`).join('');
    this.tip.hidden = false;
    const wrap = this.canvas.parentElement.getBoundingClientRect();
    const tw = this.tip.offsetWidth, th = this.tip.offsetHeight;
    let x = e.clientX - wrap.left + 14, y = e.clientY - wrap.top - th - 8;
    if (x + tw > wrap.width - 4) x = e.clientX - wrap.left - tw - 14;
    if (y < 4) y = e.clientY - wrap.top + 16;
    this.tip.style.left = `${x}px`; this.tip.style.top = `${y}px`;
  }
}
