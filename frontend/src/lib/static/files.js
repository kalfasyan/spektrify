// Reading the snapshot files that `python -m spektrify.server.snapshot` writes.
// Arrays are gzip-compressed byte planes (see `pack()` there): all first bytes of every
// value, then all second bytes, and so on.

const TYPES = { float16: Uint16Array, float32: Float32Array, float64: Float64Array, uint8: Uint8Array, uint16: Uint16Array, uint32: Uint32Array, int32: Int32Array };

async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url} (${r.status})`);
  return r;
}

export const loadJson = async (url) => (await get(url)).json();

/** Fetch a `.zbin` file → TypedArray of its dtype (float16 comes back as Float32Array). */
export async function loadArray(url, dtype) {
  const r = await get(url);
  let bytes = new Uint8Array(await r.arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) bytes = await gunzip(bytes); // unless the host already did
  const T = TYPES[dtype];
  if (!T) throw new Error(`unsupported dtype ${dtype}`);
  const size = T.BYTES_PER_ELEMENT, n = bytes.length / size;
  const out = new Uint8Array(bytes.length);
  for (let b = 0; b < size; b++) {
    const plane = bytes.subarray(b * n, (b + 1) * n);
    for (let i = 0; i < n; i++) out[i * size + b] = plane[i];
  }
  const arr = new T(out.buffer);
  return dtype === 'float16' ? halfToFloat(arr) : arr;
}

async function gunzip(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

let HALF = null; // all 65536 float16 values, built once
function halfToFloat(u16) {
  if (!HALF) {
    HALF = new Float32Array(65536);
    for (let h = 0; h < 65536; h++) {
      const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 0x1f, m = h & 0x3ff;
      HALF[h] = e === 0 ? s * m * 2 ** -24 : e === 31 ? (m ? NaN : s * Infinity) : s * (1 + m / 1024) * 2 ** (e - 15);
    }
  }
  const out = new Float32Array(u16.length);
  for (let i = 0; i < u16.length; i++) out[i] = HALF[u16[i]];
  return out;
}
