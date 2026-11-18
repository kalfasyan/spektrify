<script>
  // Data-quality dashboard: findings first, then per-band health charts, band-to-band
  // correlation and line-artefact maps. Every chart links back to the band it shows.
  import { onMount, tick } from 'svelte';
  import { ctl, store } from '../lib/controller.svelte.js';
  import { api } from '../lib/api.js';
  import { canvasUV, drawCorrelation, drawLineMap, drawMetrics, METRICS, metricHit } from '../lib/engines/qualityCharts.js';
  import { fmt } from '../lib/util.js';

  const s = store.state;
  let root;
  let metricCv = $state(), corrCv = $state(), colCv = $state(), rowCv = $state();
  let data = $state(null); // {corr, cols, rows} (plain objects; never mutated)
  let tip = $state(null); // {x, y, lines: [], warn: []}
  let geom = null;

  const q = $derived(s.quality);
  const m = $derived(s.meta);
  const nDefects = $derived(q ? q.bad_columns.length + q.bad_rows.length : 0);
  const medSnr = $derived(q ? median(q.snr) : null);

  onMount(() => {
    const ro = new ResizeObserver(() => draw());
    ro.observe(root);
    return () => ro.disconnect();
  });

  // (Re)load the chart data whenever the quality scan changes.
  $effect(() => {
    if (!q) { data = null; return; }
    Promise.all([api.correlation(), api.stripes('columns'), api.stripes('rows')])
      .then(([corr, cols, rows]) => { data = { corr: corr.data, cols, rows }; return tick(); })
      .then(draw)
      .catch((e) => ctl.toast(e.message, 'error'));
  });
  $effect(() => { s.cmap; draw(); });

  function draw() {
    if (!data || !metricCv || !q) return;
    geom = drawMetrics(metricCv, m, q, (b) => store.bandLabel(b));
    drawCorrelation(corrCv, data.corr);
    const cm = s.cmap === 'gray' ? 'gray' : 'inferno';
    drawLineMap(colCv, data.cols, cm);
    drawLineMap(rowCv, data.rows, cm);
  }

  const show = (e, lines, warn = []) => (tip = { x: e.clientX + 14, y: e.clientY + 12, lines, warn });
  const hide = () => (tip = null);
  const reasons = (b) => q.flags.find((f) => f.band === b)?.reasons || [];

  function metricMove(e) {
    const hit = geom && metricHit(geom, metricCv, e);
    if (!hit) return hide();
    const { band: b, metric: mt } = hit;
    const v = mt.band ? `${fmt(m.bandMean[b], 4)} ± ${fmt(m.bandStd[b], 3)}` : mt.pct ? `${fmt((q[mt.key][b] || 0) * 100, 3)}%` : fmt(q[mt.key][b], 4);
    show(e, [store.bandLabel(b), `${mt.label}: ${v}`], reasons(b));
  }
  function metricClick(e) { const hit = geom && metricHit(geom, metricCv, e); if (hit) ctl.openBand(hit.band); }

  function corrAt(e) { const C = m.bands, [u, v] = canvasUV(corrCv, e); return [Math.floor(u * C), Math.floor(v * C)]; }
  function corrMove(e) {
    const C = m.bands, [i, j] = corrAt(e);
    if (i < 0 || j < 0 || i >= C || j >= C) return hide();
    show(e, [`${store.bandLabel(j, true)} × ${store.bandLabel(i, true)}`, `r = ${fmt(data.corr[j * C + i], 4)}`]);
  }
  function corrClick(e) { const [i] = corrAt(e); if (i >= 0 && i < m.bands) ctl.openBand(i); }

  function mapAt(cv, r, e) { const [C, N] = r.meta.shape, [u, v] = canvasUV(cv, e); return [Math.floor(u * N), C - 1 - Math.floor(v * C), N, C]; }
  function mapMove(cv, r, axis, e) {
    const [i, b, N, C] = mapAt(cv, r, e);
    if (i < 0 || i >= N || b < 0 || b >= C) return hide();
    show(e, [`${axis} = ${i} · ${store.bandLabel(b, true)}`, `${fmt(r.data[b * N + i], 3)} σ`]);
  }
  function mapClick(cv, r, e) { const [, b, , C] = mapAt(cv, r, e); if (b >= 0 && b < C) ctl.openBand(b); }

  function median(a) { const f = a.filter((v) => v != null && Number.isFinite(v)).sort((x, y) => x - y); return f.length ? f[Math.floor(f.length / 2)] : null; }
</script>

<div class="quality-scroll" bind:this={root}>
  {#if !q || !m}
    <div class="placeholder">Scanning the cube…</div>
  {:else}
    <div class="q-head"><h2>Data quality</h2><span class="hint">{m.name} · {m.height} × {m.width} × {m.bands}</span></div>
    <div class="stat-tiles">
      {@render stat('Flagged bands', q.flags.length, q.flags.length ? 'bad' : 'ok')}
      {@render stat('Line defects', nDefects, nDefects ? 'bad' : 'ok')}
      {@render stat('Invalid pixels', q.invalid_pixels.toLocaleString(), q.invalid_pixels ? 'bad' : 'ok')}
      {@render stat('Median SNR', medSnr == null ? '—' : fmt(medSnr, 3))}
      {@render stat('Value range', `${fmt(m.global.p01, 3)} … ${fmt(m.global.p99, 3)}`)}
    </div>
    <div style="height:14px"></div>
    <div class="q-grid">
      <div class="card span-5">
        <h3>Findings</h3>
        <div class="sub">{q.flags.length + nDefects ? 'Click a band to inspect it' : 'Heuristic checks for common sensor artefacts'}</div>
        <ul class="issue-list">
          {#each q.issues as t}<li>{t}</li>{:else}<li class="ok">No problems detected.</li>{/each}
        </ul>
        {#if q.flags.length}
          <div style="height:10px"></div>
          <table class="flag-table"><tbody>
            {#each q.flags as f}
              <tr title="Open this band" onclick={() => ctl.openBand(f.band)}><td>{store.bandLabel(f.band)}</td><td>{f.reasons.join(' · ')}</td></tr>
            {/each}
          </tbody></table>
        {/if}
      </div>
      <div class="card span-7">
        <h3>Per-band health</h3>
        <div class="sub">Red = flagged band · click a chart to open the band</div>
        <canvas bind:this={metricCv} style:height="{METRICS.length * 74}px" onpointermove={metricMove} onpointerleave={hide} onclick={metricClick}></canvas>
      </div>
      <div class="card span-5">
        <h3>Band-to-band correlation</h3>
        <div class="sub">Blocks = redundant ranges · thin crosses = bands unlike their neighbours · click for the band</div>
        <canvas bind:this={corrCv} style="aspect-ratio:1;max-width:520px" onpointermove={corrMove} onpointerleave={hide} onclick={corrClick}></canvas>
      </div>
      <div class="card span-7">
        <h3>Line artefacts per band</h3>
        <div class="sub">Median second difference across each column (top) / row (bottom), in noise σ. Vertical lines through all bands = dead or hot detector lines; a lit row = a striped band.</div>
        <div class="ctrl-label">Columns (x → , λ ↑)</div>
        <canvas bind:this={colCv} style="height:230px" onpointermove={(e) => data && mapMove(colCv, data.cols, 'x', e)} onpointerleave={hide} onclick={(e) => data && mapClick(colCv, data.cols, e)}></canvas>
        <div style="height:8px"></div>
        <div class="ctrl-label">Rows (y → , λ ↑)</div>
        <canvas bind:this={rowCv} style="height:230px" onpointermove={(e) => data && mapMove(rowCv, data.rows, 'y', e)} onpointerleave={hide} onclick={(e) => data && mapClick(rowCv, data.rows, e)}></canvas>
      </div>
    </div>
  {/if}
</div>
{#if tip}
  <div class="chart-tip" style:left="{tip.x}px" style:top="{tip.y}px">
    {#each tip.lines as l}<div>{l}</div>{/each}
    {#each tip.warn as w}<div style="color:var(--bad)">⚠ {w}</div>{/each}
  </div>
{/if}

{#snippet stat(k, v, cls = '')}
  <div class="stat"><div class="k">{k}</div><div class="v {cls}">{v}</div></div>
{/snippet}
