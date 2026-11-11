import type { LayoutOptions } from 'cytoscape';
import type { LayoutName } from './types';

/** Above this many nodes layouts are not animated (keeps big graphs responsive). */
const ANIMATE_MAX_NODES = 300;

export function layoutOptions(name: LayoutName, nodeCount: number, randomize = true): LayoutOptions {
  const animate = nodeCount <= ANIMATE_MAX_NODES;
  const common = { fit: true, padding: 30, animate, animationDuration: 400 };
  switch (name) {
    case 'hierarchical':
      return { ...common, name: 'dagre', rankDir: 'LR', nodeSep: 30, rankSep: 90, edgeSep: 10 } as LayoutOptions;
    case 'concentric':
      return {
        ...common,
        name: 'concentric',
        concentric: (n: any) => n.degree(),
        levelWidth: () => 2,
        minNodeSpacing: 24,
        avoidOverlap: true,
      } as LayoutOptions;
    case 'force':
    default:
      return {
        ...common,
        name: 'fcose',
        quality: nodeCount > 1500 ? 'draft' : 'default',
        randomize,
        nodeRepulsion: 9000,
        idealEdgeLength: 90,
        edgeElasticity: 0.45,
        nodeSeparation: 80,
        packComponents: true,
      } as LayoutOptions;
  }
}
