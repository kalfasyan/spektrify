<script module>
  // A 3 × 3 window sliding over a small image, writing one output pixel per position: the
  // picture behind filtering, derivatives and morphology. "corner" shows the Harris idea.
  const LAST = {
    box: 'The output: each pixel replaced by the average of its neighbourhood, so noise is smoothed',
    gauss: 'The output: a weighted average, the centre counting most, so smoothing without blocky artefacts',
    median: 'The output: the middle value of each neighbourhood, so lone outliers simply vanish',
    dx: 'The output: large where brightness changes from left to right (orange up, blue down), zero on flat areas',
    laplace: 'The output: zero on flat areas and ramps, a ± pair on each side of an edge',
    erode: 'The output: a pixel stays 1 only if its whole window is 1, so shapes shrink and specks vanish',
    dilate: 'The output: a pixel becomes 1 if anything in its window is 1, so shapes grow and gaps close',
  };
  const RULE = {
    box: 'multiply by the weights and add up', gauss: 'multiply by the weights and add up', dx: 'multiply by the weights and add up',
    laplace: 'multiply by the weights and add up', median: 'sort the 9 values, keep the middle one', erode: 'keep the smallest value', dilate: 'keep the largest value',
  };
  export function captions(o) {
    if (o.op === 'corner') return ['Flat area: moving the window in any direction changes nothing', 'Edge: moving along it changes nothing, only across it', 'Corner: every direction changes what the window sees, so it is easy to find again'];
    return ['A 3 × 3 window sits on the image', `At each place: ${RULE[o.op]}, and write one output pixel`, 'Slide one pixel to the right and repeat', '…across every row', LAST[o.op]];
  }
</script>

<script>
  import { at, box, clamp01, grey, iso, lerp, rng, tile } from '../../../lib/figures.js';

  let { o, f } = $props();
  const N = 6, M = 4, S = 13, OFF = 8, DOWN = 2.2; // output grid: OFF to the right, DOWN forward
  const WEIGHTS = {
    box: [1, 1, 1, 1, 1, 1, 1, 1, 1].map((w) => w / 9),
    gauss: [1, 2, 1, 2, 4, 2, 1, 2, 1].map((w) => w / 16),
    dx: [-1, 0, 1, -2, 0, 2, -1, 0, 1],
    laplace: [0, 1, 0, 1, -4, 1, 0, 1, 0],
  };
  const LABEL = { box: ['1', '1', '1', '1', '1', '1', '1', '1', '1'], gauss: ['1', '2', '1', '2', '4', '2', '1', '2', '1'] };
  const SIGNED = new Set(['dx', 'laplace']);

  function image(op) {
    const r = rng(7);
    const v = (x, y) => {
      if (op === 'box' || op === 'gauss') return clamp01(0.35 + 0.3 * Math.exp(-((x - 3) ** 2 + (y - 2.5) ** 2) / 4) + (r() - 0.5) * 0.5);
      if (op === 'median') return [7, 16, 26].includes(y * N + x) ? 1 : 0.25 + 0.05 * x;
      if (op === 'dx' || op === 'laplace') return x >= 3 ? 0.85 : 0.2;
      if (op === 'erode') return (x >= 1 && x <= 4 && y >= 1 && y <= 4) || y * N + x === 30 ? 1 : 0;
      if (op === 'dilate') return x >= 1 && x <= 4 && y >= 1 && y <= 4 && x !== 3 ? 1 : 0;
      return x >= 2 && y >= 2 ? 1 : 0; // corner
    };
    return Array.from({ length: N * N }, (_, i) => v(i % N, Math.floor(i / N)));
  }
  let img = $derived(image(o.op));
  const cl = (v) => Math.max(0, Math.min(N - 1, v)); // edges repeat outwards
  const win = (c, r) => [0, 1, 2].flatMap((dy) => [0, 1, 2].map((dx) => img[cl(r + dy) * N + cl(c + dx)]));
  function apply(c, r) {
    const w = win(c, r);
    if (o.op === 'median') return [...w].sort((a, b) => a - b)[4];
    if (o.op === 'erode') return Math.min(...w);
    if (o.op === 'dilate') return Math.max(...w);
    return w.reduce((a, v, i) => a + v * WEIGHTS[o.op][i], 0);
  }
  let out = $derived(Array.from({ length: M * M }, (_, i) => apply(i % M, Math.floor(i / M))));
  let maxAbs = $derived(Math.max(1e-6, ...out.map(Math.abs)));
  const color = (v) => (SIGNED.has(o.op) ? (v >= 0 ? `color-mix(in srgb, var(--fig-accent) ${(v / maxAbs) * 100}%, var(--fig-top))` : `color-mix(in srgb, var(--fig-blue) ${(-v / maxAbs) * 100}%, var(--fig-top))`) : grey(v));

  // Window path: along row 1, then the whole output at the last frame.
  const CORNER_AT = [[3, 3], [0, 3], [1, 1]];
  let corner = $derived(o.op === 'corner');
  let pos = $derived.by(() => {
    if (corner) {
      const i = Math.min(2, Math.floor(f)), t = f - i, a = CORNER_AT[i], b = CORNER_AT[Math.min(2, i + 1)];
      return [lerp(a[0], b[0], t), lerp(a[1], b[1], t)];
    }
    return [Math.min(3, f), 1];
  });
  let done = $derived(corner ? 0 : f >= 3.5 ? M * M : M + Math.round(Math.min(3, f)) + 1);
  let winFade = $derived(corner ? 1 : 1 - at(f, 4));
  let winBox = $derived(box(pos[0], pos[1], 0.05, 3, 3, 0.35, S));
  let link = $derived(corner ? null : [iso(pos[0] + 1.5, pos[1] + 1.5, 0.4, S), iso(OFF + pos[0] + 0.5, DOWN + pos[1] + 0.5, 0.1, S)]);

  // Corner: does shifting the window one pixel this way change what it sees?
  const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  let arrows = $derived.by(() => {
    if (!corner) return [];
    const [c, r] = CORNER_AT[Math.round(Math.min(2, f))];
    const base = win(c, r);
    const cen = iso(pos[0] + 1.5, pos[1] + 1.5, 0.5, S);
    return DIRS.map(([dx, dy]) => {
      const moved = win(c + dx, r + dy);
      const change = moved.some((v, i) => v !== base[i]);
      const tip = iso(pos[0] + 1.5 + dx * 2.3, pos[1] + 1.5 + dy * 2.3, 0.5, S);
      return { cen, tip, change };
    });
  });
</script>

<svg viewBox="0 0 320 210" role="img" aria-label="A 3 by 3 window sliding over an image">
  <g transform="translate({corner ? 160 : 100} {corner ? 58 : 40})">
    {#each img as v, i}
      <polygon class="edge" points={tile(i % N + 0.04, Math.floor(i / N) + 0.04, 0, 0.92, 0.92, S)} style="fill:{grey(v)}" />
    {/each}
    <g style="opacity:{winFade}">
      <polygon class="win" points={winBox.left} />
      <polygon class="win" points={winBox.right} />
      <polygon class="win top" points={winBox.top} />
    </g>
    {#if !corner}
      {#each out as v, i}
        <polygon class="edge" points={tile(OFF + (i % M) + 0.04, DOWN + Math.floor(i / M) + 0.04, 0, 0.92, 0.92, S)}
          style="fill:{i < done ? color(v) : 'transparent'};stroke-dasharray:{i < done ? 'none' : '2 2'}" />
      {/each}
      <line class="ray" x1={link[0][0]} y1={link[0][1]} x2={link[1][0]} y2={link[1][1]} style="opacity:{winFade}" />
    {/if}
    {#each arrows as a}
      <line class="arrow" class:hot={a.change} x1={a.cen[0]} y1={a.cen[1]} x2={a.tip[0]} y2={a.tip[1]} />
      <circle cx={a.tip[0]} cy={a.tip[1]} r="3" class="tip" class:hot={a.change} />
    {/each}
  </g>
  {#if !corner}
    <g transform="translate(14 150)">
      {#if WEIGHTS[o.op]}
        {#each WEIGHTS[o.op] as w, i}
          <rect x={(i % 3) * 20} y={Math.floor(i / 3) * 16} width="19" height="15" rx="2" class="cell" />
          <text class="lbl mono" x={(i % 3) * 20 + 9.5} y={Math.floor(i / 3) * 16 + 11} text-anchor="middle">{LABEL[o.op]?.[i] ?? w}</text>
        {/each}
        {#if LABEL[o.op]}<text class="lbl" x="64" y="28">÷ {o.op === 'box' ? 9 : 16}</text>{/if}
      {:else}
        <text class="lbl strong" x="0" y="30">{{ median: 'middle value', erode: 'minimum', dilate: 'maximum' }[o.op]}</text>
      {/if}
    </g>
    <text class="lbl strong" x={100 + iso(0, 0, 0, S)[0]} y={40 + iso(0, 0, 0, S)[1] - 8} text-anchor="middle">input</text>
    <text class="lbl strong" x={100 + iso(OFF + M, DOWN + M, 0, S)[0]} y={40 + iso(OFF + M, DOWN + M, 0, S)[1] + 16} text-anchor="middle">output</text>
  {/if}
</svg>
