<script>
  // A text box for a file path with a small "Browse…" list underneath. Used by preprocessing
  // steps whose parameter names an external file (dark / white reference, flat-field frame, …).
  import { ctl } from '../../lib/controller.svelte.js';
  import { api } from '../../lib/api.js';
  import { fmtBytes } from '../../lib/util.js';

  let { value = $bindable(''), placeholder = '' } = $props();
  let open = $state(false);
  let listing = $state(null); // {dir, parent, entries}

  async function browse(dir) {
    try { listing = await api.browse(dir ?? '', true); } catch (e) { ctl.toast(e.message, 'error'); }
  }
  function toggle() {
    open = !open;
    // Start in the folder of the current value, if there is one.
    if (open) browse(value && /[\\/]/.test(value) ? value : '');
  }
  function pick(e) {
    if (e.dir) browse(e.path);
    else { value = e.path; open = false; }
  }
</script>

<div class="path-field">
  <div class="row">
    <input type="text" spellcheck="false" {placeholder} bind:value />
    <button class="btn small" type="button" title="Choose a file on this computer" onclick={toggle}>Browse…</button>
  </div>
  {#if open}
    <div class="picker">
      <div class="row dim"><button class="btn small" type="button" onclick={() => browse(listing?.parent)}>↑</button><span class="mono dir">{listing?.dir ?? ''}</span></div>
      <ul>
        {#each listing?.entries ?? [] as e (e.path)}
          <li title={e.path}><button type="button" onclick={() => pick(e)}>{e.dir ? '▸' : '◆'} {e.name}{#if !e.dir}<span class="sz">{fmtBytes(e.size)}</span>{/if}</button></li>
        {:else}
          <li class="dim">{listing ? 'No files here' : 'Loading…'}</li>
        {/each}
      </ul>
    </div>
  {/if}
</div>

<style>
  .path-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .row { display: flex; gap: 4px; align-items: center; }
  .row input { flex: 1; min-width: 0; }
  .picker { border: 1px solid var(--line); border-radius: 6px; padding: 4px; background: var(--bg-2, transparent); }
  .dir { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; font-size: 11px; }
  ul { list-style: none; margin: 4px 0 0; padding: 0; max-height: 160px; overflow: auto; }
  li button { all: unset; display: flex; justify-content: space-between; gap: 8px; width: 100%; box-sizing: border-box; padding: 2px 4px; cursor: pointer; font-size: 12px; border-radius: 4px; }
  li button:hover { background: var(--hover, rgba(128, 128, 128, 0.18)); }
  .sz { color: var(--text-2); font-size: 11px; }
  .dim { color: var(--text-2); }
</style>
