import React from 'react';
import { Link } from '@mui/material';
import { SourceDocument } from '../types/api';

interface SourceDocsProps {
  docs?: SourceDocument[];
  /** Text before the list, e.g. "Sources:". */
  label?: string;
}

/**
 * The documents a search result or an answer came from. A document with an open link
 * (Alfresco Share, Nuxeo Web UI) opens in a new tab; others are plain names.
 */
export const SourceDocs: React.FC<SourceDocsProps> = ({ docs, label }) => {
  if (!docs || docs.length === 0) return null;
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
          ) : (
            <span title={doc.path || doc.name}>{doc.name}</span>
          )}
          {i < docs.length - 1 && ', '}
        </React.Fragment>
      ))}
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
