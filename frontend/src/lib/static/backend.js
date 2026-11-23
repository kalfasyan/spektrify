// The online demo's backend: answers the viewer's /api/ requests from a static snapshot
// (written by `python -m spektrify.server.snapshot`) instead of a Python server.
//
// `siteFetch` has the same signature and responses as `fetch` against the real server, so
// api.js only swaps the transport and nothing else in the UI knows the difference. A state
// is one (demo cube, preprocessing pipeline) pair; the snapshot holds every state the lessons
// reach, with the products and band-math results they show and an answer key per task.

import { loadArray, loadJson } from './files.js';
import * as ops from './cubeops.js';

const ROOT = './data/';
const FORMAT = 1;
export const OFFLINE_HINT = 'Install spektrify (pip install spektrify) to open your own data and explore freely.';

class NotAvailable extends Error {}
const notAvailable = (what) => new NotAvailable(`${what} isn't available in the online demo. ${OFFLINE_HINT}`);

/** Same key order and spacing as the snapshot's `pipeline_key()` in Python. */
function pipelineKey(steps) {
  const sorted = (v) => (Array.isArray(v) ? v.map(sorted)
    : v && typeof v === 'object' ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sorted(v[k])])) : v);
  return JSON.stringify(sorted(steps ?? []));
}

let indexP = null;
function index() {
  indexP ??= loadJson(`${ROOT}index.json`).then((ix) => {
    if (ix.format !== FORMAT) throw new Error(`This page expects snapshot format ${FORMAT}, got ${ix.format}.`);
    // Re-key with this file's pipelineKey so number formatting can't differ from Python's.
    ix.byKey = new Map();
    for (const st of ix.states) for (const p of st.pipelines) ix.byKey.set(`${st.demo}|${pipelineKey(JSON.parse(p))}`, st);
    return ix;
  });
  return indexP;
}

const cache = new Map(); // url -> Promise (state files, lessons, arrays)
function once(url, load) {
  if (!cache.has(url)) cache.set(url, load().catch((e) => { cache.delete(url); throw e; }));
  return cache.get(url);
}

let current = null; // { demo, dir, state, cube: Promise<{data, c, h, w}> }
let generation = 0;

async function show(demo, steps) {
  const ix = await index();
  const entry = ix.byKey.get(`${demo}|${pipelineKey(steps)}`);
  if (!entry) throw notAvailable('This preprocessing pipeline');
  const base = `${ROOT}${entry.dir}/`;
  const state = await once(`${base}state.json`, () => loadJson(`${base}state.json`));
  const [c, h, w] = state.cube.meta.shape;
  const cube = once(`${base}cube`, async () => ({ data: await loadArray(base + state.cube.file, state.cube.meta.dtype), c, h, w }));
  await cube; // the image needs it at once; loading it here keeps the old cube until it's ready
  current = { demo, base, state, cube };
  generation++;
}

async function array(entry) {
  const data = await once(current.base + entry.file, () => loadArray(current.base + entry.file, entry.meta.dtype));
  return { array: data, meta: entry.meta };
}

async function precomputed(name, params) {
  const q = new URLSearchParams(Object.entries(params).sort(([a], [b]) => (a < b ? -1 : 1))).toString();
  const entry = current.state.bin[q ? `${name}?${q}` : name];
  if (!entry) throw notAvailable('This view');
  return array(entry);
}

// ---------------------------------------------------------------------- routes
const ROUTES = {
  generation: async () => ({ generation }),
  meta: async () => ({ ...current.state.json.meta, generation, recent: [] }),
  quality: async () => current.state.json.quality,
  steps: async () => (await index()).steps,
  async band(p) {
    const cube = await current.cube, i = +p.i;
    if (!(i >= 0 && i < cube.c)) throw new Error(`band ${i} out of range`);
    return bin(ops.band(cube, i), [cube.h, cube.w], { band: i });
  },
  async thumbs(p) {
    const t = ops.thumbnails(await current.cube, +(p.side ?? 128));
    return bin(t.array, t.shape, t.meta);
  },
  async spectrum(p) {
    const cube = await current.cube, x = +p.x, y = +p.y;
    if (!(x >= 0 && x < cube.w && y >= 0 && y < cube.h)) throw new Error('pixel outside the image');
    return { x, y, values: ops.spectrum(cube, x, y) };
  },
  async region(p, body) {
    const cube = await current.cube;
    return ops.regionStats(cube, ops.regionMask(body, cube.h, cube.w));
  },
  async slice(p) {
    const cube = await current.cube, axis = p.axis ?? 'row';
    if (axis !== 'row' && axis !== 'col') throw new Error('axis must be row or col');
    const i = Math.min(Math.max(+p.i, 0), (axis === 'row' ? cube.h : cube.w) - 1);
    return bin(ops.slice(cube, axis, i), [cube.c, axis === 'row' ? cube.w : cube.h], { axis, index: i });
  },
  async line(p) {
    const r = ops.line(await current.cube, +p.x0, +p.y0, +p.x1, +p.y1);
    return bin(r.array, r.shape);
  },
  async product(p, body) {
    if (p.kind === 'sam') {
      const cube = await current.cube;
      const ref = body?.reference ?? current.state.json.meta.mean_spectrum;
      return bin(ops.spectralAngle(cube, ref), [1, cube.h, cube.w], { kind: 'sam' });
    }
    if (p.kind === 'math') {
      const expr = body?.expr ?? p.expr;
      const entry = current.state.math[expr];
      if (!entry) throw new NotAvailable(`The online demo only has the lessons' own expressions precomputed. ${OFFLINE_HINT}`);
      const r = await array(entry);
      return bin(r.array, r.meta.shape, r.meta);
    }
    const r = await precomputed('product', p);
    return bin(r.array, r.meta.shape, r.meta);
  },
  correlation: (p) => passthrough('correlation', p),
  stripes: (p) => passthrough('stripes', p),
  volume: (p) => passthrough('volume', p),
  scatter: (p) => passthrough('scatter', p),
  async demo(p, body) {
    await show(body?.name || 'scene', []);
    return { ok: true };
  },
  async pipeline(p, body) {
    await show(current?.demo ?? (await index()).start, body?.steps ?? []);
    return { ok: true, steps: current.state.json.meta.pipeline, seconds: 0 };
  },
  async lessons() {
    return { lessons: (await index()).lessons, demo: current?.demo ?? null, labelled: !!current };
  },
  async lesson(p) {
    const { checks, ...lesson } = await loadLesson(p.id);
    return lesson;
  },
  async 'lesson-check'(p, body) {
    const lesson = await loadLesson(body.id);
    const key = lesson.checks[body.step];
    if (!key) throw new Error('that step has no task');
    const a = body.answer ?? {};
    let i;
    if (key.kind === 'pixel') {
      key.bytes ??= Uint8Array.from(atob(key.codes), (ch) => ch.charCodeAt(0));
      i = key.bytes[(a.y | 0) * key.width + (a.x | 0)];
    } else i = key.codes[key.kind === 'band' ? a.band : a.choice];
    if (i === undefined) throw new Error('bad answer');
    return key.outcomes[i];
  },
};

const passthrough = async (name, p) => { const r = await precomputed(name, p); return bin(r.array, r.meta.shape, r.meta); };
const loadLesson = (id) => once(`lesson:${id}`, () => loadJson(`${ROOT}lessons/${encodeURIComponent(id)}.json`));

function bin(array, shape, meta = {}) {
  const dtype = { Float32Array: 'float32', Uint8Array: 'uint8', Uint32Array: 'uint32', Float64Array: 'float64', Uint16Array: 'uint16', Int32Array: 'int32' }[array.constructor.name];
  return new Response(array, { headers: { 'X-Meta': JSON.stringify({ ...meta, dtype, shape }) } });
}

const jsonResponse = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });

/** `fetch` for `/api/...` URLs, answered from the snapshot. */
export async function siteFetch(url, opts = {}) {
  const u = new URL(url, location.href);
  const name = u.pathname.replace(/^.*\/api\//, '');
  const params = Object.fromEntries(u.searchParams);
  const body = typeof opts.body === 'string' ? JSON.parse(opts.body) : undefined;
  try {
    // Start on the default demo, as `spektrify learn` does.
    if (!current && !['steps', 'lessons', 'lesson', 'demo'].includes(name)) await show((await index()).start, []);
    const route = ROUTES[name];
    if (!route) throw notAvailable(name === 'open' || name === 'upload' || name === 'browse' ? 'Opening files' : `/api/${name}`);
    const res = await route(params, body);
    return res instanceof Response ? res : jsonResponse(res);
  } catch (e) {
    return jsonResponse({ error: e.message }, e instanceof NotAvailable ? 501 : 400);
  }
}
