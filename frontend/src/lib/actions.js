// Svelte actions shared by components.

import { ctl } from './controller.svelte.js';

/**
 * Paint a band thumbnail into a <canvas> when it scrolls into view (and again when the
 * colour map or normalisation changes). params: {band, cmap, rev, norm?, root?, cursor?}
 */
export function lazyThumb(canvas, params) {
  let p = params;
  let visible = false;
  let painted = null;
  const paint = () => {
    const t = ctl.thumbs;
    if (!visible || !t.data) return;
    const key = `${p.band}:${p.cmap}:${p.rev}:${p.norm || 'band'}`;
    if (painted === key && !p.cursor) return;
    if (canvas.width !== t.meta.width) { canvas.width = t.meta.width; canvas.height = t.meta.height; }
    const ctx = canvas.getContext('2d');
    ctx.drawImage(t.canvasFor(p.band, p.cmap, p.rev, p.norm || 'band'), 0, 0);
    if (p.cursor) {
      const { x, y } = p.cursor;
      ctx.strokeStyle = 'rgba(255,255,255,.85)';
      ctx.lineWidth = Math.max(0.6, canvas.width / 200);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
      painted = null;
    } else painted = key;
  };
  const io = new IntersectionObserver((es) => { visible = es[0].isIntersecting; paint(); }, { root: p.root || null, rootMargin: '300px' });
  io.observe(canvas);
  return {
    update(np) { p = np; paint(); },
    destroy() { io.disconnect(); },
  };
}
