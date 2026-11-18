import React, { useEffect, useRef, useState } from 'react';
import { Alert, Box, Button, CircularProgress, Typography } from '@mui/material';
import { invoke } from './tauri';

/** desktop/src-tauri/src/backend.rs `backend_status` */
interface BackendStatus {
  state: 'starting' | 'ready' | 'external' | 'failed';
  message?: string | null;
  log_path?: string | null;
}

interface BackendGateProps {
  /** Runs once when the backend answers (before the app renders). */
  onReady?: () => void;
  children: React.ReactNode;
}

/**
 * Desktop app: the app starts its own backend, which takes a while (first start: a minute or
 * more). Show that here and render the app only once the backend answers, so the app's first
 * requests don't fail.
 */
export const BackendGate: React.FC<BackendGateProps> = ({ onReady, children }) => {
  const [status, setStatus] = useState<BackendStatus>({ state: 'starting' });
  const [open, setOpen] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const readyRan = useRef(false);

  useEffect(() => {
    if (open) return;
    let stop = false;
    const started = Date.now();
    const poll = async () => {
      while (!stop) {
        try {
          const s = await invoke<BackendStatus>('backend_status');
          setStatus(s);
          if (s.state === 'ready' || s.state === 'external') {
            setOpen(true);
            return;
          }
          if (s.state === 'failed') return;
        } catch (e) {
          setStatus({ state: 'failed', message: `backend_status: ${e}` });
          return;
        }
        setSeconds(Math.round((Date.now() - started) / 1000));
        await new Promise((r) => setTimeout(r, 1000));
      }
    };
    poll();
    return () => { stop = true; };
  }, [open]);

  useEffect(() => {
    if (open && !readyRan.current) {
      readyRan.current = true;
      onReady?.();
    }
  }, [open, onReady]);

  if (open) return <>{children}</>;

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', p: 4 }}>
      {status.state === 'failed' ? (
        <Box sx={{ maxWidth: 900, width: '100%' }}>
          <Alert severity="error" sx={{ mb: 2 }}>
            <Typography variant="subtitle1" sx={{ mb: 1 }}>No Flexible GraphRAG backend to use.</Typography>
            <Typography component="pre" variant="body2"
              sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontFamily: 'monospace', m: 0 }}>
              {status.message}
            </Typography>
            {status.log_path && (
              <Typography variant="body2" sx={{ mt: 1 }}>Log: {status.log_path}</Typography>
            )}
          </Alert>
          <Button variant="outlined" onClick={() => setOpen(true)}>Open the app anyway</Button>
        </Box>
      ) : (
        <Box sx={{ textAlign: 'center' }}>
          <CircularProgress sx={{ mb: 2 }} />
          <Typography variant="h6">Starting the Flexible GraphRAG backend… {seconds > 0 ? `${seconds} s` : ''}</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            The first start can take a minute or more.
          </Typography>
          {status.log_path && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Log: {status.log_path}
            </Typography>
          )}
        </Box>
      )}
    </Box>
  );
};
