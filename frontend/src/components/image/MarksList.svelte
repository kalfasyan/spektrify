<script>
  import { ctl, store } from '../../lib/controller.svelte.js';
  const s = store.state;

  function sub(m) {
    if (m.kind === 'pin') return `x ${m.geom.x} · y ${m.geom.y}`;
    return m.n != null ? `${m.kind} · ${m.n.toLocaleString()} px` : m.kind;
  }
</script>

<div class="marks">
  {#if !s.marks.length}
    <div class="marks-empty">Click the image to pin a pixel.<br />Shift+drag for a region.</div>
  {/if}
  <ul id="marks-list">
    {#each s.marks as m (m.id)}
      {@const isRef = s.refMark === m.id}
      <li class:hidden-mark={!m.visible} title="Click to centre · right-click for actions"
        onclick={() => ctl.focusMark(m)}
        oncontextmenu={(e) => { e.preventDefault(); ctl.contextMenu({ mark: m, clientX: e.clientX, clientY: e.clientY }); }}>
        <span class="sw" style:background={m.color}></span>
        <div>
          <div class="nm">{m.name}{#if m.error}<span class="err" title={m.error}>!</span>{/if}</div>
          <div class="sub">{sub(m)}</div>
        </div>
        <div class="acts">
          <button class:on={isRef} title="Use as reference (ratio view, similarity search)" onclick={(e) => { e.stopPropagation(); store.set({ refMark: isRef ? null : m.id }); }}>{isRef ? '★' : '☆'}</button>
          <button title={m.visible ? 'Hide' : 'Show'} onclick={(e) => { e.stopPropagation(); store.updateMark(m.id, { visible: !m.visible }); }}>{m.visible ? '◉' : '○'}</button>
          <button title="Remove (Del)" onclick={(e) => { e.stopPropagation(); store.removeMark(m.id); }}>✕</button>
        </div>
      </li>
    {/each}
  </ul>
</div>
