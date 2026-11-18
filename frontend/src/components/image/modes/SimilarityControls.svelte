<script>
  import { store } from '../../../lib/controller.svelte.js';
  const s = store.state;
  let refs = $derived(s.marks.filter((k) => k.values));
</script>

<div class="ctrl-label">Reference spectrum</div>
<select value={s.refMark != null ? String(s.refMark) : 'mean'} onchange={(e) => store.set({ refMark: e.currentTarget.value === 'mean' ? null : +e.currentTarget.value })}>
  <option value="mean">Scene mean</option>
  {#each refs as k (k.id)}
    <option value={String(k.id)}>{k.name} ({k.kind === 'pin' ? `${k.geom.x}, ${k.geom.y}` : `${k.n} px`})</option>
  {/each}
</select>
<div class="ctrl-label">Highlight pixels within angle</div>
<label class="slider-row">
  <span>∠</span>
  <input type="range" min="0" max="30" step="0.25" value={s.simDeg} oninput={(e) => store.set({ simDeg: +e.currentTarget.value })} />
  <span class="val">{s.simDeg ? `${s.simDeg}°` : 'off'}</span>
</label>
<div class="note">Pin a pixel or draw a region, then pick it here (or press ★ in the list). The map shows the spectral angle to it; dark = same material, regardless of brightness.</div>
