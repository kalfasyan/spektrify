<script module>
  // A small greyscale image drawn as a grid of blocks whose height is the pixel's brightness.
  const CAPTIONS = {
    values: ['An image is a grid of pixels, each holding one brightness', 'Brightness is just a number: here it is drawn as height'],
    levels: ['Many grey levels: heights change smoothly', 'Only 4 levels: neighbours snap to the same step and smooth ramps turn into bands'],
    coarse: ['Every pixel is one sample of the scene', 'Average each 2 × 2 block: fewer, bigger pixels, and the fine detail is gone'],
    neighbours: ['One pixel, at a row and a column', 'Its 4 neighbours share an edge with it', 'Add the diagonals: 8 neighbours'],
    threshold: ['Brightness as height', 'A threshold is a flat cut at one level', 'Above the cut becomes 1, below becomes 0: a mask'],
    histogram: ['Every pixel has a value', 'Drop each pixel into a bin by its value…', '…and the heights of the piles are the histogram'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, box, grey, iso, lerp } from '../../../lib/figures.js';

  let { o, f } = $props();
  const N = 6, S = 14, HMAX = 3, T = 0.45, BINS = 6, CUBE = 0.38;
  const value = (x, y) => Math.min(1, 0.12 + 0.8 * Math.exp(-((x - 3.3) ** 2 + (y - 2.2) ** 2) / 4.5) + 0.04 * x);
  const cells = [];
  for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) cells.push({ x, y, v: value(x + 0.5, y + 0.5) });
  const quant = (v) => Math.round(v * 3) / 3;
  const block = (c) => cells.filter((d) => (d.x >> 1) === (c.x >> 1) && (d.y >> 1) === (c.y >> 1)).reduce((a, d) => a + d.v, 0) / 4;
  // Histogram: where each pixel lands (bin along x, stacked up).
  const piles = new Array(BINS).fill(0);
  const target = cells.map((c) => { const b = Math.min(BINS - 1, Math.floor(c.v * BINS)); return { b, k: piles[b]++ }; });
  const CENTER = 2 * N + 3, NB4 = new Set([CENTER - 1, CENTER + 1, CENTER - N, CENTER + N]);
  const NB8 = new Set([...NB4, CENTER - N - 1, CENTER - N + 1, CENTER + N - 1, CENTER + N + 1]);

  let blocks = $derived(cells.map((c, i) => {
    let { x, y } = c, z = 0, h = c.v * HMAX, v = c.v, fill = null, w = 1;
    switch (o.show) {
      case 'values': h = lerp(0.08, c.v * HMAX, at(f, 1)); break;
      case 'levels': v = lerp(c.v, quant(c.v), at(f, 1)); h = v * HMAX; break;
      case 'coarse': v = lerp(c.v, block(c), at(f, 1)); h = v * HMAX; w = lerp(0.92, 1, at(f, 1)); break;
      case 'neighbours':
        h = 0.08;
        if (i === CENTER) fill = 'var(--fig-accent)';
        else if (NB4.has(i) && at(f, 1)) fill = `color-mix(in srgb, var(--fig-blue) ${at(f, 1) * 100}%, ${grey(c.v)})`;
        else if (NB8.has(i) && at(f, 2)) fill = `color-mix(in srgb, var(--fig-blue) ${at(f, 2) * 60}%, ${grey(c.v)})`;
        break;
      case 'threshold': {
        const t = at(f, 2);
        h = lerp(c.v * HMAX, 0.08, t);
        if (t > 0) fill = c.v > T ? `color-mix(in srgb, var(--fig-accent) ${t * 100}%, ${grey(c.v)})` : `color-mix(in srgb, var(--fig-top) ${t * 100}%, ${grey(c.v)})`;
        break;
      }
      case 'histogram': {
        const t = at(f, 1), g = target[i];
        h = CUBE * 0.9;
        x = lerp(c.x, g.b * 1.5 - 1.5, t);
        y = lerp(c.y, 2.5, t);
        z = lerp(0, g.k * CUBE, t);
        break;
      }
    }
    return { x, y, z, w, h, fill: fill ?? grey(v), depth: x + y + z * 0.01 };
  }).sort((a, b) => a.depth - b.depth));

  let plane = $derived(o.show === 'threshold' ? box(-0.4, -0.4, T * HMAX, N + 0.8, N + 0.8, 0, S) : null);
  let bars = $derived(o.show === 'histogram' ? piles.map((n, b) => ({ n, at: iso(b * 1.5 - 1.5 + 0.45, 3.4, n * CUBE + 0.4, S) })) : []);
</script>

<svg viewBox="0 0 320 210" role="img" aria-label="A small image drawn as blocks">
  <g transform="translate(160 {o.show === 'histogram' ? 100 : 82})">
    {#each blocks as b}
      {@const fc = box(b.x + (1 - b.w) / 2, b.y + (1 - b.w) / 2, b.z, b.w * 0.94, b.w * 0.94, b.h, S)}
      <g>
        <polygon class="face-l" points={fc.left} />
        <polygon class="face-r" points={fc.right} />
        <polygon class="edge" points={fc.top} style="fill:{b.fill}" />
      </g>
    {/each}
    {#if plane}
      <polygon points={plane.top} class="plane" style="opacity:{at(f, 1) * (1 - at(f, 2)) * 0.55}" />
    {/if}
    {#each bars as bar}
      <text class="lbl strong" x={bar.at[0]} y={bar.at[1]} text-anchor="middle" style="opacity:{at(f, 2)}">{bar.n}</text>
    {/each}
  </g>
  {#if o.show === 'histogram'}<text class="lbl" x="200" y="200" style="opacity:{at(f, 1)}">dark → bright</text>{/if}
</svg>
