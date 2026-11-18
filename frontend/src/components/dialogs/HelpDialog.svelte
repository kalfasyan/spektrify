<script>
  import { SHORTCUTS } from '../../lib/shortcuts.js';
  import Modal from './Modal.svelte';
</script>

<Modal title="Shortcuts">
  <div class="keys">
    {#each SHORTCUTS as row}
      {#if row.length === 1}
        <div class="grp">{row[0]}</div>
      {:else}
        <div>{#each row[0] as k}<kbd>{k}</kbd>{/each}</div>
        <div>{row[1]}</div>
      {/if}
    {/each}
  </div>
</Modal>
