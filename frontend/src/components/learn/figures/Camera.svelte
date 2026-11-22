<script module>
  // Image formation: a pinhole camera, a push-broom scanner building a cube, and two views.
  const CAPTIONS = {
    pinhole: ['Light from the top of the object passes through the pinhole and lands low on the sensor', 'Light from the bottom lands high: the image is upside down', 'Move the object away and its image shrinks: size = focal length × height ÷ distance'],
    lens: ['A lens bends every ray from one point back to one point: a sharp image', 'Move the sensor away from that point and the rays land as a disc: defocus blur', 'Close the aperture (a larger f-number): the disc shrinks and more stays sharp, but less light gets in'],
    pushbroom: ['A push-broom camera sees one line of the scene at a time', 'A prism or grating spreads that line’s light by wavelength: line × bands on the sensor', 'As the camera moves, line after line…', '…the cube is built row by row'],
    epipolar: ['Camera 1 sees a point here: in 3D it lies somewhere on this ray', 'Seen from camera 2, every point on that ray falls on one line in its image: the epipolar line', 'So the match is searched along that line, and two crossing rays fix the point in 3D'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, box, iso, lerp, nmColor, tile } from '../../../lib/figures.js';

  let { o, f } = $props();
  let t1 = $derived(at(f, 1)), t2 = $derived(at(f, 2));

  // Pinhole (side view): axis at y = 110, pinhole at x = 170, sensor at x = 250.
  const AX = 110, PH = 170, SEN = 250;
  let objX = $derived(lerp(90, 25, t2));
  const imgY = (x, y) => AX - (y - AX) * (SEN - PH) / (PH - x);
  let top = $derived([objX, 60]), bot = $derived([objX, AX + 10]);

  // Lens (side view): a point at P, lens at x = LX, focus at FX on the axis' other side.
  const P0 = [40, 70], LX = 140, FX = 240, FY = 2 * AX - 70 - 20;
  let sensorX = $derived(lerp(FX, 285, at(f, 1)));
  let aperture = $derived(lerp(45, 16, at(f, 2)));
  let lensRays = $derived([-1, -0.5, 0, 0.5, 1].map((k) => {
    const ly = AX + k * aperture, sy = ly + ((FY - ly) * (sensorX - LX)) / (FX - LX);
    return { ly, sy };
  }));

  // Push-broom: a 6 × 6 scene; scanned rows become slabs of a cube to the right.
  const N = 6, S = 12, BANDS = 2.2;
  const SCENE = Array.from({ length: N * N }, (_, i) => { const x = i % N, y = Math.floor(i / N); return (x - 2.5) ** 2 + (y - 2.5) ** 2 < 5 ? 'hsl(110 35% 45%)' : x > 3 ? 'hsl(30 30% 55%)' : 'hsl(210 30% 60%)'; });
  let row = $derived(f < 2 ? 0 : Math.min(N - 1, (f - 2) * (N - 1)));
  let scan = $derived.by(() => {
    const cam = iso(N / 2, row + 0.5, 5.5, S), a = iso(0, row + 0.5, 0.2, S), b = iso(N, row + 0.5, 0.2, S);
    return { slit: box(-0.2, row, 0.05, N + 0.4, 1, 0.12, S), cam, fan: `${cam[0]},${cam[1]} ${a[0]},${a[1]} ${b[0]},${b[1]}` };
  });
  let rowsDone = $derived(f < 1 ? 0 : Math.floor(row) + 1);

  // Two views (top-down): cameras below, the true point above.
  const C1 = [80, 180], C2 = [240, 180], P = [150, 60], PLANE = 150;
  const along = (c, p, y) => [c[0] + (p[0] - c[0]) * (y - c[1]) / (p[1] - c[1]), y];
  const cand = [0.35, 0.55, 0.75, 1, 1.3].map((k) => [C1[0] + (P[0] - C1[0]) * k, C1[1] + (P[1] - C1[1]) * k]);
</script>

<svg viewBox="0 0 320 200" role="img" aria-label="Camera geometry">
  {#if o.show === 'pinhole'}
    <line class="grid" x1="10" x2="310" y1={AX} y2={AX} />
    <line class="axis" x1={PH} x2={PH} y1="20" y2={AX - 4} /><line class="axis" x1={PH} x2={PH} y1={AX + 4} y2="190" />
    <line class="axis thick" x1={SEN} x2={SEN} y1="40" y2="180" />
    <text class="lbl" x={PH - 18} y="16">pinhole</text><text class="lbl" x={SEN - 14} y="194">sensor</text>
    <line class="arrow hot" x1={bot[0]} y1={bot[1]} x2={top[0]} y2={top[1]} />
    <path class="ray" style="stroke:var(--fig-accent)" d="M{top[0]},{top[1]} L{SEN},{imgY(...top)}" />
    <path class="ray" style="stroke:var(--fig-blue);opacity:{t1}" d="M{bot[0]},{bot[1]} L{SEN},{imgY(...bot)}" />
    <line class="arrow hot" style="opacity:{t1}" x1={SEN + 6} y1={imgY(...bot)} x2={SEN + 6} y2={imgY(...top)} />
    <text class="lbl" x={objX - 10} y={AX + 26}>object</text>
  {:else if o.show === 'lens'}
    <line class="grid" x1="10" x2="310" y1={AX} y2={AX} />
    <ellipse cx={LX} cy={AX} rx="7" ry={aperture + 4} class="cam" style="fill-opacity:.5" />
    {#each lensRays as r}
      <path class="ray" style="stroke:var(--fig-accent);stroke-dasharray:none;opacity:.8" d="M{P0[0]},{P0[1]} L{LX},{r.ly} L{sensorX},{r.sy}" />
    {/each}
    <circle cx={P0[0]} cy={P0[1]} r="4" style="fill:var(--fig-accent)" />
    <line class="axis thick" x1={sensorX} x2={sensorX} y1="40" y2="190" />
    <line style="stroke:var(--fig-red);stroke-width:5;stroke-linecap:round" x1={sensorX - 6} x2={sensorX - 6} y1={Math.min(...lensRays.map((r) => r.sy))} y2={Math.max(...lensRays.map((r) => r.sy)) + 0.1} />
    <text class="lbl" x={LX - 12} y="20">lens</text><text class="lbl" x={sensorX - 16} y="202">sensor</text>
    <text class="lbl" x="22" y="58">a point</text>
  {:else if o.show === 'pushbroom'}
    <g transform="translate(92 70)">
      {#each SCENE as c, i}<polygon class="edge" points={tile(i % N, Math.floor(i / N), 0, 0.95, 0.95, S)} style="fill:{c}" />{/each}
      <polygon class="win top" points={scan.slit.top} />
      <polygon class="ray-fan" points={scan.fan} />
      <rect class="cam" x={scan.cam[0] - 12} y={scan.cam[1] - 14} width="24" height="12" rx="3" />
    </g>
    <g transform="translate(230 30)" style="opacity:{t1}">
      <text class="lbl" x="-20" y="-6">sensor: x × bands</text>
      {#each Array(N) as _, x}{#each Array(8) as _, k}<rect x={x * 9 - 20} y={k * 6} width="8" height="5" style="fill:{nmColor(450 + k * 70)};opacity:.85" />{/each}{/each}
    </g>
    <g transform="translate(210 150)">
      {#each Array(rowsDone) as _, r}
        {@const sl = box(0, r * 0.9, 0, N * 0.9, 0.85, BANDS, 9)}
        <polygon class="face-l" points={sl.left} /><polygon class="face-r" points={sl.right} />
        <polygon class="edge" points={sl.top} style="fill:color-mix(in srgb, var(--fig-green) 35%, var(--fig-top))" />
      {/each}
    </g>
  {:else}
    <line class="grid" x1="20" x2="300" y1={PLANE} y2={PLANE} />
    {#each [C1, C2] as c, k}
      <polygon class="cam" points="{c[0]},{c[1]} {c[0] - 30},{PLANE} {c[0] + 30},{PLANE}" />
      <text class="lbl" x={c[0] - 22} y={c[1] + 14}>camera {k + 1}</text>
    {/each}
    {@const end = [C1[0] + (P[0] - C1[0]) * 1.45, C1[1] + (P[1] - C1[1]) * 1.45]}
    <line class="ray" style="stroke:var(--fig-accent)" x1={C1[0]} y1={C1[1]} x2={end[0]} y2={end[1]} />
    <circle class="dot" cx={along(C1, P, PLANE)[0]} cy={PLANE} r="4" style="fill:var(--fig-accent)" />
    {#each cand as q}
      {@const im = along(C2, q, PLANE)}
      <circle class="pt" cx={q[0]} cy={q[1]} r="3" style="opacity:{t1}" />
      <line class="ray" x1={C2[0]} y1={C2[1]} x2={q[0]} y2={q[1]} style="opacity:{t1 * 0.5}" />
      <circle class="dot" cx={im[0]} cy={PLANE} r="3" style="fill:var(--fig-blue);opacity:{t1}" />
    {/each}
    <line class="boundary" style="stroke:var(--fig-blue);opacity:{t1}" x1={along(C2, cand[0], PLANE)[0]} x2={along(C2, cand[cand.length - 1], PLANE)[0]} y1={PLANE} y2={PLANE} />
    <line class="ray" style="stroke:var(--fig-blue);opacity:{t2}" x1={C2[0]} y1={C2[1]} x2={P[0]} y2={P[1]} />
    <circle cx={P[0]} cy={P[1]} r="6" class="ring hot" style="opacity:{t2}" />
    <text class="lbl strong" x={P[0] + 10} y={P[1] - 4} style="opacity:{t2}">the point</text>
  {/if}
</svg>
