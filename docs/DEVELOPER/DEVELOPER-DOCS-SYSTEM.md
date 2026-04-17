# Documentation System

This site is built with [Zensical](https://zensical.org) (from the creators of Material for MkDocs), using Markdown source files in the `docs/` directory.

---

## Structure

| Path | Purpose |
|---|---|
| `docs/` | All Markdown source pages |
| `zensical.toml` | Site config — nav, theme features, site URL |
| `site/` | Generated static output (git-ignored) |
| `.github/workflows/docs.yml` | Auto-deploys to GitHub Pages on push to `main` |

---

## Local Preview

Run a live-reload dev server on port **8008** (avoids conflicts with the backend on 8000 and other services).

Both flags are required — without `--config-file` it serves the pre-built `site/` folder instead of rebuilding from source:

=== "uv run (active venv)"

    ```bash
    uv run zensical serve --config-file zensical.toml
    ```

=== "direct (zensical on PATH)"

    ```bash
    zensical serve --config-file zensical.toml
    ```

=== "uvx (no install)"

    ```bash
    uvx zensical serve --config-file zensical.toml
    ```

Port 8008 is set via `dev_addr = "localhost:8008"` in `zensical.toml` — no flag needed.

Open **http://localhost:8008** — the site reloads automatically when you edit files in `docs/`.

---

## Build a Static Copy

```bash
zensical build --config-file zensical.toml
```

Output goes to `site/`. Open `site/index.html` in a browser or serve it with any static file server.

---

## Adding or Editing Pages

1. Create or edit a `.md` file in `docs/`
2. Add it to the `nav` in `zensical.toml` under the appropriate section
3. The local dev server picks up changes instantly

### Nav format (`zensical.toml`)

```toml
nav = [
  {"Section" = [
    {"Page Title" = "FILENAME.md"},
    {"Subsection" = [
      {"Child Page" = "SUBDIR/FILENAME.md"}
    ]}
  ]}
]
```

---

## Deployment

Pushing to `main` triggers the GitHub Actions workflow at `.github/workflows/docs.yml`, which builds the site and deploys it to GitHub Pages at:

**https://stevereiner.github.io/flexible-graphrag/**
