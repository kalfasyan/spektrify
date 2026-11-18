<script>
  import { onMount } from 'svelte';
  import { ctl, store } from '../../lib/controller.svelte.js';
  import { SpectrumPlot } from '../../lib/engines/spectrumPlot.js';
  import { LineProfile } from '../../lib/engines/lineProfile.js';
  import MarksList from './MarksList.svelte';
  import Icon from '../Icon.svelte';

  const s = store.state;
  const ui = ctl.ui;
  let plotCanvas, tip, lineCanvas;

  const views = [
    ['values', 'Values', 'Raw values'],
    ['normalized', 'Shape', 'Each curve divided by its mean (compare shapes, not brightness)'],
    ['derivative', 'Derivative', 'First derivative along the spectrum'],
    ['ratio', 'Ratio', 'Divided by the reference (★) curve, or the scene mean'],
    ['zscore', 'z-score', 'Deviation from the scene mean in units of scene σ'],
  ];
  const toggles = [['specStd', '±σ', 'Show ±1σ envelopes of regions'], ['specMean', 'Scene mean', 'Show the scene mean spectrum'], ['specLog', 'log y', 'Logarithmic y axis']];

  onMount(() => {
    const plot = new SpectrumPlot(plotCanvas, tip);
    plot.on('band', (b) => ctl.goBand(b));
    const lp = new LineProfile(lineCanvas, store);
    lp.on('band', (b) => ctl.goBand(b, { keepMode: true }));
    const d1 = ctl.attach('plot', plot), d2 = ctl.attach('lineProfile', lp);
    ctl.updatePlot();
    return () => { d1(); d2(); };
  });

  $effect(() => { if (ui.bottomTab === 'line') ctl.engines.lineProfile?.draw(); });
</script>

<div class="bottom">
  <div class="bottom-bar">
    <div class="seg small">
      <button class:active={ui.bottomTab === 'spectrum'} onclick={() => (ui.bottomTab = 'spectrum')}>Spectrum</button>
      <button class:active={ui.bottomTab === 'line'} onclick={() => (ui.bottomTab = 'line')}>Line profile</button>
    </div>
    <div class="seg small" style:visibility={ui.bottomTab === 'spectrum' ? 'visible' : 'hidden'}>
      {#each views as [id, label, title]}
        <button class:active={s.specView === id} {title} onclick={() => store.set({ specView: id })}>{label}</button>
      {/each}
    </div>
    {#each toggles as [key, label, title]}
      <label class="toggle small" {title}><input type="checkbox" checked={s[key]} onchange={(e) => store.set({ [key]: e.currentTarget.checked })} /><span>{label}</span></label>
    {/each}
    <div class="spacer"></div>
    <span class="readout mono">{ui.readout}</span>
    <button class="icon-btn small" title="Export spectra as CSV (Ctrl+E)" onclick={() => ctl.exportCsv()}><Icon name="download" /></button>
    <button class="icon-btn small" title="Remove all pins, regions and the line" onclick={() => ctl.clearAll()}><Icon name="trash" /></button>
  </div>
  <div class="bottom-body">
    <div class="plot-wrap">
      <canvas id="plot" bind:this={plotCanvas}></canvas>
      <div class="plot-tip" hidden bind:this={tip}></div>
      <div class="line-wrap" hidden={ui.bottomTab !== 'line'}>
        <canvas id="line-canvas" bind:this={lineCanvas}></canvas>
        {#if !ui.lineReady}
          <div class="placeholder">Pick the <b>&nbsp;line&nbsp;</b> tool ( / ) and drag across the image to see a spectral cross-section.</div>
        {/if}
      </div>
    </div>
    <MarksList />
  </div>
</div>
