import { ref } from 'vue';

/**
 * Bumped by the Processing tab each time an ingest starts. The Sources tab's lists (uploaded
 * files, local files and folders, the documents / folders picked in a repository or cloud
 * browser) empty then: the run's rows come from the configured sources, held apart from the
 * forms, so they stay in the Processing tab, where a different setting can still be chosen.
 */
export const ingestStarted = ref(0);

export const markIngestStarted = (): void => {
  ingestStarted.value++;
};
