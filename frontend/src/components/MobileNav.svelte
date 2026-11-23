<script>
  // Bottom navigation for the phone layout (hidden on wider screens by app.css). Each pane
  // shows the image on top and one panel under it; "Image" shows the image alone.
  import { ctl, store } from '../lib/controller.svelte.js';
  import { learn } from '../lib/learn.svelte.js';
  import Icon from './Icon.svelte';

  const ui = ctl.ui;
  const s = store.state;
  const PANES = [
    ['learn', 'Learn', 'learn'],
    ['image', 'Image', 'image'],
    ['adjust', 'Adjust', 'sliders'],
    ['spectrum', 'Spectrum', 'spectrum'],
  ];

  function go(pane) {
    if (pane === 'learn' && !learn.ui.open) learn.setOpen(true);
    ctl.setPane(pane);
  }
</script>

<nav class="mobile-nav" aria-label="Panels">
  {#each PANES as [id, label, icon]}
    <button class:active={s.view === 'image' && ui.pane === id} aria-label={label} onclick={() => go(id)}>
      <Icon name={icon} /><span>{label}</span>
    </button>
  {/each}
</nav>
