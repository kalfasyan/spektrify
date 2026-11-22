<script module>
  // A sensor's filter mosaic: the Bayer pattern of colour cameras, or a 4 × 4 spectral one.
  const CAPTIONS = {
    bayer: ['Each pixel sits under one colour filter: the Bayer pattern, half green, a quarter red, a quarter blue', 'So each pixel measures only one of red, green or blue', 'Demosaicing estimates the two missing colours from the neighbours'],
    spectral: ['A snapshot spectral sensor repeats a 4 × 4 pattern of 16 narrow filters', 'One shot captures all 16 bands, but each band only on a sparse grid of pixels', 'Demosaicing rebuilds each band at full size, at some cost in sharpness'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, lerp, nmColor, tile } from '../../../lib/figures.js';

  let { o, f } = $props();
  const N = 8, S = 15;
  const BAYER = ['var(--fig-red)', 'var(--fig-green)', 'var(--fig-green)', 'var(--fig-blue)'];
  // A smooth colourful scene so the demosaiced result looks like an image.
  const scene = (x, y) => `hsl(${(200 + x * 18 + y * 9) % 360} 55% ${45 + 12 * Math.sin((x + y) / 3)}%)`;
  const BAND = 5; // the spectral band highlighted
  let t1 = $derived(at(f, 1)), t2 = $derived(at(f, 2));
  let cells = $derived(Array.from({ length: N * N }, (_, i) => {
    const x = i % N, y = Math.floor(i / N);
    if (o.show === 'bayer') {
      const filt = BAYER[(y % 2) * 2 + (x % 2)];
      const fill = t2 > 0 ? `color-mix(in srgb, ${scene(x, y)} ${t2 * 100}%, ${filt})` : filt;
      return { x, y, fill, opacity: lerp(1, 0.55 + 0.45 * ((x * 7 + y * 3) % 5) / 4, t1 * (1 - t2)) };
    }
    const k = (y % 4) * 4 + (x % 4), mine = k === BAND;
    const color = nmColor(460 + k * 30);
    return { x, y, fill: mine || t2 === 0 ? color : `color-mix(in srgb, ${nmColor(460 + BAND * 30)} ${t2 * 100}%, var(--fig-top))`, opacity: mine ? 1 : lerp(1, 0.18, t1 * (1 - t2)) };
  }));
</script>

<svg viewBox="0 0 320 200" role="img" aria-label="A sensor's filter mosaic">
  <g transform="translate(160 30)">
    {#each cells as c}
      <polygon class="edge" points={tile(c.x - N / 2 + 0.04, c.y - N / 2 + 0.04 + 4, 0, 0.92, 0.92, S)} style="fill:{c.fill};fill-opacity:{c.opacity}" />
    {/each}
  </g>
  {#if o.show === 'spectral'}
    <text class="lbl strong" x="14" y="190" style="opacity:{t1}">band {BAND + 1} of 16</text>
  {/if}
</svg>
