"""OpenArch (Hyland's content repository) as a Flexible GraphRAG ingest target and retriever.

Documents are written once per source system under ``/fg-sources/<source type>/<system id>/...`` as
``CinRemote`` files carrying the parsed text (searched through ``sys_fulltext``), with
their chunks and embeddings in a ``SysEmbeddings`` child (OpenArch's kNN index).

python-openarch-api (a dependency) is imported on demand, by the submodules that use it (client,
writer, vector_store), only when OpenArch is in use.
"""
