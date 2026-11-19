<script>
  // Small stroke icon set (24×24 viewBox) so components don't repeat SVG markup.
  let { name, size = undefined } = $props();
  const PATHS = {
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .8-1 1.5V14"/><circle cx="12" cy="17.2" r=".6" fill="currentColor"/>',
    inspect: '<path d="M5 3l14 8-6 2-2 6z"/>',
    rect: '<rect x="4" y="6" width="16" height="12" rx="1"/>',
    ellipse: '<ellipse cx="12" cy="12" rx="8" ry="6"/>',
    lasso: '<path d="M6 15c-3-4 1-10 7-10s9 4 6 8-9 3-11 1c-1 3 1 6 3 6"/>',
    line: '<path d="M5 19L19 5"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/>',
    fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    one: '<text x="12" y="16" text-anchor="middle" font-size="10" fill="currentColor" stroke="none" font-weight="700">1:1</text>',
    play: '<path d="M8 5v14l11-7z" fill="currentColor"/>',
    pause: '<path d="M8 5v14M16 5v14" stroke-width="3"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/>',
    reverse: '<path d="M7 7h11l-3-3M17 17H6l3 3"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
    learn: '<path d="M2 9l10-5 10 5-10 5z"/><path d="M6 11v5c0 1.5 3 3 6 3s6-1.5 6-3v-5M22 9v6"/>',
    band: '<rect x="4" y="5" width="16" height="14" rx="1"/><path d="M9 5v14M15 5v14"/>',
  };
</script>

<svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">{@html PATHS[name] || ''}</svg>
