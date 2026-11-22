<script>
  // The diagram card above a lesson step: draws one figure kind (see index.js) and the controls
  // that step through its frames. Frames animate by tweening a continuous frame number `f`
  // that the figure component turns into geometry. It plays through once when it appears.
  import { untrack } from 'svelte';
  import { Tween, prefersReducedMotion } from 'svelte/motion';
  import { cubicInOut } from 'svelte/easing';
  import { FIGURES } from './index.js';
  import Icon from '../../Icon.svelte';
  import './figures.css';

  /** figure: {kind, ...options} from the lesson file; step: the lesson step (for its pipeline). */
  let { figure, step } = $props();

  const HOLD = 2200; // ms on each frame while playing
  let entry = $derived(FIGURES[figure.kind]);
  let captions = $derived(entry ? entry.captions(figure, step) : []);
  let last = $derived(captions.length - 1);
  let frame = $state(0);
  let playing = $state(false);
  const f = new Tween(0, { duration: 700, easing: cubicInOut });
  let timer;

  // A new diagram starts from its first frame; one carried over from the previous step keeps
  // its place, so it doesn't jump.
  let key = $derived(JSON.stringify([figure, captions]));
  $effect(() => {
    key;
    untrack(() => {
      frame = 0;
      f.set(0, { duration: 0 });
      if (last > 0 && !prefersReducedMotion.current) play();
      else stop();
    });
    return stop;
  });
  $effect(() => { f.target = frame; });

  function go(i) { frame = Math.max(0, Math.min(last, i)); }
  function stop() { playing = false; clearInterval(timer); }
  function play() {
    stop();
    if (frame >= last) go(0);
    playing = true;
    timer = setInterval(() => { if (frame < last) go(frame + 1); else stop(); }, HOLD);
  }
  const user = (fn) => () => { stop(); fn(); };
</script>

{#if entry}
  {@const Diagram = entry.component}
  <figure class="fig">
    <div class="fig-stage"><Diagram o={figure} f={f.current} {frame} {step} /></div>
    {#if last > 0}
      <figcaption class="fig-bar">
        <span class="fig-cap" aria-live="polite">{captions[frame]}</span>
        <div class="fig-ctrl">
          <button class="fig-btn" aria-label="Previous frame" disabled={frame === 0} onclick={user(() => go(frame - 1))}>‹</button>
          <button class="fig-btn play" aria-label={playing ? 'Pause' : 'Play'} onclick={() => (playing ? stop() : play())}><Icon name={playing ? 'pause' : 'play'} /></button>
          <button class="fig-btn" aria-label="Next frame" disabled={frame === last} onclick={user(() => go(frame + 1))}>›</button>
          <div class="fig-dots">
            {#each captions as cap, i}
              <button class="fig-dot" class:on={i <= frame} aria-label="Frame {i + 1}: {cap}" onclick={user(() => go(i))}></button>
            {/each}
          </div>
        </div>
      </figcaption>
    {:else if captions[0]}
      <figcaption class="fig-bar"><span class="fig-cap">{captions[0]}</span></figcaption>
    {/if}
  </figure>
{/if}
