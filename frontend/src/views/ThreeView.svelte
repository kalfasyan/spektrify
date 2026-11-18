<script>
  // 3-D view: the three.js engine (lib/engines/view3d.js) is loaded on first visit and
  // driven from these Svelte panels. The engine owns the scene; this file owns the controls.
  import { onMount } from 'svelte';
  import { ctl, store } from '../lib/controller.svelte.js';
  import { api } from '../lib/api.js';
  import { fmt } from '../lib/util.js';

  let { active = false } = $props();
  const s = store.state;
  const ui = ctl.ui;
  let wrap;
  let engine = $state(null);
  let mode = $state('cube');
  let hint = $state('');
  let busy = $state('');
  let pick = $state(null);
  let cut = $state(null);
  let opts = $state({ depth: 0.55, perBand: false, volMode: 1, volLo: 0.18, volHi: 0.95, volOpacity: 0.6, pointSize: 2.2, colorBy: 'pca' });
  let clip = $state({ x: 1, y: 1, z: 1 });

  onMount(() => {
    let detach = () => {}, e3;
    let dead = false;
    import('../lib/engines/view3d.js').then(({ View3D }) => {
      if (dead) return;
      e3 = new View3D(wrap, { store, api });
      Object.assign(e3.opts, opts);
      e3.on('hint', (h) => (hint = h));
      e3.on('busy', (b) => (busy = b));
      e3.on('pick', (p) => (pick = p));
      e3.on('cut', (c) => (cut = { ...c }));
      e3.on('pinned', (mk) => mk && ctl.toast(`Pinned ${mk.name} · see it in the Image view`));
      detach = ctl.attach('view:3d', e3);
      engine = e3;
    });
    const off = store.on('change', (keys) => e3?.stateChanged(keys));
    return () => { dead = true; off?.(); detach(); e3?.destroy(); };
  });

  $effect(() => { if (!engine) return; active ? engine.activate() : engine.deactivate(); });
  // A new cube invalidates the scene.
  let lastCube = ui.cubeVersion;
  $effect(() => { const v = ui.cubeVersion; if (engine && v !== lastCube) { lastCube = v; clip = { x: 1, y: 1, z: 1 }; engine.cubeChanged(); } });

  function setMode(m) { mode = m; pick = null; clip = { x: 1, y: 1, z: 1 }; engine?.setMode(m); }
  function setCut(patch) { cut = { ...cut, ...patch }; engine?.setCut(patch); }
  function setTop(v) { setCut({ top: v }); store.set({ band: v }); }
  function cubeOpt(k, v) { opts[k] = v; engine?.setCubeOpt(k, v); }
  function volOpt(k, v) { opts[k] = v; engine?.setVolOpt(k, v); }
  function setClip(axis, v) { clip[axis] = v; engine?.setClip(axis, v); }
  function colorBy(v) { opts.colorBy = v; engine?.setColorBy(v); }
  function pointSize(v) { opts.pointSize = v; engine?.setPointSize(v); }

  const m = $derived(s.meta);
</script>

<div class="three-wrap" bind:this={wrap}></div>
<div class="float-panel">
  <div class="seg">
    <button class:active={mode === 'cube'} title="Orthogonal slices through the cube" onclick={() => setMode('cube')}>Slice cube</button>
    <button class:active={mode === 'volume'} title="GPU volume rendering" onclick={() => setMode('volume')}>Volume</button>
    <button class:active={mode === 'cloud'} title="Pixels in PCA space" onclick={() => setMode('cloud')}>PCA cloud</button>
  </div>
  <div id="three-controls">
    {#if !engine}
      <div class="note">Loading the 3-D engine…</div>
    {:else if mode === 'cube' && cut && m}
      <div class="ctrl-label">Cut into the cube</div>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">x</span><input type="range" min="1" max={m.width} step="1" value={cut.x} onchange={(e) => setCut({ x: +e.currentTarget.value })} oninput={(e) => (cut.x = +e.currentTarget.value)} /><span class="val">{cut.x - 1}</span></label>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">y</span><input type="range" min="1" max={m.height} step="1" value={cut.z} onchange={(e) => setCut({ z: +e.currentTarget.value })} oninput={(e) => (cut.z = +e.currentTarget.value)} /><span class="val">{cut.z - 1}</span></label>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">λ top</span><input type="range" min="0" max={m.bands - 1} step="1" value={cut.top} onchange={(e) => setTop(+e.currentTarget.value)} oninput={(e) => (cut.top = +e.currentTarget.value)} /><span class="val">{store.bandLabel(cut.top, true)}</span></label>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">depth</span><input type="range" min="0.15" max="1.6" step="0.01" value={opts.depth} oninput={(e) => cubeOpt('depth', +e.currentTarget.value)} /></label>
      <label class="toggle"><input type="checkbox" checked={opts.perBand} onchange={(e) => cubeOpt('perBand', e.currentTarget.checked)} /><span>Normalise each band on the sides</span></label>
      <div class="row">
        <button class="btn small" onclick={() => engine.resetCut()}>Reset cut</button>
        <button class="btn small" onclick={() => engine.resetCamera()}>Reset camera</button>
      </div>
      <div class="note">Side faces are spectral cross-sections (x–λ, y–λ): horizontal lines are bad bands, vertical lines are bad detector columns, slanted structure is keystone / smile.</div>
    {:else if mode === 'volume'}
      <div class="seg">
        <button class:active={opts.volMode === 0} onclick={() => volOpt('volMode', 0)}>MIP</button>
        <button class:active={opts.volMode === 1} onclick={() => volOpt('volMode', 1)}>Composite</button>
      </div>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">low</span><input type="range" min="0" max="1" step="0.005" value={opts.volLo} oninput={(e) => volOpt('volLo', +e.currentTarget.value)} /></label>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">high</span><input type="range" min="0.05" max="1" step="0.005" value={opts.volHi} oninput={(e) => volOpt('volHi', +e.currentTarget.value)} /></label>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">opacity</span><input type="range" min="0.02" max="1" step="0.01" value={opts.volOpacity} oninput={(e) => volOpt('volOpacity', +e.currentTarget.value)} /></label>
      <div class="ctrl-label">Clip</div>
      {#each [['x', 'x'], ['λ', 'y'], ['y', 'z']] as [label, axis]}
        <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">{label}</span><input type="range" min="0" max="1" step="0.005" value={clip[axis]} oninput={(e) => setClip(axis, +e.currentTarget.value)} /></label>
      {/each}
      <div class="row"><button class="btn small" onclick={() => engine.resetCamera()}>Reset camera</button></div>
      <div class="note">Values are scaled with the cube-wide 0.5–99.5% range and downsampled to fit the GPU. Raise “low” to peel away background; bright blobs that persist across λ are real objects, thin sheets are bad bands.</div>
    {:else if mode === 'cloud'}
      <div class="ctrl-label">Colour points by</div>
      <div class="seg">
        {#each [['pca', 'PCA RGB'], ['band', 'Band'], ['mean', 'Mean'], ['rx', 'RX']] as [v, t]}
          <button class:active={opts.colorBy === v} onclick={() => colorBy(v)}>{t}</button>
        {/each}
      </div>
      <label class="slider-row"><span class="lbl" style="width:52px;flex:none;text-align:left;white-space:nowrap">size</span><input type="range" min="1" max="6" step="0.1" value={opts.pointSize} oninput={(e) => pointSize(+e.currentTarget.value)} /></label>
      <div class="note mono">{pick ? `x ${pick.x} · y ${pick.y} · PC ${pick.scores.map((v) => fmt(v, 3)).join(', ')}` : ' '}</div>
      <div class="row"><button class="btn small" onclick={() => engine.resetCamera()}>Reset camera</button></div>
      <div class="note">Clusters are materials; isolated points and thin streaks far from the clusters are anomalies or sensor artefacts. Click one to pin its pixel.</div>
    {/if}
  </div>
</div>
<div class="three-hint">{busy || hint}</div>

