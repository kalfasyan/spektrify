// Band thumbnails shared by the filmstrip and the channel grid: fetched once per cube as
// float32, colourised on demand with the current colour map.

import { api } from './api.js';
import { colorize, lut } from './colormaps.js';
import { percentiles } from './util.js';

export class Thumbs {
  constructor() { this.reset(); }

  reset() { this.promise = null; this.data = null; this.meta = null; this.ranges = null; this.global = null; this._bmp = new Map(); }

  load() {
    if (!this.promise) {
      this.promise = api.thumbs(160).then(({ data, meta }) => {
        this.data = data;
        this.meta = meta;
        const n = meta.width * meta.height;
        this.ranges = [];
        let glo = Infinity, ghi = -Infinity;
        for (let b = 0; b < meta.bands; b++) {
          const [lo, hi] = percentiles(data.subarray(b * n, (b + 1) * n), [2, 98], 20000);
          this.ranges.push([lo, hi > lo ? hi : lo + 1e-6]);
          glo = Math.min(glo, lo); ghi = Math.max(ghi, hi);
        }
        this.global = [glo, ghi > glo ? ghi : glo + 1e-6];
        return this;
      });
    }
    return this.promise;
  }

  /** ImageData-backed canvas for band b. norm: 'band' | 'shared'. */
  canvasFor(b, cmap, rev, norm = 'band') {
    const key = `${b}:${cmap}:${rev}:${norm}`;
    let c = this._bmp.get(key);
    if (c) return c;
    const { width: w, height: h } = this.meta;
    const n = w * h;
    c = document.createElement('canvas');
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    const img = ctx.createImageData(w, h);
    const [lo, hi] = norm === 'shared' ? this.global : this.ranges[b];
    colorize(this.data.subarray(b * n, (b + 1) * n), img.data, lo, hi, 1, lut(cmap, rev));
    ctx.putImageData(img, 0, 0);
    if (this._bmp.size > 2000) this._bmp.clear();
    this._bmp.set(key, c);
    return c;
  }
}
