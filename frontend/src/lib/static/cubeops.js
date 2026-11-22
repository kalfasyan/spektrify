// The cheap per-pixel reads of the API, computed in the browser from the shipped cube so the
// online demo stays interactive (hover spectra, pins, regions, line profiles, spectral angle).
// Each mirrors a method of the Python reference backend (compute/numpy_backend.py and
// compute/regions.py); everything heavier is precomputed by the snapshot.
//
// A cube here is { data: Float32Array (C·H·W, band-major), c, h, w }.

const finite = (v) => (Number.isFinite(v) ? v : null);

export function band({ data, h, w }, i) {
  return data.slice(i * h * w, (i + 1) * h * w);
}

export function spectrum({ data, c, h, w }, x, y) {
  const out = new Array(c);
  for (let b = 0; b < c; b++) out[b] = finite(data[b * h * w + y * w + x]);
  return out;
}

/** axis 'row' → (C, W) at row i; 'col' → (C, H) at column i. */
export function slice({ data, c, h, w }, axis, i) {
  const n = axis === 'row' ? w : h;
  const out = new Float32Array(c * n);
  for (let b = 0; b < c; b++) {
    const o = b * h * w;
    for (let j = 0; j < n; j++) out[b * n + j] = axis === 'row' ? data[o + i * w + j] : data[o + j * w + i];
  }
  return out;
}

/** Spectra sampled (nearest pixel) along a segment: (N, C). */
export function line({ data, c, h, w }, x0, y0, x1, y1) {
  const n = Math.max(2, Math.ceil(Math.hypot(x1 - x0, y1 - y0)) + 1);
  const out = new Float32Array(n * c);
  for (let k = 0; k < n; k++) {
    const t = k / (n - 1);
    const x = clamp(Math.round(x0 + (x1 - x0) * t), 0, w - 1), y = clamp(Math.round(y0 + (y1 - y0) * t), 0, h - 1);
    for (let b = 0; b < c; b++) out[k * c + b] = data[b * h * w + y * w + x];
  }
  return { array: out, shape: [n, c] };
}

/** Block-averaged thumbnails for every band: (C, th, tw). */
export function thumbnails({ data, c, h, w }, maxSide) {
  let s = Math.max(1, Math.ceil(Math.max(h, w) / maxSide));
  let th = Math.floor(h / s), tw = Math.floor(w / s);
  if (!th || !tw) { s = 1; th = h; tw = w; }
  const out = new Float32Array(c * th * tw);
  for (let b = 0; b < c; b++) {
    const o = b * h * w;
    for (let ty = 0; ty < th; ty++) for (let tx = 0; tx < tw; tx++) {
      let sum = 0, n = 0;
      for (let dy = 0; dy < s; dy++) for (let dx = 0; dx < s; dx++) {
        const v = data[o + (ty * s + dy) * w + tx * s + dx];
        if (Number.isFinite(v)) { sum += v; n++; }
      }
      out[(b * th + ty) * tw + tx] = n ? sum / n : NaN;
    }
  }
  return { array: out, shape: [c, th, tw], meta: { bands: c, height: th, width: tw, step: s } };
}

/** Spectral angle (radians) of every pixel to `ref`; NaN where a pixel has a non-finite band. */
export function spectralAngle({ data, c, h, w }, ref) {
  const r = ref.map((v) => (v == null ? NaN : v));
  const rn = Math.hypot(...r);
  const out = new Float32Array(h * w);
  for (let p = 0; p < h * w; p++) {
    let dot = 0, nn = 0, ok = true;
    for (let b = 0; b < c; b++) {
      const v = data[b * h * w + p];
      if (!Number.isFinite(v)) { ok = false; break; }
      dot += v * r[b]; nn += v * v;
    }
    out[p] = ok ? Math.acos(clamp(dot / (Math.sqrt(nn) * rn), -1, 1)) : NaN;
  }
  return out;
}

/** Rasterise a rect / ellipse / poly region (as the UI sends it) to a mask. */
export function regionMask(body, h, w) {
  const mask = new Uint8Array(h * w);
  const kind = body.kind ?? 'rect';
  if (kind === 'rect' || kind === 'ellipse') {
    const [x0, x1] = [+body.x0, +body.x1].sort((a, b) => a - b), [y0, y1] = [+body.y0, +body.y1].sort((a, b) => a - b);
    const xi0 = Math.max(0, Math.floor(x0)), xi1 = Math.min(w, Math.ceil(x1));
    const yi0 = Math.max(0, Math.floor(y0)), yi1 = Math.min(h, Math.ceil(y1));
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, rx = Math.max((x1 - x0) / 2, 1e-6), ry = Math.max((y1 - y0) / 2, 1e-6);
    for (let y = yi0; y < yi1; y++) for (let x = xi0; x < xi1; x++) {
      mask[y * w + x] = kind === 'rect' || ((x + 0.5 - cx) / rx) ** 2 + ((y + 0.5 - cy) / ry) ** 2 <= 1 ? 1 : 0;
    }
    return mask;
  }
  if (kind === 'poly') {
    const pts = body.points;
    if (pts.length < 3) return mask;
    const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
    const xi0 = Math.max(0, Math.floor(Math.min(...xs))), xi1 = Math.min(w, Math.ceil(Math.max(...xs)));
    const yi0 = Math.max(0, Math.floor(Math.min(...ys))), yi1 = Math.min(h, Math.ceil(Math.max(...ys)));
    for (let y = yi0; y < yi1; y++) for (let x = xi0; x < xi1; x++) {
      const px = x + 0.5, py = y + 0.5;
      let inside = false;
      for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { // even-odd ray casting
        if ((ys[i] > py) !== (ys[j] > py) && px < ((xs[j] - xs[i]) * (py - ys[i])) / (ys[j] - ys[i]) + xs[i]) inside = !inside;
      }
      mask[y * w + x] = inside ? 1 : 0;
    }
    return mask;
  }
  throw new Error(`unknown region kind '${kind}'`);
}

/** Per-band statistics over the masked pixels, ignoring non-finite values. */
export function regionStats({ data, c, h, w }, mask) {
  const idx = [];
  for (let p = 0; p < h * w; p++) if (mask[p]) idx.push(p);
  if (!idx.length) return { n: 0 };
  const res = { n: idx.length, mean: [], std: [], min: [], max: [], p05: [], p95: [] };
  for (let b = 0; b < c; b++) {
    const v = idx.map((p) => data[b * h * w + p]).filter(Number.isFinite).sort((a, z) => a - z);
    const m = v.reduce((s, x) => s + x, 0) / v.length;
    res.mean.push(finite(m));
    res.std.push(finite(Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / v.length)));
    res.min.push(finite(v[0]));
    res.max.push(finite(v[v.length - 1]));
    res.p05.push(finite(percentile(v, 5)));
    res.p95.push(finite(percentile(v, 95)));
  }
  return res;
}

function percentile(sorted, q) { // linear interpolation, as numpy's default
  if (!sorted.length) return NaN;
  const pos = ((sorted.length - 1) * q) / 100, lo = Math.floor(pos);
  return sorted[lo] + (sorted[Math.min(lo + 1, sorted.length - 1)] - sorted[lo]) * (pos - lo);
}

function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
