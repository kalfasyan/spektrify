<script>
  import { ctl } from '../lib/controller.svelte.js';
  const st = ctl.ui.status;
</script>

<footer id="statusbar">
  <span class="mono">{st.pos}</span>
  <span class="mono">{st.val}</span>
  <span class="spacer"></span>
  <span id="st-msg">{st.msg}</span>
  <span class="mono">{st.zoom}</span>
</footer>
