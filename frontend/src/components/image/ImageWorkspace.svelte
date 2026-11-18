<script>
  import DisplayPanel from './DisplayPanel.svelte';
  import ImageCanvas from './ImageCanvas.svelte';
  import Scrubber from './Scrubber.svelte';
  import BottomPanel from './BottomPanel.svelte';
  import Filmstrip from './Filmstrip.svelte';
  import { clamp } from '../../lib/util.js';

  let bottomH = $state(250);
  let drag = $state(null);
  function down(e) { drag = { y: e.clientY, h: bottomH }; e.currentTarget.setPointerCapture(e.pointerId); }
  function move(e) { if (drag) bottomH = clamp(drag.h + drag.y - e.clientY, 120, innerHeight * 0.7); }
</script>

<aside class="side left"><DisplayPanel /></aside>
<div class="center" style:--bottom-h="{bottomH}px">
  <ImageCanvas />
  <Scrubber />
  <div class="resize-handle" class:active={drag} title="Drag to resize" role="separator" onpointerdown={down} onpointermove={move} onpointerup={() => (drag = null)}></div>
  <BottomPanel />
</div>
<aside class="side right"><Filmstrip /></aside>
