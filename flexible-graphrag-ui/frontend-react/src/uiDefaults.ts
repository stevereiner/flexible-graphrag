// Where the UI's choices start, from the backend (GET /api/ui-defaults): the data-source forms'
// Deep checkbox (DEFAULT_RECURSIVE) and the Processing tab's Graph / RDF checkboxes for a new row
// (DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF). Asked once per page load. An older backend has
// no such endpoint: {} then, and each caller falls back to what that backend did when not told.
import { useEffect, useState } from 'react';
// import axios from 'axios';  // v0.9.0: back with the request in getUiDefaults

export interface UiDefaults {
  recursive?: boolean;
  enabled_graph?: boolean;
  enabled_rdf?: boolean;
  show_graph?: boolean;
  show_rdf?: boolean;
}

let request: Promise<UiDefaults> | null = null;

export function getUiDefaults(): Promise<UiDefaults> {
  // v0.9.0: restore the request below. The 0.8.6 backend has no /api/ui-defaults, and asking it only
  // logs a 404; until then every caller gets {} and uses its fallback.
  // request ||= axios.get('/api/ui-defaults').then((r) => r.data || {}).catch(() => ({}));
  request ||= Promise.resolve({});
  return request;
}

/** The backend's UI defaults ({} until they arrive, and from an older backend). */
export function useUiDefaults(): UiDefaults {
  const [defaults, setDefaults] = useState<UiDefaults>({});
  useEffect(() => {
    let live = true;
    getUiDefaults().then((d) => { if (live) setDefaults(d); });
    return () => { live = false; };
  }, []);
  return defaults;
}
