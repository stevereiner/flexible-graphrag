"""Which graphs an ingest, a data source or a document builds: the property graph (PG_GRAPH_DB) and
the RDF graph (RDF_GRAPH_DB), each on its own.

The API and the stored records say it with two fields, ``enabled_graph`` and ``enabled_rdf``; when
one is not given, DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF (config) decide. The older
``skip_graph`` is still accepted and means both off. Inside the pipeline the pair travels as one
``GraphFlags`` value; a document's own flags, its data source's and its scope rules' combine with
``&`` (a graph is built only where every one of them allows it).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class GraphFlags:
    graph: bool = True  # property graph (PG_GRAPH_DB)
    rdf: bool = True    # RDF graph (RDF_GRAPH_DB)

    @property
    def none(self) -> bool:
        """Neither graph: search + vector only (what skip_graph used to say)."""
        return not (self.graph or self.rdf)

    @property
    def skip_graph(self) -> bool:
        """The older single flag, for clients and records that still read it: no graph at all."""
        return self.none

    def __and__(self, other: "GraphFlags") -> "GraphFlags":
        return GraphFlags(self.graph and other.graph, self.rdf and other.rdf)

    def __or__(self, other: "GraphFlags") -> "GraphFlags":
        return GraphFlags(self.graph or other.graph, self.rdf or other.rdf)

    def built(self, config: Any) -> "GraphFlags":
        """The graphs an ingest with these flags actually writes: those with a store configured
        (PG_GRAPH_DB / RDF_GRAPH_DB not none) while ENABLE_KNOWLEDGE_GRAPH is on."""
        if config is None:
            return self

        def on(name: str) -> bool:
            value = getattr(config, name, None)
            return str(getattr(value, "value", value) or "none").lower() not in ("none", "")
        kg = bool(getattr(config, "enable_knowledge_graph", True))
        return GraphFlags(self.graph and kg and on("pg_graph_db"), self.rdf and kg and on("rdf_graph_db"))

    def to_dict(self) -> dict:
        return {"enabled_graph": self.graph, "enabled_rdf": self.rdf}

    def describe(self) -> str:
        if self.graph and self.rdf:
            return "with graphs"
        if self.graph:
            return "with the property graph"
        if self.rdf:
            return "with the RDF graph"
        return "search + vector only"

    @classmethod
    def defaults(cls, config: Any = None) -> "GraphFlags":
        """DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF: from ``config`` (Settings) when given, else
        the environment (both on when unset)."""
        if config is not None:
            return cls(bool(getattr(config, "default_enabled_graph", True)),
                       bool(getattr(config, "default_enabled_rdf", True)))
        return cls(_env_bool("DEFAULT_ENABLED_GRAPH"), _env_bool("DEFAULT_ENABLED_RDF"))

    @classmethod
    def resolve(cls, enabled_graph: Optional[bool] = None, enabled_rdf: Optional[bool] = None,
                skip_graph: Optional[bool] = None, default: Optional["GraphFlags"] = None,
                config: Any = None) -> "GraphFlags":
        """The flags a request or record means: skip_graph=True is both off; otherwise each given
        field, and ``default`` (else DEFAULT_ENABLED_GRAPH / _RDF) for one not given."""
        if skip_graph:
            return cls(False, False)
        base = default if default is not None else cls.defaults(config)
        return cls(base.graph if enabled_graph is None else bool(enabled_graph),
                   base.rdf if enabled_rdf is None else bool(enabled_rdf))

    @classmethod
    def of(cls, source: Any, default: Optional["GraphFlags"] = None) -> "GraphFlags":
        """From anything that carries the fields (a request, a config, a dict), or a GraphFlags,
        or a bare bool meaning the older skip_graph."""
        if isinstance(source, GraphFlags):
            return source
        if source is None:
            return default if default is not None else cls.defaults()
        if isinstance(source, bool):
            return cls.resolve(skip_graph=source, default=default)
        get = source.get if isinstance(source, Mapping) else (lambda k: getattr(source, k, None))
        return cls.resolve(get("enabled_graph"), get("enabled_rdf"), get("skip_graph"), default=default)


def _env_bool(name: str) -> bool:
    import os
    value = os.getenv(name)
    return True if value is None or not value.strip() else value.strip().lower() in ("1", "true", "yes", "on")


ALL = GraphFlags(True, True)
NONE = GraphFlags(False, False)
