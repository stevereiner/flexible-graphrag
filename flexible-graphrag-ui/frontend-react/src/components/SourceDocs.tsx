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

/** The store part of a result's source label ("a.txt | Neo4j property graph" -> "Neo4j property graph"). */
export const storeLabel = (source?: string): string => {
  const s = source || '';
  const i = s.lastIndexOf(' | ');
  return i >= 0 ? s.slice(i + 3) : '';
};
