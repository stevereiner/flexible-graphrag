"""The incremental registry's two stores behave the same: PostgreSQL (``datasource_config`` /
``document_state``) and the OpenArch tree (openarch/registry.py, INCREMENTAL_STATE_STORE=openarch).

Each scenario runs against both, on scratch locations:

- PostgreSQL: database ``fg_state_store_test`` next to POSTGRES_INCREMENTAL_URL (or the server of
  STATE_STORE_TEST_POSTGRES_URL), emptied first;
- OpenArch: trees ``/fg-test-sources`` and ``/fg-test-datasources`` at OPENARCH_URL (or
  STATE_STORE_TEST_OPENARCH_URL), removed after.

A store that is not reachable is skipped.
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse

import pytest

from incremental_updates.config_manager import ConfigManager, DataSourceConfig
from incremental_updates.removal import StateRow
from incremental_updates.state_manager import DocumentState, StateManager

pytestmark = [pytest.mark.integration, pytest.mark.incremental]

A = "11111111-2222-3333-4444-555555555555"   # an auto sync
B = "66666666-7777-8888-9999-000000000000"   # an ingest-only record
C = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"   # another auto sync
PARAMS = {"url": "http://alfresco-test:8080", "source_id": "test-repo", "path": "/Shared/T"}
T0 = datetime(2026, 10, 15, 10, 0, 0, 123456, tzinfo=timezone.utc)

_TEST_DB = "fg_state_store_test"


def _postgres_url():
    url = os.getenv("STATE_STORE_TEST_POSTGRES_URL") or os.getenv("POSTGRES_INCREMENTAL_URL") \
        or "postgresql://postgres:password@localhost:5433/flexible_graphrag_incremental"
    return urlparse(url)


async def _postgres_managers():
    import asyncpg
    base = _postgres_url()
    admin = await asyncpg.connect(urlunparse(base._replace(path="/postgres")), timeout=5)
    try:
        if not await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", _TEST_DB):
            await admin.execute(f'CREATE DATABASE "{_TEST_DB}"')
    finally:
        await admin.close()
    url = urlunparse(base._replace(path=f"/{_TEST_DB}"))
    cm, sm = ConfigManager(url), StateManager(url)
    await cm.initialize()
    await sm.initialize()
    async with sm.pool.acquire() as conn:
        await sm._ensure_cursor_table(conn)
        await conn.execute("TRUNCATE document_state, datasource_config, msgraph_delta_state")
    return cm, sm


def _openarch_settings():
    return {"url": os.getenv("STATE_STORE_TEST_OPENARCH_URL") or os.getenv("OPENARCH_URL") or "http://localhost:8088",
            "username": os.getenv("OPENARCH_USERNAME", "admin"), "password": os.getenv("OPENARCH_PASSWORD", "password"),
            "repository": os.getenv("OPENARCH_REPOSITORY", "default"),
            "root_path": "/fg-test-sources", "datasources_path": "/fg-test-datasources"}


def _openarch_clean(settings):
    from openarch.client import OpenArchClient
    from openarch.registry import remove_registry
    from openarch.writer import delete_with_chunks
    remove_registry(settings)
    client = OpenArchClient(settings["url"], settings["username"], settings["password"], settings["repository"])
    try:
        for path in (settings["root_path"], settings["datasources_path"]):
            doc = client.get_by_path(path)
            if doc is not None:
                for d in client.query_all(f"SELECT * FROM SysFile WHERE sys_ancestorIds = '{doc['sys_id']}'"):
                    delete_with_chunks(client, d["sys_id"])
                client.delete(doc["sys_id"])
    finally:
        client.close()


async def _openarch_managers():
    pytest.importorskip("python_openarch_api")
    from openarch.registry import OpenArchConfigManager, OpenArchStateManager
    settings = _openarch_settings()
    await asyncio.to_thread(_openarch_clean, settings)
    cm, sm = OpenArchConfigManager(settings), OpenArchStateManager(settings)
    await cm.initialize()
    await sm.initialize()
    return cm, sm


@pytest.fixture(params=["postgres", "openarch"])
def stores(request):
    """(run, config manager, state manager): ``run`` runs a coroutine on the managers' loop."""
    loop = asyncio.new_event_loop()
    try:
        make = _postgres_managers if request.param == "postgres" else _openarch_managers
        cm, sm = loop.run_until_complete(make())
    except Exception as e:  # store not running
        loop.close()
        pytest.skip(f"{request.param} not available: {e}")
    yield loop.run_until_complete, cm, sm
    loop.run_until_complete(cm.close())
    loop.run_until_complete(sm.close())
    if request.param == "openarch":
        _openarch_clean(_openarch_settings())
    loop.close()


def _config(config_id, auto_sync=True, **kw):
    return DataSourceConfig(config_id=config_id, project_id="default", source_type="alfresco",
                            source_name=kw.pop("name", f"ds-{config_id[:4]}"), connection_params=dict(PARAMS),
                            is_active=auto_sync, auto_sync=auto_sync, **kw)


def _state(config_id, node, *, graph=True, rdf=None, auto_sync=None, skip_graph=None, ordinal=1, path=None):
    return DocumentState(
        doc_id=f"{config_id}:alfresco://{node}", config_id=config_id,
        source_path=path or f"/Shared/T/{node}.txt", source_id=node, ordinal=ordinal, content_hash=f"h-{node}",
        modified_timestamp=T0, vector_synced_at=T0, search_synced_at=T0, graph_synced_at=T0 if graph else None,
        rdf_synced_at=T0 if (graph if rdf is None else rdf) else None,
        auto_sync=auto_sync, skip_graph=skip_graph)


def _id(config_id, node):
    return f"{config_id}:alfresco://{node}"


# ── data sources ─────────────────────────────────────────────────────────────────────────────

def test_datasource_lifecycle(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A, refresh_interval_seconds=300)))
    run(cm.register_ingest_only(_config(B, auto_sync=False, skip_graph=True)))
    a = run(cm.get_config(A))
    assert (a.source_type, a.connection_params, a.refresh_interval_seconds) == ("alfresco", PARAMS, 300)
    assert a.is_active and a.auto_sync and a.sync_status == "idle"
    assert [c.config_id for c in run(cm.get_all_active_configs())] == [A]
    assert sorted(c.config_id for c in run(cm.get_ingest_status_configs())) == sorted([A, B])
    assert run(cm.get_auto_sync(A)) is True and run(cm.get_auto_sync(B)) is False
    assert run(cm.get_auto_sync(C)) is None

    run(cm.update_sync_status(A, "idle", ordinal=42))
    run(cm.update_config(A, is_active=False, refresh_interval_seconds=600))
    a = run(cm.get_config(A))
    assert (a.last_sync_ordinal, a.is_active, a.refresh_interval_seconds) == (42, False, 600)
    assert a.last_sync_completed_at is not None
    assert [c.config_id for c in run(cm.get_paused_configs())] == [A]   # not the ingest-only B
    run(cm.update_sync_status(A, "error", error="boom"))
    assert run(cm.get_config(A)).last_error == "boom"

    # An ingest-only repeat leaves an auto sync alone, except that building the graph again
    # makes it a graph datasource
    run(cm.update_config(A, skip_graph=True))
    run(cm.register_ingest_only(_config(A, auto_sync=False, name="other", skip_graph=False)))
    a = run(cm.get_config(A))
    assert (a.auto_sync, a.source_name, a.skip_graph) == (True, f"ds-{A[:4]}", False)
    # ... and updates an ingest-only record
    run(cm.register_ingest_only(_config(B, auto_sync=False, name="renamed", skip_graph=False)))
    assert run(cm.get_config(B)).source_name == "renamed"

    # Re-registering a sync keeps its progress
    run(cm.create_config(_config(A, name="again")))
    a = run(cm.get_config(A))
    assert (a.source_name, a.last_sync_ordinal, a.is_active) == ("again", 42, True)

    run(cm.delete_config(B))
    assert run(cm.get_config(B)) is None


def test_sync_cursor(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A)))
    assert run(sm.load_sync_cursor(A)) is None
    run(sm.save_sync_cursor(A, "https://graph/delta?token=1"))
    run(sm.save_sync_cursor(A, "https://graph/delta?token=2"))
    assert run(sm.load_sync_cursor(A)) == "https://graph/delta?token=2"


# ── document state ───────────────────────────────────────────────────────────────────────────

def test_document_state_roundtrip_and_updates(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A)))
    run(sm.save_state(_state(A, "n1")))
    s = run(sm.get_state(_id(A, "n1")))
    assert (s.config_id, s.source_id, s.source_path, s.ordinal, s.content_hash) == (A, "n1", "/Shared/T/n1.txt", 1, "h-n1")
    assert s.modified_timestamp == T0   # exact: the sync compares it
    assert s.vector_synced_at and s.graph_synced_at
    assert run(sm.get_state_by_source_id(A, "n1")).doc_id == _id(A, "n1")
    assert run(sm.get_state_by_source_id(A, "nope")) is None
    assert not run(sm.sync_off(_id(A, "n1")))

    # A rename keeps the row; auto_sync / skip_graph None keep what it has
    run(sm.set_auto_sync([_id(A, "n1")], False))
    run(sm.save_state(_state(A, "n1", ordinal=2, path="/Shared/T/renamed.txt")))
    s = run(sm.get_state(_id(A, "n1")))
    assert (s.source_path, s.ordinal) == ("/Shared/T/renamed.txt", 2)
    assert run(sm.sync_off(_id(A, "n1")))

    # skip_graph: kept while the graph is not written, cleared by a save that wrote it
    run(sm.save_state(_state(A, "n2", graph=False, skip_graph=True)))
    run(sm.save_state(_state(A, "n2", graph=False, ordinal=2)))
    assert run(sm.doc_skip_graph(_id(A, "n2")))
    assert run(sm.doc_skip_graph(config_id=A, source_id="n2"))
    run(sm.save_state(_state(A, "n2", graph=True, ordinal=3)))
    assert not run(sm.doc_skip_graph(_id(A, "n2")))

    run(sm.clear_targets(_id(A, "n2")))
    s = run(sm.get_state(_id(A, "n2")))
    assert (s.vector_synced_at, s.search_synced_at, s.graph_synced_at) == (None, None, None)
    run(sm.mark_target_synced(_id(A, "n2"), "search"))
    assert run(sm.get_state(_id(A, "n2"))).search_synced_at is not None

    later = T0 + timedelta(minutes=5)
    run(sm._update_ordinal_only(_id(A, "n2"), 9, later))
    run(sm._update_source_path(_id(A, "n2"), "/Shared/T/moved.txt"))
    s = run(sm.get_state(_id(A, "n2")))
    assert (s.ordinal, s.modified_timestamp, s.source_path) == (9, later, "/Shared/T/moved.txt")
    assert run(sm.should_process(_id(A, "n2"), 10, "h-n2")) == (False, "content unchanged (ordinal updated)")
    assert run(sm.should_process(_id(A, "n2"), 11, "other"))[0]
    assert run(sm.should_process(_id(A, "n9"), 1, "x")) == (True, "new document")

    assert sorted(s.doc_id for s in run(sm.get_all_states_for_config(A))) == [_id(A, "n1"), _id(A, "n2")]
    assert sorted(run(sm.doc_ids_for_config(A))) == [_id(A, "n1"), _id(A, "n2")]
    assert run(sm.known_doc_ids([_id(A, "n1"), _id(A, "zz")])) == {_id(A, "n1")}
    stats = run(sm.get_sync_stats(A))
    assert (stats["total_docs"], stats["search_synced"], stats["graph_synced"]) == (2, 2, 1)

    refs = run(sm.registry_rows([_id(A, "n1")]))
    assert refs[_id(A, "n1")]["source_type"] == "alfresco"
    assert refs[_id(A, "n1")]["connection_params"]["url"] == PARAMS["url"]

    run(sm.mark_deleted(_id(A, "n1")))
    assert run(sm.get_state(_id(A, "n1"))) is None
    assert run(sm.doc_ids_for_config(A)) == [_id(A, "n2")]


def test_rows_and_auto_sync(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A)))
    run(cm.create_config(_config(C)))
    for node in ("n1", "n2"):
        run(sm.save_state(_state(A, node)))
    run(sm.save_state(_state(C, "n3", graph=False)))
    rows = {r.doc_id: r for r in run(sm.fetch_rows([A, C]))}
    assert set(rows) == {_id(A, "n1"), _id(A, "n2"), _id(C, "n3")}
    r3 = rows[_id(C, "n3")]
    assert isinstance(r3, StateRow) and r3.synced == {"vector": True, "search": True, "graph": False, "rdf": False}
    assert (r3.config_id, r3.source_id, r3.auto_sync) == (C, "n3", True)
    assert run(sm.set_auto_sync([_id(A, "n1"), _id(C, "n3")], False)) == 2
    assert {r.doc_id for r in run(sm.fetch_rows([A, C])) if not r.auto_sync} == {_id(A, "n1"), _id(C, "n3")}
    assert [r.doc_id for r in run(sm.fetch_rows([C]))] == [_id(C, "n3")]
    # which data sources have documents (the sign-ins the stored content needs)
    counts = run(cm.count_documents_by_config())
    assert (counts.get(A), counts.get(C)) == (2, 1)
    # ... and the ones query-time permission checks govern (repository doc ids)
    governed = run(cm.count_governed_documents_by_config(["alfresco://", "nuxeo://"]))
    assert (governed.get(A), governed.get(C)) == (2, 1)
    assert run(cm.count_governed_documents_by_config(["cmis://"])).get(A) is None


# ── removal, retiring, duplicate copies ──────────────────────────────────────────────────────

def test_record_removal(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A)))
    run(cm.register_ingest_only(_config(B, auto_sync=False)))
    run(sm.save_state(_state(A, "n1")))
    run(sm.save_state(_state(A, "n2")))
    run(sm.save_state(_state(B, "n4", auto_sync=False)))

    rows = [r for r in run(sm.fetch_rows([A, B])) if r.doc_id in (_id(A, "n1"), _id(B, "n4"))]
    counts = run(sm.record_removal(rows, ["vector", "search", "graph", "rdf"], [A]))
    # the ingest-only row is forgotten and its datasource dropped; the sync's row stays, off
    assert counts == {"forgotten": 1, "datasources_dropped": 1, "datasources_now_skip_graph": 0}
    assert run(cm.get_config(B)) is None
    s = run(sm.get_state(_id(A, "n1")))
    assert s is not None and run(sm.sync_off(_id(A, "n1"))) and run(sm.doc_skip_graph(_id(A, "n1")))
    assert (s.vector_synced_at, s.search_synced_at, s.graph_synced_at) == (None, None, None)

    # the property graph removed from the last document with one: the datasource no longer
    # builds it, the RDF graph stays on (each graph on its own)
    from graph_flags import GraphFlags
    rows = [r for r in run(sm.fetch_rows([A])) if r.doc_id == _id(A, "n2")]
    counts = run(sm.record_removal(rows, ["graph"], [A]))
    a = run(cm.get_config(A))
    assert counts["datasources_now_skip_graph"] == 1 and a.graphs == GraphFlags(False, True) and not a.skip_graph
    s = run(sm.get_state(_id(A, "n2")))
    assert s.vector_synced_at and s.graph_synced_at is None and not run(sm.sync_off(_id(A, "n2")))
    assert run(sm.doc_graphs(_id(A, "n2"))) == GraphFlags(False, True)
    # a removal that takes nothing out of a graph leaves the datasource building it
    run(sm.save_state(_state(A, "n3", rdf=False)))
    rows = [r for r in run(sm.fetch_rows([A])) if r.doc_id == _id(A, "n3")]
    run(sm.record_removal(rows, ["rdf"], [A]))
    assert run(cm.get_config(A)).graphs == GraphFlags(False, True)
    # ...then the RDF graph too: neither graph, so skip_graph as well
    rows = [r for r in run(sm.fetch_rows([A])) if r.doc_id in (_id(A, "n2"), _id(A, "n3"))]
    run(sm.record_removal(rows, ["rdf"], [A]))
    a = run(cm.get_config(A))
    assert a.graphs == GraphFlags(False, False) and a.skip_graph
    assert run(sm.doc_skip_graph(_id(A, "n2")))


def test_retire_datasource(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A)))
    run(cm.create_config(_config(C)))
    run(sm.save_state(_state(A, "n1")))
    run(sm.save_state(_state(C, "n2")))
    run(sm.clear_targets(_id(C, "n2")))
    assert run(sm.retire_datasource(A)) == "ingest-only"
    a = run(cm.get_config(A))
    assert (a.auto_sync, a.is_active) == (False, False)
    assert run(sm.retire_datasource(C)) == "deleted"
    assert run(cm.get_config(C)) is None and run(sm.get_state(_id(C, "n2"))) is None


def test_resolve_duplicate_copies(stores):
    run, cm, sm = stores
    run(cm.create_config(_config(A)))
    run(cm.register_ingest_only(_config(B, auto_sync=False)))
    run(sm.save_state(_state(B, "n1", auto_sync=False)))   # an older ingest of n1, n2
    run(sm.save_state(_state(B, "n2", auto_sync=False)))
    run(sm.save_state(_state(A, "n1")))                     # the sync now holds n1
    # the sync supersedes the older ingest's copy
    assert sorted(run(sm.resolve_duplicate_copies(A))) == [_id(B, "n1")]
    assert run(sm.get_state(_id(A, "n1"))) is not None
    assert run(sm.get_state(_id(B, "n1"))) is None

    # an ingest-only run of a document the sync follows: the sync keeps it
    run(sm.save_state(_state(B, "n1", auto_sync=False)))
    assert sorted(run(sm.resolve_duplicate_copies(B))) == [_id(B, "n1")]
    assert run(cm.get_config(B)) is not None   # it still has n2

    # ... unless the sync's copy has its auto sync off: then this copy is the only one, and
    # it stays (an auto sync's copy is not an ingest-only run's to supersede)
    run(sm.set_auto_sync([_id(A, "n1")], False))
    run(sm.save_state(_state(B, "n1", auto_sync=False)))
    assert run(sm.resolve_duplicate_copies(B)) == []
    assert run(sm.get_state(_id(B, "n1"))) is not None

    # a new auto sync supersedes the ingest-only copies (B, then emptied, is dropped), and
    # takes over another auto sync's copy only with sync_takeover
    run(cm.create_config(_config(C)))
    run(sm.save_state(_state(C, "n2")))
    run(sm.set_auto_sync([_id(A, "n1")], True))
    run(sm.save_state(_state(C, "n1")))
    assert sorted(run(sm.resolve_duplicate_copies(C))) == sorted([_id(B, "n1"), _id(B, "n2")])
    assert run(cm.get_config(B)) is None
    assert run(sm.resolve_duplicate_copies(C, sync_takeover=True)) == [_id(A, "n1")]
    assert sorted(run(sm.doc_ids_for_config(C))) == [_id(C, "n1"), _id(C, "n2")]
    assert run(sm.get_state(_id(A, "n1"))) is None


def test_instances_with_different_roots_share_a_repository_without_seeing_each_other():
    """Two OpenArch registries on one repository (another Flexible GraphRAG, or a test run): each sees only its own
    data sources, state and rules, and removing one's registry leaves the other's."""
    pytest.importorskip("python_openarch_api")
    from openarch.registry import OpenArchConfigManager, OpenArchStateManager, remove_registry
    loop = asyncio.new_event_loop()
    run = loop.run_until_complete
    mine = _openarch_settings()
    other = dict(mine, root_path="/fg-test-other-sources", datasources_path="/fg-test-other-datasources")
    try:
        _openarch_clean(mine)
        _openarch_clean(other)
    except Exception as e:
        loop.close()
        pytest.skip(f"openarch not available: {e}")
    managers = []
    try:
        for settings in (mine, other):
            cm, sm = OpenArchConfigManager(settings), OpenArchStateManager(settings)
            run(cm.initialize())
            run(sm.initialize())
            managers.append((cm, sm))
        (cm1, sm1), (cm2, sm2) = managers
        run(cm1.create_config(_config(A)))
        run(sm1.save_state(_state(A, "n1")))
        run(cm2.create_config(_config(C)))
        run(sm2.save_state(_state(C, "n1")))   # the same source object, in the other tree
        sm1.registry.scope.set_rules("alfresco", "test-repo", [("/Shared/T", None, True, True, {"autoSync": False})])

        assert [c.config_id for c in run(cm1.get_all_active_configs())] == [A]
        assert [c.config_id for c in run(cm2.get_all_active_configs())] == [C]
        assert run(sm1.doc_ids_for_config(A)) == [_id(A, "n1")] and run(sm2.doc_ids_for_config(A)) == []
        assert run(sm2.get_state(_id(C, "n1"))) is not None and run(sm1.get_state(_id(C, "n1"))) is None
        assert sm2.registry.scope.rules("alfresco:test-repo", fresh=True) == []
        assert not run(sm2.sync_off(_id(C, "n1")))   # mine's rule does not reach the other tree

        remove_registry(mine)
        assert run(cm1.get_all_active_configs()) == []
        assert [c.config_id for c in run(cm2.get_all_active_configs())] == [C]
        assert run(sm2.get_state(_id(C, "n1"))) is not None
    finally:
        for cm, sm in managers:
            run(cm.close())
            run(sm.close())
        _openarch_clean(mine)
        _openarch_clean(other)
        loop.close()

