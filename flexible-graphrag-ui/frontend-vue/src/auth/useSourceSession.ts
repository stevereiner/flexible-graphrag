import { computed, onMounted, onUnmounted, ref, Ref, watch } from 'vue';
import {
  SourceKind, SourceSession, getSession, ingestCredential, onAuthChange, validateSessions,
} from './sourceAuth';

/** A data-source form's sign-in state for one repository server: the session for `url`, and
 *  whether this ingest uses it (signed in there, and "Use other credentials" not ticked). */
export function useSourceSession(source: SourceKind, url: Ref<string>) {
  const session = ref<SourceSession | null>(getSession(source, url.value));
  const useOther = ref(false);
  const refresh = () => { session.value = getSession(source, url.value); };
  let stop: (() => void) | null = null;
  onMounted(() => {
    stop = onAuthChange(refresh);
    validateSessions(true);  // a kept ticket / token may be dead by now
  });
  onUnmounted(() => stop?.());
  watch(url, refresh);
  const usingSignIn = computed(() => !!session.value && !useOther.value);
  const credential = computed(() => (usingSignIn.value ? ingestCredential(source, url.value) : null));
  return { session, useOther, usingSignIn, credential };
}
