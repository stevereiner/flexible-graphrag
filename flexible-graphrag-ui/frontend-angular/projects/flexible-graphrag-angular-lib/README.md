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

Used by the standalone Flexible GraphRAG Angular app and by
[KG Spaces for Alfresco Content App](https://github.com/stevereiner/kg-spaces-aca), an
extension that adds these tabs to ACA 8.0.

## Requirements

- Angular 20.3+ and Angular Material / CDK 20.2+ (peer dependencies)
- `HttpClient` provided by the host application — the library deliberately does not provide
  it, so a host keeps its own interceptors (authentication, for example)
- A reachable Flexible GraphRAG backend, by default at `/api` (proxy it in development)

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

Data source ids for `enabledSources`: `upload`, `alfresco`, `nuxeo`, `cmis`, `web`,
`wikipedia`, `youtube`, `google_drive`, `onedrive`, `s3`, `azure_blob`, `gcs`, `box`,
`sharepoint`.

## License

Apache-2.0 — see [LICENSE](LICENSE).
