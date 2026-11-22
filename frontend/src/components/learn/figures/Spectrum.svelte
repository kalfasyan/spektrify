<script module>
  // Reflectance spectra across wavelength, with a rainbow under the axis.
  const CAPTIONS = {
    sample: ['A material reflects a smooth curve of light across wavelengths', 'A spectral camera measures it in bands, each a narrow window of wavelengths', 'What you get is one number per band: the curve, sampled'],
    absorb: ['White light holds every wavelength', 'A leaf absorbs blue and red for photosynthesis and reflects green: that is why it looks green', 'Past 700 nm it reflects strongly: invisible to us, bright to the camera'],
    edge: ['The spectrum of a healthy leaf', 'The red edge: reflectance jumps between about 680 and 750 nm', 'A stressed plant: a lower plateau and an edge shifted to shorter wavelengths'],
    compare: ['A leaf', 'Soil: a gentle rise, no edge', 'Water: dark, and almost black in the near infrared'],
    angle: ['The same leaf in sun and in shadow: same shape, different brightness', 'Draw each spectrum as an arrow (two bands shown): both point the same way', 'Soil points elsewhere. The angle between arrows compares shape, not brightness'],
    smooth: ['A noisy spectrum: every band has its own random error', 'Savitzky–Golay fits a small polynomial in a window that slides along the bands', 'The smoothed curve keeps peaks and edges but drops the noise'],
    snv: ['The same material under different light: shifted and scaled', 'Standard normal variate: subtract each spectrum’s mean, divide by its spread', 'Now the curves lie on top of each other: only the shape is left'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, gauss, lerp, nmColor, path, rng, scale } from '../../../lib/figures.js';
  import Axes from './Axes.svelte';

  let { o, f } = $props();
  const B = [44, 16, 296, 168];
  const X = scale([420, 980], [B[0], B[2]]), Y = scale([0, 1], [B[3], B[1]]);
  const NM = Array.from({ length: 113 }, (_, i) => 420 + i * 5);
  const sig = (v) => 1 / (1 + Math.exp(-v));
  const leaf = (nm, shift = 0, top = 0.48) => 0.04 + 0.09 * Math.exp(-(((nm - 550) / 35) ** 2)) + top * sig((nm - 712 - shift) / 12);
  const soil = (nm) => 0.12 + 0.25 * ((nm - 420) / 560);
  const water = (nm) => 0.09 * Math.exp(-(nm - 420) / 110) + 0.005;
  const line = (fn) => path(NM.map((nm) => [X(nm), Y(fn(nm))]));
  const BANDS = Array.from({ length: 8 }, (_, i) => 450 + i * 70);
  const r = rng(3);
  const NOISE = NM.map(() => gauss(r) * 0.035);
  const smooth = (i) => { let a = 0, n = 0; for (let k = -4; k <= 4; k++) if (NOISE[i + k] !== undefined) { a += NOISE[i + k]; n++; } return a / n; };
  const SNV = [[1, 0], [0.55, 0.12], [1.35, -0.02]];
  const stats = (fn) => { const v = NM.map(fn), m = v.reduce((a, b) => a + b) / v.length; return [m, Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / v.length)]; };

  let t1 = $derived(at(f, 1)), t2 = $derived(at(f, 2));
  // Vector view for "angle": reflectance at 670 nm (x) and 800 nm (y).
  const V = { x: scale([0, 0.55], [60, 280]), y: scale([0, 0.55], [170, 20]) };
  const vec = (fn, k) => [V.x(fn(670) * k * 2), V.y(fn(800) * k)]; // x doubled for legibility
</script>

<svg viewBox="0 0 320 210" role="img" aria-label="Reflectance spectra">
  {#if o.show !== 'angle' || t1 < 1}
    <g style="opacity:{o.show === 'angle' ? 1 - t1 : 1}">
      <Axes box={B} x="nm" y="reflectance" />
      {#each NM.slice(0, -1) as nm}<rect x={X(nm)} y={B[3] + 4} width={X(nm + 5) - X(nm) + 0.5} height="5" style="fill:{nmColor(nm)}" />{/each}
      {#each [500, 700, 900] as nm}<text class="lbl" x={X(nm)} y={B[3] + 22} text-anchor="middle">{nm}</text>{/each}

      {#if o.show === 'sample'}
        <path class="curve" d={line((nm) => leaf(nm))} style="opacity:{1 - t2 * 0.75}" />
        {#each BANDS as nm}
          <rect x={X(nm - 12)} y={B[1]} width={X(nm + 12) - X(nm - 12)} height={B[3] - B[1]} class="band" style="opacity:{t1 * 0.5};fill:{nmColor(nm)}" />
          <circle cx={X(nm)} cy={Y(leaf(nm))} r="4" class="dot" style="opacity:{t1}" />
        {/each}
        <path class="curve accent" d={path(BANDS.map((nm) => [X(nm), Y(leaf(nm))]))} style="opacity:{t2}" />
      {:else if o.show === 'absorb'}
        <path d="{path(NM.filter((nm) => nm <= 700).map((nm) => [X(nm), Y(lerp(0.9, leaf(nm), t1))]))} L{X(700)},{Y(0.9)} L{X(420)},{Y(0.9)}Z" class="shade" style="opacity:{t1 * 0.6}" />
        <path class="curve" d={line((nm) => lerp(0.9, leaf(nm), t1))} />
        <text class="lbl strong" x={X(470)} y={Y(0.62)} style="opacity:{t1}">absorbed</text>
        <rect x={X(700)} y={B[1]} width={X(980) - X(700)} height={B[3] - B[1]} class="band" style="opacity:{t2 * 0.25};fill:var(--fig-accent)" />
        <text class="lbl strong" x={X(760)} y={Y(0.78)} style="opacity:{t2}">near infrared</text>
      {:else if o.show === 'edge'}
        <rect x={X(680)} y={B[1]} width={X(750) - X(680)} height={B[3] - B[1]} class="band" style="opacity:{t1 * 0.3};fill:var(--fig-accent)" />
        <text class="lbl strong" x={X(690)} y={B[1] + 10} style="opacity:{t1}">red edge</text>
        <path class="curve" d={line((nm) => leaf(nm))} />
        <path class="curve accent dashed" d={line((nm) => leaf(nm, -18, 0.3))} style="opacity:{t2}" />
      {:else if o.show === 'compare'}
        <path class="curve" style="stroke:var(--fig-green)" d={line((nm) => leaf(nm))} />
        <path class="curve" style="stroke:var(--fig-accent);opacity:{t1}" d={line(soil)} />
        <path class="curve" style="stroke:var(--fig-blue);opacity:{t2}" d={line(water)} />
        <text class="lbl" x={X(930)} y={Y(leaf(930)) - 6} style="fill:var(--fig-green)">leaf</text>
        <text class="lbl" x={X(930)} y={Y(soil(930)) - 6} style="fill:var(--fig-accent);opacity:{t1}">soil</text>
        <text class="lbl" x={X(930)} y={Y(water(930)) - 6} style="fill:var(--fig-blue);opacity:{t2}">water</text>
      {:else if o.show === 'angle'}
        <path class="curve" d={line((nm) => leaf(nm))} />
        <path class="curve dashed" d={line((nm) => leaf(nm) * 0.5)} />
        <text class="lbl" x={X(930)} y={Y(0.55)}>sun</text>
        <text class="lbl" x={X(930)} y={Y(0.3)}>shadow</text>
      {:else if o.show === 'smooth'}
        <path class="curve thin" d={path(NM.map((nm, i) => [X(nm), Y(leaf(nm) + NOISE[i])]))} style="opacity:{1 - t2 * 0.6}" />
        {@const c = 520 + Math.min(1, Math.max(0, f - 1)) * 380}
        <rect x={X(c - 22)} y={B[1]} width={X(c + 22) - X(c - 22)} height={B[3] - B[1]} class="band" style="opacity:{t1 * (1 - t2) * 0.35};fill:var(--fig-accent)" />
        <path class="curve accent" d={path(NM.map((nm, i) => [X(nm), Y(leaf(nm) + smooth(i))]))} style="opacity:{t2}" />
      {:else if o.show === 'snv'}
        {#each SNV as [k, b], j}
          {@const fn = (nm) => leaf(nm) * k + b}
          {@const [m, sd] = stats(fn)}
          <path class="curve" style="stroke:{['var(--fig-green)', 'var(--fig-blue)', 'var(--fig-accent)'][j]}" d={line((nm) => lerp(fn(nm), 0.42 + 0.2 * ((fn(nm) - m) / sd), t2))} />
          <line class="ray" x1={B[0]} x2={B[2]} y1={Y(lerp(m, 0.42, t2))} y2={Y(lerp(m, 0.42, t2))} style="opacity:{t1 * (1 - t2)}" />
        {/each}
      {/if}
    </g>
  {/if}
  {#if o.show === 'angle' && t1 > 0}
    <g style="opacity:{t1}">
      <Axes box={[60, 20, 280, 170]} x="band 1" y="band 2" />
      {#each [[leaf, 1, 'var(--fig-green)', 'sun'], [leaf, 0.5, 'var(--fig-green)', 'shadow'], [soil, 1, 'var(--fig-accent)', 'soil']] as [fn, k, c, name], j}
        {@const [x, y] = vec(fn, k)}
        <g style="opacity:{j === 2 ? t2 : 1}">
          <line class="arrow" style="stroke:{c}" x1="60" y1="170" x2={x} y2={y} />
          <circle cx={x} cy={y} r="3.5" style="fill:{c}" />
          <text class="lbl" x={x + 6} y={y + 3}>{name}</text>
        </g>
      {/each}
    </g>
  {/if}
</svg>
