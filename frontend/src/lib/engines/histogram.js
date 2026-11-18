// Histogram with draggable low / high stretch handles (log-scaled counts).
// Emits: 'change' {lo: [...], hi: [...]} while dragging, 'commit' on release.

import { Emitter, fitCanvas, histogram, percentiles } from '../util.js';

const CH_COLORS = ['#ff6b6b', '#51cf66', '#4dabf7'];

export class Histogram extends Emitter {
  constructor(canvas) {
    super();
    this.canvas = canvas;
    this.layer = null;
    this.st = null;
    this.hists = null;
    this.range = [0, 1];
    this.active = 0; // channel whose handles are dragged (RGB: nearest)
    new ResizeObserver(() => this.draw()).observe(canvas);
    this._bind();
  }

  set(layer, stretch) {
    if (layer !== this.layer) {
      this.layer = layer;
      this.hists = null;
      if (layer) {
        const all = layer.channels.map((c) => percentiles(c, [0.1, 99.9]));
        let a = Math.min(...all.map((p) => p[0])), b = Math.max(...all.map((p) => p[1]));
        if (!(b > a)) b = a + 1;
        const pad = (b - a) * 0.04;
        this._base = [a - pad, b + pad];
      }
    }
    this.st = stretch;
    if (layer) {
      const lo = Math.min(this._base[0], ...stretch.lo), hi = Math.max(this._base[1], ...stretch.hi);
      const pad = (hi - lo) * 0.02;
      const range = [Math.min(this._base[0], lo - pad), Math.max(this._base[1], hi + pad)];
      if (!this.hists || range[0] !== this.range[0] || range[1] !== this.range[1]) {
        this.range = range;
        this.hists = layer.channels.map((c) => histogram(c, range[0], range[1], 160));
      }
    }
    this.draw();
  }

  _x(v, w) { return ((v - this.range[0]) / (this.range[1] - this.range[0])) * w; }
  _v(x, w) { return this.range[0] + (x / w) * (this.range[1] - this.range[0]); }

  draw() {
    const { ctx, w, h } = fitCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    if (!this.hists) return;
    const n = this.hists[0].length;
    const maxLog = Math.max(...this.hists.map((hh) => Math.log1p(Math.max(...hh))));
    const rgb = this.hists.length === 3;
    ctx.globalCompositeOperation = rgb ? 'lighter' : 'source-over';
    this.hists.forEach((hh, c) => {
      ctx.fillStyle = rgb ? CH_COLORS[c] + '88' : '#6f7d93';
      ctx.beginPath();
      ctx.moveTo(0, h);
      for (let i = 0; i < n; i++) {
        const y = h - 4 - (Math.log1p(hh[i]) / maxLog) * (h - 10);
        ctx.lineTo((i / n) * w, y);
        ctx.lineTo(((i + 1) / n) * w, y);
      }
      ctx.lineTo(w, h);
      ctx.fill();
    });
    ctx.globalCompositeOperation = 'source-over';
    const st = this.st;
    const chans = rgb ? [0, 1, 2] : [0];
    // shade outside the stretch
    if (!rgb) {
      ctx.fillStyle = 'rgba(11,14,19,.55)';
      ctx.fillRect(0, 0, this._x(st.lo[0], w), h);
      ctx.fillRect(this._x(st.hi[0], w), 0, w, h);
    }
    for (const c of chans) {
      const color = rgb ? CH_COLORS[c] : '#e5e9f0';
      for (const v of [st.lo[c], st.hi[c]]) {
        const x = Math.round(this._x(v, w)) + 0.5;
        ctx.strokeStyle = color; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
        ctx.fillStyle = color;
        ctx.beginPath(); ctx.moveTo(x - 5, h); ctx.lineTo(x + 5, h); ctx.lineTo(x, h - 7); ctx.fill();
      }
    }
  }

  _bind() {
    const c = this.canvas;
    let drag = null;
    const pick = (e) => {
      const r = c.getBoundingClientRect();
      const x = e.clientX - r.left;
      const w = r.width;
      let best = null;
      const chans = this.st.lo.length === 3 ? [0, 1, 2] : [0];
      for (const ch of chans) for (const which of ['lo', 'hi']) {
        const d = Math.abs(this._x(this.st[which][ch], w) - x);
        if (!best || d < best.d) best = { d, ch, which };
      }
      return { ...best, w, all: e.altKey || chans.length === 1 ? false : !e.shiftKey };
    };
    c.addEventListener('pointerdown', (e) => {
      if (!this.st) return;
      c.setPointerCapture(e.pointerId);
      drag = pick(e);
      this._move(e, drag);
    });
    c.addEventListener('pointermove', (e) => { if (drag) this._move(e, drag); });
    c.addEventListener('pointerup', () => { if (drag) { drag = null; this.emit('commit', this.st); } });
    c.title = 'Drag the handles to set the stretch. RGB: drag moves all three channels; hold Shift for one channel.';
  }

  _move(e, d) {
    const r = this.canvas.getBoundingClientRect();
    const v = this._v(e.clientX - r.left, d.w);
    const st = { lo: [...this.st.lo], hi: [...this.st.hi] };
    const chans = d.all ? st.lo.map((_, i) => i) : [d.ch];
    if (d.all) {
      // move all channels by the same delta
      const delta = v - this.st[d.which][d.ch];
      for (const ch of chans) st[d.which][ch] += delta;
    } else st[d.which][d.ch] = v;
    for (const ch of chans) {
      if (st.hi[ch] <= st.lo[ch]) {
        const eps = (this.range[1] - this.range[0]) * 1e-3;
        if (d.which === 'lo') st.lo[ch] = st.hi[ch] - eps; else st.hi[ch] = st.lo[ch] + eps;
      }
    }
    this.st = st;
    this.draw();
    this.emit('change', st);
  }
}
