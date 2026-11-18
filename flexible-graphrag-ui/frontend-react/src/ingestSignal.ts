import { useEffect, useRef, useSyncExternalStore } from 'react';

/**
 * Bumped by the Processing tab each time an ingest starts. The Sources tab's lists (uploaded
 * files, local files and folders, the documents / folders picked in a repository or cloud
 * browser) empty then: the run's rows come from the configured sources, held apart from the
 * forms, so they stay in the Processing tab, where a different setting can still be chosen.
 */
let started = 0;
const listeners = new Set<() => void>();

export const markIngestStarted = (): void => {
  started++;
  listeners.forEach((l) => l());
};

const useIngestStarted = (): number => useSyncExternalStore(
  (l) => { listeners.add(l); return () => { listeners.delete(l); }; },
  () => started,
);

/** Runs ``clear`` each time an ingest starts while the component is mounted (not on mount). */
export const useOnIngestStarted = (clear: () => void): void => {
  const n = useIngestStarted();
  const seen = useRef(n);
  const latest = useRef(clear);
  latest.current = clear;
  useEffect(() => {
    if (n === seen.current) return;
    seen.current = n;
    latest.current();
  }, [n]);
};
