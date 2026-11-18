// The app controller: everything the UI does that isn't drawing. Svelte components call
// these methods and read `ui` (reactive); canvas / WebGL engines register themselves with
// `attach()` and get driven from here. Keeping this framework-light means the components stay
// thin and the logic stays testable and replaceable.

import { api } from './api.js';
import { COLORMAPS } from './colormaps.js';
import { store } from './store.svelte.js';
import { Thumbs } from './thumbs.js';
import { transform, transformEnvelope, VIEWS } from './spectra.js';
import { clamp, download, fmt, percentiles } from './util.js';

class Controller {
  constructor() {
    this.thumbs = new Thumbs();
    this.engines = {}; // imageView, plot, hist, scrubber, lineProfile
    this.layer = null;
    this.stretch = null;
    this._token = 0;
    this._hover = { req: null, pending: null, spec: null };
    this._playTimer = null;
    this.ui = $state({
      ready: false,
      hud: null, // {label, sub}
      stretch: null, // {lo: [], hi: []}
      layerKind: null,
      cmap: 'viridis',
      cmapReversed: false,
      status: { pos: '', val: '', zoom: '', msg: '' },
      readout: '',
      toast: null, // {msg, kind}
      modal: null, // 'open' | 'help' | null
      menu: null, // {kind: 'cmap' | 'ctx', x, y, items?}
      bottomTab: 'spectrum',
      lineReady: false,
      mathError: '',
      playing: false,
      dragging: false,
      thumbsVersion: 0,
      cubeVersion: 0,
    });
    store.on('change', (keys) => this._onChange(keys));
    store.on('layer-dirty', () => this.refreshLayer());
  }

  attach(name, engine) {
    this.engines[name] = engine;
    return () => { if (this.engines[name] === engine) delete this.engines[name]; };
  }

  // ------------------------------------------------------------------ cube lifecycle
  async loadCube() {
    const meta = await store.load();
    this.thumbs.reset();
    this.layer = null;
    this._hover.spec = null;
    this.ui.ready = !!meta;
    this.ui.cubeVersion++;
    if (!meta) return;
    document.title = `${meta.name} · spektrify`;
    this.engines.imageView?.forceFit();
    await this.refreshLayer();
    this.thumbs.load().then(() => this.ui.thumbsVersion++);
  }

  async open(opts) { await api.open(opts); await this.loadCube(); }

  async upload(files) {
    files = [...files].sort((a, b) => (b.name.toLowerCase().endsWith('.hdr') ? 1 : 0) - (a.name.toLowerCase().endsWith('.hdr') ? 1 : 0));
    this.ui.status.msg = `Uploading ${files.map((f) => f.name).join(', ')}…`;
    try {
      let done = false;
      for (const f of files) { const r = await api.upload(f); done = done || !r.pending; }
      if (done) await this.loadCube();
      else this.toast('ENVI header received; drop its data file too');
    } catch (e) { this.toast(e.message, 'error'); }
    this.ui.status.msg = '';
  }

  // ------------------------------------------------------------------ layers & stretch
  async refreshLayer() {
    const token = ++this._token;
    let L;
    try {
      L = await store.layer();
    } catch (e) {
      if (store.state.mode === 'math') this.ui.mathError = e.message;
      else this.toast(e.message, 'error');
      return;
    }
    if (token !== this._token) return;
    this.ui.mathError = '';
    const iv = this.engines.imageView;
    if (!L) { this.layer = null; iv?.setLayer(null, null); this.engines.hist?.set(null, null); this.ui.hud = null; this.ui.layerKind = null; return; }
    this.layer = L;
    L.cmapOverride = L.cmap && !store.state.cmapPicked ? L.cmap : null;
    this.stretch = store.stretchFor(L);
    this._applyThreshold();
    iv?.setLayer(L, this.stretch);
    this.engines.hist?.set(L, this.stretch);
    this.ui.stretch = this.stretch;
    this.ui.hud = { label: L.label, sub: L.sub || '' };
    this.ui.layerKind = L.kind;
    this._syncCmap();
    this.updatePlot();
  }

  _applyThreshold() {
    const s = store.state, L = this.layer;
    if (!L) return;
    L.thrMode = 0;
    if (L.threshold && s.simDeg > 0) { L.thrMode = 1; L.thrV = (s.simDeg * Math.PI) / 180; }
    if (L.highlight && s.anomalyTop > 0) { L.thrMode = 2; L.thrV = percentiles(L.channels[0], [100 - s.anomalyTop])[0]; }
  }

  /** Live stretch update (commit=false while dragging histogram handles). */
  setStretch(st, commit = true) {
    this.stretch = st;
    if (this.layer && commit) store.setStretch(this.layer, st);
    const iv = this.engines.imageView;
    if (iv) { iv.stretch = st; iv.redraw(); }
    this.ui.stretch = st;
    if (commit) store.set({ preset: null });
  }

  setLimit(which, value) {
    if (!this.stretch || !Number.isFinite(value)) return;
    const st = { lo: [...this.stretch.lo], hi: [...this.stretch.hi] };
    st[which] = st[which].map(() => value);
    this.engines.hist?.set(this.layer, st);
    this.setStretch(st);
  }

  applyPreset(p) {
    store.set({ preset: p });
    if (!this.layer) return;
    store.resetStretch(this.layer, p);
    this.stretch = store.stretchFor(this.layer, p);
    this.engines.hist?.set(this.layer, this.stretch);
    this.setStretch(this.stretch, false);
  }

  currentCmap() { return this.layer?.cmapOverride || store.state.cmap; }

  _syncCmap() {
    this.ui.cmap = this.currentCmap();
    this.ui.cmapReversed = store.state.cmapRev !== !!this.layer?.cmapRev;
  }

  pickCmap(id) { store.set({ cmap: id, cmapPicked: true }); }

  cycleCmap(d) {
    const ids = COLORMAPS.map((c) => c.id);
    const i = ids.indexOf(this.currentCmap());
    this.pickCmap(ids[(i + d + ids.length) % ids.length]);
  }

  // ------------------------------------------------------------------ spectra
  hover(px) {
    const h = this._hover;
    h.pending = px;
    this._status(px);
    if (!px) { h.spec = null; this.updatePlot(); return; }
    if (h.req) return;
    const go = (p) => {
      h.req = api.spectrum(p.x, p.y).then((r) => {
        h.req = null;
        if (h.pending && (h.pending.x !== p.x || h.pending.y !== p.y)) return go(h.pending);
        if (!h.pending) return;
        h.spec = r;
        this.updatePlot();
      }).catch(() => { h.req = null; });
    };
    go(px);
  }

  _status(px) {
    const st = this.ui.status;
    if (!px || !this.layer) { st.pos = ''; st.val = ''; return; }
    const m = store.meta;
    const i = px.y * m.width + px.x;
    st.pos = `x ${px.x}  y ${px.y}`;
    const vals = this.layer.channels.map((c) => fmt(c[i], 5));
    st.val = this.layer.kind === 'rgb' ? `R ${vals[0]}  G ${vals[1]}  B ${vals[2]}` : `value ${vals[0]}${this.layer.units ? ' ' + this.layer.units : ''}`;
  }

  updatePlot() {
    const s = store.state, m = store.meta, plot = this.engines.plot;
    if (!m || !plot) return;
    const ref = store.referenceSpectrum();
    const ctx = { axis: m.axis, ref: ref?.values, sceneMean: m.mean_spectrum, sceneStd: m.bandStd };
    const series = [];
    if (s.specMean || s.specView === 'zscore') series.push({ id: 'mean', label: 'scene mean', color: '#8b95a5', values: transform(m.mean_spectrum, s.specView, ctx), dashed: true, width: 1.3 });
    for (const mk of s.marks) {
      if (!mk.visible || !mk.values) continue;
      series.push({
        id: mk.id, label: mk.name + (ref?.id === mk.id ? ' ★' : ''), color: mk.color, width: mk.id === s.refMark ? 2.4 : 1.8,
        values: transform(mk.values, s.specView, ctx),
        env: s.specStd && mk.std ? transformEnvelope(mk.values, mk.std, s.specView, ctx) : null,
      });
    }
    const hs = this._hover.spec;
    if (hs) series.push({ id: 'hover', label: `x ${hs.x} y ${hs.y}`, color: '#ffffff', values: transform(hs.values, s.specView, ctx), width: 1.3, faint: true });
    plot.update({
      axis: m.axis, unit: m.unit, wavelengths: !!m.wavelengths,
      band: s.mode === 'rgb' ? null : s.band,
      rgb: s.mode === 'rgb' ? s.rgb : null,
      flagged: new Set((s.quality?.flags || []).map((f) => f.band)),
      series, log: s.specLog && s.specView === 'values', yLabel: VIEWS[s.specView].label,
    });
    this.ui.readout = hs ? `x ${hs.x} · y ${hs.y} · ${fmt(hs.values[s.band], 5)} @ ${store.bandLabel(s.band, true)}` : '';
  }

  // ------------------------------------------------------------------ navigation
  goBand(b, { keepMode = false } = {}) {
    if (b == null || !store.meta) return;
    const s = store.state;
    const patch = { band: clamp(b, 0, store.nBands - 1) };
    if (!keepMode && s.mode !== 'band' && s.mode !== 'rgb') patch.mode = 'band';
    store.set(patch);
  }

  stepBand(d) {
    const s = store.state;
    if (s.mode === 'pca') return store.set({ pcaOffset: clamp(s.pcaOffset + Math.sign(d), 0, Math.max(0, store.nBands - (s.pcaAsRgb ? 3 : 1))) });
    this.goBand(s.band + d);
  }

  togglePlay() {
    if (this._playTimer) { clearInterval(this._playTimer); this._playTimer = null; }
    else {
      if (store.state.mode !== 'band') store.set({ mode: 'band' });
      this._playTimer = setInterval(() => store.set({ band: (store.state.band + 1) % store.nBands }), 110);
    }
    this.ui.playing = !!this._playTimer;
  }

  setView(name) {
    if (!store.meta && name !== 'image') return;
    store.set({ view: name });
  }

  openBand(b) { store.set({ mode: 'band', band: b }); this.setView('image'); }

  // ------------------------------------------------------------------ marks & line profile
  async setLine(g) {
    store.set({ line: g });
    this.ui.bottomTab = 'line';
    const r = await api.line(g.x0, g.y0, g.x1, g.y1);
    this.engines.lineProfile?.set({ values: r.data, n: r.meta.shape[0], c: r.meta.shape[1] });
    this.ui.lineReady = true;
  }

  clearAll() {
    store.clearMarks();
    store.set({ line: null });
    this.engines.lineProfile?.set(null);
    this.ui.lineReady = false;
  }

  focusMark(mk) {
    const g = mk.geom, iv = this.engines.imageView;
    if (!iv) return;
    if (mk.kind === 'pin') iv.centerOn(g.x + 0.5, g.y + 0.5);
    else if (mk.kind === 'poly') { const xs = g.points.map((p) => p[0]), ys = g.points.map((p) => p[1]); iv.centerOn((Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2); }
    else iv.centerOn((g.x0 + g.x1) / 2, (g.y0 + g.y1) / 2);
  }

  contextMenu({ mark, pixel, clientX, clientY }) {
    const s = store.state;
    const items = [];
    if (mark) {
      items.push([s.refMark === mark.id ? 'Clear reference' : 'Use as reference ★', () => store.set({ refMark: s.refMark === mark.id ? null : mark.id })]);
      items.push(['Find similar pixels', () => store.set({ refMark: mark.id, mode: 'similarity', simDeg: s.simDeg || 5 })]);
      items.push([`Remove ${mark.name}`, () => store.removeMark(mark.id)]);
    }
    if (pixel) {
      items.push([`Pin pixel (${pixel.x}, ${pixel.y})`, () => store.addMark('pin', pixel)]);
      items.push(['Copy coordinates', () => navigator.clipboard?.writeText(`${pixel.x}, ${pixel.y}`)]);
    }
    items.push(['Fit to window', () => this.engines.imageView?.fit()]);
    this.ui.menu = { kind: 'ctx', x: clientX, y: clientY, items };
  }

  // ------------------------------------------------------------------ export
  exportCsv() {
    const s = store.state, m = store.meta;
    if (!m) return;
    const rows = s.marks.filter((k) => k.values).map((k) => ({ ...k }));
    const hs = this._hover.spec;
    if (hs) rows.push({ name: `hover_x${hs.x}_y${hs.y}`, values: hs.values, kind: 'pin', geom: { x: hs.x, y: hs.y } });
    if (!rows.length) { this.toast('Pin a pixel or draw a region first'); return; }
    const head = ['band', m.wavelengths ? `wavelength_${m.unit || 'nm'}` : 'axis'];
    for (const r of rows) { head.push(r.name); if (r.std) head.push(`${r.name}_std`); }
    const lines = [`# ${m.name} · ${m.height}x${m.width}x${m.bands}`, ...rows.map((r) => `# ${r.name}: ${r.kind === 'pin' ? `pixel x=${r.geom.x} y=${r.geom.y}` : `${r.kind} n=${r.n} ${JSON.stringify(r.geom)}`}`), head.join(',')];
    for (let b = 0; b < m.bands; b++) {
      const row = [b, m.axis[b]];
      const cell = (v) => (v != null && Number.isFinite(v) ? v : '');
      for (const r of rows) { row.push(cell(r.values[b])); if (r.std) row.push(cell(r.std[b])); }
      lines.push(row.join(','));
    }
    download(`${stem(m.name)}_spectra.csv`, lines.join('\n'), 'text/csv');
  }

  snapshot() {
    const m = store.meta;
    if (!m) return;
    const view = store.state.view;
    const canvas = view === 'image' ? this.engines.imageView?.snapshot() : this.engines[`view:${view}`]?.snapshot?.();
    if (!canvas) { this.toast('Nothing to save in this view'); return; }
    canvas.toBlob((b) => download(`${stem(m.name)}_${view}.png`, b, 'image/png'));
  }

  toast(msg, kind = 'info', ms = kind === 'error' ? 6000 : 3200) {
    this.ui.toast = { msg, kind };
    clearTimeout(this._toastT);
    this._toastT = setTimeout(() => (this.ui.toast = null), ms);
  }

  // ------------------------------------------------------------------ store reactions
  _onChange(keys) {
    const s = store.state;
    const has = (...k) => k.some((x) => keys.has(x));
    if (has('mode')) s.cmapPicked = false;
    const layerKeys = ['mode', 'band', 'rgb', 'pcaOffset', 'pcaAsRgb', 'anomaly', 'anomalyK', 'summary', 'lockStretch'];
    if (has(...layerKeys) || (s.mode === 'similarity' && has('refMark'))) this.refreshLayer();
    else if (has('anomalyTop', 'simDeg')) { this._applyThreshold(); this.engines.imageView?.redraw(); }
    if (has('cmap', 'cmapRev', 'cmapPicked')) {
      if (this.layer) this.layer.cmapOverride = this.layer.cmap && !s.cmapPicked ? this.layer.cmap : null;
      this._syncCmap();
      const lp = this.engines.lineProfile;
      if (lp) { lp._img = null; lp.draw(); }
      this.engines.imageView?.redraw();
    }
    if (has('gamma', 'overlays', 'marks', 'refMark', 'line', 'quality')) this.engines.imageView?.redraw();
    if (has('band', 'rgb', 'mode', 'quality')) {
      this.engines.scrubber?.set({ band: s.band, marks: s.mode === 'rgb' ? s.rgb : null, flagged: new Set((s.quality?.flags || []).map((f) => f.band)) });
    }
    if (has('quality') && s.quality && !store.correlation) api.correlation().then((r) => (store.correlation = r.data)).catch(() => {});
    if (has('marks', 'refMark', 'band', 'rgb', 'mode', 'specView', 'specStd', 'specMean', 'specLog', 'quality')) this.updatePlot();
    if (has('band') && this.ui.bottomTab === 'line') this.engines.lineProfile?.draw();
  }
}

function stem(name) { return name.replace(/\.[^.]+$/, '').replace(/[^\w.-]+/g, '_'); }

export const ctl = new Controller();
export { store };
