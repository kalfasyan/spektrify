// Keyboard shortcuts: one table drives both the handler and the help dialog.

import { ctl, store } from './controller.svelte.js';

const s = () => store.state;
const lastMark = () => s().marks[s().marks.length - 1];

/** [keys shown in help, description, key names matched, action] or [group title] */
export const SHORTCUTS = [
  ['Navigate'],
  [['←', '→'], 'Previous / next band (Shift: ×10; PCA: shift components)', [], null],
  [['Home', 'End'], 'First / last band', ['Home', 'End'], (e) => ctl.goBand(e.key === 'Home' ? 0 : store.nBands - 1)],
  [['Space'], 'Play through bands', [' '], () => ctl.togglePlay()],
  [['0'], 'Fit image (double-click works too)', ['0'], () => ctl.engines.imageView?.fit()],
  [['1'], '1:1 pixels', ['1'], () => ctl.engines.imageView?.oneToOne()],
  [['wheel'], 'Zoom at cursor · drag, right-drag or middle-drag to pan', [], null],
  ['Display'],
  [['B'], 'Band', ['b'], () => store.set({ mode: 'band' })],
  [['C'], 'RGB composite', ['c'], () => store.set({ mode: 'rgb' })],
  [['P'], 'PCA', ['p'], () => store.set({ mode: 'pca' })],
  [['N'], 'Anomaly', ['n'], () => store.set({ mode: 'anomaly' })],
  [['S'], 'Similarity', ['s'], () => store.set({ mode: 'similarity' })],
  [['M'], 'Band math', ['m'], () => store.set({ mode: 'math' })],
  [['[', ']'], 'Cycle colour maps (PCA: shift components)', ['[', ']'], (e) => (s().mode === 'pca' ? ctl.stepBand(e.key === ']' ? 1 : -1) : ctl.cycleCmap(e.key === ']' ? 1 : -1))],
  [['R'], 'Reverse colour map', ['r'], () => store.set({ cmapRev: !s().cmapRev })],
  [['A'], 'Auto stretch (2–98%)', ['a'], () => ctl.applyPreset('2')],
  [['L'], 'Lock stretch across bands', ['l'], () => store.set({ lockStretch: !s().lockStretch })],
  [['K'], 'Highlight clipped pixels', ['k'], () => store.set({ overlays: { ...s().overlays, clip: !s().overlays.clip } })],
  ['Inspect'],
  [['click'], 'Pin a pixel spectrum (drag a pin to move it)', [], null],
  [['Shift', 'drag'], 'Rectangle region (mean ± σ)', [], null],
  [['V'], 'Inspect tool', ['v'], () => store.set({ tool: 'inspect' })],
  [['E'], 'Ellipse tool', ['e'], () => store.set({ tool: 'ellipse' })],
  [['F'], 'Freehand tool', ['f'], () => store.set({ tool: 'lasso' })],
  [['/'], 'Line-profile tool', ['/'], () => store.set({ tool: 'line' })],
  [['Del'], 'Remove the last pin / region', ['Delete', 'Backspace'], () => { const m = lastMark(); if (m) store.removeMark(m.id); }],
  [['Esc'], 'Cancel / close', [], null],
  ['Views'],
  [['I'], 'Image', ['i'], () => ctl.setView('image')],
  [['G'], 'All channels', ['g'], () => ctl.setView('grid')],
  [['D'], '3D', ['d'], () => ctl.setView('3d')],
  [['Q'], 'Quality', ['q'], () => ctl.setView('quality')],
  ['Files'],
  [['Ctrl', 'O'], 'Open a cube (or drop a file on the window)', [], null],
  [['Ctrl', 'S'], 'Save the view as PNG', [], null],
  [['Ctrl', 'E'], 'Export spectra as CSV', [], null],
  [['?'], 'This help', ['?'], () => (ctl.ui.modal = 'help')],
];

const byKey = new Map();
for (const row of SHORTCUTS) if (row.length > 1 && row[3]) for (const k of row[2]) byKey.set(k, row[3]);

export function handleKey(e) {
  if (e.target.matches?.('input[type=text], input[type=number], input:not([type]), textarea, select')) return;
  const ui = ctl.ui;
  const mod = e.ctrlKey || e.metaKey;
  if (e.key === 'Escape') { ui.modal = null; ui.menu = null; ctl.engines.imageView?.cancelDraft(); if (ui.playing) ctl.togglePlay(); return; }
  if (ui.modal) return;
  const k = e.key.toLowerCase();
  if (mod && k === 'o') { e.preventDefault(); ui.modal = 'open'; return; }
  if (mod && k === 's') { e.preventDefault(); ctl.snapshot(); return; }
  if (mod && k === 'e') { e.preventDefault(); ctl.exportCsv(); return; }
  if (mod || e.altKey || !store.meta) return;
  if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    e.preventDefault();
    ctl.stepBand((e.key === 'ArrowRight' ? 1 : -1) * (e.shiftKey ? 10 : 1));
    return;
  }
  const act = byKey.get(e.key) || byKey.get(k);
  if (act) { e.preventDefault(); ui.menu = null; act(e); }
}
