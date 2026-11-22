<script module>
  // A cube travelling through preprocessing steps. Without `steps`, it shows the lesson
  // step's own pipeline; captions use each step's help text from the server.
  import { api } from '../../../lib/api.js';

  const help = $state({});
  let asked = false;
  function loadHelp() {
    if (asked) return;
    asked = true;
    api.steps().then((r) => { for (const s of r.steps) help[s.name] = s.help; }).catch(() => {});
  }
  export function stages(o, step) {
    const names = o.steps ?? (step?.pipeline ?? []).map((p) => p.name);
    return ['raw', ...names];
  }
  export function captions(o, step) {
    if (!o.steps) loadHelp();
    return stages(o, step).map((n, i) => (i === 0 ? 'Start: the raw cube, as the camera recorded it' : `${i}. ${n}${help[n] ? `: ${help[n].replace(/\.$/, '')}` : ''}`));
  }
</script>

<script>
  import { at, box, iso, lerp } from '../../../lib/figures.js';

  let { o, f, step } = $props();
  let names = $derived(stages(o, step));
  let n = $derived(names.length);
  let gapU = $derived(n > 1 ? Math.min(3.4, 13 / (n - 1)) : 0);
  const S = 15, C = 1.4;
  let plates = $derived(names.map((name, i) => {
    const x = i * gapU;
    return { name, i, plate: box(x - 0.4, -0.4, 0, C + 0.8, C + 0.8, 0.15, S), label: iso(x + C / 2, C + 1.2, 0, S), done: at(f, i) };
  }));
  let pos = $derived(Math.max(0, Math.min(n - 1, f)) * gapU);
  let token = $derived(box(pos, 0, 0.2 + Math.sin(Math.PI * (f % 1)) * 0.6, C, C, C, S));
  let width = $derived(iso((n - 1) * gapU + C, 0, 0, S)[0] - iso(0, C, 0, S)[0]);
</script>

<svg viewBox="0 0 320 200" role="img" aria-label="Preprocessing pipeline">
  <g transform="translate({160 - width / 2 - iso(0, C, 0, S)[0]} {110 - iso((n - 1) * gapU, 0, 0, S)[1] / 2})">
    {#each plates as p, i}
      {#if i > 0}
        {@const a = iso((i - 1) * gapU + C + 0.5, C / 2, 0.1, S)}
        {@const b = iso(i * gapU - 0.5, C / 2, 0.1, S)}
        <line class="ray" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} />
      {/if}
      <polygon class="face-l" points={p.plate.left} />
      <polygon class="face-r" points={p.plate.right} />
      <polygon class="edge" points={p.plate.top} style="fill:color-mix(in srgb, var(--fig-accent) {p.done * 35}%, var(--fig-top))" />
      <text class="lbl" class:strong={Math.round(f) === i} x={p.label[0]} y={p.label[1] + 8} text-anchor="middle">{p.name}</text>
    {/each}
    <polygon class="face-l" points={token.left} style="fill:color-mix(in srgb, var(--fig-blue) {lerp(30, 70, Math.min(1, f / Math.max(1, n - 1)))}%, var(--fig-left))" />
    <polygon class="face-r" points={token.right} style="fill:color-mix(in srgb, var(--fig-green) {lerp(30, 70, Math.min(1, f / Math.max(1, n - 1)))}%, var(--fig-right))" />
    <polygon class="edge" points={token.top} style="fill:color-mix(in srgb, var(--fig-accent) 50%, var(--fig-top))" />
  </g>
</svg>
