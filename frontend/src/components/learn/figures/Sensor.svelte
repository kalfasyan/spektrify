<script module>
  // Pixels as wells that collect electrons: photons in, a number out.
  const CAPTIONS = {
    photons: ['Light arrives as photons', 'A photon that is absorbed frees one electron in a pixel’s well. Some pass through unabsorbed: the quantum efficiency is below 100 %', 'More light, more electrons: the well fills'],
    counts: ['Each pixel has collected some electrons', 'Reading out turns the charge into a voltage…', '…and the converter turns the voltage into a number: the pixel value'],
    shot: ['The same light falls on every pixel', 'Photons arrive at random, so each well catches a slightly different number', 'That spread is shot noise, about √N for N electrons: more light, relatively less noise'],
    saturate: ['A well holds only so many electrons', 'Too much light: the wells fill to the top', 'Full wells all read the same maximum value: the detail there is lost (clipped)'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, box, gauss, iso, lerp, nmColor, rng } from '../../../lib/figures.js';

  let { o, f } = $props();
  const N = 5, S = 15, H = 4, GAP = 1.7, MAXV = 4095;
  const r = rng(9);
  const BASE = [1.2, 2.0, 2.9, 1.6, 2.4];
  const NOISE = BASE.map(() => gauss(r) * 0.45);
  const PHOTONS = Array.from({ length: 22 }, (_, k) => ({ well: k % N, dx: 0.2 + r() * 0.6, dy: 0.2 + r() * 0.6, z: 5.5 + r() * 3, nm: 420 + r() * 300, lost: r() < 0.25 }));
  let t1 = $derived(at(f, 1)), t2 = $derived(at(f, 2));
  let levels = $derived(BASE.map((b, i) => {
    switch (o.show) {
      case 'photons': return lerp(0.15, lerp(b * 0.35, b, t2), t1);
      case 'shot': return Math.max(0.2, 2.4 + NOISE[i] * t1);
      case 'saturate': return Math.min(H, b * lerp(1, 2.6, t1));
      default: return b;
    }
  }));
  let wells = $derived(levels.map((lv, i) => ({ i, glass: box(i * GAP, 0, 0, 1, 1, H, S), fill: box(i * GAP, 0, 0, 1, 1, lv, S), full: lv >= H - 1e-6, label: iso(i * GAP + 0.5, 1.6, 0, S), value: Math.round((lv / H) * MAXV) })));
  let showNumbers = $derived(o.show === 'counts' ? t2 : o.show === 'saturate' ? t2 : o.show === 'shot' ? t1 : 0);
</script>

<svg viewBox="0 0 320 210" role="img" aria-label="Pixels as wells collecting electrons">
  <g transform="translate(110 112)">
    {#each wells as w}
      <polygon class="face-l" points={w.glass.left} style="fill-opacity:.35" />
      <polygon class="face-r" points={w.glass.right} style="fill-opacity:.35" />
      <polygon points={w.fill.left} style="fill:var(--fig-blue);opacity:.75" />
      <polygon points={w.fill.right} style="fill:var(--fig-blue);opacity:.6" />
      <polygon points={w.fill.top} style="fill:{w.full && o.show === 'saturate' ? 'var(--fig-red)' : 'var(--fig-blue)'};opacity:.9" />
      <polygon class="edge" points={w.glass.top} />
      <text class="lbl strong mono" x={w.label[0]} y={w.label[1] + 12} text-anchor="middle" style="opacity:{showNumbers}">{w.value}</text>
    {/each}
    {#if o.show === 'photons'}
      {#each PHOTONS as p}
        {@const z = lerp(p.z, p.lost ? -1.5 : levels[p.well], t1)}
        {@const [x, y] = iso(p.well * GAP + p.dx, p.dy, z, S)}
        <circle cx={x} cy={y} r="3" style="fill:{p.lost && t1 > 0.5 ? 'var(--fig-ink-2)' : nmColor(p.nm)};opacity:{p.lost ? 1 - t1 * 0.6 : 1 - t1 * 0.85}" />
      {/each}
    {/if}
  </g>
  {#if o.show === 'counts'}
    <g style="opacity:{t1}">
      <text class="lbl strong" x="14" y="22">charge → voltage → number (0 to {MAXV})</text>
    </g>
  {:else if o.show === 'saturate'}
    <text class="lbl strong" x="14" y="22" style="opacity:{t2};fill:var(--fig-red)">full well = {MAXV}: clipped</text>
  {:else if o.show === 'shot'}
    <text class="lbl strong" x="14" y="22" style="opacity:{t2}">mean ± √mean</text>
  {/if}
</svg>
