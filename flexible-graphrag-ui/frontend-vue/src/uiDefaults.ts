// Where the UI's choices start, from the backend (GET /api/ui-defaults): the data-source forms'
// Deep checkbox (DEFAULT_RECURSIVE) and the Processing tab's Graph / RDF checkboxes for a new row
// (DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF). Asked once per page load. An older backend has
// no such endpoint: it stays {} then, and each caller falls back to what that backend did when not told.
import { reactive } from 'vue';
// import axios from 'axios';  // v0.9.0: back with the request in loadUiDefaults

export interface UiDefaults {
  recursive?: boolean;
  enabled_graph?: boolean;
  enabled_rdf?: boolean;
  show_graph?: boolean;
  show_rdf?: boolean;
}

const defaults = reactive<UiDefaults>({});
let asked = false;

/** The backend's UI defaults (reactive: filled in when they arrive). */
export function loadUiDefaults(): UiDefaults {
  if (!asked) {
    asked = true;
    // v0.9.0: restore the request below. The 0.8.6 backend has no /api/ui-defaults, and asking it only
    // logs a 404; until then every caller gets {} and uses its fallback.
    // axios.get('/api/ui-defaults').then((r) => Object.assign(defaults, r.data || {})).catch(() => {});
  }
  return defaults;
}
