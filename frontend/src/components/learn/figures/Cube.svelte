<script module>
  // A spectral cube drawn as a stack of band slices. "band" and "rgb" follow the viewer: the
  // highlighted slices are the band(s) on screen right now.
  const CAPTIONS = {
    stack: ['One greyscale picture for one band of wavelengths', 'One picture for every band, from blue to near infrared', 'Stacked, they make a cube: x, y and wavelength'],
    band: ['The cube on screen, one slice per band', 'The slice pulled out is the band shown in the viewer: move the band slider and it follows'],
    pixel: ['Pick one pixel position', 'Follow it down through every band', 'Its values, band by band, are its spectrum'],
    rgb: ['Pick three bands', 'Show them as red, green and blue', 'Each pixel gets a colour from three numbers'],
  };
  export const captions = (o) => CAPTIONS[o.focus];
</script>

<script>
  import { store } from '../../../lib/controller.svelte.js';
  import { at, box, iso, lerp, nmColor, path, scale } from '../../../lib/figures.js';

  let { o, f } = $props();
  const N = 9, W = 6, H = 0.22, S = 12;
  const PX = [3, 1]; // the pixel followed in "pixel"

  // Map the viewer's bands onto the drawn slices; on a cube without wavelengths, 450-950 nm.
  const s = store.state;
  let nb = $derived(store.nBands || 1);
  const slice = (band) => Math.round((band / Math.max(1, nb - 1)) * (N - 1));
  const nmOf = (i) => 450 + (i / (N - 1)) * 500;
  let liveBand = $derived(slice(s.band));
  let liveRgb = $derived(s.rgb.map(slice));
  const RGB = ['var(--fig-red)', 'var(--fig-green)', 'var(--fig-blue)'];

  let gap = $derived(o.focus === 'stack' ? lerp(1.15, 0.34, at(f, 2)) : o.focus === 'band' ? 0.34 : lerp(0.34, 0.95, at(f, 1)));
  let layers = $derived(Array.from({ length: N }, (_, i) => {
    let visible = 1, slide = 0, color = null;
    if (o.focus === 'stack') visible = i === 0 ? 1 : at(f, 1);
    if (o.focus === 'band' && i === liveBand) { slide = 3.4 * at(f, 1) + 0.5; color = 'var(--fig-accent)'; }
    if (o.focus === 'rgb') {
      const k = liveRgb.indexOf(i);
      if (k >= 0) color = RGB[k];
    }
    return { i, visible, z: i * gap, color, faces: box(0, slide, 0, W, W, H, S), out: slide > 0 };
  }).sort((a, b) => a.out - b.out)); // a slice pulled out like a drawer is drawn last
  // A short spectrum for the followed pixel (a leaf-like curve).
  const leaf = (t) => 0.2 + 0.15 * Math.exp(-((t - 0.2) ** 2) / 0.01) + 0.55 / (1 + Math.exp(-(t - 0.55) * 25));
  let spec = $derived.by(() => {
    const x = scale([0, 1], [228, 300]), y = scale([0, 1], [170, 100]);
    return Array.from({ length: N }, (_, i) => [x(i / (N - 1)), y(leaf(i / (N - 1)))]);
  });
  let ax = $derived({ a: iso(W + 0.6, 0, 0, S), b: iso(W + 0.6, 0, (N - 1) * gap + 1.2, S), x: iso(W / 2, W + 0.9, 0, S), y: iso(W + 0.9, W / 2, 0, S) });
  const ox = 120, oy = 118;
</script>

<svg viewBox="0 0 320 210" role="img" aria-label="A spectral cube as a stack of band slices">
  <g transform="translate({ox} {oy})">
    {#each layers as L (L.i)}
      <g style="opacity:{L.visible}" transform="translate(0 {-L.z * S})">
        <polygon class="face-l" points={L.faces.left} />
        <polygon class="face-r" points={L.faces.right} />
        <polygon class="face-t" points={L.faces.top} style="fill:{L.color ?? nmColor(nmOf(L.i))};fill-opacity:{L.color ? 0.9 : 0.28}" />
        <polygon class="edge" points={L.faces.top} />
        {#if o.focus === 'pixel'}
          {@const c = box(PX[0], PX[1], H, 1, 1, 0.01, S)}
          <polygon points={c.top} style="fill:var(--fig-accent);opacity:{L.i === N - 1 ? 1 : at(f, 1)}" />
        {/if}
      </g>
    {/each}
    {#if o.focus === 'pixel'}
      {@const top = iso(PX[0] + 0.5, PX[1] + 0.5, (N - 1) * gap + H, S)}
      {@const bot = iso(PX[0] + 0.5, PX[1] + 0.5, 0, S)}
      <line class="ray" x1={top[0]} y1={top[1]} x2={bot[0]} y2={bot[1]} style="opacity:{at(f, 1)}" />
    {/if}
    <line class="axis" x1={ax.a[0]} y1={ax.a[1]} x2={ax.b[0]} y2={ax.b[1]} />
    <text class="lbl" x={ax.b[0] + 6} y={ax.b[1] + 4}>λ</text>
    <text class="lbl" x={ax.x[0] - 14} y={ax.x[1] + 10}>x</text>
    <text class="lbl" x={ax.y[0] + 2} y={ax.y[1] + 12}>y</text>
  </g>
  {#if o.focus === 'pixel'}
    <g style="opacity:{at(f, 2)}">
      <path class="curve" d={path(spec)} />
      {#each spec as [x, y], i}<circle cx={x} cy={y} r="3" style="fill:{nmColor(nmOf(i))}" />{/each}
      <text class="lbl" x="228" y="188">wavelength →</text>
    </g>
  {/if}
  {#if o.focus === 'rgb'}
    <g style="opacity:{at(f, 1)}">
      {#each ['R', 'G', 'B'] as c, k}
        <rect x={236 + k * 24} y="60" width="20" height="20" rx="3" style="fill:{RGB[k]}" />
        <text class="lbl" x={242 + k * 24} y="94">{c}</text>
      {/each}
    </g>
    <g style="opacity:{at(f, 2)}">
      <path class="ray" d="M266,100 L266,118" />
      <rect x="252" y="122" width="28" height="28" rx="4" style="fill:hsl(95 35% 45%)" />
      <text class="lbl" x="244" y="166">one pixel</text>
    </g>
  {/if}
  {#if o.focus === 'band'}
    <text class="lbl strong" x="12" y="20">band {s.band + 1} of {nb}</text>
  {/if}
</svg>
