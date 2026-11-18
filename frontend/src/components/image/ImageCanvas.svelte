<script>
  import { onMount } from 'svelte';
  import { ctl, store } from '../../lib/controller.svelte.js';
  import { ImageView } from '../../lib/engines/imageView.js';
  import { fmt } from '../../lib/util.js';
  import Icon from '../Icon.svelte';

  const s = store.state;
  const ui = ctl.ui;
  let wrap, glCanvas, overlay;
  let error = $state('');

  const tools = [
    ['inspect', 'Inspect: hover for spectra, click to pin, drag to pan (V)'],
    ['rect', 'Rectangle region (Shift+drag works in any tool)'],
    ['ellipse', 'Ellipse region (E)'],
    ['lasso', 'Freehand region (F)'],
    ['line', 'Line profile (/)'],
  ];

  onMount(() => {
    let iv;
    try {
      iv = new ImageView({ wrap, glCanvas, overlay, store });
    } catch (e) {
      error = `This viewer needs WebGL2 (${e.message}). Try a recent Chrome, Edge or Firefox.`;
      return;
    }
    const detach = ctl.attach('imageView', iv);
    iv.on('hover', (px) => ctl.hover(px));
    iv.on('pin', (px) => store.addMark('pin', px));
    iv.on('region', (d) => store.addMark(d.kind, d.geom));
    iv.on('mark-moved', (mk) => store.refreshMark(mk));
    iv.on('mark-moving', (mk) => { clearTimeout(mk._t); mk._t = setTimeout(() => store.refreshMark(mk), 40); });
    iv.on('line', (g) => ctl.setLine(g));
    iv.on('context', (e) => ctl.contextMenu(e));
    iv.on('view', (v) => (ui.status.zoom = `${v.scale >= 1 ? fmt(v.scale, 3) : '1/' + fmt(1 / v.scale, 3)}×`));
    if (ctl.layer) iv.setLayer(ctl.layer, ctl.stretch);
    return () => { detach(); iv.destroy(); };
  });
</script>

<div class="canvas-wrap" bind:this={wrap}>
  <canvas id="gl" bind:this={glCanvas}></canvas>
  <canvas id="overlay" bind:this={overlay}></canvas>
  <div class="tool-dock">
    {#each tools as [id, title]}
      <button class:active={s.tool === id} {title} onclick={() => store.set({ tool: id })}><Icon name={id} /></button>
    {/each}
    <span class="sep"></span>
    <button title="Fit to window (0 or double-click)" onclick={() => ctl.engines.imageView?.fit()}><Icon name="fit" /></button>
    <button title="1:1 pixels (1)" onclick={() => ctl.engines.imageView?.oneToOne()}><Icon name="one" /></button>
  </div>
  {#if ui.hud}
    <div class="band-hud"><span class="t">{ui.hud.label}</span><span class="s">{ui.hud.sub}</span></div>
  {/if}
  <div class="drop-hint"><div>Drop a cube file to open it<br /><span>.npy · .npz · .h5 · .mat · .tif · ENVI .hdr + data</span></div></div>
  {#if !ui.ready || error}
    <div class="empty">
      <div class="empty-card">
        {#if error}
          <h2>WebGL2 unavailable</h2><p>{error}</p>
        {:else}
          <h2>Open a spectral cube</h2>
          <p>Drop a file here, or browse for one. Supports .npy, .npz, .h5 / .hdf5, .mat, .tif and ENVI (.hdr + data).</p>
          <div class="row"><button class="btn primary" onclick={() => (ui.modal = 'open')}>Browse…</button></div>
        {/if}
      </div>
    </div>
  {/if}
</div>
