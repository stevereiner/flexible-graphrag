# Flexible GraphRAG desktop app (Early Version)

A [Tauri 2](https://tauri.app) shell around the React UI (`../frontend-react`, built in its `desktop` mode), or the
Vue or Angular UI (`../frontend-vue`, `../frontend-angular`; see [Vue or Angular UI](#vue-or-angular-ui)). It adds
what a browser page can't do: browse the local disk, ingest local files and folders by path (the
**Local Files and Folders** source on the Sources tab, kept in sync with Auto Sync), open the local files that search
results and answers name, and run its own backend.

- `src-tauri/src/fs_browse.rs`: `fs_roots` (home folder, the Flexible GraphRAG folder, drives), `fs_list_dir` (one
  folder level) and `fs_start` (the first-time start folder, `sample-docs/`), read-only.
- `src-tauri/src/open_file.rs`: `open_local_file`, opens a source document with its default app or shows it in its
  folder (only files inside the folders added in the app, never programs or scripts).
- `src-tauri/src/links.rs`: web links (a document's Alfresco Share / Nuxeo Web UI page, any other http(s)
  link) open in the default browser, where you are signed in; the backend's sign-in popup (Microsoft 365, Box)
  stays an app window, since the UI watches it. The main window is made here (`"create": false` in the
  `tauri*.conf.json` files) so it gets these handlers.
- `src-tauri/src/backend.rs`: starts, restarts and stops the backend, `backend_info` (URL + API token for the
  UI), `backend_status`.
- `src-tauri/src/tray.rs`: the tray icon. With the app's own backend, closing the window keeps the backend
  running there (auto sync keeps watching your folders). Left click opens the window. The menu has Open, the
  backend's state, Show backend log and Show backend settings (its log file and its `.env`, for any backend on this
  machine, even one the app didn't start; greyed out for a backend on another machine), Edit app settings (the
  app's `desktop.json`), Restart backend, and Quit, which stops the backend. With a backend the app didn't start,
  closing the window quits the app (that backend keeps running on its own).
- The UI side: `frontend-react/src/desktop/` (Tauri bridge, startup screen, the folders sent to the backend) and
  `frontend-react/src/browser/` (the file browser, on react-file-manager).
  - Vue: `frontend-vue/src/desktop/` and `src/apiConnection.ts`.
  - Angular: `frontend-angular/src/app/desktop/` (startup screen, token, backend URL). The library adds
    `src/lib/desktop/` and the Local Files and Folders form; the library never imports `@tauri-apps/api`
    itself, so its other hosts (KG Spaces) need nothing new.

Not yet: the Library view of the OpenArch mirror, starting the Docker stores. See `planning/source-browser-plan.md`.

## Prerequisites

- Rust (rustup) and each system's build tools and webview (see Tauri's
  [prerequisites](https://v2.tauri.app/start/prerequisites/)):
  - Windows: rustup's `stable-x86_64-pc-windows-msvc`, the MSVC C++ build tools ("Desktop development with
    C++"); WebView2 (Windows 10 / 11 have it).
  - macOS: Xcode or its command line tools (`xcode-select --install`).
  - Linux (Debian / Ubuntu): `sudo apt install libwebkit2gtk-4.1-dev build-essential curl wget file libxdo-dev
    libssl-dev libayatana-appindicator3-dev librsvg2-dev`.
- Node.js; `npm install` here and in `../frontend-react`.
- The backend set up as usual (a venv with flexible-graphrag installed with `uv pip`, `flexible-graphrag/.env`), or
  a folder with it installed from PyPI (see [Which backend](#which-backend)); its stores running (Docker).

## Run (development)

From here:

```powershell
npm run dev
```

This starts the React dev server (port 5174, as `tauri.conf.json` expects: keep that port free), opens the window
and starts the backend; a startup screen shows until the backend answers. The UI calls the backend the app chose
directly, as a built app does: the dev server's `/api` proxy (and `VITE_API_PROXY_TARGET`) is not used, so a
backend you run yourself with `CORS_ORIGINS` set needs the dev server's origin in it too
(`http://localhost:5174`; Vue `http://localhost:3000`, Angular `http://localhost:4200`). Unset, it takes any.

## Vue or Angular UI

The same app (Rust side, backend, tray, API token) with another UI, through a config overlay:

| UI | Run | Build | Dev server port |
| --- | --- | --- | --- |
| React | `npm run dev` (or `dev:react`) | `npm run build` (or `build:react`) | 5174 |
| Vue | `npm run dev:vue` | `npm run build:vue` | 3000 |
| Angular | `npm run dev:angular` | `npm run build:angular` | 4200 |

`src-tauri/tauri.vue.conf.json` and `src-tauri/tauri.angular.conf.json` change only the dev server, the
frontend build and the window title. Run `npm install` in that UI's folder first. All three share the app
identifier, so they share the per-install API token and the backend the app starts; the builds install as the
same app (one replaces another).

## Which backend

1. A backend run elsewhere (another machine, a server, Docker): no Python is needed on this machine and the app
   starts nothing. Set it in the app's `desktop.json`: **Edit app settings (desktop.json)** in the tray menu
   opens it (making it first if needed), so you don't have to find its folder
   (`%APPDATA%\com.integratedsemantics.flexiblegraphrag` on Windows, the Roaming one; the Local one of the same
   name holds only the app's logs). The app reads it when it starts, so quit and reopen the app after editing:

   ```json
   { "backend_url": "https://graphrag.example.com", "api_token": "<that backend's API_TOKEN, if it has one>" }
   ```

   or with `FLEXIBLE_GRAPHRAG_URL` and `FLEXIBLE_GRAPHRAG_API_TOKEN`, which take precedence. That backend needs
   the app in its `CORS_ORIGINS` (see [Build](#build)). When it runs on this machine (`localhost`), **Show backend
   log** and **Show backend settings** in the tray menu show its log and `.env` (the backend tells the app where they
   are, through `/api/backend-files`, which answers only callers on this machine). Local Files and Folders don't work this way yet: the backend can't read this machine's disk (see
   `planning/source-browser-plan.md`, phase 2).
2. Else, a backend already answering on `127.0.0.1:8000` (one you started yourself): used as is. Nothing about it
   needs changing for the app: no `API_TOKEN` (one would also lock out the browser UI and the MCP server unless
   they send it too). The app can't add folders to it at runtime; list them in its `INGEST_ALLOWED_PATHS`, or stop
   it and let the app start its own. (If you gave it an `API_TOKEN` for your own reasons, set
   `FLEXIBLE_GRAPHRAG_API_TOKEN` to the same value for the app.)
3. Else the app starts one in the backend folder, on `127.0.0.1` only. What it runs depends on the folder:
   - A source checkout (the folder has `start.py`): `<venv python> start.py`.
   - An install from PyPI: the venv's `flexible-graphrag` command, run in the folder, so the folder holds its
     `.env`, `flows/`, `schemas/` and `uploads/`. To make one:

     ```powershell
     cd C:\newdev3\flexible-test
     uv venv venv-3.14 --python 3.14
     uv pip install --python venv-3.14 flexible-graphrag
     ```

   A folder without a `.env` gets one from `env-sample.txt` first (the checkout's, or the one the package installs
   in `site-packages`). An install folder also gets the app's sample documents in `sample-docs/` then; delete it
   if you don't want it, it is not added again. **Show backend settings** in the tray menu shows the `.env` in its
   folder; after editing it, use **Restart backend**.

   The backend runs with:
   - `API_TOKEN`: a token made once per install, in the app's config folder (`api-token`;
     `%APPDATA%\com.integratedsemantics.flexiblegraphrag` on Windows).
   - `CORS_ORIGINS`: the app's own pages.

   These override the same settings in `.env`. The backend's output goes to `backend.log` in the app's log folder
   (`%LOCALAPPDATA%\com.integratedsemantics.flexiblegraphrag\logs`); notes from the app (a `.env` it made) come
   first. The backend is stopped when the app exits; on Windows a job object also ends it when the app is killed
   (Ctrl-C on `npm run dev`, Task Manager).

   | Variable | Default |
   | --- | --- |
   | `FLEXIBLE_GRAPHRAG_BACKEND_DIR` | this checkout's `flexible-graphrag/` (an app built here), else the app's data folder (`%APPDATA%\com.integratedsemantics.flexiblegraphrag` on Windows) |
   | `FLEXIBLE_GRAPHRAG_PYTHON` | the first of `.venv`, `venv`, `venv-3.14`, `venv-3.13` found in the backend folder or the one above it; for an install, its `flexible-graphrag` command is taken from the same venv |
   | `FLEXIBLE_GRAPHRAG_PORT` | `8000` |

## The local file browser

Top folders: Home, **Flexible GraphRAG** (the install folder, or the repo root of a checkout), then the drives
(Windows) or `/`. It opens in the folder you were last in. The first time, it opens in `sample-docs/` of the
Flexible GraphRAG folder when there is one. The remote sources' browsers remember their last folder too (per source
type, in the UI's local storage).

## Build

```powershell
npm run build
```

Builds `../frontend-react` (`npm run build:desktop` → `dist-desktop`) and the installers under
`src-tauri/target/release/bundle/`. A built app calls the backend directly (no proxy). A backend the app starts
gets the matching `CORS_ORIGINS`. A backend you run yourself needs `CORS_ORIGINS=http://tauri.localhost` (Windows;
`tauri://localhost` on macOS / Linux).

## Icons

`src-tauri/icons/app-icon.png` is a placeholder; `npm run icon` regenerates the icon set from it.
