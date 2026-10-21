import React, { useCallback, useEffect, useState } from 'react';
import { Box, Chip, Tooltip, Typography } from '@mui/material';
import {
  AvailableSource, Requirements, getAvailableSources, labelOf, getPickedSources, getRequirements, onAuthChange,
  openSignIn, setPickedSources, signInFor, sourceKey, sourceNeedsSignIn,
} from './sourceAuth';
import { SOURCE_COLORS } from './SourceSignIn';

/**
 * Which sources a search / AI chat question covers (like Angel's content-lake UI): "All sources"
 * plus one chip per source with documents in the stores (one per server when a type has several).
 * Several can be picked. A repository (Alfresco, Nuxeo, CMIS) needs a sign-in to that server
 * first: its chip is greyed and clicking it opens the sign-in. The choice is shared by Search and
 * AI Chat and sent as the request's `sources` (sourceAuth's axios interceptor). Hidden when the
 * backend cannot tell sources apart (no incremental registry) or holds only one source.
 */
export const SourcePicker: React.FC = () => {
  const [sources, setSources] = useState<AvailableSource[]>([]);
  const [req, setReq] = useState<Requirements>({ required: false, providers: [] });
  const [picked, setPicked] = useState<string[]>(getPickedSources());

  const refresh = useCallback(async (force = false) => {
    const [list, r] = await Promise.all([getAvailableSources(force), getRequirements(force)]);
    setSources(list);
    setReq(r);
    // drop picks that are gone from the stores or now need a sign-in (e.g. after signing out)
    const usable = new Set(list.filter((s) => !sourceNeedsSignIn(s, r)).map(sourceKey));
    const kept = getPickedSources().filter((k) => usable.has(k));
    if (kept.length !== getPickedSources().length) setPickedSources(kept);
    setPicked(kept);
  }, []);

  useEffect(() => { refresh(true); }, [refresh]);
  useEffect(() => onAuthChange(() => { refresh(); }), [refresh]);

  if (sources.length < 2) return null;

  const toggle = (key: string) => {
    const next = picked.includes(key) ? picked.filter((k) => k !== key) : [...picked, key];
    setPickedSources(next);
    setPicked(next);
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, mb: 2 }}>
      <Typography variant="body2" sx={{ opacity: 0.7, mr: 0.5 }}>Sources:</Typography>
      <Chip
        label="All sources" size="small"
        color={picked.length ? 'default' : 'primary'} variant={picked.length ? 'outlined' : 'filled'}
        onClick={() => { setPickedSources([]); setPicked([]); }}
      />
      {sources.map((s) => {
        const key = sourceKey(s);
        const locked = sourceNeedsSignIn(s, req);
        const on = picked.includes(key);
        const several = sources.filter((x) => x.source === s.source).length > 1;
        const label = several && s.url ? `${s.label} (${s.url.replace(/^https?:\/\//, '')})` : s.label;
        const color = SOURCE_COLORS[s.source];
        return (
          <Tooltip key={key} title={locked
            ? `Sign in to ${labelOf(signInFor(s).source)} first`
            : `${s.label} only (${s.documents} document${s.documents === 1 ? '' : 's'})${s.url ? ` — ${s.url}` : ''}`}>
            <Chip
              size="small" label={label}
              variant={on ? 'filled' : 'outlined'}
              color={on && !color ? 'primary' : 'default'}
              onClick={() => (locked
                ? openSignIn({ ...signInFor(s), methods: ['basic'], documents: s.documents }, 'ask')
                : toggle(key))}
              sx={{
                opacity: locked ? 0.5 : 1,
                ...(on && color ? { bgcolor: color, color: '#fff' } : {}),
                ...(!on && color ? { borderColor: color } : {}),
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
};
