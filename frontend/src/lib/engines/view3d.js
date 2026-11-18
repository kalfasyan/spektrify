// 3-D view (three.js): an orthogonal-slice cube you can cut into, GPU volume rendering of the
// whole cube, and the pixels as a point cloud in PCA space.

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { colorize, lut } from '../colormaps.js';
import { Emitter, el, fmt, percentiles } from '../util.js';

const VOL_VS = /* glsl */ `
uniform vec3 uCam;
out vec3 vOrigin;
out vec3 vDir;
void main() {
  vOrigin = uCam;
  vDir = position - uCam;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const VOL_FS = /* glsl */ `
precision highp float;
precision highp sampler3D;
in vec3 vOrigin;
in vec3 vDir;
out vec4 outColor;
uniform sampler3D uVol;
uniform sampler2D uLut;
uniform int uMode;          // 0 MIP, 1 composite
uniform float uLo, uHi, uOpacity, uSteps;
uniform vec3 uClipMin, uClipMax; // in box coords (-0.5..0.5)
vec2 hitBox(vec3 o, vec3 d) {
  vec3 inv = 1.0 / d;
  vec3 t0 = (uClipMin - o) * inv, t1 = (uClipMax - o) * inv;
  vec3 tmin = min(t0, t1), tmax = max(t0, t1);
  return vec2(max(max(tmin.x, tmin.y), tmin.z), min(min(tmax.x, tmax.y), tmax.z));
}
float sampleVol(vec3 p) { return texture(uVol, vec3(p.x + 0.5, p.z + 0.5, p.y + 0.5)).r; }
float tf(float v) { return clamp((v - uLo) / max(uHi - uLo, 1e-4), 0.0, 1.0); }
void main() {
  vec3 d = normalize(vDir);
  vec2 b = hitBox(vOrigin, d);
  if (b.x > b.y) discard;
  b.x = max(b.x, 0.0);
  float dt = 1.7320508 / uSteps;
  vec3 p = vOrigin + b.x * d;
  // jitter start to hide slicing artefacts
  p += d * dt * fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453);
  if (uMode == 0) {
    float m = 0.0;
    for (float t = b.x; t < b.y; t += dt) { m = max(m, sampleVol(p)); p += d * dt; }
    float a = tf(m);
    if (a <= 0.0) discard;
    outColor = vec4(texture(uLut, vec2(a, 0.5)).rgb, 1.0);
  } else {
    vec4 acc = vec4(0.0);
    for (float t = b.x; t < b.y; t += dt) {
      float a = tf(sampleVol(p));
      if (a > 0.0) {
        vec3 c = texture(uLut, vec2(a, 0.5)).rgb;
        float alpha = 1.0 - pow(1.0 - clamp(a * a * uOpacity, 0.0, 1.0), dt * 120.0);
        acc.rgb += (1.0 - acc.a) * alpha * c;
        acc.a += (1.0 - acc.a) * alpha;
        if (acc.a > 0.97) break;
      }
      p += d * dt;
    }
    if (acc.a < 0.01) discard;
    outColor = vec4(acc.rgb / max(acc.a, 1e-3), acc.a);
  }
}`;

/**
 * Framework-free 3-D engine. UI panels call the setters; the engine emits
 * 'hint' (string), 'busy' (string | ''), 'pick' ({x, y, scores} | null), 'cut' (cut), 'pinned'.
 */
export class View3D extends Emitter {
  constructor(wrap, { store, api }) {
    super();
    this.store = store;
    this.api = api;
    this.wrap = wrap;
    this.mode = 'cube';
    this.active = false;
    this.opts = { depth: 0.55, perBand: false, volMode: 1, volLo: 0.18, volHi: 0.95, volOpacity: 0.6, pointSize: 2.2, colorBy: 'pca' };
    this.cut = null;
    this.labels = [];

    const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, alpha: true });
    r.setPixelRatio(window.devicePixelRatio || 1);
    r.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer = r;
    this.wrap.append(r.domElement);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
    this.camera.position.set(2.6, 2.1, 3.1);
    this.controls = new OrbitControls(this.camera, r.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.12;
    this.controls.addEventListener('change', () => this.requestRender());
    this.root = new THREE.Group();
    this.scene.add(this.root);
    this.labelLayer = el('div', { style: { position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden' } });
    this.wrap.append(this.labelLayer);
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(this.wrap);
    this.raycaster = new THREE.Raycaster();
    r.domElement.addEventListener('pointermove', (e) => this._hover(e));
    r.domElement.addEventListener('click', (e) => this._click(e));
    this._loop = this._loop.bind(this);
  }

  // ---------------------------------------------------------------- lifecycle
  activate() {
    this.active = true;
    this.resize();
    if (!this.built) this.setMode(this.mode);
    this.requestRender();
  }

  deactivate() { this.active = false; }

  destroy() {
    this.active = false;
    this._ro.disconnect();
    this.clearScene();
    this.controls.dispose();
    this.renderer.dispose();
    this.wrap.removeChild(this.renderer.domElement);
    this.wrap.removeChild(this.labelLayer);
  }
  cubeChanged() { this.built = false; this.cut = null; this.cache = {}; if (this.active) this.activate(); }

  stateChanged(keys) {
    if (!this.built) return;
    if (keys.has('cmap') || keys.has('cmapRev')) { if (this.mode === 'cube') this.updateCubeTextures(); if (this.mode === 'volume') this._setVolLut(); }
  }

  resize() {
    const w = this.wrap.clientWidth, h = this.wrap.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  requestRender() {
    if (this._pending || !this.active) return;
    this._pending = true;
    requestAnimationFrame(this._loop);
  }

  _loop() {
    this._pending = false;
    if (!this.active) return;
    const moving = this.controls.update();
    if (this.volMesh) {
      const inv = new THREE.Matrix4().copy(this.volMesh.matrixWorld).invert();
      this.volMesh.material.uniforms.uCam.value.copy(this.camera.position).applyMatrix4(inv);
    }
    this.renderer.render(this.scene, this.camera);
    this._placeLabels();
    if (moving) this.requestRender();
  }

  setMode(m) {
    this.mode = m;
    this.clearScene();
    this.built = true;
    const hint = { cube: 'Drag to orbit · scroll to zoom · right-drag to pan · move the cut sliders to slice into the cube', volume: 'Drag to orbit · MIP shows the brightest value along each ray; Composite blends the whole volume', cloud: 'Each dot is a pixel in PCA space · hover to identify · click to pin it in the image' }[m];
    this.emit('hint', hint);
    ({ cube: () => this.buildCube(), volume: () => this.buildVolume(), cloud: () => this.buildCloud() })[m]();
  }

  clearScene() {
    for (const c of [...this.root.children]) {
      this.root.remove(c);
      c.traverse?.((o) => { o.geometry?.dispose(); if (o.material) { for (const k of ['map']) o.material[k]?.dispose(); o.material.dispose?.(); } });
    }
    this.volMesh = null;
    this.points = null;
    this.labels = [];
    this.labelLayer.innerHTML = '';
  }

  // ---------------------------------------------------------------- geometry helpers
  dims() {
    const m = this.store.meta;
    const s = 2 / Math.max(m.width, m.height);
    return { X: m.width * s, Z: m.height * s, Y: 2 * this.opts.depth };
  }

  _label(text, pos, cls = '') {
    const d = el('div', { class: `three-label ${cls}` }, text);
    this.labelLayer.append(d);
    this.labels.push({ el: d, pos: pos.clone() });
  }

  _placeLabels() {
    const w = this.wrap.clientWidth, h = this.wrap.clientHeight;
    for (const l of this.labels) {
      const p = l.pos.clone().project(this.camera);
      const vis = p.z < 1 && p.z > -1;
      l.el.style.display = vis ? '' : 'none';
      l.el.style.transform = `translate(${((p.x + 1) / 2) * w}px, ${((1 - p.y) / 2) * h}px) translate(-50%, -50%)`;
    }
  }

  // ---------------------------------------------------------------- slice cube
  async buildCube() {
    const m = this.store.meta;
    if (!this.cut) this.cut = { x: m.width, z: m.height, top: m.bands - 1 };
    this.cache = this.cache || {};
    this.emit('cut', this.cut);
    const c = this.cut;
    const key = (k) => k;
    const fetchSlice = async (axis, i) => {
      const k = key(`${axis}:${i}`);
      if (!this.cache[k]) this.cache[k] = this.api.slice(axis, i).then((r) => r.data);
      return this.cache[k];
    };
    const fetchBand = async (b) => { const k = `band:${b}`; if (!this.cache[k]) this.cache[k] = this.store.band(b); return this.cache[k]; };
    const xi = Math.max(1, c.x) - 1, zi = Math.max(1, c.z) - 1;
    const [top, front, right, back, left, bottom] = await Promise.all([
      fetchBand(c.top), fetchSlice('row', zi), fetchSlice('col', xi), fetchSlice('row', 0), fetchSlice('col', 0), fetchBand(0),
    ]);
    this.faces = { top, front, right, back, left, bottom };
    this.updateCubeTextures(true);
  }

  _stretchFor(data) {
    if (this.opts.perBand) return null;
    const g = this.store.meta.global;
    return [g.p01, g.p99];
  }

  /** RGBA texture of a (rows × cols) float array, optionally normalised per row (= per band). */
  _tex(data, cols, rows, perRow = false) {
    const st = this.store.state;
    const L = lut(st.cmap, st.cmapRev);
    const rgba = new Uint8Array(cols * rows * 4);
    if (perRow) {
      for (let r = 0; r < rows; r++) {
        const row = data.subarray(r * cols, (r + 1) * cols);
        const [lo, hi] = percentiles(row, [1, 99], 4000);
        colorize(row, rgba.subarray(r * cols * 4, (r + 1) * cols * 4), lo, hi > lo ? hi : lo + 1e-6, 1, L);
      }
    } else {
      const [lo, hi] = this._stretchFor(data);
      colorize(data, rgba, lo, hi, 1, L);
    }
    const t = new THREE.DataTexture(rgba, cols, rows, THREE.RGBAFormat);
    t.colorSpace = THREE.SRGBColorSpace;
    t.magFilter = THREE.NearestFilter;
    t.minFilter = THREE.LinearFilter;
    t.needsUpdate = true;
    return t;
  }

  _quad(corners, uvs, tex) {
    // corners: 4 Vector3 (bl, br, tr, tl), uvs: 4 [u, v]
    const g = new THREE.BufferGeometry();
    const p = [0, 1, 2, 0, 2, 3].flatMap((i) => corners[i].toArray());
    const u = [0, 1, 2, 0, 2, 3].flatMap((i) => uvs[i]);
    g.setAttribute('position', new THREE.Float32BufferAttribute(p, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(u, 2));
    return new THREE.Mesh(g, new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide }));
  }

  updateCubeTextures() {
    if (!this.faces) return;
    for (const c of [...this.root.children]) { this.root.remove(c); c.geometry?.dispose(); c.material?.map?.dispose(); c.material?.dispose(); }
    this.labels = []; this.labelLayer.innerHTML = '';
    const m = this.store.meta;
    const { X, Y, Z } = this.dims();
    const C = m.bands, W = m.width, H = m.height;
    const c = this.cut;
    const fx = c.x / W, fz = c.z / H, fy = (c.top + 1) / C;
    const x1 = -X / 2 + X * fx, z1 = -Z / 2 + Z * fz, y1 = -Y / 2 + Y * fy;
    const x0 = -X / 2, z0 = -Z / 2, y0 = -Y / 2;
    const V = (x, y, z) => new THREE.Vector3(x, y, z);
    const pb = this.opts.perBand;
    // Top: band image, rows run +z (towards the viewer)
    const topTex = this._tex(this.faces.top, W, H, false);
    topTex.flipY = false;
    this.root.add(this._quad([V(x0, y1, z1), V(x1, y1, z1), V(x1, y1, z0), V(x0, y1, z0)], [[0, fz], [fx, fz], [fx, 0], [0, 0]], topTex));
    const botTex = this._tex(this.faces.bottom, W, H, false);
    this.root.add(this._quad([V(x0, y0, z0), V(x1, y0, z0), V(x1, y0, z1), V(x0, y0, z1)], [[0, 0], [fx, 0], [fx, fz], [0, fz]], botTex));
    // Front (row z1-1): x across, bands up. Slice data is (C, W): row = band.
    const fr = this._tex(this.faces.front, W, C, pb);
    this.root.add(this._quad([V(x0, y0, z1), V(x1, y0, z1), V(x1, y1, z1), V(x0, y1, z1)], [[0, 0], [fx, 0], [fx, fy], [0, fy]], fr));
    const bk = this._tex(this.faces.back, W, C, pb);
    this.root.add(this._quad([V(x1, y0, z0), V(x0, y0, z0), V(x0, y1, z0), V(x1, y1, z0)], [[fx, 0], [0, 0], [0, fy], [fx, fy]], bk));
    // Right (col x1-1): rows across (z), bands up. Data (C, H).
    const rt = this._tex(this.faces.right, H, C, pb);
    this.root.add(this._quad([V(x1, y0, z1), V(x1, y0, z0), V(x1, y1, z0), V(x1, y1, z1)], [[fz, 0], [0, 0], [0, fy], [fz, fy]], rt));
    const lf = this._tex(this.faces.left, H, C, pb);
    this.root.add(this._quad([V(x0, y0, z0), V(x0, y0, z1), V(x0, y1, z1), V(x0, y1, z0)], [[0, 0], [fz, 0], [fz, fy], [0, fy]], lf));
    // Edges of the cut block and a ghost of the full cube
    const edges = (w, h, d, cx, cy, cz, color, opacity) => {
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)), new THREE.LineBasicMaterial({ color, transparent: true, opacity }));
      e.position.set(cx, cy, cz);
      return e;
    };
    this.root.add(edges(x1 - x0, y1 - y0, z1 - z0, (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2, 0xffffff, 0.55));
    if (fx < 1 || fz < 1 || fy < 1) this.root.add(edges(X, Y, Z, 0, 0, 0, 0x8ea0bb, 0.22));
    // Labels
    const unit = m.unit ? ` ${m.unit}` : '';
    this._label(`λ ${fmt(m.axis[0], 4)}${unit}`, V(x0 - 0.08, y0, z1 + 0.05));
    this._label(`λ ${fmt(m.axis[c.top], 4)}${unit}`, V(x0 - 0.08, y1, z1 + 0.05));
    this._label(`x 0…${c.x - 1}`, V((x0 + x1) / 2, y0 - 0.1, z1 + 0.08));
    this._label(`y 0…${c.z - 1}`, V(x1 + 0.12, y0 - 0.1, (z0 + z1) / 2));
    this.requestRender();
  }

  /** Change the cut (any of x, z = rows, top = band) and rebuild the faces. */
  setCut(patch) { Object.assign(this.cut, patch); return this.buildCube(); }
  resetCut() { this.cut = null; return this.buildCube(); }
  setCubeOpt(k, v) { this.opts[k] = v; this.updateCubeTextures(); }

  resetCamera() {
    this.camera.position.set(2.6, 2.1, 3.1);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
    this.requestRender();
  }

  // ---------------------------------------------------------------- volume
  async buildVolume() {
    this.emit('busy', 'Preparing volume…');
    const r = await this.api.volume(192);
    this.emit('busy', '');
    if (this.mode !== 'volume') return;
    const [cc, hh, ww] = r.meta.shape;
    const tex = new THREE.Data3DTexture(r.data, ww, hh, cc);
    tex.format = THREE.RedFormat;
    tex.type = THREE.UnsignedByteType;
    tex.minFilter = tex.magFilter = THREE.LinearFilter;
    tex.unpackAlignment = 1;
    tex.needsUpdate = true;
    const { X, Y, Z } = this.dims();
    const mat = new THREE.ShaderMaterial({
      glslVersion: THREE.GLSL3,
      vertexShader: VOL_VS,
      fragmentShader: VOL_FS,
      side: THREE.BackSide,
      transparent: true,
      uniforms: {
        uVol: { value: tex }, uLut: { value: null }, uCam: { value: new THREE.Vector3() },
        uMode: { value: this.opts.volMode }, uLo: { value: this.opts.volLo }, uHi: { value: this.opts.volHi },
        uOpacity: { value: this.opts.volOpacity }, uSteps: { value: 320 },
        uClipMin: { value: new THREE.Vector3(-0.5, -0.5, -0.5) }, uClipMax: { value: new THREE.Vector3(0.5, 0.5, 0.5) },
      },
    });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mat);
    mesh.scale.set(X, Y, Z);
    this.volMesh = mesh;
    this.root.add(mesh);
    const e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(X, Y, Z)), new THREE.LineBasicMaterial({ color: 0x8ea0bb, transparent: true, opacity: 0.35 }));
    this.root.add(e);
    const m = this.store.meta;
    const unit = m.unit ? ` ${m.unit}` : '';
    this._label(`λ ${fmt(m.axis[0], 4)}${unit}`, new THREE.Vector3(-X / 2 - 0.1, -Y / 2, Z / 2));
    this._label(`λ ${fmt(m.axis[m.bands - 1], 4)}${unit}`, new THREE.Vector3(-X / 2 - 0.1, Y / 2, Z / 2));
    this._setVolLut();
    this.requestRender();
  }

  _setVolLut() {
    if (!this.volMesh) return;
    const st = this.store.state;
    const t = new THREE.DataTexture(lut(st.cmap, st.cmapRev), 256, 1, THREE.RGBAFormat);
    t.minFilter = t.magFilter = THREE.LinearFilter;
    t.colorSpace = THREE.SRGBColorSpace;
    t.needsUpdate = true;
    this.volMesh.material.uniforms.uLut.value?.dispose();
    this.volMesh.material.uniforms.uLut.value = t;
    this.requestRender();
  }

  setVolOpt(k, v) {
    this.opts[k] = v;
    const u = this.volMesh?.material.uniforms;
    if (u) { u.uMode.value = this.opts.volMode; u.uLo.value = this.opts.volLo; u.uHi.value = this.opts.volHi; u.uOpacity.value = this.opts.volOpacity; }
    this.requestRender();
  }

  /** Clip the volume: axis 'x' | 'y' (λ) | 'z' (rows), fraction kept 0..1. */
  setClip(axis, frac) {
    const u = this.volMesh?.material.uniforms;
    if (u) { u.uClipMax.value[axis] = -0.5 + frac; this.requestRender(); }
  }

  // ---------------------------------------------------------------- PCA cloud
  async buildCloud() {
    const r = await this.api.scatter(50000);
    if (this.mode !== 'cloud') return;
    const n = r.meta.n;
    const scores = new Float32Array(r.data.buffer, 0, n * 3);
    this.cloudIdx = new Uint32Array(r.data.buffer, n * 3 * 4, n);
    this.cloudScores = scores;
    const ex = r.meta.explained;
    // robust scaling per axis
    const pos = new Float32Array(n * 3);
    const span = [0, 1, 2].map((k) => { const a = new Float32Array(n); for (let i = 0; i < n; i++) a[i] = scores[i * 3 + k]; return percentiles(a, [0.5, 99.5], 50000); });
    const scale = Math.max(...span.map(([a, b]) => b - a)) || 1;
    for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) pos[i * 3 + k] = ((scores[i * 3 + k] - (span[k][0] + span[k][1]) / 2) / scale) * 2.2;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    this.span = span;
    const mat = new THREE.PointsMaterial({ size: this.opts.pointSize, sizeAttenuation: false, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false });
    this.points = new THREE.Points(g, mat);
    this.root.add(this.points);
    // axes
    const axes = [[1, 0, 0, 0xff6b6b], [0, 1, 0, 0x51cf66], [0, 0, 1, 0x4dabf7]];
    axes.forEach(([x, y, z, col], k) => {
      const geo = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-x * 1.25, -y * 1.25, -z * 1.25), new THREE.Vector3(x * 1.25, y * 1.25, z * 1.25)]);
      this.root.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.5 })));
      this._label(`PC${k + 1} · ${(ex[k] * 100).toFixed(ex[k] < 0.01 ? 2 : 1)}%`, new THREE.Vector3(x * 1.38, y * 1.38, z * 1.38));
    });
    this.hoverMarker = new THREE.Mesh(new THREE.SphereGeometry(0.025, 12, 12), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    this.hoverMarker.visible = false;
    this.root.add(this.hoverMarker);
    await this._colorCloud();
    this.requestRender();
  }

  async _colorCloud() {
    if (!this.points) return;
    const n = this.cloudIdx.length;
    const col = this.points.geometry.attributes.color.array;
    const by = this.opts.colorBy;
    if (by === 'pca') {
      for (let i = 0; i < n; i++) for (let k = 0; k < 3; k++) {
        const [a, b] = this.span[k];
        col[i * 3 + k] = Math.min(1, Math.max(0, (this.cloudScores[i * 3 + k] - a) / (b - a || 1)));
      }
    } else {
      const map = by === 'band' ? await this.store.band(this.store.state.band) : (await this.store.product(by === 'rx' ? 'rx' : 'mean')).channels[0];
      const vals = new Float32Array(n);
      for (let i = 0; i < n; i++) vals[i] = map[this.cloudIdx[i]];
      const [lo, hi] = percentiles(vals, [1, 99]);
      const st = this.store.state;
      const L = lut(by === 'rx' ? 'inferno' : st.cmap, by === 'rx' ? false : st.cmapRev);
      for (let i = 0; i < n; i++) {
        const t = Math.min(255, Math.max(0, Math.round(((vals[i] - lo) / (hi - lo || 1)) * 255)));
        for (let k = 0; k < 3; k++) col[i * 3 + k] = (L[t * 4 + k] / 255) ** 2.2;
      }
    }
    if (by === 'pca') for (let i = 0; i < col.length; i++) col[i] = col[i] ** 2.2;
    this.points.geometry.attributes.color.needsUpdate = true;
    this.requestRender();
  }

  setColorBy(v) { this.opts.colorBy = v; return this._colorCloud(); }
  setPointSize(v) { this.opts.pointSize = v; if (this.points) { this.points.material.size = v; this.requestRender(); } }

  _pick(e) {
    if (this.mode !== 'cloud' || !this.points) return null;
    const r = this.renderer.domElement.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(ndc, this.camera);
    this.raycaster.params.Points.threshold = 0.02 * this.camera.position.length() / 3;
    const hit = this.raycaster.intersectObject(this.points)[0];
    return hit ? hit.index : null;
  }

  _hover(e) {
    if (this.mode !== 'cloud' || this._hoverBusy) return;
    this._hoverBusy = true;
    requestAnimationFrame(() => {
      this._hoverBusy = false;
      const i = this._pick(e);
      if (i == null) { if (this.hoverMarker) this.hoverMarker.visible = false; this.emit('pick', null); this.requestRender(); return; }
      const W = this.store.meta.width;
      const idx = this.cloudIdx[i];
      const p = this.points.geometry.attributes.position;
      this.hoverMarker.position.set(p.getX(i), p.getY(i), p.getZ(i));
      this.hoverMarker.visible = true;
      this.emit('pick', { x: idx % W, y: Math.floor(idx / W), scores: [0, 1, 2].map((k) => this.cloudScores[i * 3 + k]) });
      this.requestRender();
    });
  }

  async _click(e) {
    const i = this._pick(e);
    if (i == null) return;
    const W = this.store.meta.width;
    const idx = this.cloudIdx[i];
    const mark = await this.store.addMark('pin', { x: idx % W, y: Math.floor(idx / W) });
    this.emit('pinned', mark);
  }

  snapshot() {
    this.renderer.render(this.scene, this.camera);
    return this.renderer.domElement;
  }
}
