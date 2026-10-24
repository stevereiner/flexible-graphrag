// Where the UI's choices start, from the backend (GET /api/ui-defaults): the data-source forms'
// Deep checkbox (DEFAULT_RECURSIVE) and the Processing tab's Graph / RDF checkboxes for a new row
// (DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF). Asked once per page load. An older backend has
// no such endpoint: {} then, and each caller falls back to what that backend did when not told.
import { useEffect, useState } from 'react';
import axios from 'axios';

export interface UiDefaults {
  recursive?: boolean;
  enabled_graph?: boolean;
  enabled_rdf?: boolean;
  show_graph?: boolean;
  show_rdf?: boolean;
}

let request: Promise<UiDefaults> | null = null;

export function getUiDefaults(): Promise<UiDefaults> {
  request ||= axios.get('/api/ui-defaults').then((r) => r.data || {}).catch(() => ({}));
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
