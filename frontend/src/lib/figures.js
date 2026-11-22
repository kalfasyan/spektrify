// Drawing helpers shared by the lesson diagrams (components/learn/figures/). Diagrams are plain
// SVG computed from a continuous frame number `f`: frame 2 → 3 animates as f goes 2.0 → 3.0,
// so every diagram animates by interpolating between its frames, with no animation library.

export const clamp01 = (t) => Math.max(0, Math.min(1, t));
export const lerp = (a, b, t) => a + (b - a) * t;
/** 0 before frame `i`, 1 once frame `i` is reached, in between while animating towards it. */
export const at = (f, i) => clamp01(f - i + 1);

/** Deterministic pseudo-random numbers (mulberry32), so a diagram looks the same every time. */
export function rng(seed = 1) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), a | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/** Normal(0, 1) samples from a uniform generator (Box–Muller). */
export const gauss = (rand) => Math.sqrt(-2 * Math.log(rand() + 1e-9)) * Math.cos(2 * Math.PI * rand());

/** Linear map from a data range to a pixel range. */
export const scale = ([d0, d1], [r0, r1]) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0);

/** SVG path through [x, y] points. */
export const path = (p) => p.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('');
/** SVG points attribute. */
export const pts = (p) => p.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');

// ------------------------------------------------------------------ isometric projection
// World axes: x runs to the lower right, y to the lower left, z up. `s` is pixels per unit.
const C30 = Math.cos(Math.PI / 6);
export const iso = (x, y, z = 0, s = 1) => [(x - y) * C30 * s, (x + y) * 0.5 * s - z * s];

/** The three faces of a box you can see: top, left (the +y side) and right (the +x side). */
export function box(x, y, z, w, d, h, s) {
  const P = (a, b, c) => iso(a, b, c, s);
  return {
    top: pts([P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + d, z + h), P(x, y + d, z + h)]),
    left: pts([P(x, y + d, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x, y + d, z + h)]),
    right: pts([P(x + w, y, z), P(x + w, y + d, z), P(x + w, y + d, z + h), P(x + w, y, z + h)]),
  };
}
/** A flat square on the ground plane (or at height z). */
export const tile = (x, y, z, w, d, s) =>
  pts([iso(x, y, z, s), iso(x + w, y, z, s), iso(x + w, y + d, z, s), iso(x, y + d, z, s)]);

// ------------------------------------------------------------------ colour
/** Colour of a wavelength in nm: the visible rainbow, then a dull red-brown for near infrared. */
export function nmColor(nm) {
  if (nm >= 700) return `hsl(8 ${Math.max(15, 45 - (nm - 700) / 10)}% 42%)`;
  const hue = 265 - clamp01((nm - 420) / 280) * 265;
  return `hsl(${hue.toFixed(0)} 75% 52%)`;
}
/** Grey for a value 0..1. */
export const grey = (v) => { const g = Math.round(30 + clamp01(v) * 210); return `rgb(${g},${g},${g})`; };
