// Application state (a Svelte 5 `$state` proxy, so components react to it directly), data caches and "layers" (what the image view displays).
//
// Components read `store.state`; engines and the controller call `store.set(patch)` and listen
// to `store.on('change', keys)`.
// Data fetching that several components share (bands, products, marks' spectra) lives here.

import { api } from './api.js';
import { Emitter, PALETTE, percentiles } from './util.js';

const BAND_CACHE_BYTES = 768 * 2 ** 20;

class Store extends Emitter {
  constructor() {
    super();
    this.state = $state({
      meta: null,
      cmapPicked: false,
      view: 'image',
      mode: 'band',
      band: 0,
      rgb: [0, 0, 0],
      pcaOffset: 0,
      pcaAsRgb: true,
      anomaly: 'rx',
      anomalyK: 3,
      simRef: 'mean',
      simDeg: 0,
      anomalyTop: 0,
      summary: 'mean',
      mathExpr: '',
      cmap: 'viridis',
      cmapRev: false,
      lockStretch: false,
      gamma: 1,
      preset: '2',
      overlays: { nan: true, clip: false, values: true, defects: false },
      tool: 'inspect',
      marks: [],
      refMark: null,
      hover: null,
      line: null,
      specView: 'values',
      specStd: true,
      specMean: false,
      specLog: false,
      quality: null,
    });
    this._bands = new Map(); // i -> Promise<Float32Array>
    this._bandBytes = 0;
    this._products = new Map(); // key -> Promise<{channels, meta}>
    this._stretch = new Map(); // layer key -> {lo:[..], hi:[..]}
    this._markSeq = 0;
  }

  set(patch) {
    const keys = Object.keys(patch).filter((k) => this.state[k] !== patch[k]);
    if (!keys.length) return;
    Object.assign(this.state, patch);
    this.emit('change', new Set(keys));
  }

  get meta() { return this.state.meta; }
  get nBands() { return this.state.meta?.bands || 0; }

  // ---------------------------------------------------------------- cube lifecycle
  async load() {
    const meta = frozen(await api.meta());
    this._bands.clear(); this._bandBytes = 0; this._products.clear(); this._stretch.clear();
    if (!meta.loaded) { this.set({ meta: null }); this.emit('cube', null); return null; }
    meta.bandMean = meta.band_stats.map((s) => s.mean ?? null);
    meta.bandStd = meta.band_stats.map((s) => s.std ?? null);
    const patch = {
      meta,
      band: Math.min(this.state.band, meta.bands - 1),
      rgb: defaultRgb(meta),
      marks: [], refMark: null, hover: null, line: null, quality: null, pcaOffset: 0,
    };
    this._markSeq = 0;
    Object.assign(this.state, patch);
    this.emit('cube', meta);
    this.emit('change', new Set(Object.keys(patch)));
    api.quality().then((q) => this.set({ quality: frozen(q) })).catch(() => {});
    return meta;
  }

  /** What a reload should keep: cube size, display settings and marks (geometry only). */
  snapshot() {
    const s = this.state, m = this.meta;
    return {
      dims: [m.height, m.width, m.bands],
      view: Object.fromEntries(KEEP_KEYS.map((k) => [k, $state.snapshot(s[k])])),
      marks: s.marks.map(({ id, kind, geom, visible, color, name }) => ({ id, kind, geom: $state.snapshot(geom), visible, color, name })),
      refMark: s.refMark,
      seq: this._markSeq,
    };
  }

  /** Re-apply a snapshot() after a reload; false (nothing restored) if the size changed. */
  restore(snap) {
    const m = this.meta;
    if (snap.dims.join() !== [m.height, m.width, m.bands].join()) return false;
    this._markSeq = snap.seq;
    this.set({ ...snap.view, marks: snap.marks.map((mk) => ({ ...mk })), refMark: snap.refMark });
    for (const mk of snap.marks) this.refreshMark(mk);
    return true;
  }

  /** Human label for a band: "#12 · 652.3 nm" or "#12". */
  bandLabel(i, short = false) {
    const m = this.meta;
    if (!m) return '';
    const name = m.band_names?.[i];
    const wl = m.wavelengths ? `${(+m.axis[i]).toFixed(m.axis[i] < 100 ? 2 : 1)}${m.unit ? ' ' + m.unit : ''}` : null;
    if (short) return wl || name || `#${i}`;
    return [`#${i}`, wl, !wl && name ? name : null].filter(Boolean).join(' · ');
  }

  nearestBand(value) {
    const ax = this.meta.axis;
    let best = 0;
    for (let i = 1; i < ax.length; i++) if (Math.abs(ax[i] - value) < Math.abs(ax[best] - value)) best = i;
    return best;
  }

  // ---------------------------------------------------------------- data
  band(i) {
    let p = this._bands.get(i);
    if (p) { this._bands.delete(i); this._bands.set(i, p); return p; } // LRU touch
    p = api.band(i).then((r) => r.data);
    this._bands.set(i, p);
    this._bandBytes += this.meta.width * this.meta.height * 4;
    while (this._bandBytes > BAND_CACHE_BYTES && this._bands.size > 4) {
      this._bands.delete(this._bands.keys().next().value);
      this._bandBytes -= this.meta.width * this.meta.height * 4;
    }
    p.catch(() => this._bands.delete(i));
    return p;
  }

  prefetchAround(i, n = 2) {
    for (let d = 1; d <= n; d++) for (const j of [i + d, i - d]) if (j >= 0 && j < this.nBands && !this._bands.has(j)) this.band(j);
  }

  product(kind, params = {}, body) {
    const key = JSON.stringify([kind, params, body ?? null]);
    let p = this._products.get(key);
    if (!p) {
      p = api.product(kind, params, body).then(({ data, meta }) => {
        const [k, h, w] = meta.shape;
        const channels = [];
        for (let c = 0; c < k; c++) channels.push(data.subarray(c * h * w, (c + 1) * h * w));
        return { channels, meta };
      });
      p.catch(() => this._products.delete(key));
      if (kind !== 'sam' && kind !== 'math') this._products.set(key, p);
    }
    return p;
  }

  // ---------------------------------------------------------------- layers
  /** Resolve the current display mode into a layer: {key, kind, channels[], label, sub, cmap?}. */
  async layer() {
    const s = this.state, m = this.meta;
    if (!m) return null;
    switch (s.mode) {
      case 'band': {
        const data = await this.band(s.band);
        this.prefetchAround(s.band);
        return { key: s.lockStretch ? 'band:locked' : `band:${s.band}`, kind: 'single', channels: [data], label: `Band ${this.bandLabel(s.band)}`, sub: 'single channel', bandIndex: s.band };
      }
      case 'rgb': {
        const chans = await Promise.all(s.rgb.map((b) => this.band(b)));
        return { key: `rgb:${s.rgb.join(',')}`, kind: 'rgb', channels: chans, label: 'RGB composite', sub: s.rgb.map((b) => this.bandLabel(b, true)).join(' · ') };
      }
      case 'pca': {
        const k = s.pcaAsRgb ? 3 : 1;
        const off = Math.min(s.pcaOffset, Math.max(0, m.bands - k));
        const r = await this.product('pca', { k, offset: off });
        const ex = r.meta.explained.map((e) => (e * 100).toFixed(e < 0.001 ? 3 : 1) + '%').join(' · ');
        return { key: `pca:${k}:${off}`, kind: k === 3 ? 'rgb' : 'single', channels: r.channels, label: k === 3 ? `PC ${off + 1}–${off + 3} as RGB` : `PC ${off + 1}`, sub: `variance ${ex}`, cmap: 'diverging', symmetric: true };
      }
      case 'anomaly': {
        const kind = s.anomaly;
        const r = await this.product(kind, kind === 'residual' ? { k: s.anomalyK } : {});
        const label = { rx: 'RX anomaly score', residual: `PCA residual (k=${s.anomalyK})`, gradient: 'Spectral roughness' }[kind];
        const sub = { rx: 'Mahalanobis distance to scene background', residual: 'what the top components can’t explain', gradient: 'mean |Δ| between adjacent bands' }[kind];
        return { key: `anomaly:${kind}:${s.anomalyK}`, kind: 'single', channels: r.channels, label, sub, cmap: 'inferno', highlight: true };
      }
      case 'similarity': {
        const ref = this.referenceSpectrum();
        const r = await this.product('sam', {}, { reference: ref?.values ? Array.from(ref.values, (v) => (Number.isFinite(v) ? v : null)) : null });
        return { key: 'sam', kind: 'single', channels: r.channels, label: `Spectral angle to ${ref ? ref.name : 'scene mean'}`, sub: 'radians · low = similar', cmap: 'magma', cmapRev: true, threshold: true, units: 'rad' };
      }
      case 'summary': {
        const r = await this.product(s.summary);
        const label = { mean: 'Mean across bands', std: 'Std across bands', max: 'Max across bands', argmax: `Peak ${m.wavelengths ? 'wavelength' : 'band'}`, invalid: 'Invalid bands per pixel' }[s.summary];
        return { key: `summary:${s.summary}`, kind: 'single', channels: r.channels, label, sub: 'per-pixel statistic', cmap: s.summary === 'argmax' ? 'spectral' : s.summary === 'invalid' ? 'inferno' : undefined, preset: s.summary === 'invalid' ? 'minmax' : undefined };
      }
      case 'math': {
        if (!s.mathExpr.trim()) return null;
        const r = await this.product('math', {}, { expr: s.mathExpr });
        return { key: `math:${s.mathExpr}`, kind: 'single', channels: r.channels, label: 'Band math', sub: s.mathExpr };
      }
    }
    return null;
  }

  /** Stretch for a layer: remembered per layer key, else from percentiles of its data. */
  stretchFor(layer, preset = this.state.preset) {
    const saved = this._stretch.get(layer.key);
    if (saved) return saved;
    let st;
    if (layer.key === 'band:locked') {
      const g = this.meta.global;
      st = { lo: [g.p01], hi: [g.p99] };
    } else {
      st = computeStretch(layer, layer.preset || preset);
    }
    this._stretch.set(layer.key, st);
    return st;
  }

  setStretch(layer, st) { this._stretch.set(layer.key, st); this.emit('stretch', st); }
  resetStretch(layer, preset) {
    this._stretch.delete(layer.key);
    if (layer.key === 'band:locked') {
      this._stretch.set(layer.key, computeStretch(layer, preset));
    }
    this.emit('stretch', this.stretchFor(layer, preset));
  }

  // ---------------------------------------------------------------- marks (pins & regions)
  async addMark(kind, geom) {
    const n = this.state.marks.filter((m) => (m.kind === 'pin') === (kind === 'pin')).length + 1;
    const mark = {
      id: ++this._markSeq, kind, geom, visible: true,
      color: PALETTE[(this._markSeq - 1) % PALETTE.length],
      name: kind === 'pin' ? `P${n}` : `R${n}`,
    };
    this.set({ marks: [...this.state.marks, mark] });
    await this.refreshMark(mark);
    return this.state.marks.find((m) => m.id === mark.id);
  }

  async refreshMark(mark) {
    // `mark` may be the plain object passed to set() (state holds a proxied copy), so write the
    // result through updateMark(). Arrays become typed arrays so Svelte does not deep-proxy them.
    const f64 = (a) => (a ? Float64Array.from(a, (v) => (v == null ? NaN : v)) : a);
    let patch;
    try {
      if (mark.kind === 'pin') {
        const r = await api.spectrum(mark.geom.x, mark.geom.y);
        patch = { values: f64(r.values), n: 1, error: null };
      } else {
        const r = await api.region(regionDesc(mark));
        patch = { values: f64(r.mean), std: f64(r.std), min: f64(r.min), max: f64(r.max), p05: f64(r.p05), p95: f64(r.p95), n: r.n, error: null };
      }
    } catch (e) { patch = { error: e.message }; }
    this.updateMark(mark.id, patch);
    if (this.state.mode === 'similarity' && this.state.refMark === mark.id) this.emit('layer-dirty');
  }

  updateMark(id, patch) {
    const marks = this.state.marks.map((m) => (m.id === id ? Object.assign(m, patch) : m));
    this.set({ marks: [...marks] });
  }

  removeMark(id) {
    this.set({ marks: this.state.marks.filter((m) => m.id !== id), refMark: this.state.refMark === id ? null : this.state.refMark });
  }

  clearMarks() { this.set({ marks: [], refMark: null }); }

  /** The spectrum used as reference for ratio views and similarity search. */
  referenceSpectrum() {
    const s = this.state;
    const m = s.marks.find((k) => k.id === s.refMark) || (s.mode === 'similarity' && s.simRef !== 'mean' ? s.marks.find((k) => k.id === +s.simRef) : null);
    if (m && m.values) return m;
    return null;
  }
}

// Display settings that survive re-processing the same cube (see snapshot / restore).
const KEEP_KEYS = ['mode', 'band', 'rgb', 'pcaOffset', 'pcaAsRgb', 'anomaly', 'anomalyK', 'summary', 'mathExpr', 'simRef', 'simDeg', 'anomalyTop'];

/** Wrap big read-only payloads in a class instance so Svelte doesn't deep-proxy them. */
class Payload {}
function frozen(o) { return Object.assign(new Payload(), o); }

export function regionDesc(mark) {
  const g = mark.geom;
  if (mark.kind === 'poly') return { kind: 'poly', points: g.points };
  return { kind: mark.kind, x0: g.x0, y0: g.y0, x1: g.x1, y1: g.y1 };
}

export function computeStretch(layer, preset) {
  const lo = [], hi = [];
  for (const ch of layer.channels) {
    let a, b;
    if (preset === 'minmax') [a, b] = percentiles(ch, [0, 100]);
    else { const p = +preset || 2; [a, b] = percentiles(ch, [p, 100 - p]); }
    if (layer.symmetric && layer.kind === 'single') { const m = Math.max(Math.abs(a), Math.abs(b)); a = -m; b = m; }
    if (!(b > a)) { b = a + (Math.abs(a) || 1) * 1e-3; }
    lo.push(a); hi.push(b);
  }
  return { lo, hi };
}

function defaultRgb(meta) {
  const C = meta.bands;
  if (C < 3) return [0, Math.min(1, C - 1), C - 1];
  const ax = meta.axis;
  if (meta.wavelengths && ax[0] <= 480 && ax[C - 1] >= 620) {
    const near = (nm) => ax.reduce((b, v, i) => (Math.abs(v - nm) < Math.abs(ax[b] - nm) ? i : b), 0);
    return [near(640), near(550), near(465)];
  }
  return [Math.round((C - 1) * 0.85), Math.round((C - 1) * 0.5), Math.round((C - 1) * 0.15)];
}

export const store = new Store();
