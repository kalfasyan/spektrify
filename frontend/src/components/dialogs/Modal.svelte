<script>
  // Shared modal shell: backdrop click and the close button dismiss it.
  import { ctl } from '../../lib/controller.svelte.js';
  import Icon from '../Icon.svelte';

  let { title, wide = false, children } = $props();
  const close = () => (ctl.ui.modal = null);
</script>

<div class="modal" role="presentation" onclick={(e) => e.target === e.currentTarget && close()}>
  <div class="modal-card" class:wide role="dialog" aria-label={title}>
    <div class="modal-head"><h3>{title}</h3><button class="icon-btn small" title="Close (Esc)" onclick={close}><Icon name="close" /></button></div>
    {@render children()}
  </div>
</div>
