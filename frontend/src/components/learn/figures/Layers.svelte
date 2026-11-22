<script module>
  // Neural network architectures as stacks of feature maps.
  const CAPTIONS = {
    cnn: ['Input: an image, or a cube with one channel per band', 'Convolution: many small filters, each making its own feature map', 'Pooling: keep the strongest response in each 2 × 2 block, so maps shrink', 'Deeper: more maps on a coarser grid, each seeing a larger patch', 'At the end, a few numbers: one score per class'],
    resnet: ['A deep network: block after block', 'Residual connections add each block’s input to its output', 'So the signal (and the training gradient) can flow straight through: very deep networks still train'],
    unet: ['Encoder: shrink the image, grow the number of features', 'Decoder: grow it back to full size', 'Skip connections carry fine detail across, so the output is sharp: one label per pixel'],
    attention: ['Cut the image into patches: tokens', 'One patch weighs how relevant every other patch is to it (line thickness)', 'Every patch does this at once, so distant parts of the image interact in a single layer'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, box, iso, lerp, rng, tile } from '../../../lib/figures.js';

  let { o, f } = $props();
  const S = 11;
  // [channels (x), spatial size (y and z), label]
  const CNN = [[0.6, 7, 'input'], [1.6, 7, 'conv'], [1.6, 4.5, 'pool'], [3, 4.5, 'conv'], [0.8, 0.8, 'scores']];
  let cnn = $derived.by(() => {
    let x = 0;
    return CNN.map(([c, s, name], i) => {
      const b = box(x, -s / 2, -s / 2 + 3.5, c, s, s, S);
      const l = iso(x + c / 2, s / 2 + 1, -s / 2 + 3.5, S);
      x += c + 1.6;
      return { b, l, name, show: at(f, i), cur: Math.round(f) === i };
    });
  });
  // ResNet / U-Net: 2D blocks.
  const RES = [0, 1, 2, 3, 4].map((i) => 30 + i * 56);
  const UNET = [[30, 40, 60], [80, 80, 40], [130, 120, 22], [180, 80, 40], [230, 40, 60]]; // [x, y, h]
  // Attention: a 6 × 4 grid of patch tiles.
  const r = rng(5);
  const PATCHES = Array.from({ length: 24 }, (_, i) => ({ x: i % 6, y: Math.floor(i / 6), w: r() }));
  let query = $derived(f < 1.5 ? 8 : 15);
</script>

<svg viewBox="0 0 320 200" role="img" aria-label="Network architecture">
  {#if o.show === 'cnn'}
    <g transform="translate(110 110)">
      {#each cnn as L}
        <g style="opacity:{0.15 + 0.85 * L.show}">
          <polygon class="face-l" points={L.b.left} /><polygon class="face-r" points={L.b.right} />
          <polygon class="edge" points={L.b.top} style="fill:{L.cur ? 'color-mix(in srgb, var(--fig-accent) 60%, var(--fig-top))' : ''}" />
          <text class="lbl" class:strong={L.cur} x={L.l[0]} y={L.l[1] + 14} text-anchor="middle">{L.name}</text>
        </g>
      {/each}
    </g>
  {:else if o.show === 'resnet'}
    {#each RES as x, i}
      <rect class="block" x={x} y="90" width="36" height="34" rx="6" />
      {#if i}<line class="arrow" x1={RES[i - 1] + 36} x2={x} y1="107" y2="107" />{/if}
      {#if i < RES.length - 1}
        <path class="skip" d="M{x + 18},90 C{x + 18},50 {x + 74},50 {x + 74},90" style="opacity:{at(f, 1)}" />
        <circle cx={x + 74} cy="92" r="5" class="plus" style="opacity:{at(f, 1)}" />
      {/if}
    {/each}
    {@const p = Math.min(1, Math.max(0, f - 1.2))}
    <circle class="dot" cx={lerp(RES[0] + 18, RES[4] + 18, p)} cy={56 + Math.abs(Math.sin(p * Math.PI * 4)) * -6} r="5" style="fill:var(--fig-accent);opacity:{at(f, 2)}" />
  {:else if o.show === 'unet'}
    {#each UNET as [x, y, h], i}
      {@const show = i < 3 ? 1 : at(f, 1)}
      <rect class="block" x={x} y={y} width={i === 2 ? 34 : 22} height={h} rx="4" style="opacity:{show}" />
      {#if i}<line class="arrow" x1={UNET[i - 1][0] + (i === 3 ? 34 : 22)} y1={UNET[i - 1][1] + UNET[i - 1][2] / 2} x2={x} y2={y + h / 2} style="opacity:{show}" />{/if}
    {/each}
    {#each [[0, 4], [1, 3]] as [a, b]}
      <line class="skip" x1={UNET[a][0] + 22} x2={UNET[b][0]} y1={UNET[a][1] + 8} y2={UNET[b][1] + 8} style="opacity:{at(f, 2)}" />
    {/each}
    <text class="lbl" x="30" y="120">image</text><text class="lbl" x="220" y="120" style="opacity:{at(f, 1)}">label map</text>
  {:else}
    <g transform="translate(160 50)">
      {#each PATCHES as p, i}
        <polygon class="edge" points={tile(p.x * 1.1 - 3.3, p.y * 1.1 - 2.2, 0, 1, 1, 22)} style="fill:{i === query && at(f, 1) ? 'var(--fig-accent)' : `color-mix(in srgb, var(--fig-green) ${20 + p.w * 50}%, var(--fig-top))`}" />
      {/each}
      {#each PATCHES as p, i}
        {#if i !== query}
          {@const q = PATCHES[query]}
          {@const a = iso(q.x * 1.1 - 2.8, q.y * 1.1 - 1.7, 0, 22)}
          {@const b = iso(p.x * 1.1 - 2.8, p.y * 1.1 - 1.7, 0, 22)}
          <line class="attn" x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} style="stroke-width:{0.4 + 3.5 * ((p.w * 7 + query) % 1) ** 2};opacity:{at(f, 1) * 0.8}" />
        {/if}
      {/each}
    </g>
  {/if}
</svg>
