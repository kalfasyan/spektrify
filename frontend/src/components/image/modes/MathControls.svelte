<script>
  import { ctl, store } from '../../../lib/controller.svelte.js';
  const s = store.state;
  let expr = $state(s.mathExpr);
  $effect(() => { expr = s.mathExpr; }); // follow changes made elsewhere (e.g. a lesson step)

  let examples = $derived.by(() => {
    const m = s.meta, ax = m.axis;
    const mid = Math.floor(m.bands / 2), hi = Math.floor(m.bands * 0.8), lo = Math.floor(m.bands * 0.3);
    const nm = (i) => Math.round(ax[i]);
    return m.wavelengths
      ? [`(nm(${nm(hi)}) - nm(${nm(lo)})) / (nm(${nm(hi)}) + nm(${nm(lo)}))`, `avg(${nm(lo)}, ${nm(mid)}) / mean`, `b[${mid}] - (b[${mid - 1}] + b[${mid + 1}]) / 2`, 'std / mean']
      : [`(b[${hi}] - b[${lo}]) / (b[${hi}] + b[${lo}])`, `b[${mid}] - (b[${mid - 1}] + b[${mid + 1}]) / 2`, 'std / mean'];
  });

  function run() {
    ctl.ui.mathError = '';
    store.set({ mathExpr: expr.trim() });
    store.emit('layer-dirty');
  }
</script>

<textarea class="expr" spellcheck="false" placeholder="(nm(800) - nm(670)) / (nm(800) + nm(670))" bind:value={expr}
  onkeydown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); run(); } }}></textarea>
<div class="row"><button class="btn primary small" onclick={run}>Compute</button><span class="hint">Enter to run</span></div>
{#if ctl.ui.mathError}<div class="err">{ctl.ui.mathError}</div>{/if}
<div class="examples">
  {#each examples as x}<button onclick={() => { expr = x; run(); }}>{x}</button>{/each}
</div>
<div class="note"><b>b[i]</b> band by index · <b>nm(λ)</b> nearest band · <b>avg(λ1, λ2)</b> band average · <b>mean std</b> across bands · sqrt log exp abs clip minimum maximum where · comparisons give 0/1 masks.</div>
