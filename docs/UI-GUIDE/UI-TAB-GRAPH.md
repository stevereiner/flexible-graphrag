# Tab 5 — Graph

Shows the entities and relationships extracted from documents into the property graph
(`PG_GRAPH_DB`), as an interactive graph. In the React, Vue and Angular UIs, the desktop app, and
KG Spaces (v0.10.0+).

## Opening a graph

Use **View graph** on another tab; the Graph tab then loads the graph for those documents:

- **Processing tab:** on the success message of an ingest, and on each completed ingest in the Jobs list:
  the documents that ingest wrote.
- **Hybrid Search tab:** above the search results (the documents they came from), and **View graph of
  sources** for an AI query answer.
- **AI Chat tab:** **View graph of sources** for an answer.
- **KG Spaces:** **View graph** for a document or folder.

The documents need a property graph: `ENABLE_KNOWLEDGE_GRAPH=true`, a `PG_GRAPH_DB`, and **Graph** ticked
for the ingest (Processing tab, or `enabled_graph` / `DEFAULT_ENABLED_GRAPH`). RDF graphs aren't shown yet.

Only documents the asker may read are included: with sign-in, documents from a source you aren't signed in to
are left out, and a notice says which sources.

## The view

- The toolbar shows what the graph is for, and its counts: nodes (entities and chunks), relationships, the
  graph store, and the number of documents.
- **Layout:** Force, Hierarchical or Concentric.
- **Zoom in**, **Zoom out**, **Fit to screen**, **Reload**, **Save as PNG**, and **Show / Hide side panel**.
- Entity types have their own colours.
- **Double-click a node** to add its neighbours from the same documents. A large graph is shown in part
  first, with a notice; expand it this way.

The side panel:

- **Details:** the selected node (an entity's name and type and its properties, or a chunk's text and its
  document) or relationship.
- **Nodes:** the entity types, each with a checkbox to show or hide it (**All** / **None**), and **Chunks**
  to show the text chunks the entities came from.
- **Relationships:** the relationship types, each with a checkbox (**All** / **None**).

## API

`GET /api/graph/capabilities`, `POST /api/graph/subgraph` (the graph for `processing_id` or `doc_ids`), and
`POST /api/graph/neighbors` (a node's neighbours). See [REST API](../DEVELOPER/REST-API.md#graph). The view
itself is the npm package `@flexible-graphrag/graph-view` (Cytoscape.js), shared by the three UIs and KG Spaces.
