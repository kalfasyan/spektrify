// Lesson diagrams by kind. A lesson step names one with `figure = { kind = "…", … }`; the
// kinds and their options are declared in Python (spektrify/learn/model.py, FIGURES), which
// validates lesson files. To add a kind: write a component here that takes
// {o (options), f (continuous frame), frame, step} and exports `captions(o, step)` (one per
// frame), list it below and in FIGURES.

import * as cube from './Cube.svelte';
import * as pixels from './Pixels.svelte';
import * as kernel from './Kernel.svelte';
import * as tone from './Tone.svelte';
import * as spectrum from './Spectrum.svelte';
import * as pipeline from './Pipeline.svelte';
import * as scatter from './Scatter.svelte';
import * as waves from './Waves.svelte';
import * as camera from './Camera.svelte';
import * as layers from './Layers.svelte';
import * as sensor from './Sensor.svelte';
import * as mosaic from './Mosaic.svelte';

const entry = (m) => ({ component: m.default, captions: m.captions });

export const FIGURES = {
  cube: entry(cube),
  pixels: entry(pixels),
  kernel: entry(kernel),
  tone: entry(tone),
  spectrum: entry(spectrum),
  pipeline: entry(pipeline),
  scatter: entry(scatter),
  waves: entry(waves),
  camera: entry(camera),
  layers: entry(layers),
  sensor: entry(sensor),
  mosaic: entry(mosaic),
};
