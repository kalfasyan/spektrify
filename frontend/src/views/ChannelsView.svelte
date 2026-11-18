<script>
  // "All channels": every band as a tile with a crosshair linked across all tiles, so
  // misregistration, striping, dead pixels and noisy bands jump out side by side.
  import { onMount } from 'svelte';
  import { ctl, store } from '../lib/controller.svelte.js';
  import { lazyThumb } from '../lib/actions.js';
  import { fmt } from '../lib/util.js';

  const s = store.state;
  const ui = ctl.ui;
  let norm = $state('band');
  let size = $state(168);
  let cursor = $state(null); // thumb-space {x, y}
  let scroller = $state();
  let ready = $state(false);

  onMount(() => { ctl.thumbs.load().then(() => (ready = true)); });

  let flags = $derived(new Map((s.quality?.flags || []).map((f) => [f.band, f.reasons])));
  let bands = $derived(ready && s.meta ? Array.from({ length: s.meta.bands }, (_, i) => i) : []);

  function move(b, e) {
    const t = ctl.thumbs.meta;
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * t.width, y = ((e.clientY - r.top) / r.height) * t.height;
    cursor = { x, y };
    const n = t.width * t.height;
    const v = ctl.thumbs.data[b * n + Math.floor(y) * t.width + Math.floor(x)];
    ui.status.pos = `x ${Math.floor(x * t.step)}  y ${Math.floor(y * t.step)}`;
    ui.status.val = `${store.bandLabel(b)} · ${fmt(v, 5)}${t.step > 1 ? ` (${t.step}×${t.step} mean)` : ''}`;
  }
</script>

<div class="grid-toolbar">
  <span class="title">All channels</span>
  <span class="hint">Hover links a crosshair across every channel · click opens a channel</span>
  <div class="spacer"></div>
  <div class="seg small">
    <button class:active={norm === 'band'} title="Each channel stretched on its own (texture)" onclick={() => (norm = 'band')}>Per channel</button>
    <button class:active={norm === 'shared'} title="One stretch for all channels (radiometry)" onclick={() => (norm = 'shared')}>Shared</button>
  </div>
  <label class="slider-row small"><span>Size</span><input type="range" min="80" max="360" bind:value={size} /></label>
</div>
<div class="grid-scroll" bind:this={scroller}>
  {#if !ready}
    <div class="placeholder">Loading thumbnails…</div>
  {:else}
    <div class="grid" style:--tile="{size}px">
      {#each bands as b (b)}
        {@const reasons = flags.get(b)}
        <div class="tile" class:active={b === s.band} class:flagged={!!reasons} role="button" tabindex="-1"
          title={reasons ? reasons.join('\n') : store.bandLabel(b)}
          onclick={() => ctl.openBand(b)} onkeydown={() => {}}>
          <canvas onpointermove={(e) => move(b, e)} onpointerleave={() => { cursor = null; ui.status.pos = ''; ui.status.val = ''; }}
            use:lazyThumb={{ band: b, cmap: s.cmap, rev: s.cmapRev, norm, root: scroller, cursor }}></canvas>
          <div class="lab"><span>{store.bandLabel(b, true)}{s.meta.wavelengths ? ` · #${b}` : ''}</span><span class="r">{reasons ? reasons[0] : ''}</span></div>
        </div>
      {/each}
    </div>
  {/if}
</div>
