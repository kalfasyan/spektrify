<script>
  // Floating menus: the colour-map picker and the image context menu. `ctl.ui.menu` says which.
  import { onMount } from 'svelte';
  import { ctl } from "../../lib/controller.svelte.js";
  import { COLORMAPS, drawLut } from '../../lib/colormaps.js';

  const ui = ctl.ui;
  let menu = $state();
  let pos = $state({ x: ui.menu.x, y: ui.menu.y });

  onMount(() => {
    const r = menu.getBoundingClientRect();
    pos = { x: Math.max(8, Math.min(ui.menu.x, innerWidth - r.width - 8)), y: Math.max(8, Math.min(ui.menu.y, innerHeight - r.height - 8)) };
    const off = (e) => { if (!menu.contains(e.target)) ui.menu = null; };
    const t = setTimeout(() => document.addEventListener('pointerdown', off, true));
    return () => { clearTimeout(t); document.removeEventListener('pointerdown', off, true); };
  });

  function lutAction(canvas, id) { drawLut(canvas, id); }
  const run = (fn) => { ui.menu = null; fn(); };
</script>

{#if ui.menu.kind === 'cmap'}
  <div class="cmap-menu" bind:this={menu} style:left="{pos.x}px" style:top="{pos.y}px">
    {#each COLORMAPS as c, i (c.id)}
      {#if i === 0 || COLORMAPS[i - 1].group !== c.group}<div class="grp">{c.group}</div>{/if}
      <button class:active={c.id === ui.cmap} onclick={() => run(() => ctl.pickCmap(c.id))}><canvas width="120" height="10" use:lutAction={c.id}></canvas>{c.id}</button>
    {/each}
  </div>
{:else}
  <div class="ctx-menu" bind:this={menu} style:left="{pos.x}px" style:top="{pos.y}px">
    {#each ui.menu.items.filter(Boolean) as [label, fn]}
      <button onclick={() => run(fn)}>{label}</button>
    {/each}
  </div>
{/if}
