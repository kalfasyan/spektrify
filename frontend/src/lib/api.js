// The only module that knows the backend's URLs. Every other module calls these methods,
// so the transport (or the whole backend) can change without touching UI code.

let inflight = 0;
function busy(delta) {
  inflight = Math.max(0, inflight + delta);
  const bar = document.getElementById('loading-bar');
  if (!bar) return;
  bar.classList.toggle('on', inflight > 0);
  bar.classList.toggle('done', inflight === 0);
}

async function request(url, opts = {}, quiet = false) {
  if (!quiet) busy(+1);
  try {
    const r = await fetch(url, opts);
    if (!r.ok) {
      let msg = `${r.status} ${r.statusText}`;
      try { msg = (await r.json()).error || msg; } catch { /* not JSON */ }
      throw new Error(msg);
    }
    return r;
  } finally {
    if (!quiet) busy(-1);
  }
}

const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v != null)).toString();

const DTYPES = { float32: Float32Array, float64: Float64Array, uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array, int32: Int32Array };

async function json(path, body, quiet) {
  return (await request(path, body === undefined ? {} : post(body), quiet)).json();
}

/** Binary endpoint → { data: TypedArray, meta: {shape, dtype, ...} } */
async function bin(path, body, quiet) {
  const r = await request(path, body === undefined ? {} : post(body), quiet);
  const meta = JSON.parse(r.headers.get('X-Meta') || '{}');
  const T = DTYPES[meta.dtype] || Float32Array;
  return { data: new T(await r.arrayBuffer()), meta };
}

export const api = {
  meta: () => json('/api/meta'),
  generation: () => json('/api/generation', undefined, true),
  band: (i) => bin(`/api/band?i=${i}`, undefined, true),
  thumbs: (side = 128) => bin(`/api/thumbs?side=${side}`),
  spectrum: (x, y) => json(`/api/spectrum?${qs({ x, y })}`, undefined, true),
  region: (desc) => json('/api/region', desc, true),
  slice: (axis, i) => bin(`/api/slice?${qs({ axis, i })}`, undefined, true),
  line: (x0, y0, x1, y1) => bin(`/api/line?${qs({ x0, y0, x1, y1 })}`),
  /** Derived maps: kind ∈ pca | rx | residual | sam | gradient | mean | std | max | argmax | invalid | math */
  product: (kind, params = {}, body) => bin(`/api/product?${qs({ kind, ...params })}`, body),
  quality: () => json('/api/quality'),
  correlation: () => bin('/api/correlation'),
  stripes: (which) => bin(`/api/stripes?which=${which}`),
  volume: (max = 192) => bin(`/api/volume?max=${max}`),
  scatter: (n = 40000) => bin(`/api/scatter?n=${n}`),
  browse: (dir = '') => json(`/api/browse?${qs({ dir })}`),
  open: (opts) => json('/api/open', opts),
  transpose: (order) => json('/api/transpose', { order }),
  async upload(file, layout = 'auto') {
    return (await request(`/api/upload?${qs({ name: file.name, layout })}`, { method: 'POST', body: file })).json();
  },
};
