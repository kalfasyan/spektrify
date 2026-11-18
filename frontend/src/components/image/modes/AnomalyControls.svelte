<script>
  import { store } from '../../../lib/controller.svelte.js';
  const s = store.state;
  const methods = [['rx', 'RX'], ['residual', 'PCA residual'], ['gradient', 'Roughness']];
  const notes = {
    rx: 'RX: Mahalanobis distance of each spectrum from the scene background. Bright = spectrally rare.',
    residual: 'What the top-k principal components can’t reconstruct. Bright = unusual materials, glints or sensor glitches.',
    gradient: 'Mean jump between adjacent bands. Bright = spiky / noisy spectra (hot pixels, bad bands).',
  };
  let k = $state(s.anomalyK);
</script>

<div class="seg">
  {#each methods as [id, label]}
    <button class:active={s.anomaly === id} onclick={() => store.set({ anomaly: id })}>{label}</button>
  {/each}
</div>
{#if s.anomaly === 'residual'}
  <label class="slider-row" title="Components kept">
    <span>k</span>
    <input type="range" min="1" max={Math.min(30, s.meta.bands - 1)} bind:value={k} onchange={() => store.set({ anomalyK: k })} />
    <span class="val">{k}</span>
  </label>
{/if}
<div class="ctrl-label">Highlight the most anomalous pixels</div>
<label class="slider-row">
  <span>⚑</span>
  <input type="range" min="0" max="5" step="0.05" value={s.anomalyTop} oninput={(e) => store.set({ anomalyTop: +e.currentTarget.value })} />
  <span class="val">{s.anomalyTop ? `${s.anomalyTop}%` : 'off'}</span>
</label>
<div class="note">{notes[s.anomaly]}</div>
