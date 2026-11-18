import React from 'react';
import ReactDOM from 'react-dom/client';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import App from './App';
import { installSourceAuth } from './auth/sourceAuth';
import { installApiConnection } from './apiConnection';
import { isTauri } from './desktop/tauri';
import { syncLocalRoots } from './desktop/localRoots';
import { BackendGate } from './desktop/BackendGate';

// Alfresco sign-in for search / AI chat (attaches the ticket, asks when the stores need it)
installSourceAuth();

const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#90caf9',
    },
    secondary: {
      main: '#f48fb1',
    },
  },
});

// The desktop app gives the backend back the local folders the user added (it keeps them in
// memory only)
const sendLocalRoots = () => {
  syncLocalRoots().then((r) => { if (!r.ok) console.warn('Local folders not sent to the backend:', r.message); });
};

// Backend URL + API token first (the first requests go out on mount). In the desktop app the
// backend may still be starting: BackendGate waits for it before rendering the app.
installApiConnection().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {isTauri() ? (
          <BackendGate onReady={sendLocalRoots}>
            <App />
          </BackendGate>
        ) : (
          <App />
        )}
      </ThemeProvider>
    </React.StrictMode>
  );
});
