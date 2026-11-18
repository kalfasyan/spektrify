<script>
  import { ctl, store } from '../../../lib/controller.svelte.js';
  const s = store.state;
</script>

<div class="row">
  <button class="btn small" title="Previous component ([)" onclick={() => ctl.stepBand(-1)}>‹</button>
  <div class="spacer" style="text-align:center"><span class="v" style="font-size:15px">{s.pcaAsRgb ? `PC ${s.pcaOffset + 1} · ${s.pcaOffset + 2} · ${s.pcaOffset + 3}` : `PC ${s.pcaOffset + 1}`}</span></div>
  <button class="btn small" title="Next component (])" onclick={() => ctl.stepBand(1)}>›</button>
</div>
<label class="toggle"><input type="checkbox" checked={s.pcaAsRgb} onchange={(e) => store.set({ pcaAsRgb: e.currentTarget.checked })} /><span>Three components as RGB</span></label>
<div class="note">Low components show the main material contrasts; higher ones isolate rare spectra, sensor noise and stripes.</div>
