<script>
  // The lesson panel: the course catalog, or one step of a lesson (diagram, text, task).
  // All lesson content comes from the server (TOML files), so this file never changes when
  // lessons are added. Its look lives in learn.css (a warm light theme with a dark variant).
  import { learn } from '../../lib/learn.svelte.js';
  import { store } from '../../lib/controller.svelte.js';
  import { markdown } from '../../lib/markdown.js';
  import Icon from '../Icon.svelte';
  import Figure from './figures/Figure.svelte';
  import './learn.css';

  const L = learn.ui;
  const s = store.state;
  const LEVELS = [['basics', 'Basics'], ['intermediate', 'Intermediate'], ['advanced', 'Advanced']];
  const DEMO_NAMES = { scene: 'demo scene', capture: 'raw capture demo', photo: 'photo demo' };
  const TASK_ICONS = { pixel: 'inspect', band: 'band', choice: 'help' };
  const THEME_LABEL = { auto: 'Theme: follows your system', light: 'Theme: light', dark: 'Theme: dark' };
  const THEME_ICON = { auto: 'auto', light: 'sun', dark: 'moon' };

  let lesson = $derived(L.lesson);
  let step = $derived(lesson?.steps[L.step] ?? null);
  let finished = $derived(lesson && L.step >= lesson.steps.length);
  let mismatch = $derived(lesson?.demo && lesson.demo !== L.demo);
  let index = $derived(lesson ? L.lessons.findIndex((x) => x.id === lesson.id) : -1);
  let nextLesson = $derived(index >= 0 ? L.lessons[index + 1] ?? null : null);
  let doneCount = $derived(L.lessons.filter((x) => L.progress[x.id]?.done).length);
  let levelName = $derived(LEVELS.find(([k]) => k === lesson?.level)?.[1] ?? '');
  let scroller = $state();

  // Each new step starts at the top of the panel.
  $effect(() => { L.step; lesson; scroller?.scrollTo({ top: 0 }); });
</script>

<aside class="learn" aria-label="Lessons" data-theme={L.theme}>
  <header class="learn-head">
    {#if lesson}
      <button class="link" onclick={() => learn.leave()}>← All lessons</button>
    {:else}
      <span class="learn-title"><Icon name="learn" /> Learn</span>
    {/if}
    <div class="spacer"></div>
    <button class="icon-btn small" title={THEME_LABEL[L.theme]} aria-label={THEME_LABEL[L.theme]} onclick={() => learn.cycleTheme()}><Icon name={THEME_ICON[L.theme]} /></button>
    <button class="icon-btn small" title="Close lessons" aria-label="Close lessons" onclick={() => learn.setOpen(false)}><Icon name="close" /></button>
  </header>

  <div class="learn-body" bind:this={scroller}>
    {#if !lesson}
      <section class="learn-hero">
        <div class="eyebrow">Computer vision, step by step</div>
        <h1>Learn to see like a camera</h1>
        <p>Short lessons from pixels to filters, geometry and learning, taught on spectral images. Each step has a diagram you can play through and changes the real viewer next to it.</p>
      </section>
      {#if L.lessons.length}
        <div class="meter-row">
          <div class="meter"><span style="width:{(100 * doneCount) / L.lessons.length}%"></span></div>
          {doneCount} of {L.lessons.length} done
        </div>
      {/if}
      {#each LEVELS as [level, label]}
        {@const items = L.lessons.filter((x) => x.level === level)}
        {#if items.length}
          <section class="level">
            <div class="level-head"><h2>{label}</h2><span>{items.filter((x) => L.progress[x.id]?.done).length} / {items.length}</span></div>
            <ol class="lesson-list">
              {#each items as item, i}
                {@const p = L.progress[item.id]}
                {#if item.unit && item.unit !== items[i - 1]?.unit}<li class="unit-title">{item.unit}</li>{/if}
                <li>
                  <button class="lesson-card" disabled={L.busy} onclick={() => learn.start(item.id)}>
                    <span class="lc-num" class:done={p?.done} class:started={!p?.done && p?.step > 0}>{p?.done ? '✓' : L.lessons.indexOf(item) + 1}</span>
                    <span class="lc-title">{item.title}</span>
                    <span class="lc-sum">{item.summary}</span>
                    <span class="lc-meta">{item.steps} steps{item.demo ? ` · ${DEMO_NAMES[item.demo] ?? item.demo}` : ''}</span>
                  </button>
                </li>
              {/each}
            </ol>
          </section>
        {/if}
      {/each}
      <p class="note">Lessons are plain text files. Write your own and load them with <code>spektrify learn --lessons my-folder/</code>.</p>
    {:else if finished}
      <div class="finish step-anim">
        <div class="big">✓</div>
        <h2>{lesson.title}</h2>
        <p>Lesson complete.</p>
        {#if lesson.reading?.length}
          <div class="reading">
            <div class="section-title">Further reading</div>
            <ul>{#each lesson.reading as ref}<li class="md">{@html markdown(ref)}</li>{/each}</ul>
          </div>
        {/if}
        <div class="row col">
          {#if nextLesson}<button class="btn primary" onclick={() => learn.leave().then(() => learn.start(nextLesson.id))}>Next: {nextLesson.title}</button>{/if}
          <button class="btn" onclick={() => learn.go(0)}>Start again</button>
          <button class="btn" onclick={() => learn.leave()}>All lessons</button>
        </div>
      </div>
    {:else if step}
      <div class="lesson-top">
        <div class="eyebrow">Lesson {index + 1} · {levelName}{lesson.unit ? ` · ${lesson.unit}` : ''}</div>
        <h1>{lesson.title}</h1>
        <div class="steps-bar">
          {#each lesson.steps as st, i}
            <button class:active={i === L.step} class:seen={i < L.step} class:solved={L.solved[i]} title="{i + 1}. {st.title}" aria-label="Step {i + 1}: {st.title}" onclick={() => learn.go(i)}></button>
          {/each}
          <span class="count">{L.step + 1} / {lesson.steps.length}</span>
        </div>
      </div>

      {#if mismatch}
        <div class="banner">
          This lesson was written for the built-in {DEMO_NAMES[lesson.demo] ?? lesson.demo}.
          On another cube, tasks accept any answer.
          <button class="btn small primary" disabled={L.busy} onclick={() => learn.useDemo(lesson.demo)}>Load it</button>
        </div>
      {/if}

      {#if step.figure}<Figure figure={step.figure} {step} />{/if}

      {#key L.step}
        <div class="step-head step-anim">
          <h2 class="step-title">{step.title}</h2>
        </div>
        <div class="md step-anim">{@html markdown(step.text)}</div>
      {/key}

      {#if learn.comparable}
        <div class="compare">
          <span class="ctrl-label">Preprocessing: {step.pipeline.map((p) => p.name).join(' → ')}</span>
          <div class="seg">
            <button class:active={L.compare === 'before'} onclick={() => learn.setCompare('before')}>Before</button>
            <button class:active={L.compare === 'after'} onclick={() => learn.setCompare('after')}>After</button>
          </div>
        </div>
      {/if}

      {#if step.task}
        {@const t = step.task}
        <div class="task" class:ok={L.feedback?.correct} class:bad={L.feedback && !L.feedback.correct}>
          <div class="task-prompt"><Icon name={TASK_ICONS[t.kind]} /><span>{t.prompt}</span></div>
          {#if t.kind === 'choice'}
            <div class="options">
              {#each t.options as opt, i}
                <button class="option" onclick={() => learn.answer({ choice: i })}>{opt}</button>
              {/each}
            </div>
          {:else if t.kind === 'pixel'}
            <div class="hint">Click on the image.</div>
          {:else}
            <div class="hint">Current band: {store.bandLabel(s.band)}</div>
          {/if}
          {#if L.feedback}
            <div class="feedback" role="status">
              <b>{L.feedback.correct ? 'Correct.' : 'Not quite.'}</b> {L.feedback.message}
              {#if L.feedback.note}<div class="hint">{L.feedback.note}</div>{/if}
            </div>
          {:else if t.hint}
            {#if L.showHint}<div class="hint">{t.hint}</div>
            {:else}<button class="link" onclick={() => (L.showHint = true)}>Show a hint</button>{/if}
          {/if}
        </div>
      {/if}
    {/if}
  </div>

  {#if step && !finished}
    <footer class="learn-foot">
      <button class="btn" title="Previous step (key ,)" disabled={L.step === 0} onclick={() => learn.prev()}>Back</button>
      <div class="spacer"></div>
      <button class="btn" title="Next step (key .)" class:primary={!step.task || L.solved[L.step]} onclick={() => learn.next()}>
        {L.step === lesson.steps.length - 1 ? 'Finish' : step.task && !L.solved[L.step] ? 'Skip' : 'Next'}
      </button>
    </footer>
  {/if}
</aside>
