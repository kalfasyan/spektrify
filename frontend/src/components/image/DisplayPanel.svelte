<script>
  import { ctl, store } from '../../lib/controller.svelte.js';
  import BandControls from './modes/BandControls.svelte';
  import RgbControls from './modes/RgbControls.svelte';
  import PcaControls from './modes/PcaControls.svelte';
  import AnomalyControls from './modes/AnomalyControls.svelte';
  import SimilarityControls from './modes/SimilarityControls.svelte';
  import StatsControls from './modes/StatsControls.svelte';
  import MathControls from './modes/MathControls.svelte';
  import StretchPanel from './StretchPanel.svelte';

  const s = store.state;
  const modes = [
    ['band', 'Band', 'Single channel (B)', BandControls],
    ['rgb', 'RGB', 'False-colour composite (C)', RgbControls],
    ['pca', 'PCA', 'Principal components (P)', PcaControls],
    ['anomaly', 'Anomaly', 'Anomaly detectors (N)', AnomalyControls],
    ['similarity', 'Similar', 'Spectral similarity (S)', SimilarityControls],
    ['summary', 'Stats', 'Per-pixel statistics across bands', StatsControls],
    ['math', 'Math', 'Band math (M)', MathControls],
  ];
  let Controls = $derived(modes.find((m) => m[0] === s.mode)?.[3]);
  const overlays = [
    ['nan', 'NaN / Inf pixels', 'Show NaN / Inf pixels in magenta'],
    ['clip', 'Clipped (under / over)', 'Pixels below / above the stretch in blue / red (K)'],
    ['values', 'Pixel values at high zoom', 'Pixel grid and values when zoomed in'],
    ['defects', 'Line defects', 'Mark sensor-level row / column defects found by the quality scan'],
  ];
</script>

<div class="panel-section">
  <div class="section-title">Display</div>
  <div class="seg seg-wrap">
    {#each modes as [id, label, title]}
      <button class:active={s.mode === id} {title} onclick={() => store.set({ mode: id })}>{label}</button>
    {/each}
  </div>
  {#if s.meta && Controls}
    <div id="mode-controls"><Controls /></div>
  {/if}
</div>

<StretchPanel />

<div class="panel-section">
  <div class="section-title">Highlight</div>
  <div class="row toggles col">
    {#each overlays as [key, label, title]}
      <label class="toggle" {title}>
        <input type="checkbox" checked={s.overlays[key]} onchange={(e) => store.set({ overlays: { ...s.overlays, [key]: e.currentTarget.checked } })} />
        <span>{label}</span>
      </label>
    {/each}
  </div>
</div>
