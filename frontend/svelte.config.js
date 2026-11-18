// Mouse-first data tool: clickable list rows are fine here (every action also has a keyboard
// shortcut, see src/lib/shortcuts.js), so silence those two a11y lints only.
const quiet = new Set(['a11y_click_events_have_key_events', 'a11y_no_noninteractive_element_interactions']);

export default {
  onwarn(warning, handler) {
    if (!quiet.has(warning.code)) handler(warning);
  },
};
