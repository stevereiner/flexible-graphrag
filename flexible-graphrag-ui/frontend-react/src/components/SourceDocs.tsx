import React, { useState } from 'react';
import { IconButton, Link, Tooltip } from '@mui/material';
import { FolderOpen as FolderOpenIcon } from '@mui/icons-material';
import { SourceDocument } from '../types/api';
import { invoke, isTauri } from '../desktop/tauri';
import { openRoots } from '../desktop/localRoots';
import { isRemoteBackend } from '../apiConnection';

interface SourceDocsProps {
  docs?: SourceDocument[];
  /** Text before the list, e.g. "Sources:". */
  label?: string;
}

/** A local file's path (Windows drive or UNC path, or a Unix path): the desktop app can open it. */
const isLocalPath = (p?: string): boolean => !!p && (/^[A-Za-z]:[\\/]/.test(p) || p.startsWith('\\\\') || p.startsWith('/'));

/**
 * The documents a search result or an answer came from. A document with an open link
 * (Alfresco Share, Nuxeo Web UI) opens in a new tab. In the desktop app a local file opens with
 * its default app, and its folder icon shows it in its folder (desktop/src-tauri/src/open_file.rs,
 * which opens only files inside the folders added in the app or the backend's own allowed folders,
 * desktop/localRoots.ts openRoots). Others are plain names (a remote backend's files among them).
 */
export const SourceDocs: React.FC<SourceDocsProps> = ({ docs, label }) => {
  const [error, setError] = useState('');
  if (!docs || docs.length === 0) return null;
  const desktop = isTauri();

  const openLocal = (path: string, reveal: boolean) => {
    setError('');
    openRoots()
      .then((roots) => invoke<void>('open_local_file', { path, roots, reveal }))
      .catch((e) => setError(String(e)));
  };
  // a file on this computer: not a remote backend's document, nor with the app's backend elsewhere
  const openable = (doc: SourceDocument) => desktop && !doc.backend && !isRemoteBackend() && isLocalPath(doc.path);

  return (
    <span>
      {label && <strong style={{ marginRight: 4 }}>{label}</strong>}
      {docs.map((doc, i) => (
        <React.Fragment key={doc.doc_id || doc.name || i}>
          {doc.open_url ? (
            <Link href={doc.open_url} target="_blank" rel="noopener noreferrer" underline="hover"
                  title={doc.path || doc.name}>
              {doc.name}
            </Link>
          ) : openable(doc) ? (
            <>
              <Link component="button" underline="hover" title={`Open ${doc.path}`}
                    sx={{ verticalAlign: 'baseline', font: 'inherit' }}
                    onClick={() => openLocal(doc.path, false)}>
                {doc.name}
              </Link>
              <Tooltip title="Show in folder">
                <IconButton size="small" sx={{ p: 0.25, ml: 0.25 }} onClick={() => openLocal(doc.path, true)}>
                  <FolderOpenIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
            </>
          ) : (
            <span title={doc.path || doc.name}>{doc.name}</span>
          )}
          {i < docs.length - 1 && ', '}
        </React.Fragment>
      ))}
      {error && <span style={{ display: 'block', color: '#f44336', fontSize: '0.8em' }}>{error}</span>}
    </span>
  );
};

/** Display names of the data source types a result's documents came from (backend source_type). */
const SOURCE_TYPE_LABELS: Record<string, string> = {
  alfresco: 'Alfresco', nuxeo: 'Nuxeo', cmis: 'CMIS', sharepoint: 'SharePoint', onedrive: 'OneDrive',
  box: 'Box', google_drive: 'Google Drive', s3: 'Amazon S3', gcs: 'Google Cloud Storage',
  azure_blob: 'Azure Blob', filesystem: 'Files', upload: 'Uploads', web: 'Web', wikipedia: 'Wikipedia',
  youtube: 'YouTube',
};

/** The data source part of a result's source line ("SharePoint"), '' when unknown. */
export const sourceTypeLabel = (docs?: { source_type?: string }[]): string =>
  Array.from(new Set((docs || []).map((d) => d.source_type || '').filter(Boolean)))
    .map((t) => SOURCE_TYPE_LABELS[t] || t).join(', ');

/** The store part of a result's source label ("a.txt | Neo4j property graph" -> "Neo4j property graph"). */
export const storeLabel = (source?: string): string => {
  const s = source || '';
  const i = s.lastIndexOf(' | ');
  return i >= 0 ? s.slice(i + 3) : '';
};
