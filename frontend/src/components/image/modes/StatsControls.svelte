<script>
  import { store } from '../../../lib/controller.svelte.js';
  const s = store.state;
  const items = [['mean', 'Mean'], ['std', 'Std'], ['max', 'Max'], ['argmax', 'Peak λ'], ['invalid', 'Invalid']];
  const notes = {
    mean: 'Average over all bands: a panchromatic view.',
    std: 'Spectral variability per pixel.',
    max: 'Brightest value along the spectrum: saturation shows up here.',
    argmax: 'Where each pixel’s spectrum peaks.',
    invalid: 'How many bands are NaN / Inf at each pixel.',
  };
</script>

<div class="seg seg-wrap">
  {#each items as [id, label]}
    <button class:active={s.summary === id} onclick={() => store.set({ summary: id })}>{label}</button>
  {/each}
</div>
<div class="note">{notes[s.summary]}</div>
