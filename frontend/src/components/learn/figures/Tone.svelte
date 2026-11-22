<script module>
  // An intensity transform as a curve from input brightness to output brightness, with a
  // grey ramp before and after so you can see where contrast is gained and lost.
  const CAPTIONS = {
    linear: ['Each input brightness maps to an output brightness by one rule', 'The identity: nothing changes'],
    log: ['Start from the identity', 'The logarithm lifts the darks and squeezes the brights, so dim detail shows'],
    gamma: ['Start from the identity', 'Gamma below 1 bends the curve up: darks brighten', 'Gamma above 1 bends it down: darks get darker, highlights keep their contrast'],
    stretch: ['Start from the identity', 'A stretch maps a narrow range to the full scale: steeper curve, more contrast'],
  };
  export const captions = (o) => CAPTIONS[o.curve];
</script>

<script>
  import { at, grey, lerp, path, scale } from '../../../lib/figures.js';
  import Axes from './Axes.svelte';

  let { o, f } = $props();
  const B = [52, 18, 212, 172];
  const X = scale([0, 1], [B[0], B[2]]), Y = scale([0, 1], [B[3], B[1]]);
  const clamp = (v) => Math.max(0, Math.min(1, v));
  let fn = $derived.by(() => {
    const t1 = at(f, 1), t2 = at(f, 2);
    switch (o.curve) {
      case 'log': return (v) => lerp(v, Math.log1p(9 * v) / Math.log(10), t1);
      case 'gamma': return (v) => v ** lerp(lerp(1, 0.45, t1), 2.2, t2);
      case 'stretch': return (v) => lerp(v, clamp((v - 0.3) / 0.4), t1);
      default: return (v) => v;
    }
  });
  const XS = Array.from({ length: 61 }, (_, i) => i / 60);
  let curve = $derived(path(XS.map((v) => [X(v), Y(fn(v))])));
  const PROBES = [0.1, 0.3, 0.5, 0.7, 0.9];
</script>

<svg viewBox="0 0 320 210" role="img" aria-label="An intensity transform curve">
  <Axes box={B} x="input" y="output" />
  <line class="grid" x1={X(0)} y1={Y(0)} x2={X(1)} y2={Y(1)} />
  {#each PROBES as v}
    <path class="ray" d="M{X(v)},{B[3]} L{X(v)},{Y(fn(v))} L{B[0]},{Y(fn(v))}" />
  {/each}
  <path class="curve" d={curve} />
  <!-- the same grey ramp before and after the transform -->
  {#each XS.slice(0, 60) as v}
    <rect x={X(v)} y="186" width="3" height="8" style="fill:{grey(v)}" />
    <rect x={X(v)} y="197" width="3" height="8" style="fill:{grey(fn(v))}" />
  {/each}
  <text class="lbl" x="220" y="193">before</text>
  <text class="lbl" x="220" y="204">after</text>
</svg>
