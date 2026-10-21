import React, { useEffect, useMemo, useState } from 'react';
import { Box, Button, Checkbox, FormControlLabel, Typography } from '@mui/material';
import {
  SourceKind, SourceSession, getSession, ingestCredential, labelOf, onAuthChange, openSignIn, signOut, validateSessions,
} from './sourceAuth';

/** The data-source form's sign-in state for one repository server: the session for `url`, and
 *  whether this ingest uses it (signed in there, and "Use other credentials" not ticked). */
export function useSourceSession(source: SourceKind, url: string) {
  const [session, setSession] = useState<SourceSession | null>(getSession(source, url));
  const [useOther, setUseOther] = useState(false);
  useEffect(() => { setSession(getSession(source, url)); }, [source, url]);
  useEffect(() => onAuthChange(() => setSession(getSession(source, url))), [source, url]);
  useEffect(() => { validateSessions(true); }, []);  // a kept ticket / token may be dead by now
  const usingSignIn = !!session && !useOther;
  // memoized on the session: a new object every render would re-emit the form's config forever
  const credential = useMemo(
    () => (usingSignIn ? ingestCredential(source, url) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [usingSignIn, session, source],
  );
  return { session, useOther, setUseOther, usingSignIn, credential };
}

interface Props {
  source: SourceKind;
  url: string;
  session: SourceSession | null;
  usingSignIn: boolean;
  useOther: boolean;
  onUseOtherChange: (v: boolean) => void;
}

/** "Signed in to X as Y (used for this ingest)" with Sign out / Use other credentials, or a
 *  "Sign in to X" button -- the same sign-in the header and search / chat use. */
export const SourceSignInSection: React.FC<Props> = ({ source, url, session, usingSignIn, useOther, onUseOtherChange }) => {
  const label = labelOf(source);
  return (
    <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
      {session ? (
        <>
          <Typography variant="body2">
            Signed in to {label} as <strong>{session.user_id}</strong>
            {usingSignIn ? ' (used for this ingest)' : ''}
          </Typography>
          <Button size="small" onClick={() => { signOut(session); }}>Sign out</Button>
          <FormControlLabel
            control={<Checkbox size="small" checked={useOther} onChange={(e) => onUseOtherChange(e.target.checked)} />}
            // an Alfresco ticket expires, so Auto Sync needs other credentials; a Nuxeo token does not
            label={source === 'alfresco' ? 'Use other credentials (e.g. for Auto Sync)' : 'Use other credentials'}
          />
        </>
      ) : (
        <>
          <Button
            variant="outlined" size="small" disabled={!url.trim()}
            onClick={() => openSignIn({ source, url, methods: ['basic'], documents: null }, 'ingest')}
          >
            Sign in to {label}
          </Button>
          <Typography variant="body2" color="text.secondary">or enter credentials below</Typography>
        </>
      )}
    </Box>
  );
};
