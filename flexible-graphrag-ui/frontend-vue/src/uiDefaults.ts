// Where the UI's choices start, from the backend (GET /api/ui-defaults): the data-source forms'
// Deep checkbox (DEFAULT_RECURSIVE) and the Processing tab's Graph / RDF checkboxes for a new row
// (DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF). Asked once per page load. An older backend has
// no such endpoint: it stays {} then, and each caller falls back to what that backend did when not told.
import { reactive } from 'vue';
import axios from 'axios';

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
    axios.get('/api/ui-defaults').then((r) => Object.assign(defaults, r.data || {})).catch(() => {});
  }
  return defaults;
}
