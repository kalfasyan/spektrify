<script>
  import { ctl, store } from '../../lib/controller.svelte.js';
  import { lazyThumb } from '../../lib/actions.js';

  const s = store.state;
  const ui = ctl.ui;
  let root = $state();
  let flags = $derived(new Map((s.quality?.flags || []).map((f) => [f.band, f.reasons])));
  let bands = $derived(s.meta && ui.thumbsVersion ? Array.from({ length: s.meta.bands }, (_, i) => i) : []);

  function pick(b, e) {
    if (s.mode === 'rgb') {
      const rgb = [...s.rgb];
      rgb[e.altKey || e.ctrlKey || e.metaKey ? 2 : e.shiftKey ? 1 : 0] = b;
      store.set({ rgb });
    } else store.set({ mode: 'band', band: b });
  }

  // Keep the current band in view.
  $effect(() => {
    const b = s.band;
    if (s.mode !== 'band' || !root) return;
    const el = root.querySelector(`[data-band="${b}"]`);
    if (!el) return;
    const r = root.getBoundingClientRect(), ir = el.getBoundingClientRect();
    if (ir.top < r.top || ir.bottom > r.bottom) el.scrollIntoView({ block: 'nearest' });
  });
</script>

<div class="section-title row"><span>Channels</span><span class="hint">{s.meta?.bands ?? ''}</span></div>
<div class="filmstrip" bind:this={root}>
  {#each bands as b (b)}
    {@const reasons = flags.get(b)}
    <div class="film" data-band={b} role="button" tabindex="-1"
      class:active={s.mode === 'band' && s.band === b}
      class:rgb-r={s.mode === 'rgb' && s.rgb[0] === b}
      class:rgb-g={s.mode === 'rgb' && s.rgb[1] === b}
      class:rgb-b={s.mode === 'rgb' && s.rgb[2] === b}
      title={store.bandLabel(b) + (reasons ? '\n⚠ ' + reasons.join('\n⚠ ') : '')}
      onclick={(e) => pick(b, e)} onkeydown={() => {}}>
      <canvas use:lazyThumb={{ band: b, cmap: s.cmap, rev: s.cmapRev, root }}></canvas>
      <div class="lab"><span>#{b}</span><span>{s.meta.wavelengths ? store.bandLabel(b, true) : ''}</span></div>
      {#if reasons}<span class="flag"></span>{/if}
    </div>
  {/each}
</div>
