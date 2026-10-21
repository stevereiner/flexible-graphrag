import React from 'react';
import { Checkbox, FormControlLabel } from '@mui/material';

/**
 * The Deep checkbox next to a form's folder field (Alfresco, Nuxeo, Box): a selected folder's
 * subfolders, at every depth, are ingested too and its auto sync follows them. Off: only the
 * documents directly in the folder. Sent as the config's `recursive`, always explicitly.
 */
export const DeepCheckbox: React.FC<{ checked: boolean; onChange: (checked: boolean) => void }> = ({ checked, onChange }) => (
  <FormControlLabel
    sx={{ ml: 1, mb: 2, flexShrink: 0 }}
    title="Include subfolders, at every depth, in the ingest and its auto sync"
    control={<Checkbox size="small" checked={checked} onChange={(e) => onChange(e.target.checked)} />}
    label="Deep"
  />
);

/** The Deep value a form shows: its own (a saved / existing config's) choice, else the backend's
 *  DEFAULT_RECURSIVE (/api/ui-defaults), else what an older backend did when not told. */
export const deepValue = (own: boolean | undefined, backendDefault: boolean | undefined, fallback: boolean): boolean =>
  own ?? backendDefault ?? fallback;
