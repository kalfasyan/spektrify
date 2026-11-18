<script>
  import { onMount } from 'svelte';
  import { ctl, store } from './lib/controller.svelte.js';
  import { api } from './lib/api.js';
  import TopBar from './components/TopBar.svelte';
  import StatusBar from './components/StatusBar.svelte';
  import ImageWorkspace from './components/image/ImageWorkspace.svelte';
  import ChannelsView from './views/ChannelsView.svelte';
  import ThreeView from './views/ThreeView.svelte';
  import QualityView from './views/QualityView.svelte';
  import OpenDialog from './components/dialogs/OpenDialog.svelte';
  import HelpDialog from './components/dialogs/HelpDialog.svelte';
  import PopupMenu from './components/dialogs/PopupMenu.svelte';
  import Toast from './components/dialogs/Toast.svelte';
  import { handleKey } from './lib/shortcuts.js';

  const s = store.state;
  const ui = ctl.ui;
  let seen3d = $state(false);
  $effect(() => { if (s.view === '3d') seen3d = true; });

  onMount(() => {
    ctl.loadCube().then(() => { if (!store.meta) ui.modal = 'open'; });
    // Live updates from Python (`Viewer.update(...)` in a notebook).
    const poll = setInterval(async () => {
      if (document.hidden) return;
      try {
        const { generation } = await api.generation();
        if (generation !== (store.meta?.generation ?? 0)) ctl.loadCube();
      } catch { /* server gone */ }
    }, 1500);
    return () => clearInterval(poll);
  });

  let dragDepth = 0;
  function dragenter(e) { if (e.dataTransfer?.types.includes('Files')) { dragDepth++; ui.dragging = true; } }
  function dragleave() { if (--dragDepth <= 0) { dragDepth = 0; ui.dragging = false; } }
  function drop(e) {
    e.preventDefault();
    dragDepth = 0;
    ui.dragging = false;
    const files = e.dataTransfer?.files;
    if (files?.length) ctl.upload(files);
  }
</script>

<svelte:window onkeydown={handleKey} ondragenter={dragenter} ondragleave={dragleave} ondragover={(e) => e.preventDefault()} ondrop={drop} />

<div id="app" class:dragging={ui.dragging}>
  <TopBar />
  <main id="main">
    <section class="view" class:active={s.view === 'image'} id="view-image"><ImageWorkspace /></section>
    {#if s.view === 'grid' && ui.ready}
      <section class="view active" id="view-grid"><ChannelsView /></section>
    {/if}
    {#if seen3d && ui.ready}
      <section class="view" class:active={s.view === '3d'} id="view-3d"><ThreeView active={s.view === '3d'} /></section>
    {/if}
    {#if s.view === 'quality' && ui.ready}
      <section class="view active" id="view-quality"><QualityView /></section>
    {/if}
  </main>
  <StatusBar />
</div>

{#if ui.modal === 'open'}<OpenDialog />{/if}
{#if ui.modal === 'help'}<HelpDialog />{/if}
{#if ui.menu}<PopupMenu />{/if}
<Toast />
<div class="loading-bar" id="loading-bar"></div>
