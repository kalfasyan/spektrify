// A deliberately tiny Markdown subset for lesson text: paragraphs, "- " and "1. " lists
// (indented lines continue an item), **bold**, *italic*, `code` and [links](https://…).
// Everything is HTML-escaped first, so lesson files can't inject markup. Anything fancier
// belongs in a real Markdown library.

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const escape = (s) => s.replace(/[&<>"']/g, (c) => ESC[c]);

function inline(text) {
  // Split on code spans first so nothing inside them is formatted.
  return text.split(/(`[^`]+`)/).map((part) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 1) return `<code>${escape(part.slice(1, -1))}</code>`;
    return escape(part)
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/\*(.+?)\*/g, '<i>$1</i>')
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  }).join('');
}

const ITEM = /^\s*(?:[-*]|(\d+)\.) /;

/** A block whose first line starts a list item → <ul>/<ol>, or null. Indented lines continue
 * the item above them, so long items can wrap in the lesson file. */
function list(lines) {
  const first = lines[0].match(ITEM);
  if (!first) return null;
  const items = [];
  for (const line of lines) {
    if (ITEM.test(line)) items.push(line.replace(ITEM, ''));
    else if (/^\s/.test(line)) items[items.length - 1] += ` ${line.trim()}`;
    else return null;
  }
  const tag = first[1] ? 'ol' : 'ul';
  return `<${tag}>${items.map((i) => `<li>${inline(i)}</li>`).join('')}</${tag}>`;
}

/** Markdown subset → safe HTML. */
export function markdown(src = '') {
  return src.trim().split(/\n\s*\n/).map((block) => {
    const lines = block.split('\n');
    return list(lines) ?? `<p>${inline(lines.join(' '))}</p>`;
  }).join('');
}
