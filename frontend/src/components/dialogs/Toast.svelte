<script>
  import { ctl } from '../../lib/controller.svelte.js';
  const ui = ctl.ui;
</script>

{#if ui.toast}<div class="toast {ui.toast.kind}" role="status">{ui.toast.msg}</div>{/if}
