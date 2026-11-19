// The main 2-D image view: WebGL image + a 2-D overlay canvas for marks, tools and pixel
// values. Emits: 'hover' {x, y} | null, 'pin' {x, y}, 'region' {kind, geom}, 'line' {..},
// 'mark-moved' (mark), 'context' {mark, clientX, clientY}, 'view' (view).

import { ImageRenderer } from '../gl/imageRenderer.js';
import { Emitter, clamp, fitCanvas, fmt } from '../util.js';
import { lut } from '../colormaps.js';

const MIN_SCALE = 1 / 64, MAX_SCALE = 256;

export class ImageView extends Emitter {
  constructor({ wrap, glCanvas, overlay, store }) {
    super();
    this.wrap = wrap;
    this.store = store;
    this.glCanvas = glCanvas;
    this.ov = overlay;
    this.renderer = new ImageRenderer(this.glCanvas);
    this.view = { scale: 1, tx: 0, ty: 0 };
    this.layer = null;
    this.size = null;
    this.stretch = null;
    this.drag = null;
    this.draft = null; // shape being drawn
    this.hoverPx = null;
    this._raf = 0;
    this._bind();
    this._ro = new ResizeObserver(() => { if (this._fitPending) this.fit(); this.redraw(); });
    this._ro.observe(wrap);
  }

  // ---------------------------------------------------------------- data
  setLayer(layer, stretch) {
    const m = this.store.meta;
    if (!m) { this.clear(); return; }
    const first = !this.size || this.size[0] !== m.width || this.size[1] !== m.height;
    this.size = [m.width, m.height];
    this.layer = layer;
    this.stretch = stretch;
    if (layer) this.renderer.setChannels(layer.channels, m.width, m.height);
    if (first) this.fit();
    this.redraw();
  }

  clear() { this.layer = null; this.size = null; this.redraw(); }

  /** Re-fit the view on the next layer (e.g. after a new cube is loaded). */
  forceFit() { this.size = null; }

  // ---------------------------------------------------------------- view transform
  fit() {
    if (!this.size) return;
    const W = this.wrap.clientWidth, H = this.wrap.clientHeight;
    // Hidden (another view is showing): fit when it becomes visible instead.
    this._fitPending = !W || !H;
    if (this._fitPending) return;
    const [w, h] = this.size;
    const s = Math.min((W - 24) / w, (H - 24) / h);
    this.view.scale = clamp(s, MIN_SCALE, MAX_SCALE);
    this.view.tx = (W - w * this.view.scale) / 2;
    this.view.ty = (H - h * this.view.scale) / 2;
    this.redraw();
    this.emit('view', this.view);
  }

  oneToOne() { this.zoomAt(this.wrap.clientWidth / 2, this.wrap.clientHeight / 2, 1 / (window.devicePixelRatio || 1) / this.view.scale); }

  zoomAt(sx, sy, factor) {
    const v = this.view;
    const ns = clamp(v.scale * factor, MIN_SCALE, MAX_SCALE);
    const ix = (sx - v.tx) / v.scale, iy = (sy - v.ty) / v.scale;
    v.scale = ns;
    v.tx = sx - ix * ns;
    v.ty = sy - iy * ns;
    this.redraw();
    this.emit('view', v);
  }

  /** Centre the view on image coords (keeps zoom). */
  centerOn(x, y) {
    const v = this.view;
    v.tx = this.wrap.clientWidth / 2 - x * v.scale;
    v.ty = this.wrap.clientHeight / 2 - y * v.scale;
    this.redraw();
  }

  toImage(sx, sy) { return { x: (sx - this.view.tx) / this.view.scale, y: (sy - this.view.ty) / this.view.scale }; }
  toScreen(x, y) { return { x: x * this.view.scale + this.view.tx, y: y * this.view.scale + this.view.ty }; }
  pixelAt(sx, sy) {
    if (!this.size) return null;
    const p = this.toImage(sx, sy);
    const x = Math.floor(p.x), y = Math.floor(p.y);
    if (x < 0 || y < 0 || x >= this.size[0] || y >= this.size[1]) return null;
    return { x, y };
  }

  // ---------------------------------------------------------------- drawing
  redraw() {
    if (this._raf) return;
    this._raf = requestAnimationFrame(() => { this._raf = 0; this._draw(); });
  }

  _draw() {
    const s = this.store.state;
    const L = this.layer;
    if (L && this.stretch) {
      const cmap = L.cmapOverride || s.cmap;
      this.renderer.setLut(lut(cmap, s.cmapRev !== !!L.cmapRev));
      this.renderer.draw(this.view, {
        mode: L.kind === 'rgb' ? 1 : 0,
        lo: this.stretch.lo, hi: this.stretch.hi, gamma: s.gamma,
        nan: s.overlays.nan, clip: s.overlays.clip,
        thr: L.thrMode || 0, thrV: L.thrV,
      });
    } else {
      this.renderer.draw(this.view, null);
    }
    this._drawOverlay();
  }

  _drawOverlay() {
    const { ctx, w, h } = fitCanvas(this.ov);
    ctx.clearRect(0, 0, w, h);
    if (!this.size) return;
    const s = this.store.state, v = this.view;
    const [iw, ih] = this.size;

    // image frame
    ctx.strokeStyle = 'rgba(255,255,255,.14)';
    ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(v.tx) - 0.5, Math.round(v.ty) - 0.5, Math.round(iw * v.scale) + 1, Math.round(ih * v.scale) + 1);

    // pixel grid + values at high zoom
    if (s.overlays.values && v.scale >= 14 && this.layer) this._drawPixelGrid(ctx, w, h);

    // sensor line defects
    if (s.overlays.defects && s.quality) {
      ctx.save();
      ctx.strokeStyle = 'rgba(255, 180, 84, .85)';
      ctx.setLineDash([4, 3]);
      for (const x of s.quality.bad_columns) { const a = this.toScreen(x + 0.5, 0), b = this.toScreen(x + 0.5, ih); ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      for (const y of s.quality.bad_rows) { const a = this.toScreen(0, y + 0.5), b = this.toScreen(iw, y + 0.5); ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      ctx.restore();
    }

    // line profile
    if (s.line) this._drawLine(ctx, s.line, '#ffffff');

    // marks
    for (const m of s.marks) if (m.visible) this._drawMark(ctx, m, m.id === s.refMark);

    // shape being drawn
    if (this.draft) {
      const d = this.draft;
      if (d.kind === 'line') this._drawLine(ctx, d.geom, '#ffffff');
      else this._drawMark(ctx, { kind: d.kind, geom: d.geom, color: '#ffffff', name: '' }, false, true);
    }

    // hover pixel outline
    if (this.hoverPx && v.scale >= 4) {
      const p = this.toScreen(this.hoverPx.x, this.hoverPx.y);
      ctx.strokeStyle = 'rgba(255,255,255,.9)';
      ctx.lineWidth = 1.5;
      ctx.strokeRect(p.x, p.y, v.scale, v.scale);
    }
  }

  _drawPixelGrid(ctx, w, h) {
    const v = this.view, [iw, ih] = this.size;
    const x0 = Math.max(0, Math.floor(-v.tx / v.scale)), y0 = Math.max(0, Math.floor(-v.ty / v.scale));
    const x1 = Math.min(iw, Math.ceil((w - v.tx) / v.scale)), y1 = Math.min(ih, Math.ceil((h - v.ty) / v.scale));
    ctx.strokeStyle = 'rgba(0,0,0,.35)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = x0; x <= x1; x++) { const sx = Math.round(x * v.scale + v.tx) + 0.5; ctx.moveTo(sx, y0 * v.scale + v.ty); ctx.lineTo(sx, y1 * v.scale + v.ty); }
    for (let y = y0; y <= y1; y++) { const sy = Math.round(y * v.scale + v.ty) + 0.5; ctx.moveTo(x0 * v.scale + v.tx, sy); ctx.lineTo(x1 * v.scale + v.tx, sy); }
    ctx.stroke();
    if (v.scale < 44 || (x1 - x0) * (y1 - y0) > 1600) return;
    const ch = this.layer.channels;
    const fs = Math.min(12, v.scale / 5);
    ctx.font = `${fs}px ${getComputedStyle(document.body).getPropertyValue('--mono')}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const st = this.stretch;
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) {
      const i = y * iw + x;
      const cx = (x + 0.5) * v.scale + v.tx, cy = (y + 0.5) * v.scale + v.ty;
      if (ch.length === 1) {
        const val = ch[0][i];
        const t = (val - st.lo[0]) / (st.hi[0] - st.lo[0]);
        ctx.fillStyle = 'rgba(0,0,0,.55)';
        ctx.fillText(fmt(val, 4), cx + 0.6, cy + 0.6);
        ctx.fillStyle = t > 0.65 && !this.store.state.cmapRev ? '#111' : '#fff';
        ctx.fillText(fmt(val, 4), cx, cy);
      } else {
        const lines = ch.map((c) => fmt(c[i], 3));
        const colors = ['#ff9b9b', '#9bf0c6', '#a9d0ff'];
        lines.forEach((t, k) => {
          const yy = cy + (k - 1) * fs * 1.15;
          ctx.fillStyle = 'rgba(0,0,0,.7)'; ctx.fillText(t, cx + 0.6, yy + 0.6);
          ctx.fillStyle = colors[k]; ctx.fillText(t, cx, yy);
        });
      }
    }
  }

  _drawLine(ctx, g, color) {
    const a = this.toScreen(g.x0 + 0.5, g.y0 + 0.5), b = this.toScreen(g.x1 + 0.5, g.y1 + 0.5);
    ctx.save();
    ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(0,0,0,.6)';
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.lineWidth = 1.5; ctx.strokeStyle = color; ctx.setLineDash([6, 4]);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.setLineDash([]);
    for (const [p, l] of [[a, 'A'], [b, 'B']]) {
      ctx.fillStyle = color; ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill();
      ctx.font = '600 11px Inter, system-ui'; ctx.fillStyle = '#fff'; ctx.fillText(l, p.x + 7, p.y - 7);
    }
    ctx.restore();
  }

  _drawMark(ctx, m, isRef, draft = false) {
    ctx.save();
    const g = m.geom;
    ctx.lineWidth = 2;
    ctx.strokeStyle = m.color;
    if (m.kind === 'pin') {
      const p = this.toScreen(g.x + 0.5, g.y + 0.5);
      const r = Math.max(5, Math.min(10, this.view.scale * 0.5));
      ctx.fillStyle = 'rgba(0,0,0,.55)'; ctx.beginPath(); ctx.arc(p.x, p.y, r + 2.5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = m.color; ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'rgba(0,0,0,.8)'; ctx.beginPath(); ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2); ctx.fill();
      this._label(ctx, m.name + (isRef ? ' ★' : ''), p.x + r + 4, p.y - r - 2, m.color);
    } else {
      ctx.fillStyle = m.color + '22';
      ctx.beginPath();
      if (m.kind === 'rect' || m.kind === 'ellipse') {
        const a = this.toScreen(Math.min(g.x0, g.x1), Math.min(g.y0, g.y1)), b = this.toScreen(Math.max(g.x0, g.x1), Math.max(g.y0, g.y1));
        if (m.kind === 'rect') ctx.rect(a.x, a.y, b.x - a.x, b.y - a.y);
        else ctx.ellipse((a.x + b.x) / 2, (a.y + b.y) / 2, Math.abs(b.x - a.x) / 2, Math.abs(b.y - a.y) / 2, 0, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,.6)'; ctx.lineWidth = 3.5; ctx.stroke();
        ctx.strokeStyle = m.color; ctx.lineWidth = 1.8; if (draft) ctx.setLineDash([5, 4]); ctx.stroke();
        if (m.name) this._label(ctx, m.name + (isRef ? ' ★' : ''), a.x + 2, a.y - 6, m.color);
      } else if (m.kind === 'poly' && g.points.length) {
        g.points.forEach(([x, y], i) => { const p = this.toScreen(x, y); i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); });
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = 'rgba(0,0,0,.6)'; ctx.lineWidth = 3.5; ctx.stroke();
        ctx.strokeStyle = m.color; ctx.lineWidth = 1.8; if (draft) ctx.setLineDash([5, 4]); ctx.stroke();
        if (m.name) { const p = this.toScreen(...g.points[0]); this._label(ctx, m.name + (isRef ? ' ★' : ''), p.x + 4, p.y - 6, m.color); }
      }
    }
    ctx.restore();
  }

  _label(ctx, text, x, y, color) {
    if (!text) return;
    ctx.font = '600 11px Inter, system-ui, sans-serif';
    const w = ctx.measureText(text).width;
    ctx.fillStyle = 'rgba(12,15,20,.85)';
    ctx.beginPath(); ctx.roundRect(x - 3, y - 10, w + 6, 15, 3); ctx.fill();
    ctx.fillStyle = color;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(text, x, y + 1);
  }

  // ---------------------------------------------------------------- hit testing
  hitMark(sx, sy) {
    const marks = this.store.state.marks;
    for (let i = marks.length - 1; i >= 0; i--) {
      const m = marks[i];
      if (!m.visible) continue;
      const g = m.geom;
      if (m.kind === 'pin') {
        const p = this.toScreen(g.x + 0.5, g.y + 0.5);
        if (Math.hypot(p.x - sx, p.y - sy) <= Math.max(9, this.view.scale * 0.5 + 3)) return m;
      } else {
        const ip = this.toImage(sx, sy);
        if (m.kind === 'poly') { if (pointInPoly(ip.x, ip.y, g.points)) return m; }
        else {
          const [x0, x1] = [Math.min(g.x0, g.x1), Math.max(g.x0, g.x1)], [y0, y1] = [Math.min(g.y0, g.y1), Math.max(g.y0, g.y1)];
          if (ip.x >= x0 && ip.x <= x1 && ip.y >= y0 && ip.y <= y1) return m;
        }
      }
    }
    return null;
  }

  // ---------------------------------------------------------------- interaction
  _bind() {
    const ov = this.ov;
    const pos = (e) => { const r = ov.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };

    ov.addEventListener('wheel', (e) => {
      e.preventDefault();
      const p = pos(e);
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY;
      this.zoomAt(p.x, p.y, Math.exp(-dy * (e.ctrlKey ? 0.01 : 0.0018)));
    }, { passive: false });

    ov.addEventListener('dblclick', (e) => { e.preventDefault(); this.fit(); });
    ov.addEventListener('contextmenu', (e) => e.preventDefault());

    ov.addEventListener('pointerdown', (e) => {
      if (!this.size) return;
      ov.setPointerCapture(e.pointerId);
      const p = pos(e);
      const ip = this.toImage(p.x, p.y);
      const tool = this.store.state.tool;
      const base = { sx: p.x, sy: p.y, tx: this.view.tx, ty: this.view.ty, moved: false, button: e.button };
      if (e.button === 1 || e.button === 2 || (e.button === 0 && this._space)) { this.drag = { ...base, type: 'pan', mark: e.button === 2 ? this.hitMark(p.x, p.y) : null }; return; }
      if (e.button !== 0) return;
      if (e.shiftKey || tool === 'rect' || tool === 'ellipse') {
        const kind = e.shiftKey && tool !== 'ellipse' ? 'rect' : tool === 'inspect' || tool === 'lasso' || tool === 'line' ? 'rect' : tool;
        this.drag = { ...base, type: 'shape' };
        this.draft = { kind, geom: { x0: ip.x, y0: ip.y, x1: ip.x, y1: ip.y } };
      } else if (tool === 'lasso') {
        this.drag = { ...base, type: 'shape' };
        this.draft = { kind: 'poly', geom: { points: [[ip.x, ip.y]] } };
      } else if (tool === 'line') {
        const px = this.pixelAt(p.x, p.y) || { x: Math.floor(ip.x), y: Math.floor(ip.y) };
        this.drag = { ...base, type: 'shape' };
        this.draft = { kind: 'line', geom: { x0: px.x, y0: px.y, x1: px.x, y1: px.y } };
      } else {
        const mark = this.hitMark(p.x, p.y);
        if (mark) this.drag = { ...base, type: 'move', mark, start: ip, orig: JSON.parse(JSON.stringify(mark.geom)) };
        else this.drag = { ...base, type: 'pan' };
      }
    });

    ov.addEventListener('pointermove', (e) => {
      const p = pos(e);
      const px = this.pixelAt(p.x, p.y);
      if (!this.drag) {
        if (px?.x !== this.hoverPx?.x || px?.y !== this.hoverPx?.y) {
          this.hoverPx = px;
          this.emit('hover', px);
          this.redraw();
        }
        ov.style.cursor = this.store.state.tool === 'inspect' && this.hitMark(p.x, p.y) ? 'move' : '';
        return;
      }
      const d = this.drag;
      if (Math.hypot(p.x - d.sx, p.y - d.sy) > 3) d.moved = true;
      const ip = this.toImage(p.x, p.y);
      if (d.type === 'pan') {
        if (!d.moved) return;
        ov.classList.add('panning');
        this.view.tx = d.tx + p.x - d.sx;
        this.view.ty = d.ty + p.y - d.sy;
        this.redraw();
        this.emit('view', this.view);
      } else if (d.type === 'shape') {
        const g = this.draft.geom;
        if (this.draft.kind === 'poly') {
          const last = g.points[g.points.length - 1];
          if (Math.hypot((ip.x - last[0]) * this.view.scale, (ip.y - last[1]) * this.view.scale) > 4) g.points.push([ip.x, ip.y]);
        } else if (this.draft.kind === 'line') {
          g.x1 = clamp(Math.floor(ip.x), 0, this.size[0] - 1); g.y1 = clamp(Math.floor(ip.y), 0, this.size[1] - 1);
        } else {
          g.x1 = ip.x; g.y1 = ip.y;
          if (this.draft.kind === 'rect' || this.draft.kind === 'ellipse') { g.x1 = Math.round(g.x1); g.y1 = Math.round(g.y1); g.x0 = Math.round(g.x0); g.y0 = Math.round(g.y0); }
        }
        this.redraw();
      } else if (d.type === 'move' && d.moved) {
        const dx = ip.x - d.start.x, dy = ip.y - d.start.y;
        const g = d.mark.geom, o = d.orig;
        if (d.mark.kind === 'pin') { g.x = clamp(Math.round(o.x + dx), 0, this.size[0] - 1); g.y = clamp(Math.round(o.y + dy), 0, this.size[1] - 1); }
        else if (d.mark.kind === 'poly') g.points = o.points.map(([x, y]) => [x + dx, y + dy]);
        else { const rx = Math.round(dx), ry = Math.round(dy); g.x0 = o.x0 + rx; g.x1 = o.x1 + rx; g.y0 = o.y0 + ry; g.y1 = o.y1 + ry; }
        this.redraw();
        if (d.mark.kind === 'pin') this.emit('mark-moving', d.mark);
      }
      if (px) { this.hoverPx = px; this.emit('hover', px); }
    });

    const end = (e) => {
      const d = this.drag;
      this.drag = null;
      ov.classList.remove('panning');
      if (!d) return;
      const p = pos(e);
      if (d.type === 'pan' && !d.moved) {
        if (d.button === 2) {
          const m = this.hitMark(p.x, p.y);
          this.emit('context', { mark: m, pixel: this.pixelAt(p.x, p.y), clientX: e.clientX, clientY: e.clientY });
        } else if (d.button === 0) {
          const px = this.pixelAt(p.x, p.y);
          if (px) this.emit('pin', px);
        }
      } else if (d.type === 'shape') {
        const draft = this.draft;
        this.draft = null;
        if (draft.kind === 'line') { if (d.moved) this.emit('line', draft.geom); }
        else if (draft.kind === 'poly') { if (draft.geom.points.length >= 3) this.emit('region', draft); }
        else {
          const g = draft.geom;
          if (Math.abs(g.x1 - g.x0) >= 1 && Math.abs(g.y1 - g.y0) >= 1) this.emit('region', draft);
        }
        this.redraw();
      } else if (d.type === 'move') {
        if (d.moved) this.emit('mark-moved', d.mark);
        else if (d.mark.kind === 'pin') this.emit('mark-click', d.mark);
        else this.emit('mark-click', d.mark);
      }
    };
    ov.addEventListener('pointerup', end);
    ov.addEventListener('pointercancel', () => { this.drag = null; this.draft = null; this.redraw(); });
    ov.addEventListener('pointerleave', () => { if (!this.drag) { this.hoverPx = null; this.emit('hover', null); this.redraw(); } });

    this._kd = (e) => { if (e.code === 'Space' && e.target === document.body) this._space = true; };
    this._ku = (e) => { if (e.code === 'Space') this._space = false; };
    window.addEventListener('keydown', this._kd);
    window.addEventListener('keyup', this._ku);
  }

  destroy() {
    this._ro.disconnect();
    window.removeEventListener('keydown', this._kd);
    window.removeEventListener('keyup', this._ku);
  }

  cancelDraft() { this.draft = null; this.drag = null; this.redraw(); }

  /** PNG of the current view (image + overlay). */
  snapshot() {
    this._draw();
    const c = document.createElement('canvas');
    c.width = this.glCanvas.width; c.height = this.glCanvas.height;
    const ctx = c.getContext('2d');
    ctx.fillStyle = '#0b0e13'; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(this.glCanvas, 0, 0);
    ctx.drawImage(this.ov, 0, 0, c.width, c.height);
    return c;
  }
}

export function pointInPoly(x, y, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
