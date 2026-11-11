import type { StylesheetJson } from 'cytoscape';
import type { Theme } from './types';

const THEMES = {
  light: { text: '#1f2328', outline: '#ffffff', edge: '#a0a7b0', edgeText: '#57606a', selected: '#ff6d00',
           chunk: '#9aa1a9', mention: '#b4bac1' },
  dark: { text: '#e6edf3', outline: '#121212', edge: '#5c6670', edgeText: '#9aa4ae', selected: '#ffab40',
          chunk: '#6b747d', mention: '#4c555e' },
};

export function stylesheet(theme: Theme): StylesheetJson {
  const t = THEMES[theme] ?? THEMES.light;
  return [
    {
      selector: 'node',
      style: {
        'background-color': 'data(color)',
        width: 26, // one size for every entity
        height: 26,
        label: 'data(caption)',
        'font-size': 9,
        color: t.text,
        'text-valign': 'bottom',
        'text-halign': 'center',
        'text-margin-y': 4,
        'text-outline-color': t.outline,
        'text-outline-width': 2,
        'min-zoomed-font-size': 6,
        'border-width': 1,
        'border-color': t.outline,
      },
    },
    {
      selector: 'edge',
      style: {
        width: 1.5,
        'curve-style': 'bezier',
        'line-color': t.edge,
        'target-arrow-color': t.edge,
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.9,
        label: 'data(type)',
        'font-size': 7,
        color: t.edgeText,
        'text-rotation': 'autorotate',
        'text-outline-color': t.outline,
        'text-outline-width': 2,
        'min-zoomed-font-size': 7, // edge captions only once zoomed in
      },
    },
    // Chunks: small grey squares, captions only when zoomed in; MENTIONS: thin dashed, no caption
    {
      selector: 'node[kind = "chunk"]',
      style: {
        shape: 'round-rectangle',
        'background-color': t.chunk,
        width: 14,
        height: 14,
        'font-size': 7,
        'min-zoomed-font-size': 10,
      },
    },
    {
      selector: 'edge[kind = "mention"]',
      style: {
        width: 1,
        'line-style': 'dashed',
        'line-color': t.mention,
        'target-arrow-color': t.mention,
        'arrow-scale': 0.6,
        label: '',
      },
    },
    {
      selector: 'node:selected',
      style: { 'border-width': 4, 'border-color': t.text }, // text colour: shows on any type colour
    },
    {
      selector: 'edge:selected',
      style: { width: 3, 'line-color': t.selected, 'target-arrow-color': t.selected },
    },
    { selector: '.faded', style: { opacity: 0.15, 'text-opacity': 0 } },
    { selector: '.hidden', style: { display: 'none' } },
  ];
}
