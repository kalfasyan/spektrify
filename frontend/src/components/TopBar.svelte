<script>
  import { ctl, store } from '../lib/controller.svelte.js';
  import Icon from './Icon.svelte';
  import { learn } from '../lib/learn.svelte.js';

  const s = store.state;
  const ui = ctl.ui;
  const tabs = [
    ['image', 'Image', 'I'],
    ['grid', 'Channels', 'G'],
    ['3d', '3D', 'D'],
    ['quality', 'Quality', 'Q'],
  ];
  let issues = $derived(s.quality ? s.quality.flags.length + s.quality.bad_columns.length + s.quality.bad_rows.length : 0);
</script>

<header id="topbar">
  <div class="brand">
    <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden="true"><defs><linearGradient id="bg" x1="0" x2="1"><stop offset="0" stop-color="#6b5bff" /><stop offset=".5" stop-color="#33d1a0" /><stop offset="1" stop-color="#ff5d5d" /></linearGradient></defs><path d="M4 10l12-6 12 6-12 6z" fill="url(#bg)" /><path d="M4 10v12l12 6V16z" fill="#2a3341" /><path d="M28 10v12l-12 6V16z" fill="#3a4657" /></svg>
    <span>spektr<b>ify</b></span>
  </div>
  <button class="file-chip" title={s.meta?.source || 'Open a cube (Ctrl+O)'} onclick={() => (ui.modal = 'open')}>
    <span id="file-name">{s.meta ? s.meta.name : 'No cube loaded'}</span>
    {#if s.meta}<span class="dim" id="file-dims">{s.meta.height} × {s.meta.width} × {s.meta.bands}</span>{/if}
  </button>
  <nav class="tabs">
    {#each tabs as [id, label, key]}
      <button class:active={s.view === id} title="{label} ({key})" disabled={!s.meta && id !== 'image'} onclick={() => ctl.setView(id)}>
        {label}{#if id === 'quality' && issues}<span class="badge">{issues}</span>{/if}
      </button>
    {/each}
  </nav>
  <button class="learn-btn" class:active={learn.ui.open} title="Interactive lessons on spectral imaging" onclick={() => learn.setOpen(!learn.ui.open)}><Icon name="learn" />Learn</button>
  <div class="spacer"></div>
  <div class="top-actions">
    <button class="icon-btn" title="Open cube (Ctrl+O)" onclick={() => (ui.modal = 'open')}><Icon name="folder" /></button>
    <button class="icon-btn" title="Save view as PNG (Ctrl+S)" onclick={() => ctl.snapshot()}><Icon name="camera" /></button>
    <button class="icon-btn" title="Shortcuts (?)" onclick={() => (ui.modal = 'help')}><Icon name="help" /></button>
  </div>
</header>
