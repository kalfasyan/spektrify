// Pure spectrum transforms used by the spectrum plot and CSV export.

export const VIEWS = {
  values: { label: 'Value' },
  normalized: { label: 'Value ÷ mean' },
  derivative: { label: 'd value / dλ' },
  ratio: { label: 'Ratio to reference' },
  zscore: { label: 'z-score vs scene' },
};

/**
 * Transform a spectrum for display.
 * ctx: {axis: number[], ref?: number[], sceneMean?: number[], sceneStd?: number[]}
 * Returns an array the same length as `v` (null where undefined).
 */
export function transform(v, view, ctx) {
  if (!v) return null;
  const n = v.length;
  const out = new Array(n);
  switch (view) {
    case 'normalized': {
      let s = 0, c = 0;
      for (const x of v) if (x != null && Number.isFinite(x)) { s += Math.abs(x); c++; }
      const m = c ? s / c : 1;
      for (let i = 0; i < n; i++) out[i] = v[i] == null ? null : v[i] / (m || 1);
      return out;
    }
    case 'derivative': {
      const ax = ctx.axis;
      for (let i = 0; i < n; i++) {
        const a = Math.max(0, i - 1), b = Math.min(n - 1, i + 1);
        out[i] = v[a] == null || v[b] == null || ax[b] === ax[a] ? null : (v[b] - v[a]) / (ax[b] - ax[a]);
      }
      return out;
    }
    case 'ratio': {
      const r = ctx.ref || ctx.sceneMean;
      for (let i = 0; i < n; i++) out[i] = v[i] == null || !r?.[i] ? null : v[i] / r[i];
      return out;
    }
    case 'zscore': {
      const m = ctx.sceneMean, s = ctx.sceneStd;
      for (let i = 0; i < n; i++) out[i] = v[i] == null || m?.[i] == null || !s?.[i] ? null : (v[i] - m[i]) / s[i];
      return out;
    }
    default:
      return v;
  }
}

/** Envelope transform for ±σ bands where it stays meaningful (values / normalized / ratio). */
export function transformEnvelope(mean, std, view, ctx) {
  if (!std || !['values', 'normalized', 'ratio', 'zscore'].includes(view)) return null;
  const lo = Array.from(mean, (m, i) => (m == null || std[i] == null ? null : m - std[i]));
  const hi = Array.from(mean, (m, i) => (m == null || std[i] == null ? null : m + std[i]));
  if (view === 'normalized') {
    let s = 0, c = 0;
    for (const x of mean) if (x != null) { s += Math.abs(x); c++; }
    const k = c ? s / c : 1;
    return [lo.map((x) => (x == null ? null : x / k)), hi.map((x) => (x == null ? null : x / k))];
  }
  return [transform(lo, view, ctx), transform(hi, view, ctx)];
}
