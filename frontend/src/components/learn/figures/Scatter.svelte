<script module>
  // Pixels as points in a two-band feature space: PCA, k-means, classifiers, RX, unmixing.
  const CAPTIONS = {
    pca: ['Each pixel is a point; its bands are its coordinates', 'PCA finds the direction of largest spread (PC1), then the next one at a right angle (PC2)', 'Keep only PC1: each point becomes one number, and most of the variation survives'],
    kmeans: ['Points without labels, and k = 3 starting centres', 'Give each point the colour of its nearest centre', 'Move each centre to the mean of its points', 'Recolour by the nearest centre again', 'Repeat until nothing changes: three clusters'],
    boundary: ['Training pixels with known labels', 'A linear classifier draws a straight boundary between them', 'New pixels get the class of the side they fall on'],
    overfit: ['A straight boundary makes a few mistakes on the training points', 'A nearest-neighbour rule gets every training point right…', '…but on new points (rings) it makes more mistakes: it learned the noise'],
    metrics: ['Points right of the line are called “leaf” (filled = really leaf)', 'Right calls (true positives, ✓) and false alarms (false positives, ✗)', 'Leaves it missed (false negatives, ringed)'],
    anomaly: ['Background pixels form a cloud', 'RX measures distance in units of the cloud’s own spread: each ring is one step further', 'This pixel is ordinary in each band alone, yet far from the cloud: an anomaly'],
    unmix: ['Pure materials (endmembers) sit at the corners', 'Mixed pixels fall inside the triangle', 'A pixel’s position gives its mix of the three'],
  };
  export const captions = (o) => CAPTIONS[o.show];
</script>

<script>
  import { at, gauss, lerp, rng, scale } from '../../../lib/figures.js';
  import Axes from './Axes.svelte';

  let { o, f } = $props();
  const B = [62, 22, 242, 186]; // near-square, so angles and ellipses look right
  const X = scale([0, 1], [B[0], B[2]]), Y = scale([0, 1], [B[3], B[1]]);
  const COL = ['var(--fig-blue)', 'var(--fig-accent)', 'var(--fig-green)'];
  const r = rng(11);
  const blob = (cx, cy, sd, n, k) => Array.from({ length: n }, () => ({ x: cx + gauss(r) * sd, y: cy + gauss(r) * sd, k }));
  const d2 = (a, b) => (a.x - b.x) ** 2 + (a.y - b.y) ** 2;

  // Shared data sets (seeded, so the picture is always the same).
  const CLUSTERS = [...blob(0.25, 0.3, 0.07, 14, 0), ...blob(0.72, 0.38, 0.07, 14, 1), ...blob(0.48, 0.76, 0.07, 14, 2)];
  const TWO = [...blob(0.33, 0.38, 0.12, 18, 0), ...blob(0.66, 0.62, 0.12, 18, 1)];
  const TEST = [...blob(0.33, 0.38, 0.12, 10, 0), ...blob(0.66, 0.62, 0.12, 10, 1)];
  // The line between the class means, perpendicular to the line joining them.
  const side = (p) => (p.x - 0.5) * 0.33 + (p.y - 0.5) * 0.24 > 0 ? 1 : 0;
  const nn = (p) => TWO.reduce((best, q) => (d2(p, q) < d2(p, best) ? q : best)).k;
  const GRID = 26;
  const CELLS = Array.from({ length: GRID * GRID }, (_, i) => {
    const p = { x: (i % GRID + 0.5) / GRID, y: (Math.floor(i / GRID) + 0.5) / GRID };
    return { ...p, lin: side(p), nn: nn(p) };
  });
  const boundaryLine = [[0.5 - 0.6 * 0.24, 0.5 + 0.6 * 0.33], [0.5 + 0.6 * 0.24, 0.5 - 0.6 * 0.33]];

  // PCA on an elongated cloud: the axes come from its covariance (2 × 2 eigenvectors).
  const PCA = Array.from({ length: 40 }, () => { const t = gauss(r) * 0.17, n = gauss(r) * 0.045; return { x: 0.5 + t * 0.82 + n * -0.57, y: 0.5 + t * 0.57 + n * 0.82 }; });
  const pc = (() => {
    const mx = PCA.reduce((a, p) => a + p.x, 0) / PCA.length, my = PCA.reduce((a, p) => a + p.y, 0) / PCA.length;
    let sxx = 0, syy = 0, sxy = 0;
    for (const p of PCA) { sxx += (p.x - mx) ** 2; syy += (p.y - my) ** 2; sxy += (p.x - mx) * (p.y - my); }
    const th = 0.5 * Math.atan2(2 * sxy, sxx - syy);
    return { mx, my, u: [Math.cos(th), Math.sin(th)] };
  })();

  // k-means, precomputed: frame 0 = start, odd frames assign, even frames move the centres.
  const KM = (() => {
    let c = [{ x: 0.15, y: 0.85 }, { x: 0.3, y: 0.22 }, { x: 0.42, y: 0.3 }];
    const states = [{ c, a: null }];
    for (let it = 0; it < 2; it++) {
      const a = CLUSTERS.map((p) => c.reduce((bi, q, i) => (d2(p, q) < d2(p, c[bi]) ? i : bi), 0));
      states.push({ c, a });
      c = c.map((q, i) => { const m = CLUSTERS.filter((_, j) => a[j] === i); return m.length ? { x: m.reduce((s, p) => s + p.x, 0) / m.length, y: m.reduce((s, p) => s + p.y, 0) / m.length } : q; });
      states.push({ c, a });
    }
    return states;
  })();

  // RX: correlated background and one off-axis pixel.
  const BG = Array.from({ length: 45 }, () => { const t = gauss(r) * 0.16, n = gauss(r) * 0.035; return { x: 0.5 + t * 0.7 + n * -0.7, y: 0.5 + t * 0.7 + n * 0.7 }; });
  const ODD = { x: 0.36, y: 0.64 };
  const ELL = [1, 2, 3].map((k) => ({ rx: 0.16 * k * 0.99, ry: 0.035 * k * 1.3 }));

  // Unmixing: three endmembers and mixed pixels as weighted averages of them.
  const E = [{ x: 0.12, y: 0.85, n: 'leaf' }, { x: 0.88, y: 0.66, n: 'soil' }, { x: 0.22, y: 0.1, n: 'water' }];
  const mix = (w) => ({ x: w[0] * E[0].x + w[1] * E[1].x + w[2] * E[2].x, y: w[0] * E[0].y + w[1] * E[1].y + w[2] * E[2].y });
  const MIXED = Array.from({ length: 24 }, () => { const a = r(), b = r(), c = r(), s = a + b + c; return mix([a / s, b / s, c / s]); });
  const PICK = [0.6, 0.3, 0.1];

  let t1 = $derived(at(f, 1)), t2 = $derived(at(f, 2));
  let km = $derived.by(() => {
    const i = Math.min(KM.length - 1, Math.floor(f)), j = Math.min(KM.length - 1, i + 1), t = f - i;
    const c = KM[i].c.map((q, k) => ({ x: lerp(q.x, KM[j].c[k].x, t), y: lerp(q.y, KM[j].c[k].y, t) }));
    return { c, a: KM[Math.round(f)]?.a ?? KM[i].a };
  });
  let counts = $derived.by(() => {
    const tp = TWO.filter((p) => p.k === 1 && side(p) === 1).length, fp = TWO.filter((p) => p.k === 0 && side(p) === 1).length, fn = TWO.filter((p) => p.k === 1 && side(p) === 0).length;
    return { tp, fp, fn };
  });
</script>

<svg viewBox="0 0 320 200" role="img" aria-label="Pixels as points in a two-band space">
  <Axes box={B} x="band 1" y="band 2" />
  {#if o.show === 'pca'}
    {#each PCA as p}
      {@const q = { x: pc.mx + ((p.x - pc.mx) * pc.u[0] + (p.y - pc.my) * pc.u[1]) * pc.u[0], y: pc.my + ((p.x - pc.mx) * pc.u[0] + (p.y - pc.my) * pc.u[1]) * pc.u[1] }}
      <circle class="pt" cx={X(lerp(p.x, q.x, t2))} cy={Y(lerp(p.y, q.y, t2))} r="3.2" />
    {/each}
    {@const L = 0.42 * t1}
    {@const M = 0.13 * t1}
    <line class="arrow hot" x1={X(pc.mx - pc.u[0] * L)} y1={Y(pc.my - pc.u[1] * L)} x2={X(pc.mx + pc.u[0] * L)} y2={Y(pc.my + pc.u[1] * L)} />
    <line class="arrow" style="opacity:{1 - t2}" x1={X(pc.mx + pc.u[1] * M)} y1={Y(pc.my - pc.u[0] * M)} x2={X(pc.mx - pc.u[1] * M)} y2={Y(pc.my + pc.u[0] * M)} />
    <text class="lbl strong" x={X(pc.mx + pc.u[0] * 0.44) + 4} y={Y(pc.my + pc.u[1] * 0.44)} style="opacity:{t1}">PC1</text>
  {:else if o.show === 'kmeans'}
    {#each CLUSTERS as p, i}<circle class="pt" cx={X(p.x)} cy={Y(p.y)} r="3.2" style={km.a ? `fill:${COL[km.a[i]]}` : ''} />{/each}
    {#each km.c as c, k}<rect class="centre" x={X(c.x) - 6} y={Y(c.y) - 6} width="12" height="12" rx="2" transform="rotate(45 {X(c.x)} {Y(c.y)})" style="fill:{COL[k]}" />{/each}
  {:else if o.show === 'boundary' || o.show === 'overfit' || o.show === 'metrics'}
    {#if o.show === 'overfit'}
      {#each CELLS as c}<rect x={X(c.x - 0.5 / GRID)} y={Y(c.y + 0.5 / GRID)} width={(B[2] - B[0]) / GRID + 0.3} height={(B[3] - B[1]) / GRID + 0.3} style="fill:{COL[lerp(c.lin, c.nn, t1) > 0.5 ? 1 : 0]};opacity:.1" />{/each}
    {/if}
    <line class="boundary" style="opacity:{o.show === 'boundary' ? t1 : o.show === 'overfit' ? 1 - t1 : 1}" x1={X(boundaryLine[0][0])} y1={Y(boundaryLine[0][1])} x2={X(boundaryLine[1][0])} y2={Y(boundaryLine[1][1])} />
    {#each TWO as p}
      {@const right = o.show !== 'metrics' || t1 === 0 ? null : side(p) === 1 ? (p.k === 1 ? '✓' : '✗') : null}
      <circle class="pt" cx={X(p.x)} cy={Y(p.y)} r="3.4" style="fill:{COL[p.k]}" />
      {#if right}<text class="lbl strong" x={X(p.x) + 4} y={Y(p.y) - 3} style="opacity:{t1}">{right}</text>{/if}
      {#if o.show === 'metrics' && p.k === 1 && side(p) === 0}<circle class="ring" cx={X(p.x)} cy={Y(p.y)} r="7" style="opacity:{t2}" />{/if}
    {/each}
    {#if o.show === 'boundary'}
      {#each TEST.slice(0, 8) as p}<circle class="pt hollow" cx={X(p.x)} cy={Y(p.y)} r="4" style="stroke:{COL[side(p)]};opacity:{t2}" />{/each}
    {:else if o.show === 'overfit'}
      {#each TEST as p}
        {@const wrong = nn(p) !== p.k}
        <circle class="pt hollow" cx={X(p.x)} cy={Y(p.y)} r="4.5" style="stroke:{COL[p.k]};opacity:{t2}" />
        {#if wrong}<text class="lbl strong" x={X(p.x) + 5} y={Y(p.y) - 4} style="opacity:{t2}">✗</text>{/if}
      {/each}
    {:else}
      <text class="lbl strong" x="190" y="140" style="opacity:{t1}">TP {counts.tp} · FP {counts.fp}</text>
      <text class="lbl strong" x="190" y="154" style="opacity:{t2}">FN {counts.fn}</text>
      <text class="lbl" x="190" y="168" style="opacity:{t2}">precision {Math.round((100 * counts.tp) / (counts.tp + counts.fp))} %</text>
      <text class="lbl" x="190" y="181" style="opacity:{t2}">recall {Math.round((100 * counts.tp) / (counts.tp + counts.fn))} %</text>
    {/if}
  {:else if o.show === 'anomaly'}
    {#each ELL as e}<ellipse class="ring" cx={X(0.5)} cy={Y(0.5)} rx={(e.rx * (B[2] - B[0]))} ry={(e.ry * (B[3] - B[1]))} transform="rotate(-45 {X(0.5)} {Y(0.5)})" style="opacity:{t1}" />{/each}
    {#each BG as p}<circle class="pt" cx={X(p.x)} cy={Y(p.y)} r="3" />{/each}
    <circle class="pt" cx={X(ODD.x)} cy={Y(ODD.y)} r="4" style="fill:{t2 ? 'var(--fig-red)' : ''}" />
    <circle class="ring hot" cx={X(ODD.x)} cy={Y(ODD.y)} r="9" style="opacity:{t2}" />
  {:else if o.show === 'unmix'}
    <polygon class="simplex" points={E.map((e) => `${X(e.x)},${Y(e.y)}`).join(' ')} />
    {#each MIXED as p}<circle class="pt" cx={X(p.x)} cy={Y(p.y)} r="2.8" style="opacity:{t1}" />{/each}
    {#each E as e, k}
      <circle cx={X(e.x)} cy={Y(e.y)} r="5" style="fill:{COL[[2, 1, 0][k]]}" />
      <text class="lbl strong" x={X(e.x) + (k === 1 ? -26 : 8)} y={Y(e.y) + (k === 2 ? 14 : -6)}>{e.n}</text>
    {/each}
    {@const m = mix(PICK)}
    <g style="opacity:{t2}">
      {#each E as e, k}<line class="ray" x1={X(m.x)} y1={Y(m.y)} x2={X(e.x)} y2={Y(e.y)} />{/each}
      <circle cx={X(m.x)} cy={Y(m.y)} r="5" class="pt" style="fill:var(--fig-ink)" />
      {#each ['60 % leaf', '30 % soil', '10 % water'] as line, k}<text class="lbl strong" x="248" y={112 + k * 14}>{line}</text>{/each}
    </g>
  {/if}
</svg>
