// Band scrubber under the image: one tick per band (coloured by wavelength, height by the
// scene-mean value, red for flagged bands). Click / drag to change band. Emits 'band'.

import { Emitter, fitCanvas, wavelengthColor } from '../util.js';

export class Scrubber extends Emitter {
  constructor(canvas) {
    super();
    this.canvas = canvas;
    this.meta = null;
    this.band = 0;
    this.flagged = new Set();
    this.marks = null; // e.g. RGB markers [r,g,b]
    new ResizeObserver(() => this.draw()).observe(canvas);
    let drag = false;
    canvas.addEventListener('pointerdown', (e) => { if (!this.meta) return; drag = true; canvas.setPointerCapture(e.pointerId); this.emit('band', this._at(e)); });
    canvas.addEventListener('pointermove', (e) => { if (drag) this.emit('band', this._at(e)); });
    canvas.addEventListener('pointerup', () => (drag = false));
  }

  set({ meta, band, flagged, marks }) {
    if (meta !== undefined) this.meta = meta;
    if (band !== undefined) this.band = band;
    if (flagged !== undefined) this.flagged = flagged;
    if (marks !== undefined) this.marks = marks;
    this.draw();
  }

  _at(e) {
    const r = this.canvas.getBoundingClientRect();
    const n = this.meta.bands;
    return Math.max(0, Math.min(n - 1, Math.floor(((e.clientX - r.left) / r.width) * n)));
  }

  draw() {
    const { ctx, w, h } = fitCanvas(this.canvas);
    ctx.clearRect(0, 0, w, h);
    const m = this.meta;
    if (!m) return;
    const n = m.bands;
    const bw = w / n;
    const means = m.bandMean;
    const fin = means.filter((v) => v != null);
    const lo = Math.min(...fin), hi = Math.max(...fin);
    for (let i = 0; i < n; i++) {
      const [r, g, b] = m.wavelengths ? wavelengthColor(m.axis[i]) : [120, 140, 170];
      const t = means[i] == null ? 0 : (means[i] - lo) / (hi - lo || 1);
      const bh = 5 + t * (h - 13);
      ctx.fillStyle = `rgba(${r},${g},${b},${i === this.band ? 1 : 0.75})`;
      ctx.fillRect(i * bw + (bw > 3 ? 0.5 : 0), h - 4 - bh, Math.max(1, bw - (bw > 3 ? 1 : 0)), bh);
      if (this.flagged.has(i)) {
        ctx.fillStyle = '#ff5d6c';
        ctx.beginPath(); ctx.arc((i + 0.5) * bw, h - 7 - bh, 2.2, 0, Math.PI * 2); ctx.fill();
      }
    }
    if (this.marks) {
      ['#ff5d5d', '#3ddc97', '#5aa9ff'].forEach((c, k) => {
        const x = (this.marks[k] + 0.5) * bw;
        ctx.fillStyle = c;
        ctx.beginPath(); ctx.moveTo(x - 4, 0); ctx.lineTo(x + 4, 0); ctx.lineTo(x, 6); ctx.fill();
      });
    }
    const x = (this.band + 0.5) * bw;
    ctx.fillStyle = '#fff';
    ctx.fillRect(Math.round(x - Math.max(1, bw / 2)), h - 3, Math.max(2, Math.round(bw)), 3);
    ctx.strokeStyle = 'rgba(255,255,255,.9)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, 2); ctx.lineTo(Math.round(x) + 0.5, h - 3); ctx.stroke();
  }
}
