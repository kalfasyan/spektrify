<script>
  import { onMount } from 'svelte';
  import { ctl } from '../../lib/controller.svelte.js';
  import { api } from '../../lib/api.js';
  import { fmtBytes } from '../../lib/util.js';
  import Icon from '../Icon.svelte';
  import Modal from './Modal.svelte';

  let path = $state('');
  let dataset = $state('');
  let layout = $state('auto');
  let mosaic = $state('');
  let method = $state('block');
  let listing = $state(null); // {dir, parent, entries, recent}
  let busy = $state(false);
  let input;

  onMount(() => { input?.focus(); browse(''); });

  async function browse(dir) {
    try { listing = await api.browse(dir ?? ''); } catch (e) { ctl.toast(e.message, 'error'); }
  }

  async function open(p = path) {
    p = p.trim();
    if (!p || busy) return;
    busy = true;
    try {
      await ctl.open({ path: p, dataset: dataset.trim() || null, layout, mosaic: +mosaic || null, demosaic: method });
      ctl.ui.modal = null;
    } catch (e) { ctl.toast(e.message, 'error', 6000); }
    busy = false;
  }
</script>

<Modal title="Open a cube" wide>
  <div class="row path-row">
    <input bind:this={input} bind:value={path} type="text" placeholder="/path/to/cube.h5 (or browse below)" spellcheck="false" onkeydown={(e) => e.key === 'Enter' && open()} />
    <button class="btn primary" disabled={busy} onclick={() => open()}>{busy ? 'Opening…' : 'Open'}</button>
  </div>
  <details class="open-advanced">
    <summary>Options</summary>
    <div class="row opts">
      <label>Dataset <input type="text" placeholder="auto" bind:value={dataset} /></label>
      <label>Axis order <select bind:value={layout}><option value="auto">auto</option><option value="hwc">H × W × C</option><option value="chw">C × H × W</option></select></label>
      <label>Mosaic <input type="number" min="0" max="8" placeholder="—" title="Demosaic a snapshot mosaic with this macropixel size" bind:value={mosaic} /></label>
      <label>Demosaic <select bind:value={method} title="block: one pixel per macropixel (fast) · bilinear: full sensor resolution, channels co-registered"><option value="block">block</option><option value="bilinear">bilinear</option></select></label>
    </div>
  </details>
  <div class="browser">
    <div class="browser-path row"><button class="icon-btn small" title="Parent folder" onclick={() => browse(listing?.parent)}><Icon name="up" /></button><span class="mono">{listing?.dir ?? ''}</span></div>
    <ul id="browse-list">
      {#each listing?.entries ?? [] as e (e.path)}
        <li title={e.path} onclick={() => (e.dir ? browse(e.path) : (path = e.path))} ondblclick={() => !e.dir && open(e.path)}>
          <span class="ic">{e.dir ? '▸' : '◆'}</span><span>{e.name}</span>{#if !e.dir}<span class="sz">{fmtBytes(e.size)}</span>{/if}
        </li>
      {:else}
        <li class="dim">{listing ? 'No supported files here' : 'Loading…'}</li>
      {/each}
    </ul>
  </div>
  {#if listing?.recent?.length}
    <div class="recent"><div class="section-title">Recent</div>
      <ul id="recent-list">{#each listing.recent as p}<li title={p} onclick={() => open(p)}>{p}</li>{/each}</ul>
    </div>
  {/if}
  <div class="modal-foot hint">Or drag &amp; drop a file anywhere in the window. ENVI: drop the .hdr together with its data file.</div>
</Modal>
