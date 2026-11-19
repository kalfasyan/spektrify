<script>
  // Preprocessing pipeline editor. The form is generated from the server's step schema, so a
  // step registered in Python shows up here without any UI change.
  import { onMount } from 'svelte';
  import { ctl, store } from '../../lib/controller.svelte.js';
  import { api } from '../../lib/api.js';
  import Icon from '../Icon.svelte';
  import PathField from './PathField.svelte';

  const s = store.state;
  let schema = $state([]);
  let draft = $state([]); // [{name, params}]
  let busy = $state(false);
  let adding = $state('');

  onMount(() => { api.steps().then((r) => (schema = r.steps)).catch(() => {}); });
  // Follow the server's pipeline whenever a cube (re)loads.
  $effect(() => { draft = JSON.parse(applied); });

  const specOf = (name) => schema.find((x) => x.name === name);
  const defaults = (name) => Object.fromEntries((specOf(name)?.params ?? []).map((p) => [p.name, p.default]));
  function withDefaults(steps) { return steps.map((st) => ({ ...st, params: { ...defaults(st.name), ...st.params } })); }
  // The applied pipeline with every parameter filled in (a pipeline from the CLI or a lesson
  // may name only some), so the form has a value for each field.
  const applied = $derived(JSON.stringify(withDefaults(s.meta?.pipeline ?? [])));
  const dirty = $derived(JSON.stringify(draft) !== applied);
  function add(name) {
    const spec = specOf(name);
    if (spec) draft.push({ name, params: defaults(name) });
    adding = '';
  }
  async function apply() {
    busy = true;
    try {
      await ctl.reprocess(draft);
      ctl.toast(draft.length ? `Applied ${draft.map((d) => d.name).join(' → ')}` : 'Showing the raw cube');
    } catch (e) { ctl.toast(e.message, 'error'); }
    busy = false;
  }
</script>

<div class="panel-section">
  <div class="section-title">Preprocess {#if dirty}<span class="hint">not applied</span>{/if}</div>
  {#each draft as st, i}
    {@const spec = specOf(st.name)}
    <div class="pp-step" title={spec?.help}>
      <div class="row"><b>{i + 1}. {st.name}</b><span class="spacer"></span>
        <button class="icon-btn small" title="Remove step" onclick={() => draft.splice(i, 1)}><Icon name="close" /></button>
      </div>
      {#each spec?.params ?? [] as p}
        <label class="pp-param" class:stacked={p.kind === 'path'} title={p.help}>
          <span>{p.name}</span>
          {#if p.type === 'bool'}
            <input type="checkbox" bind:checked={st.params[p.name]} />
          {:else if p.kind === 'path'}
            <PathField bind:value={st.params[p.name]} placeholder="number or file path" />
          {:else if p.type === 'int' || p.type === 'float'}
            <input type="number" step={p.type === 'int' ? 1 : 'any'} bind:value={st.params[p.name]} />
          {:else}
            <input type="text" spellcheck="false" bind:value={st.params[p.name]} />
          {/if}
        </label>
      {/each}
    </div>
  {:else}
    <div class="note">No preprocessing: you are looking at the cube as loaded.</div>
  {/each}
  <select bind:value={adding} onchange={() => add(adding)}>
    <option value="">Add a step…</option>
    {#each schema as x}<option value={x.name} title={x.help}>{x.name}: {x.help}</option>{/each}
  </select>
  <div class="row">
    <button class="btn small primary" disabled={!dirty || busy} onclick={apply}>{busy ? 'Applying…' : 'Apply'}</button>
    <button class="btn small" disabled={!dirty || busy} onclick={() => (draft = JSON.parse(applied))}>Revert</button>
  </div>
</div>

<style>
  .pp-step { border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; display: flex; flex-direction: column; gap: 4px; }
  .pp-param { display: grid; grid-template-columns: 96px 1fr; align-items: center; gap: 6px; color: var(--text-2); font-size: 12px; }
  .pp-param.stacked { grid-template-columns: 1fr; gap: 2px; }
  .pp-param input[type=checkbox] { justify-self: start; }
</style>
