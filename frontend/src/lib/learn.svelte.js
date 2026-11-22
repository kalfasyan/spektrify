// Learn mode: runs a lesson (fetched from the server) against the live viewer. A step can
// switch the view, set display state, run a preprocessing pipeline (with a Before / After
// switch) and ask for a pixel, a band or a multiple-choice answer, which the server grades.
// Lessons are data (TOML files in Python), so nothing here knows about any one lesson.

import { api } from './api.js';
import { ctl, store } from './controller.svelte.js';

const PROGRESS_KEY = 'spektrify.learn.progress';
const THEME_KEY = 'spektrify.learn.theme';
export const THEMES = ['auto', 'light', 'dark']; // auto follows the system setting

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
}
const same = (a, b) => JSON.stringify(a ?? []) === JSON.stringify(b ?? []);

class Learn {
  constructor() {
    this.ui = $state({
      open: false,
      lessons: [], // catalog summaries
      demo: null, // which built-in demo is on display (null = the learner's own cube)
      lesson: null, // the running lesson (resolved for the current cube)
      step: 0,
      feedback: null, // {correct, message, note}
      solved: {}, // step index -> true
      compare: 'after', // 'before' shows the raw cube while a step's pipeline is active
      showHint: false,
      busy: false,
      progress: load(PROGRESS_KEY, {}), // lesson id -> {done, step}
      theme: THEMES.includes(load(THEME_KEY)) ? load(THEME_KEY) : 'auto',
    });
    this._userPipeline = null; // restored when the lesson ends
    this._applying = false;
    this._bandTimer = null;
    store.on('change', (keys) => { if (keys.has('band')) this._bandChanged(); });
  }

  get step() { return this.ui.lesson?.steps[this.ui.step] ?? null; }
  get task() { return this.step?.task ?? null; }
  /** The step runs a pipeline, so Before / After makes sense. */
  get comparable() { return !!this.step?.pipeline?.length; }

  async setOpen(open) {
    this.ui.open = open;
    // The panel changes the image area's width: re-fit once the layout has settled.
    requestAnimationFrame(() => ctl.engines.imageView?.fit());
    if (open) await this.refresh();
    else await this.leave();
  }

  async refresh() {
    try {
      const r = await api.lessons();
      this.ui.lessons = r.lessons;
      this.ui.demo = r.demo;
    } catch (e) { ctl.toast(e.message, 'error'); }
  }

  async start(id) {
    this.ui.busy = true;
    try {
      const summary = this.ui.lessons.find((l) => l.id === id);
      if (!store.meta) { await api.demo(summary?.demo || 'scene'); await ctl.loadCube(); await this.refresh(); }
      const lesson = await api.lesson(id);
      if (lesson.uses_pipeline && this._userPipeline == null) this._userPipeline = store.meta?.pipeline ?? [];
      Object.assign(this.ui, { lesson, solved: {}, feedback: null });
      await this.go(Math.min(this.ui.progress[id]?.step ?? 0, lesson.steps.length - 1));
    } catch (e) { ctl.toast(e.message, 'error'); }
    this.ui.busy = false;
  }

  /** Swap in the built-in cube a lesson was written for, and restart the current step there. */
  async useDemo(name) {
    this.ui.busy = true;
    try {
      await api.demo(name);
      this._userPipeline = null; // the learner's pipeline belonged to their own cube
      await ctl.loadCube();
      await this.refresh();
      if (this.ui.lesson) {
        const step = this.ui.step;
        this.ui.lesson = await api.lesson(this.ui.lesson.id);
        if (this.ui.lesson.uses_pipeline) this._userPipeline = [];
        await this.go(step);
      }
    } catch (e) { ctl.toast(e.message, 'error'); }
    this.ui.busy = false;
  }

  async go(i) {
    const L = this.ui.lesson;
    if (!L) return;
    i = Math.max(0, Math.min(i, L.steps.length - 1));
    const st = L.steps[i];
    Object.assign(this.ui, { step: i, feedback: null, compare: 'after', showHint: false });
    this._remember({ step: i });
    this._applying = true;
    try {
      if (st.pipeline) await this._pipeline(st.pipeline);
      if (st.view) ctl.setView(st.view);
      if (Object.keys(st.show).length) {
        store.set(st.show);
        if ('mathExpr' in st.show) store.emit('layer-dirty'); // band math recomputes on demand
      }
    } catch (e) { ctl.toast(e.message, 'error'); }
    finally { this._applying = false; }
  }

  next() {
    const L = this.ui.lesson;
    if (!L) return;
    if (this.ui.step < L.steps.length - 1) return this.go(this.ui.step + 1);
    this._remember({ done: true, step: 0 });
    this.ui.step = L.steps.length; // "lesson complete" screen
  }

  prev() { return this.go(this.ui.step - 1); }

  /** Cycle the panel's colour theme: auto → light → dark. */
  cycleTheme() {
    this.ui.theme = THEMES[(THEMES.indexOf(this.ui.theme) + 1) % THEMES.length];
    save(THEME_KEY, this.ui.theme);
  }

  /** Back to the lesson list, restoring the learner's own pipeline. */
  async leave() {
    this.ui.lesson = null;
    this.ui.feedback = null;
    if (this._userPipeline != null) {
      const p = this._userPipeline;
      this._userPipeline = null;
      if (store.meta && !same(p, store.meta.pipeline)) {
        try { await ctl.reprocess(p); } catch (e) { ctl.toast(e.message, 'error'); }
      }
    }
  }

  async setCompare(which) {
    if (!this.comparable || which === this.ui.compare) return;
    this.ui.compare = which;
    try { await this._pipeline(which === 'before' ? [] : this.step.pipeline); } catch (e) { ctl.toast(e.message, 'error'); }
  }

  async _pipeline(steps) {
    if (!store.meta || same(steps, store.meta.pipeline)) return;
    await ctl.reprocess(steps);
  }

  // ------------------------------------------------------------------ answers
  async answer(payload) {
    const L = this.ui.lesson, i = this.ui.step;
    if (!L || !this.task) return;
    try {
      const r = await api.lessonCheck(L.id, i, payload);
      if (this.ui.lesson !== L || this.ui.step !== i) return; // moved on meanwhile
      this.ui.feedback = r;
      if (r.correct) this.ui.solved = { ...this.ui.solved, [i]: true };
    } catch (e) { ctl.toast(e.message, 'error'); }
  }

  /** Called for every click on the image (a pin). */
  pixel(px) {
    if (this.ui.open && this.task?.kind === 'pixel') this.answer({ x: px.x, y: px.y });
  }

  _bandChanged() {
    if (this._applying || !this.ui.open || this.task?.kind !== 'band') return;
    clearTimeout(this._bandTimer);
    // Wait until the learner stops scrubbing before grading.
    this._bandTimer = setTimeout(() => this.answer({ band: store.state.band }), 450);
  }

  _remember(patch) {
    const id = this.ui.lesson?.id;
    if (!id) return;
    this.ui.progress = { ...this.ui.progress, [id]: { ...this.ui.progress[id], ...patch } };
    save(PROGRESS_KEY, this.ui.progress);
  }
}

export const learn = new Learn();
