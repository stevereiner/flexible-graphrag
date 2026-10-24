# @flexible-graphrag/angular-ui

Angular components for [Flexible GraphRAG](https://github.com/stevereiner/flexible-graphrag):
the four tabs of its UI — **Sources**, **Processing**, **Hybrid Search** and **AI Chat** — plus
the fifteen data-source forms behind the Sources tab, packaged for embedding in another
Angular application.

Flexible GraphRAG is an open source AI context platform: document processing (Docling,
LlamaParse or LiteParse), knowledge-graph auto-building, ontologies, GraphRAG and RAG, hybrid
search (fulltext, vector, property graph, RDF/SPARQL), AI query and AI chat. These components
are a front end for its REST API; a running Flexible GraphRAG backend is required. See the
[documentation](https://stevereiner.github.io/flexible-graphrag/).

Used by the standalone Flexible GraphRAG Angular app, by
[KG Spaces for Alfresco Content App](https://github.com/stevereiner/kg-spaces-aca), an
extension that adds these tabs to ACA 8.0, and by KG Spaces for Nuxeo, an app opened from a
Nuxeo Web UI add-on.

## Requirements

- Angular 20.3+ and Angular Material / CDK 20.2+ (peer dependencies)
- `HttpClient` provided by the host application — the library deliberately does not provide
  it, so a host keeps its own interceptors (authentication, for example)
- A reachable Flexible GraphRAG backend, by default at `/api` (proxy it in development); use a
  backend of the same version. Library 0.9.0 reads the backend's `GET /api/ui-defaults` (where
  the Deep, Graph and RDF checkboxes start); an older backend answers 404 there and the library
  falls back to its own defaults

## Install

```bash
npm install @flexible-graphrag/angular-ui
```

## Use

Import the module once with your configuration:

```ts
import { provideHttpClient } from '@angular/common/http';
import { FlexibleGraphragUiModule } from '@flexible-graphrag/angular-ui';

@NgModule({
  imports: [
    FlexibleGraphragUiModule.forRoot({
      apiUrl: '/api',
      alfrescoBaseUrl: 'http://localhost:8080',
    }),
  ],
  providers: [provideHttpClient()],
})
export class AppModule {}
```

A standalone host can import `FlexibleGraphragUiModule` in its component's `imports` and
provide the configuration through the `FLEXIBLE_GRAPHRAG_CONFIG` injection token — for example
from a factory that reads it at runtime, as the KG Spaces extension does from ACA's
`app.config.json`.

Then place the tabs, e.g. in a Material tab group:

```html
<app-sources-tab
  (sourcesConfigured)="onSourcesConfigured($event)"
  (configureProcessing)="selectedTab = 1">
</app-sources-tab>

<app-processing-tab
  [hasConfiguredSources]="hasConfiguredSources"
  [configuredDataSource]="configuredDataSource"
  [configuredFiles]="configuredFiles"
  [configuredAlfrescoConfig]="configuredAlfrescoConfig"
  ...>
</app-processing-tab>

<app-search-tab></app-search-tab>
<app-chat-tab></app-chat-tab>
```

The Sources tab emits the chosen source's configuration; the host passes it to the Processing
tab's `configured*` inputs. For complete wiring, see the KG Spaces page component, which also
supplies a repository selection (`nodeDetails`) and an Alfresco login ticket.

## Title bar and dark / light theme

Since 0.9.0 the library also has the pieces of an app's header:

- `<app-title-bar>`: icon and title, anything projected after the title (a how-to line), the
  host repository's user, the sign-in pill for the other sources and a Dark / Light switch.
  Inputs: `title` (default `Flexible GraphRAG`), `icon` (a Material icon name), `hostSource`
  (default `alfresco`) / `hostUser` / `hostUrl` (nothing is shown without `hostUser`), `signIn`
  and `themeSwitch` (both default `true`). The standalone Angular app and KG Spaces for Nuxeo
  use it.
- `<app-host-identity>`: who the user is in the host's own repository, e.g. "Alfresco · admin"
  or "Nuxeo · Administrator". Read only: the host's session is the sign-in there, so there is no
  sign-out or server switch. Inputs `source`, `user`, `url` (for the tooltip) and `light` (for a
  light background instead of a coloured toolbar). A host with its own header (KG Spaces for ACA)
  places it, and `<app-source-sign-in>`, in that header instead of using the title bar.
- `FlexibleGraphragThemeService`: dark or light mode as a `dark-theme` / `light-theme` class on
  `<body>`, kept per browser in localStorage (key `angular-theme-mode`); before the user picks
  one, the browser's colour scheme decides. `toggle()`, `setDark()`, `dark` and `darkChanges`.
  The title bar's switch uses it. A host with a theme of its own (ACA) does not need it.
- `styles/fg-theme.scss`: the global rules for those body classes (Material's overlays render
  under `<body>`, so the components' own styles cannot reach them). Add it to `angular.json`
  `"styles"`, after the Material theme:

  ```json
  "styles": [
    "src/styles.scss",
    "node_modules/@flexible-graphrag/angular-ui/styles/fg-theme.scss"
  ]
  ```

  It also styles a main tab group given the class `full-width-tabs`.

```html
<app-title-bar title="KG Spaces" icon="hub" hostSource="nuxeo" [hostUser]="user" [hostUrl]="nuxeoUrl">
</app-title-bar>
```

## Configuration

| Option | Default | Purpose |
| --- | --- | --- |
| `apiUrl` | `/api` | Base URL of the Flexible GraphRAG REST API |
| `defaultFolderPath` | `/Shared/GraphRAG` | Folder pre-filled in the CMIS and Alfresco source forms |
| `alfrescoBaseUrl` | `http://localhost:8080` | Where the **backend** reaches Alfresco (server to server) |
| `cmisBaseUrl` | `http://localhost:8080` | CMIS server, for the CMIS source form |
| `nuxeoBaseUrl` / `nuxeoPath` | `http://localhost:8081/nuxeo` / `/default-domain/workspaces/GraphRAG` | Nuxeo source form defaults |
| `enabledSources` | all | Data sources offered on the Sources tab, in picker order — e.g. leave out `alfresco` when the host already is Alfresco |
| `agentIconUrl` | `assets/agent.png` | AI-chat avatar; point it at an asset your host actually serves |
| `noSourcesMessage` / `goToSourcesLabel` | "Please go to the Sources tab…" / `← Go to Sources` | Processing tab text and button when no data source is configured |
| `chatWelcomeTitle` / `chatWelcomeLines` | Flexible GraphRAG welcome | AI Chat welcome heading and the lines under it |
| `showChatScope` | `false` | Show AI Chat's *Asking about: …* bar even with no scope |
| `runInBackground` | `false` | Where the Processing tab's **Run in background** starts (0.9.0). A host the user leaves while a job runs (KG Spaces) turns it on, so jobs carry on and are followed on the Jobs sub-tab |
| `requestHeaders` | none | Function returning extra HTTP headers for search / chat questions, per request; KG Spaces for ACA sends ACA's Alfresco ticket (`X-Alfresco-Ticket`) |
| `hostSourceAuth` | none | Function returning the host's own identity on one repository, `{ source, url, auth }` (e.g. `nuxeo`, the server, `{ auth_method: 'token', token }`), or `null` while there is none (0.9.0). Called per question and added to its `source_auth`; that server then needs no sign-in and its source chip is not greyed. KG Spaces for Nuxeo passes the Web UI user's Nuxeo token |
| `currentUser` | none | Function returning who is using the app, or `null` (0.9.0). Sent as `owner` on the Processing tab's ingests; its Jobs sub-tab then lists and clears only that user's jobs, plus the auto-sync runs everyone sees (a view filter, not access control). KG Spaces passes the ACA or Web UI user |
| `sourceSignIn` | `true` | The library's repository sign-ins (sign-in pill, a sign-in before a question, the forms' sign-in rows) |
| `searchSignIn` | on, except in a host whose `requestHeaders` supply an Alfresco ticket | The sign-ins also apply to search / AI chat questions; KG Spaces for ACA sets it `true` |
| `sourcePicker` | `true` | Source chips on Search and AI Chat ("All sources" plus one per source with documents in the stores); refreshed when a Processing run finishes (0.9.0) |
| `openDocument` / `canOpenDocument` | none | Open a result's source document in the host's own viewer (return `true` when handled; else its `open_url` opens in a new tab) |

Data source ids for `enabledSources`: `upload`, `alfresco`, `nuxeo`, `cmis`, `web`,
`wikipedia`, `youtube`, `google_drive`, `onedrive`, `s3`, `azure_blob`, `gcs`, `box`,
`sharepoint`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
