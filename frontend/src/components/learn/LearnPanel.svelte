<script>
  // The lesson panel: the catalog, or the current step of a lesson with its task.
  // All lesson content comes from the server (TOML files), so this file never changes when
  // lessons are added.
  import { learn } from '../../lib/learn.svelte.js';
  import { store } from '../../lib/controller.svelte.js';
  import { markdown } from '../../lib/markdown.js';
  import Icon from '../Icon.svelte';

  const L = learn.ui;
  const s = store.state;
  const LEVELS = [['basics', 'Basics'], ['intermediate', 'Intermediate'], ['advanced', 'Advanced']];
  const DEMO_NAMES = { scene: 'demo scene', capture: 'raw capture demo' };
  const TASK_ICONS = { pixel: 'inspect', band: 'band', choice: 'help' };

  let lesson = $derived(L.lesson);
  let step = $derived(lesson?.steps[L.step] ?? null);
  let finished = $derived(lesson && L.step >= lesson.steps.length);
  let mismatch = $derived(lesson?.demo && lesson.demo !== L.demo);
  let nextLesson = $derived.by(() => {
    if (!lesson) return null;
    const i = L.lessons.findIndex((x) => x.id === lesson.id);
    return L.lessons[i + 1] ?? null;
  });
</script>

<aside class="learn" aria-label="Lessons">
  <header class="learn-head">
    {#if lesson}
      <button class="link" onclick={() => learn.leave()}>← All lessons</button>
    {:else}
      <span class="learn-title"><Icon name="learn" /> Learn</span>
    {/if}
    <div class="spacer"></div>
    <button class="icon-btn small" title="Close lessons" onclick={() => learn.setOpen(false)}><Icon name="close" /></button>
  </header>

  <div class="learn-body">
    {#if !lesson}
      <p class="intro">A hands-on course in computer vision, taught on spectral images: from pixels to filters, geometry and learning. Each step changes the viewer next to it; click, scrub and compare as you go.</p>
      {#each LEVELS as [level, label]}
        {@const items = L.lessons.filter((x) => x.level === level)}
        {#if items.length}
          <div class="section-title">{label}<span class="hint">{items.filter((x) => L.progress[x.id]?.done).length} / {items.length} done</span></div>
          <ol class="lesson-list">
            {#each items as item, i}
              {#if item.unit && item.unit !== items[i - 1]?.unit}<li class="unit-title">{item.unit}</li>{/if}
              <li>
                <button class="lesson-card" disabled={L.busy} onclick={() => learn.start(item.id)}>
                  <span class="lc-title">{item.title}{#if L.progress[item.id]?.done}<span class="done" title="Completed">✓</span>{/if}</span>
                  <span class="lc-sum">{item.summary}</span>
                  <span class="lc-meta">{item.steps} steps{item.demo ? ` · ${DEMO_NAMES[item.demo] ?? item.demo}` : ''}</span>
                </button>
              </li>
            {/each}
          </ol>
        {/if}
      {/each}
      <p class="note">Lessons are plain text files. Write your own and load them with <code>spektrify learn --lessons my-folder/</code>.</p>
    {:else if finished}
      <div class="finish">
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
      <div class="lesson-name">{lesson.title}</div>
      <div class="dots" role="tablist">
        {#each lesson.steps as st, i}
          <button class="dot" class:active={i === L.step} class:solved={L.solved[i]} title="{i + 1}. {st.title}" aria-label="Step {i + 1}: {st.title}" onclick={() => learn.go(i)}></button>
        {/each}
        <span class="count">{L.step + 1} / {lesson.steps.length}</span>
      </div>

      {#if mismatch}
        <div class="banner">
          This lesson was written for the built-in {DEMO_NAMES[lesson.demo] ?? lesson.demo}.
          On another cube, tasks accept any answer.
          <button class="btn small primary" disabled={L.busy} onclick={() => learn.useDemo(lesson.demo)}>Load it</button>
        </div>
      {/if}

      <h2 class="step-title">{step.title}</h2>
      <div class="md">{@html markdown(step.text)}</div>

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
      <button class="btn" disabled={L.step === 0} onclick={() => learn.prev()}>Back</button>
      <div class="spacer"></div>
      <button class="btn" class:primary={!step.task || L.solved[L.step]} onclick={() => learn.next()}>
        {L.step === lesson.steps.length - 1 ? 'Finish' : step.task && !L.solved[L.step] ? 'Skip' : 'Next'}
      </button>
    </footer>
  {/if}
</aside>
