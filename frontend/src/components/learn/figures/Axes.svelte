<script>
  // Two plain axes with labels, shared by the 2D diagrams.
  let { box, x = '', y = '' } = $props();
  let [x0, y0, x1, y1] = $derived(box);
</script>

<line class="axis" x1={x0} y1={y1} x2={x1} y2={y1} />
<line class="axis" x1={x0} y1={y0} x2={x0} y2={y1} />
<text class="lbl" x={x1 + 6} y={y1 + 4}>{x}</text>
<text class="lbl" x={x0 - 6} y={y0 - 6}>{y}</text>
