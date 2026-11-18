<script>
  import { onMount } from 'svelte';
  import { ctl, store } from '../../lib/controller.svelte.js';
  import { Histogram } from '../../lib/engines/histogram.js';
  import { drawLut } from '../../lib/colormaps.js';
  import { fmt } from '../../lib/util.js';
  import Icon from '../Icon.svelte';

  const s = store.state;
  const ui = ctl.ui;
  let histCanvas, cmapCanvas, cmapBtn;
  let gammaSlider = $state(0);

  const presets = [['minmax', 'min–max', 'Min to max'], ['1', '1–99%', '1st–99th percentile'], ['2', '2–98%', '2nd–98th percentile (A)'], ['5', '5–95%', '5th–95th percentile']];

  onMount(() => {
    const h = new Histogram(histCanvas);
    h.on('change', (st) => ctl.setStretch(st, false));
    h.on('commit', (st) => ctl.setStretch(st));
    if (ctl.layer) h.set(ctl.layer, ctl.stretch);
    return ctl.attach('hist', h);
  });

  $effect(() => { if (cmapCanvas) drawLut(cmapCanvas, ui.cmap, ui.cmapReversed); });

  function gamma(v) { gammaSlider = v; store.set({ gamma: 10 ** -v }); }
  function limit(which, e) {
    const v = parseFloat(e.currentTarget.value);
    if (Number.isFinite(v)) ctl.setLimit(which, v);
    else e.currentTarget.value = fmt(ui.stretch?.[which][0], 4);
  }
  function openCmaps() {
    const r = cmapBtn.getBoundingClientRect();
    ui.menu = { kind: 'cmap', x: r.left, y: r.bottom + 4 };
  }
</script>

<div class="panel-section">
  <div class="section-title">Stretch <span class="hint">{ui.layerKind === 'rgb' ? 'R G B · Shift-drag: one channel' : ''}</span></div>
  <canvas id="histogram" height="92" bind:this={histCanvas}></canvas>
  <div class="chips">
    {#each presets as [p, label, title]}
      <button class:active={s.preset === p} {title} onclick={() => ctl.applyPreset(p)}>{label}</button>
    {/each}
  </div>
  <div class="row stretch-readout">
    <input class="num" type="text" spellcheck="false" title="Low limit (type a value)" value={fmt(ui.stretch?.lo[0], 4)} onchange={(e) => limit('lo', e)} />
    <span class="hint spacer" style="text-align:center">limits</span>
    <input class="num" type="text" spellcheck="false" title="High limit (type a value)" value={fmt(ui.stretch?.hi[0], 4)} onchange={(e) => limit('hi', e)} />
  </div>
  <label class="row slider-row" title="Gamma (double-click to reset)">
    <span>γ</span>
    <input type="range" min="-1.2" max="1.2" step="0.01" value={gammaSlider} oninput={(e) => gamma(+e.currentTarget.value)} ondblclick={() => gamma(0)} />
    <span class="val">{s.gamma.toFixed(2)}</span>
  </label>
  <div class="row toggles">
    <label class="toggle" title="Keep the same stretch while changing band (L)"><input type="checkbox" checked={s.lockStretch} onchange={(e) => store.set({ lockStretch: e.currentTarget.checked })} /><span>Lock across bands</span></label>
  </div>
  <div class="row" style:opacity={ui.layerKind === 'rgb' ? 0.4 : 1}>
    <button class="cmap-btn" title="Colour map ([ / ] cycle, R reverse)" bind:this={cmapBtn} onclick={openCmaps}><canvas width="160" height="12" bind:this={cmapCanvas}></canvas><span>{ui.cmap}</span></button>
    <button class="icon-btn small" class:on={s.cmapRev} title="Reverse colour map (R)" onclick={() => store.set({ cmapRev: !s.cmapRev })}><Icon name="reverse" /></button>
  </div>
</div>
