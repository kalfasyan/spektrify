<script module>
  // Signals as sums of waves: Fourier, aliasing and filtering, on one image row.
  const CAPTIONS = {
    sum: ['A slow wave', 'Add a faster, weaker one', 'And a faster one still', 'Their sum. Any image row is a sum of waves; the bars on the right (how much of each) are its Fourier spectrum'],
    alias: ['A fine pattern: a fast wave', 'Sample it too sparsely (dots)…', '…and the samples trace a slow wave that was never there: aliasing'],
    filter: ['A row of an image: a slow wave plus fine detail', 'Low-pass keeps only the slow part: a blur', 'High-pass keeps only the fine part: detail and edges'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, lerp, path, scale } from '../../../lib/figures.js';

  let { o, f } = $props();
  const W = [20, 230];
  const X = scale([0, 1], W);
  const XS = Array.from({ length: 241 }, (_, i) => i / 240);
  const COMP = [[1, 1], [3, 0.5], [7, 0.3]]; // [cycles, amplitude]
  const COL = ['var(--fig-blue)', 'var(--fig-green)', 'var(--fig-accent)'];
  const wave = ([k, a], x) => a * Math.sin(2 * Math.PI * k * x);
  const row = (fn, y0, h) => path(XS.map((x) => [X(x), y0 - fn(x) * h]));
  let t = $derived([at(f, 0), at(f, 1), at(f, 2), at(f, 3)]);
  const N_SAMPLES = 10, FAST = 9;
  const samples = Array.from({ length: N_SAMPLES + 1 }, (_, i) => i / N_SAMPLES);
</script>

<svg viewBox="0 0 320 200" role="img" aria-label="Waves">
  {#if o.show === 'sum'}
    {#each COMP as c, i}
      <path class="curve" style="stroke:{COL[i]};opacity:{t[i] * (1 - 0.6 * t[3])}" d={row((x) => wave(c, x), 30 + i * 36, 14)} />
    {/each}
    <line class="grid" x1={W[0]} x2={W[1]} y1="160" y2="160" />
    <path class="curve" d={row((x) => COMP.reduce((s, c, i) => s + t[i] * wave(c, x), 0), 160, 18)} />
    <text class="lbl" x={W[0]} y="196">sum</text>
    <g transform="translate(250 0)">
      <line class="axis" x1="0" x2="60" y1="160" y2="160" />
      {#each COMP as [k, a], i}
        <rect x={k * 7} y={160 - a * 90 * t[i]} width="8" height={a * 90 * t[i]} rx="1.5" style="fill:{COL[i]}" />
      {/each}
      <text class="lbl" x="0" y="176">frequency →</text>
    </g>
  {:else if o.show === 'alias'}
    <line class="grid" x1={W[0]} x2={W[1]} y1="100" y2="100" />
    <path class="curve" style="opacity:{1 - 0.7 * t[2]}" d={row((x) => Math.sin(2 * Math.PI * FAST * x), 100, 50)} />
    {#each samples as x}
      <line class="ray" x1={X(x)} x2={X(x)} y1="40" y2="160" style="opacity:{t[1] * 0.6}" />
      <circle class="dot" cx={X(x)} cy={100 - Math.sin(2 * Math.PI * FAST * x) * 50} r="4.5" style="opacity:{t[1]}" />
    {/each}
    <path class="curve accent" style="opacity:{t[2]}" d={row((x) => -Math.sin(2 * Math.PI * (N_SAMPLES - FAST) * x), 100, 50)} />
    <text class="lbl strong" x="240" y="60" style="opacity:{t[1]}">{N_SAMPLES} samples</text>
    <text class="lbl" x="240" y="74" style="opacity:{t[1]}">for {FAST} cycles</text>
    <text class="lbl strong" x="240" y="130" style="opacity:{t[2]}; fill:var(--fig-accent)">looks like</text>
    <text class="lbl strong" x="240" y="144" style="opacity:{t[2]}; fill:var(--fig-accent)">1 cycle</text>
  {:else}
    {@const low = (x) => 0.8 * Math.sin(2 * Math.PI * x)}
    {@const high = (x) => 0.3 * Math.sin(2 * Math.PI * 11 * x) + (x > 0.62 && x < 0.66 ? 0.5 : 0)}
    <line class="grid" x1={W[0]} x2={W[1]} y1="100" y2="100" />
    <path class="curve" style="opacity:{1 - 0.75 * t[1]}" d={row((x) => low(x) + high(x), 100, 50)} />
    <path class="curve accent" style="opacity:{t[1] * (1 - t[2])}" d={row(low, 100, 50)} />
    <path class="curve" style="stroke:var(--fig-blue);opacity:{t[2]}" d={row(high, 100, 50)} />
    <g transform="translate(250 0)">
      <line class="axis" x1="0" x2="60" y1="160" y2="160" />
      <rect x="4" y={160 - 70 * lerp(1, 1 - t[2], t[1])} width="9" height={70 * lerp(1, 1 - t[2], t[1])} rx="1.5" style="fill:var(--fig-accent)" />
      <rect x="44" y={160 - 30 * (1 - t[1] + t[2])} width="9" height={30 * (1 - t[1] + t[2])} rx="1.5" style="fill:var(--fig-blue)" />
      <text class="lbl" x="0" y="176">slow · fast</text>
    </g>
  {/if}
</svg>
