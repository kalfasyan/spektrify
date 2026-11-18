// Perceptual colour maps as 256-entry RGB lookup tables.

const hex = (s) => [1, 3, 5].map((i) => parseInt(s.slice(i, i + 2), 16));

const STOPS = {
  viridis: ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#fde725'],
  magma: ['#000004', '#1c1044', '#4f127b', '#812581', '#b5367a', '#e55964', '#fb8761', '#fec287', '#fcfdbf'],
  inferno: ['#000004', '#1f0c48', '#550f6d', '#88226a', '#ba3655', '#e35933', '#f98e09', '#f8cb34', '#fcffa4'],
  plasma: ['#0d0887', '#4c02a1', '#7e03a8', '#a92395', '#cc4778', '#e56b5d', '#f89540', '#fdc328', '#f0f921'],
  cividis: ['#00224e', '#123570', '#3b496c', '#575d6d', '#707173', '#8a8678', '#a59c74', '#c3b369', '#fee838'],
  gray: ['#000000', '#ffffff'],
  bone: ['#000000', '#1c1c27', '#3a3a50', '#535f74', '#6d8592', '#8aa7ad', '#aec8c8', '#d6e4e4', '#ffffff'],
  diverging: ['#053061', '#2166ac', '#4393c3', '#92c5de', '#e8eef2', '#fddbc7', '#f4a582', '#d6604d', '#b2182b', '#67001f'],
  spectral: ['#5e4fa2', '#3288bd', '#66c2a5', '#abdda4', '#e6f598', '#fee08b', '#fdae61', '#f46d43', '#d53e4f', '#9e0142'],
};

function turbo(t) {
  const r = 0.13572138 + t * (4.6153926 + t * (-42.66032258 + t * (132.13108234 + t * (-152.94239396 + t * 59.28637943))));
  const g = 0.09140261 + t * (2.19418839 + t * (4.84296658 + t * (-14.18503333 + t * (4.27729857 + t * 2.82956604))));
  const b = 0.1066733 + t * (12.64194608 + t * (-60.58204836 + t * (110.36276771 + t * (-89.90310912 + t * 27.34824973))));
  return [r, g, b].map((c) => Math.round(255 * Math.min(1, Math.max(0, c))));
}

export const COLORMAPS = [
  { id: 'viridis', group: 'Sequential' },
  { id: 'magma', group: 'Sequential' },
  { id: 'inferno', group: 'Sequential' },
  { id: 'plasma', group: 'Sequential' },
  { id: 'cividis', group: 'Sequential' },
  { id: 'gray', group: 'Sequential' },
  { id: 'bone', group: 'Sequential' },
  { id: 'turbo', group: 'Rainbow' },
  { id: 'spectral', group: 'Rainbow' },
  { id: 'diverging', group: 'Diverging' },
];

const cache = new Map();

/** Uint8Array(256*4) RGBA lookup table. */
export function lut(id, reverse = false) {
  const key = `${id}:${reverse}`;
  if (cache.has(key)) return cache.get(key);
  const out = new Uint8Array(256 * 4);
  const stops = STOPS[id]?.map(hex);
  for (let i = 0; i < 256; i++) {
    const t = (reverse ? 255 - i : i) / 255;
    let c;
    if (id === 'turbo' || !stops) c = turbo(t);
    else {
      const x = t * (stops.length - 1);
      const j = Math.min(stops.length - 2, Math.floor(x));
      const f = x - j;
      c = [0, 1, 2].map((k) => Math.round(stops[j][k] + (stops[j + 1][k] - stops[j][k]) * f));
    }
    out.set([c[0], c[1], c[2], 255], i * 4);
  }
  cache.set(key, out);
  return out;
}

export function drawLut(canvas, id, reverse = false) {
  const ctx = canvas.getContext('2d');
  const L = lut(id, reverse);
  const img = ctx.createImageData(256, 1);
  img.data.set(L);
  const tmp = new OffscreenCanvas(256, 1);
  tmp.getContext('2d').putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(tmp, 0, 0, canvas.width, canvas.height);
}

/** Map a Float32Array to RGBA bytes with a stretch (lo, hi, gamma) and LUT. NaN → magenta. */
export function colorize(src, out, lo, hi, gamma, L, nanRGBA = [255, 61, 242, 255]) {
  const k = 1 / (hi - lo || 1e-12);
  const inv = 1 / gamma;
  const n = src.length;
  for (let i = 0; i < n; i++) {
    const v = src[i];
    const o = i * 4;
    if (!Number.isFinite(v)) { out[o] = nanRGBA[0]; out[o + 1] = nanRGBA[1]; out[o + 2] = nanRGBA[2]; out[o + 3] = nanRGBA[3]; continue; }
    let t = (v - lo) * k;
    t = t < 0 ? 0 : t > 1 ? 1 : t;
    if (inv !== 1) t = Math.pow(t, inv);
    const j = (t * 255 + 0.5) | 0;
    out[o] = L[j * 4]; out[o + 1] = L[j * 4 + 1]; out[o + 2] = L[j * 4 + 2]; out[o + 3] = 255;
  }
  return out;
}
