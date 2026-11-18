<script>
  import { store } from '../../../lib/controller.svelte.js';

  const s = store.state;
  const COLORS = ['#ff5d5d', '#3ddc97', '#5aa9ff'];
  let m = $derived(s.meta);

  let presets = $derived.by(() => {
    const ax = m.axis, out = [];
    const has = (a, b) => m.wavelengths && ax[0] <= a && ax[ax.length - 1] >= b;
    if (has(470, 630)) out.push(['True colour', [640, 550, 465].map((x) => store.nearestBand(x)), '']);
    if (has(540, 800)) out.push(['Colour-IR', [800, 650, 550].map((x) => store.nearestBand(x)), '']);
    const C = m.bands;
    out.push(['Spread', [Math.round((C - 1) * 0.85), Math.round((C - 1) * 0.5), Math.round((C - 1) * 0.15)], 'Bands at 85 / 50 / 15 % of the range']);
    out.push(['Max contrast', null, 'The three least-correlated bands']);
    return out;
  });

  function setChannel(k, b) { const rgb = [...s.rgb]; rgb[k] = b; store.set({ rgb }); }

  // Greedy: highest-variance band first, then bands least correlated with those chosen.
  function decorrelated() {
    const corr = store.correlation, C = m.bands;
    if (!corr) return [...s.rgb];
    const stds = m.bandStd.map((v) => v || 0);
    const chosen = [stds.indexOf(Math.max(...stds))];
    while (chosen.length < 3) {
      let best = -1, bestScore = Infinity;
      for (let b = 0; b < C; b++) {
        if (chosen.includes(b)) continue;
        const score = Math.max(...chosen.map((c) => Math.abs(corr[b * C + c])));
        if (score < bestScore) { bestScore = score; best = b; }
      }
      chosen.push(best);
    }
    return chosen.sort((a, b) => m.axis[b] - m.axis[a]);
  }
</script>

{#each [0, 1, 2] as k}
  <div class="band-pick">
    <span class="dot" style:background={COLORS[k]}></span>
    <input type="range" min="0" max={m.bands - 1} step="1" value={s.rgb[k]} oninput={(e) => setChannel(k, +e.currentTarget.value)} />
    <span class="wl">{store.bandLabel(s.rgb[k], true)}</span>
  </div>
{/each}
<div class="examples">
  {#each presets as [name, rgb, title]}
    <button {title} onclick={() => store.set({ rgb: rgb ?? decorrelated() })}>{name}</button>
  {/each}
</div>
<div class="note">Click a channel thumbnail to set <b>R</b>, Shift-click for <b>G</b>, Alt-click for <b>B</b>.</div>
