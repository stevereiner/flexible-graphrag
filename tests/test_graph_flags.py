"""Unit tests for which graphs an ingest builds (graph_flags.GraphFlags): enabled_graph /
enabled_rdf, the older skip_graph, DEFAULT_ENABLED_GRAPH / DEFAULT_ENABLED_RDF, and the gates of
the property graph and RDF steps."""
import asyncio
from types import SimpleNamespace as NS

import pytest

from graph_flags import ALL, NONE, GraphFlags

pytestmark = pytest.mark.unit


def test_resolve_fields_skip_graph_and_defaults():
    assert GraphFlags.resolve() == ALL
    assert GraphFlags.resolve(enabled_rdf=False) == GraphFlags(True, False)
    assert GraphFlags.resolve(enabled_graph=False, enabled_rdf=True) == GraphFlags(False, True)
    assert GraphFlags.resolve(enabled_graph=True, skip_graph=True) == NONE          # older flag: neither
    cfg = NS(default_enabled_graph=True, default_enabled_rdf=False)
    assert GraphFlags.resolve(config=cfg) == GraphFlags(True, False)
    assert GraphFlags.resolve(enabled_rdf=True, config=cfg) == ALL


def test_defaults_from_the_environment(monkeypatch):
    monkeypatch.delenv("DEFAULT_ENABLED_GRAPH", raising=False)
    monkeypatch.setenv("DEFAULT_ENABLED_RDF", "false")
    assert GraphFlags.defaults() == GraphFlags(True, False)
    monkeypatch.setenv("DEFAULT_ENABLED_RDF", "")
    assert GraphFlags.defaults() == ALL


def test_of_combine_and_describe():
    assert GraphFlags.of({"enabled_graph": False}, default=ALL) == GraphFlags(False, True)
    assert GraphFlags.of(NS(enabled_graph=None, enabled_rdf=None, skip_graph=True)) == NONE
    assert GraphFlags.of(True) == NONE and GraphFlags.of(False, default=ALL) == ALL
    assert GraphFlags(True, False) & GraphFlags(False, True) == NONE
    assert GraphFlags(True, False) | GraphFlags(False, True) == ALL
    assert NONE.skip_graph and not GraphFlags(False, True).skip_graph
    assert GraphFlags(False, True).describe() == "with the RDF graph"
    assert {GraphFlags(True, False): 1}[GraphFlags(True, False)] == 1   # usable as a pass key


def _system(pg="neo4j", rdf="graphdb"):
    cfg = NS(enable_knowledge_graph=True, pg_graph_db=pg, rdf_graph_db=rdf,
             default_enabled_graph=True, default_enabled_rdf=True)
    return NS(config=cfg, graph_index=None, graph_intentionally_skipped=False)


def test_graph_step_is_skipped_when_neither_wanted_graph_is_on():
    from ingest.update_pg_graph import update_pg_graph
    system = _system()
    out = asyncio.run(update_pg_graph(system, ["n"], [], None, graphs=NONE))
    assert out == (["n"], False, 0.0, 0.0, 0, 0) and system.graph_intentionally_skipped
    system = _system(rdf="none")   # RDF on but no RDF store, property graph off: nothing to build
    out = asyncio.run(update_pg_graph(system, ["n"], [], None, graphs=GraphFlags(False, True)))
    assert out[1] is False and system.graph_intentionally_skipped


def test_rdf_step_follows_only_its_own_flag():
    from ingest.update_rdf_graph import _should_export_rdf
    cfg = _system().config
    assert _should_export_rdf(cfg, GraphFlags(False, True))
    assert not _should_export_rdf(cfg, GraphFlags(True, False))
    assert not _should_export_rdf(_system(rdf="none").config, ALL)


def test_completion_message_names_only_the_graphs_built():
    from ingest._helpers import generate_completion_message
    cfg = NS(vector_db="qdrant", search_db="elasticsearch", pg_graph_db="neo4j", rdf_graph_db="graphdb",
             enable_knowledge_graph=True, enable_openarch=False, default_enabled_graph=True,
             default_enabled_rdf=True)
    msg = generate_completion_message(cfg, 2, graphs=GraphFlags(False, True))
    assert "rdf" in msg.lower() and "property graph" not in msg.lower()


def test_a_row_flags_its_own_graphs():
    from openarch.scope import row_flags
    assert row_flags("ingest", None, GraphFlags(True, False)) == {"searchVector": True, "pgGraph": True, "rdfGraph": False}
    assert row_flags("ingest_no_graph", None, ALL)["pgGraph"] is False        # the action decides
