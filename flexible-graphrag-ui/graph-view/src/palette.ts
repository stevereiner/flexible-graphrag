/**
 * Stable type -> colour, the same in every view, session and app (React, Vue, Angular, KG Spaces).
 * Common schema types get fixed, distinct colours (synonyms share one); any other type is
 * hashed to a hue.
 */

// Okabe-Ito based, extended; readable on light and dark backgrounds.
export const PALETTE: Record<string, string> = {
  PERSON: '#0072B2',
  ORGANIZATION: '#E69F00',
  LOCATION: '#009E73',
  TECHNOLOGY: '#CC79A7',
  PROJECT: '#7F63B8',
  DOCUMENT: '#A0785A',
  EVENT: '#D55E00',
  DATE: '#B8A000',
  PRODUCT: '#56B4E9',
  SKILL: '#2CA6A4',
  TOPIC: '#E2556F',
  DEPARTMENT: '#6C8EBF',
};

const SYNONYMS: Record<string, string> = {
  COMPANY: 'ORGANIZATION', ORG: 'ORGANIZATION',
  PLACE: 'LOCATION', CITY: 'LOCATION', COUNTRY: 'LOCATION', GPE: 'LOCATION',
  PEOPLE: 'PERSON', EMPLOYEE: 'PERSON',
  TIME: 'DATE',
};

/** Colour for the generic fallback type, so untyped entities read as "no type". */
export const ENTITY_COLOR = '#8C8C8C';

function hash(s: string): number {
  let h = 0x811c9dc5; // FNV-1a
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export function colorFor(type: string): string {
  const t = (type || '').toUpperCase();
  if (!t || t === 'ENTITY') return ENTITY_COLOR;
  const known = PALETTE[SYNONYMS[t] ?? t];
  if (known) return known;
  const h = hash(t);
  return `hsl(${h % 360}, ${45 + (h >> 9) % 20}%, ${45 + (h >> 17) % 12}%)`;
}
