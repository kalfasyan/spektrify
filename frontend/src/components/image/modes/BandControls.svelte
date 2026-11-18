<script>
  import { store } from '../../../lib/controller.svelte.js';
  import { fmt } from '../../../lib/util.js';

  const s = store.state;
  let m = $derived(s.meta);
  let st = $derived(m.band_stats[s.band] || {});
  let flag = $derived(s.quality?.flags.find((f) => f.band === s.band));
</script>

<div class="big-readout">
  <span class="v">{m.wavelengths ? fmt(m.axis[s.band], 5) : `#${s.band}`}</span>
  <span class="u">{m.wavelengths ? `${m.unit} · band ${s.band} of ${m.bands}` : `of ${m.bands}`}</span>
</div>
<div class="slider-row"><input type="range" min="0" max={m.bands - 1} step="1" value={s.band} oninput={(e) => store.set({ band: +e.currentTarget.value })} /></div>
<div class="kv">
  <span>mean ± std</span><span>{fmt(st.mean, 4)} ± {fmt(st.std, 3)}</span>
  <span>min / max</span><span>{fmt(st.min, 4)} / {fmt(st.max, 4)}</span>
  <span>SNR (est.)</span><span>{st.snr == null ? '—' : fmt(st.snr, 3)}</span>
  <span>NaN / Inf</span><span>{st.nan ?? 0} / {st.inf ?? 0}</span>
</div>
{#if flag}<div class="note" style="color: var(--bad)">⚠ {flag.reasons.join(' · ')}</div>{/if}
<div class="note">Scrub with <b>← →</b> (Shift ×10), the bar under the image, or by clicking the spectrum plot.</div>
