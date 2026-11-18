<script>
  import { onMount } from 'svelte';
  import { ctl, store } from '../../lib/controller.svelte.js';
  import { Scrubber } from '../../lib/engines/scrubber.js';
  import Icon from '../Icon.svelte';

  const s = store.state;
  const ui = ctl.ui;
  let canvas;
  let engine;

  onMount(() => {
    engine = new Scrubber(canvas);
    engine.on('band', (b) => ctl.goBand(b));
    return ctl.attach('scrubber', engine);
  });

  $effect(() => {
    const meta = s.meta;
    ui.cubeVersion;
    engine?.set({ meta, band: s.band, marks: s.mode === 'rgb' ? [...s.rgb] : null, flagged: new Set((s.quality?.flags || []).map((f) => f.band)) });
  });

  let label = $derived(!s.meta ? '' : s.mode === 'rgb' ? s.rgb.map((b) => store.bandLabel(b, true)).join(' · ') : store.bandLabel(s.band));
</script>

<div class="scrubber" title="Click or drag to change band (← / →, Shift for ×10)">
  <button class="icon-btn small" class:on={ui.playing} title="Play through bands (Space)" onclick={() => ctl.togglePlay()}><Icon name={ui.playing ? 'pause' : 'play'} /></button>
  <canvas id="scrub-canvas" height="30" bind:this={canvas}></canvas>
  <div class="scrub-label">{label}</div>
</div>
