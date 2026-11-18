# Desktop App (Early Version)

An early version of a desktop app: a [Tauri 2](https://tauri.app) (Rust) shell around the React, Vue or
Angular UI, with the same 5 tabs (Sources, Processing, Hybrid Search, AI Chat, Graph). It adds what a
browser page can't do:

- **Local Files and Folders** source on the Sources tab: browse the local disk and ingest files and
  folders by path, kept in sync with Auto Sync (a folder is watched and rescanned with its subfolders);
- open the local files that search results and AI answers name, with their default app, or show them
  in their folder (only files inside the folders added in the app, never programs or scripts);
- run its own backend, or use one already running;
- a tray icon showing the backend's state.

All the other data sources work as in the web UIs, including **Browse...** in the repository and cloud
source forms (see [Sources tab](../UI-GUIDE/UI-TAB-SOURCES.md#browse)). Web links, such as a result's
Alfresco Share or Nuxeo Web UI page, open in your default browser.

This is an early version: there are no published installers yet. Build and run it from a source checkout,
as described in the [desktop app README](https://github.com/stevereiner/flexible-graphrag/blob/main/flexible-graphrag-ui/desktop/README.md).

## Prerequisites

- Rust, installed with [rustup](https://rustup.rs), plus each system's build tools and webview (Tauri's
  [prerequisites](https://v2.tauri.app/start/prerequisites/) page has the full list):

    | System | Build tools | Webview |
    | --- | --- | --- |
    | Windows | rustup's `stable-x86_64-pc-windows-msvc` toolchain; the MSVC C++ build tools (Visual Studio Build Tools, "Desktop development with C++") | WebView2 (Windows 10 / 11 have it) |
    | macOS | Xcode, or just its command line tools: `xcode-select --install` | WKWebView (part of macOS) |
    | Linux (Debian / Ubuntu) | `sudo apt install build-essential curl wget file libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev` | WebKitGTK: `sudo apt install libwebkit2gtk-4.1-dev` |

    On macOS and Linux, install Rust with
    `curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh`. For other Linux distributions, see Tauri's
    prerequisites page.
- Node.js; `npm install` in `flexible-graphrag-ui/desktop` and in the UI's folder
  (`frontend-react`, `frontend-vue` or `frontend-angular`).
- A backend: a source checkout set up as usual (a venv with flexible-graphrag installed with `uv pip`,
  and `flexible-graphrag/.env`), a folder with flexible-graphrag installed from PyPI, or a backend run
  elsewhere (see [Which backend](#which-backend)).
- The backend's stores running: the Docker stores, or none with the
  [Docker-Free Setup](DOCKER-FREE-SETUP.md) (embedded stores and SQLite).

## Run

From `flexible-graphrag-ui/desktop`:

| UI | Run (development) | Build (installers) |
| --- | --- | --- |
| React | `npm run dev` or `npm run dev:react` | `npm run build` or `npm run build:react` |
| Vue | `npm run dev:vue` | `npm run build:vue` |
| Angular | `npm run dev:angular` | `npm run build:angular` |

`npm run dev` starts the UI's dev server, opens the window and starts the backend. A startup screen shows
until the backend answers. `npm run build` puts the installers for the system it runs on under
`src-tauri/target/release/bundle/`: `.msi` and `.exe` (NSIS) on Windows, `.app` and `.dmg` on macOS, `.deb`,
`.rpm` and `.AppImage` on Linux. Build on each system for its own installers. The three UIs install as the
same app (one replaces another) and share its settings and API token.

On Linux the tray icon needs AppIndicator support (Ubuntu's desktop has it; on plain GNOME, the
AppIndicator extension). On macOS it is in the menu bar.

## Which backend

The app picks the first of these:

1. **A backend set in the app's settings** (another machine, a server, Docker). No Python is needed on
   this machine and the app starts nothing. In the tray menu, **Edit app settings (desktop.json)** opens
   the settings file (making it first if needed). Quit and reopen the app after editing:

    ```json
    { "backend_url": "https://graphrag.example.com", "api_token": "<that backend's API_TOKEN, if it has one>" }
    ```

    The environment variables `FLEXIBLE_GRAPHRAG_URL` and `FLEXIBLE_GRAPHRAG_API_TOKEN` take precedence over
    the file. That backend needs the app in its `CORS_ORIGINS`: `http://tauri.localhost` on Windows,
    `tauri://localhost` on macOS / Linux (see [API Token and CORS](../CONFIGURATION/API-TOKEN-CORS.md)).
    Local Files and Folders don't work with a backend on another machine yet: it can't read this machine's disk.

2. **A backend already answering on `127.0.0.1:8000`** (one you started yourself): used as is. It needs no
   `API_TOKEN`. The app can't add folders to it at runtime: list them in its `INGEST_ALLOWED_PATHS` (when
   you pick a folder outside them, the app shows the `INGEST_ALLOWED_PATHS=[...]` line to put in its `.env`),
   or stop it and let the app start its own.

3. **Its own backend**, started on `127.0.0.1` only, in the backend folder
   (`FLEXIBLE_GRAPHRAG_BACKEND_DIR`; default: the checkout's `flexible-graphrag/` for an app built there,
   else the app's data folder):
    - a source checkout (the folder has `start.py`): the venv's Python runs `start.py`;
    - an install from PyPI: the venv's `flexible-graphrag` command, run in the folder, which then holds its
      `.env`, `flows/`, `schemas/` and `uploads/`. To make one:

        ```
        cd C:\flexible-graphrag-desktop
        uv venv venv-3.14 --python 3.14
        uv pip install --python venv-3.14 flexible-graphrag
        ```

    A folder without a `.env` gets one from `env-sample.txt` first, and an install folder also gets the
    sample documents in `sample-docs/`. The app gives this backend a per-install `API_TOKEN` and limits its
    `CORS_ORIGINS` to the app, overriding the same settings in `.env`; with it, folders you add in the app
    are allowed for ingest right away. The backend is stopped when the app quits.

| Variable | Default |
| --- | --- |
| `FLEXIBLE_GRAPHRAG_BACKEND_DIR` | the checkout's `flexible-graphrag/` (an app built there), else the app's data folder (see [App folders](#app-folders)) |
| `FLEXIBLE_GRAPHRAG_PYTHON` | the first of `.venv`, `venv`, `venv-3.14`, `venv-3.13` in the backend folder or the one above it |
| `FLEXIBLE_GRAPHRAG_PORT` | `8000` |

## Tray icon

Left click opens the window. The menu has:

- **Open**, and the backend's state;
- **Show backend log** and **Show backend settings**: the backend's log file and its `.env`, for any backend
  on this machine (greyed out for one on another machine);
- **Edit app settings (desktop.json)**;
- **Restart backend** (after editing the backend's `.env`);
- **Quit**, which also stops the app's own backend.

With the app's own backend, closing the window keeps the backend running in the tray, so auto sync keeps
watching your folders. With a backend the app didn't start, closing the window quits the app.

The app's backend writes its output to `backend.log` in the app's log folder.

## App folders

The app's identifier is `com.integratedsemantics.flexiblegraphrag`:

| Folder | Windows | macOS | Linux |
| --- | --- | --- | --- |
| Settings (`desktop.json`, `api-token`) | `%APPDATA%\com.integratedsemantics.flexiblegraphrag` | `~/Library/Application Support/com.integratedsemantics.flexiblegraphrag` | `~/.config/com.integratedsemantics.flexiblegraphrag` |
| Data (default backend folder) | `%APPDATA%\com.integratedsemantics.flexiblegraphrag` | `~/Library/Application Support/com.integratedsemantics.flexiblegraphrag` | `~/.local/share/com.integratedsemantics.flexiblegraphrag` |
| Logs (`backend.log`) | `%LOCALAPPDATA%\com.integratedsemantics.flexiblegraphrag\logs` | `~/Library/Logs/com.integratedsemantics.flexiblegraphrag` | `~/.local/share/com.integratedsemantics.flexiblegraphrag/logs` |

## The local file browser

Top folders: Home, **Flexible GraphRAG** (the install folder, or the repo root of a checkout), then the
drives (Windows) or `/`. It opens in the folder you were last in; the first time, in `sample-docs/` when
there is one. Select files and folders (Ctrl / Shift for several), or add the folder you are in.

## Not yet

- Published installers.
- Local Files and Folders with a backend on another machine.
- Starting the Docker stores from the app.
