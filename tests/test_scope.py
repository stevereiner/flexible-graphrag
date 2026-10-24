"""Per-object scope rules (openarch/scope.py): resolution, and the rule store on OpenArch."""
import asyncio
import os
from datetime import datetime, timezone

import pytest

from incremental_updates.ingest_status import Item
from incremental_updates.removal import StateRow
from openarch.scope import (
    ScopeRule, apply_rule, connection_roots, effective_flags, follower, graphs_skipped, item_flags, match_item,
    roots_params, row_flags, sync_decision,
)

ON = {"searchVector": True, "pgGraph": True, "rdfGraph": True}
NO_GRAPH = {"searchVector": True, "pgGraph": False, "rdfGraph": False}


def _row(path, node=None):
    return StateRow(doc_id="d", config_id="c", source_id=node, source_path=path, synced={})


def _folder(path, flags, recursive=True):
    return ScopeRule(item=Item(path, True, None), flags=dict(flags), recursive=recursive)


def _file(path, node, flags):
    return ScopeRule(item=Item(path, False, node), flags=dict(flags))


@pytest.mark.unit
def test_row_flags_from_processing_tab_columns():
    assert row_flags("ingest") == ON
    assert row_flags("ingest_no_graph", auto_sync=True) == {**NO_GRAPH, "autoSync": True}
    assert row_flags("remove_graph") == {"pgGraph": False, "rdfGraph": False}
    # two graph columns: a remove_graph row keeps the graph it says (RDF unchecked alone)
    from graph_flags import GraphFlags
    assert row_flags("remove_graph", graphs=GraphFlags(True, False)) == {"rdfGraph": False}
    assert row_flags("ingest", graphs=GraphFlags(True, False)) == {**ON, "rdfGraph": False}
    assert row_flags("remove_all") == {"searchVector": False, "pgGraph": False, "rdfGraph": False}
    assert row_flags("keep", auto_sync=False) == {"autoSync": False}
    assert row_flags("keep") == {}


@pytest.mark.unit
def test_nearest_rule_wins_flag_by_flag():
    rules = [_folder("/Shared", {**ON, "autoSync": True}),
             _folder("/Shared/Drafts", {"pgGraph": False, "rdfGraph": False}),   # subfolder: no graphs
             _file("/Shared/Drafts/keep.txt", "n9", {"autoSync": False})]
    assert effective_flags(rules, _row("/Shared/a.txt")) == {**ON, "autoSync": True}
    # graphs from the subfolder, search+vector and auto sync inherited from /Shared
    assert effective_flags(rules, _row("/Shared/Drafts/x/b.txt")) == {**NO_GRAPH, "autoSync": True}
    # the document's own rule beats the folders' (matched by node id, even after a move)
    assert effective_flags(rules, _row("/Elsewhere/keep.txt", "n9")) == {
        "searchVector": None, "pgGraph": None, "rdfGraph": None, "autoSync": False}
    assert effective_flags(rules, _row("/Other/c.txt")) == dict.fromkeys(ON | {"autoSync": 0}, None)


@pytest.mark.unit
def test_non_recursive_folder_covers_only_its_direct_documents():
    rules = [_folder("/Shared", ON, recursive=False)]
    assert effective_flags(rules, _row("/Shared/a.txt"))["searchVector"] is True
    assert effective_flags(rules, _row("/Shared/sub/a.txt"))["searchVector"] is None


@pytest.mark.unit
def test_company_home_and_windows_paths_compare_canonically():
    rules = [_folder("/Shared", ON)]
    assert effective_flags(rules, _row("/Company Home/Shared/a.txt"))["pgGraph"] is True
    fs = ScopeRule(item=match_item("filesystem", r"C:\Docs\Reports", None, True), flags=ON, recursive=True)
    assert effective_flags([fs], _row(r"C:\Docs\Reports\q1.txt"))["searchVector"] is True


@pytest.mark.unit
def test_a_folder_rule_clears_the_same_flags_below_it():
    rules = [_folder("/Shared/Drafts", {"pgGraph": False, "rdfGraph": False, "autoSync": False}),
             _file("/Shared/Drafts/a.txt", "n1", {"searchVector": True, "pgGraph": False})]
    rules, changed = apply_rule(rules, _folder("/Shared", {"pgGraph": True, "rdfGraph": True}))
    drafts = next(r for r in rules if r.item.path == "/Shared/Drafts")
    a = next(r for r in rules if r.item.id == "n1")
    assert drafts.flags == {"autoSync": False} and a.flags == {"searchVector": True}
    assert len(changed) == 3   # /Shared (new), /Shared/Drafts, a.txt
    assert effective_flags(rules, _row("/Shared/Drafts/a.txt", "n1"))["pgGraph"] is True


@pytest.mark.unit
def test_a_rule_merges_into_the_same_object_and_follows_a_rename():
    rules, _ = apply_rule([], _file("/Shared/a.txt", "n1", ON))
    rules, _ = apply_rule(rules, _file("/Shared/renamed.txt", "n1", {"autoSync": False}))
    assert len(rules) == 1
    assert rules[0].item.path == "/shared/renamed.txt".replace("shared", "Shared")
    assert rules[0].flags == {**ON, "autoSync": False}


@pytest.mark.unit
def test_item_flags_of_a_folder_row_include_its_own_rule():
    rules = [_folder("/Shared", {**ON, "autoSync": True}), _folder("/Shared/Drafts", {"pgGraph": False})]
    assert item_flags(rules, Item("/Shared/Drafts", True, None)) == {
        "searchVector": True, "pgGraph": False, "rdfGraph": True, "autoSync": True}
    assert item_flags(rules, Item("/Shared/Drafts/x.txt", False, "n2"))["pgGraph"] is False


@pytest.mark.unit
def test_folder_rules_match_by_ancestor_ids_nearest_first():
    # an Alfresco event's primary hierarchy: parent first; its path is not reliable
    rules = [ScopeRule(item=Item("/Shared/T", True, "f-top"), flags={**ON, "autoSync": True}, recursive=True),
             ScopeRule(item=Item("/Shared/T/Drafts", True, "f-drafts"), flags={"autoSync": False}, recursive=False)]
    row = _row("/Shared/T/whatever.txt", "n5")
    assert effective_flags(rules, row, ["f-drafts", "f-top", "root"])["autoSync"] is False
    # two levels below the non-recursive Drafts rule: only /Shared/T (recursive) reaches it
    assert effective_flags(rules, row, ["f-sub", "f-drafts", "f-top"])["autoSync"] is True
    assert effective_flags(rules, row, ["other", "root"]) == dict.fromkeys(ON | {"autoSync": 0}, None)


@pytest.mark.unit
def test_sync_decision():
    assert sync_decision(dict.fromkeys(ON | {"autoSync": 0}, None)) == {
        "follow": True, "graph": None, "rdf": None, "skip_graph": None, "reason": None}
    # each graph on its own: a rule on one leaves the other to the data source
    rdf_only = sync_decision({"searchVector": True, "pgGraph": False, "rdfGraph": None, "autoSync": None})
    assert rdf_only["follow"] and rdf_only["graph"] is False and rdf_only["rdf"] is None
    assert sync_decision({**NO_GRAPH, "autoSync": True})["skip_graph"] is True
    assert sync_decision({**ON, "autoSync": None})["skip_graph"] is False
    assert not sync_decision({**ON, "autoSync": False})["follow"]
    off = sync_decision({"searchVector": False, "pgGraph": False, "rdfGraph": False, "autoSync": None})
    assert not off["follow"] and "excluded" in off["reason"]
    graph_only = sync_decision({"searchVector": False, "pgGraph": True, "rdfGraph": None, "autoSync": None})
    assert not graph_only["follow"] and "not supported yet" in graph_only["reason"]
    assert graphs_skipped({"pgGraph": False, "rdfGraph": None}) is True
    assert graphs_skipped({"pgGraph": False, "rdfGraph": True}) is False


@pytest.mark.unit
def test_follower_is_the_sync_of_the_folder_above_else_the_owner():
    t = ScopeRule(Item("/T", True, "f-t"), {"autoSync": True}, True, config_ids=["support"])
    shallow = ScopeRule(Item("/S", True, "f-s"), {"autoSync": True}, False, config_ids=["sales"])
    off = ScopeRule(Item("/U", True, "f-u"), {"autoSync": False}, True, config_ids=["support"])
    rules = [t, shallow, off]
    assert follower(rules, Item("/T/a/b.txt", False, "n1"), "new") == "support"   # resumed in its sync
    assert follower(rules, Item("/S/x.txt", False, "n2"), "new") == "sales"
    assert follower(rules, Item("/S/deep/x.txt", False, "n3"), "new") == "new"     # /S is not deep
    assert follower(rules, Item("/U", True, "f-u"), "new") == "support"            # it followed it before
    assert follower(rules, Item("/V", True, "f-v"), None) is None


@pytest.mark.unit
def test_a_sync_watches_its_top_most_objects_with_auto_sync_on():
    rules = [
        ScopeRule(Item("/T", True, "f-t"), {"autoSync": True}, True, config_ids=["c1"]),
        ScopeRule(Item("/T/In", True, "f-i"), {"autoSync": True}, True, config_ids=["c1"]),     # covered
        ScopeRule(Item("/T/Off", True, "f-o"), {"autoSync": False}, True, config_ids=["c1"]),
        ScopeRule(Item("/A/b.txt", False, "n1"), {"autoSync": True}, config_ids=["c1"]),
        ScopeRule(Item("/Other", True, "f-x"), {"autoSync": True}, True, config_ids=["c2"]),
        ScopeRule(Item("/G", True, "f-g"), {"pgGraph": False}, True, config_ids=["c1"]),          # no auto sync
    ]
    assert [r.item.path for r in connection_roots(rules, "c1")] == ["/A/b.txt", "/T"]
    assert [r.item.path for r in connection_roots(rules, "c2")] == ["/Other"]
    # a folder turning auto sync on for another sync takes what is below it
    rules, _ = apply_rule(rules, ScopeRule(Item("/", True, None), {"autoSync": True}, True, config_ids=["c3"]))
    assert connection_roots(rules, "c1") == [] and [r.item.path for r in connection_roots(rules, "c3")] == ["/"]


@pytest.mark.unit
def test_roots_become_connection_params_in_the_detectors_form():
    roots = [ScopeRule(Item("/T", True, "f-t"), {"autoSync": True}, True, source_path="/T"),
             ScopeRule(Item("/A/b.txt", False, "n1"), {"autoSync": True}, source_path="/A/b.txt")]
    old = {"url": "u", "nodeDetails": [{"id": "f-t", "name": "T", "path": "/Company Home/T", "isFolder": True}],
           "nodeIds": ["f-t", "gone"]}
    cp = roots_params("alfresco", old, roots)
    assert cp["nodeDetails"][0] == old["nodeDetails"][0]                     # kept as it was
    assert cp["nodeDetails"][1] == {"id": "n1", "name": "b.txt", "path": "/A/b.txt", "isFile": True,
                                    "isFolder": False}
    assert cp["nodeIds"] == ["f-t", "n1"] and cp["url"] == "u"
    # a repository rooted at one folder chosen by path stays so
    by_path = roots_params("nuxeo", {"path": "/old"}, [ScopeRule(Item("/ws/T", True, None), {}, True, source_path="/ws/T")])
    assert by_path == {"path": "/ws/T"}
    # a filesystem keeps its paths as given
    fs = [ScopeRule(match_item("filesystem", r"C:\Data\Docs", None, True), {}, True, source_path=r"C:\Data\Docs")]
    assert roots_params("filesystem", {"paths": [r"C:\data\docs", r"C:\Other"]}, fs)["paths"] == [r"C:\data\docs"]


# ── on OpenArch ──────────────────────────────────────────────────────────────────────────────

def _settings():
    return {"url": os.getenv("STATE_STORE_TEST_OPENARCH_URL") or os.getenv("OPENARCH_URL") or "http://localhost:8088",
            "username": os.getenv("OPENARCH_USERNAME", "admin"), "password": os.getenv("OPENARCH_PASSWORD", "password"),
            "repository": os.getenv("OPENARCH_REPOSITORY", "default"),
            "root_path": "/fg-test-sources", "datasources_path": "/fg-test-datasources"}


@pytest.fixture
def openarch():
    pytest.importorskip("python_openarch_api")
    from test_state_store import _openarch_clean
    from openarch.registry import OpenArchConfigManager, OpenArchStateManager
    settings = _settings()
    try:
        _openarch_clean(settings)
    except Exception as e:
        pytest.skip(f"openarch not available: {e}")
    loop = asyncio.new_event_loop()
    cm, sm = OpenArchConfigManager(settings), OpenArchStateManager(settings)
    loop.run_until_complete(cm.initialize())
    loop.run_until_complete(sm.initialize())
    yield loop.run_until_complete, cm, sm
    loop.run_until_complete(cm.close())
    loop.run_until_complete(sm.close())
    _openarch_clean(settings)
    loop.close()


@pytest.mark.integration
def test_rules_on_openarch_objects_and_effective_flags(openarch):
    from incremental_updates.config_manager import DataSourceConfig
    from incremental_updates.state_manager import DocumentState
    run, cm, sm = openarch
    cfg = "11111111-2222-3333-4444-555555555555"
    params = {"url": "http://alfresco-test:8080", "source_id": "test-repo"}
    run(cm.create_config(DataSourceConfig(config_id=cfg, project_id="default", source_type="alfresco",
                                          source_name="t", connection_params=params)))
    now = datetime.now(timezone.utc)
    for node, path in (("n1", "/Shared/T/a.txt"), ("n2", "/Shared/T/Drafts/b.txt")):
        run(sm.save_state(DocumentState(doc_id=f"{cfg}:alfresco://{node}", config_id=cfg, source_path=path,
                                        source_id=node, ordinal=1, content_hash="h",
                                        vector_synced_at=now, search_synced_at=now)))
    scope = sm.registry.scope
    n = scope.set_rules("alfresco", "test-repo", [
        ("/Shared/T", None, True, True, {**ON, "autoSync": True}),
        ("/Shared/T/Drafts", None, True, True, {"pgGraph": False, "rdfGraph": False}),
        ("/Shared/T/new.txt", "n3", False, False, {"autoSync": False}),   # not ingested yet
    ])
    assert n == 3
    rules = {r.item.path: r for r in scope.rules("alfresco:test-repo", fresh=True)}
    assert set(rules) == {"/Shared/T", "/Shared/T/Drafts", "/Shared/T/new.txt"}
    client = sm.registry.client
    folder = client.get(rules["/Shared/T/Drafts"].oa_id)
    assert folder["sys_path"] == "/fg-test-sources/alfresco/test-repo/Shared/T/Drafts"
    new = client.get(rules["/Shared/T/new.txt"].oa_id)
    assert new["cin_id"] == "alfresco://n3" and new["sys_path"].endswith("/Shared/T/new.txt")

    b = sm.registry.doc_of(f"{cfg}:alfresco://n2")
    assert (b["fg_flags_searchVector"], b["fg_flags_pgGraph"], b["fg_flags_autoSync"]) == (True, False, True)
    a = sm.registry.doc_of(f"{cfg}:alfresco://n1")
    assert (a["fg_flags_pgGraph"], a["fg_flags_rdfGraph"]) == (True, True)

    # graphs back on for all of /Shared/T: the Drafts rule loses its graph flags (and goes)
    scope.set_rules("alfresco", "test-repo", [("/Shared/T", None, True, True, {"pgGraph": True, "rdfGraph": True})])
    assert "/Shared/T/Drafts" not in {r.item.path for r in scope.rules("alfresco:test-repo", fresh=True)}
    assert sm.registry.doc_of(f"{cfg}:alfresco://n2")["fg_flags_pgGraph"] is True

    # a document saved later gets its effective flags from the rules
    run(sm.save_state(DocumentState(doc_id=f"{cfg}:alfresco://n4", config_id=cfg, source_path="/Shared/T/c.txt",
                                    source_id="n4", ordinal=1, content_hash="h", vector_synced_at=now)))
    assert sm.registry.doc_of(f"{cfg}:alfresco://n4")["fg_flags_autoSync"] is True

    # the rule-only mirror of new.txt goes when its rule is emptied
    scope._clear(rules["/Shared/T/new.txt"].oa_id)
    assert client.get(rules["/Shared/T/new.txt"].oa_id) is None



@pytest.mark.integration
def test_sync_follows_the_rules_on_openarch(openarch):
    """2a / 2b: the sync's checks answer from the rules -- recursive and non-recursive folders,
    by path (filesystem, Nuxeo) and by ancestor ids (Alfresco)."""
    from incremental_updates.config_manager import DataSourceConfig
    from incremental_updates.state_manager import DocumentState
    run, cm, sm = openarch
    cfg = "11111111-2222-3333-4444-555555555555"
    run(cm.create_config(DataSourceConfig(config_id=cfg, project_id="default", source_type="alfresco",
                                          source_name="t", connection_params={"url": "http://alf:8080", "source_id": "r"})))
    now = datetime.now(timezone.utc)
    run(sm.save_state(DocumentState(doc_id=f"{cfg}:alfresco://n1", config_id=cfg, source_path="/T/Drafts/a.txt",
                                    source_id="n1", ordinal=1, content_hash="h", vector_synced_at=now,
                                    search_synced_at=now, graph_synced_at=now)))
    assert not run(sm.sync_off(f"{cfg}:alfresco://n1"))           # no rules: its entry decides
    assert not run(sm.doc_skip_graph(f"{cfg}:alfresco://n1"))
    assert run(sm.document_scope(cfg, "/T/x.txt", "n9")) == {
        "follow": True, "graph": None, "rdf": None, "skip_graph": None, "reason": None}

    sm.registry.scope.set_rules("alfresco", "r", [
        ("/T", "f-t", True, True, {**ON, "autoSync": True}),                       # deep
        ("/T/Drafts", "f-d", True, False, {"pgGraph": False, "rdfGraph": False, "autoSync": False}),  # not deep
        ("/T/Old", "f-o", True, True, {"searchVector": False, "pgGraph": False, "rdfGraph": False}),
    ])
    # 2a: a document already ingested follows its folder's rule
    assert run(sm.sync_off(f"{cfg}:alfresco://n1"))
    assert run(sm.doc_skip_graph(f"{cfg}:alfresco://n1"))
    assert run(sm.doc_skip_graph(config_id=cfg, source_id="n1"))
    # 2b: new documents, by path
    assert run(sm.document_scope(cfg, "/T/new.txt", "n2")) == {"follow": True, "graph": True, "rdf": True, "skip_graph": False, "reason": None}
    assert not run(sm.document_scope(cfg, "/T/Drafts/new.txt", "n3"))["follow"]
    deeper = run(sm.document_scope(cfg, "/T/Drafts/sub/new.txt", "n4"))       # Drafts is not deep
    assert deeper == {"follow": True, "graph": True, "rdf": True, "skip_graph": False, "reason": None}
    assert "excluded" in run(sm.document_scope(cfg, "/T/Old/y/new.txt", "n5"))["reason"]
    # ... and by ancestor ids, whatever the path says
    assert not run(sm.document_scope(cfg, "/T/new.txt", "n6", ["f-d", "f-t"]))["follow"]
    assert run(sm.document_scope(cfg, "/T/new.txt", "n7", ["f-sub", "f-d", "f-t"]))["follow"]
    assert run(sm.document_scope(cfg, "/elsewhere/z.txt", "n8")) == {"follow": True, "graph": None, "rdf": None, "skip_graph": None, "reason": None}

    # resuming Drafts: graphs back, auto sync on, for the document already there too
    sm.registry.scope.set_rules("alfresco", "r", [("/T/Drafts", "f-d", True, False, {**ON, "autoSync": True})])
    assert not run(sm.sync_off(f"{cfg}:alfresco://n1"))
    assert not run(sm.doc_skip_graph(f"{cfg}:alfresco://n1"))


@pytest.mark.integration
def test_syncs_watch_what_the_rules_follow_on_openarch(openarch):
    """2c: two connections to one repository each watch the objects their rules follow; a row
    turned off or taken over by another sync changes their roots; a sync registered before
    rules named followers is named on the rules of its roots."""
    from incremental_updates.config_manager import DataSourceConfig
    run, cm, sm = openarch
    support, sales, old = ("aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000002",
                           "aaaaaaaa-0000-0000-0000-000000000003")
    repo = {"url": "http://alf:8080", "source_id": "r"}
    for cid, cp in ((support, {**repo, "path": "/Support"}), (sales, {**repo, "path": "/Sales"}),
                    (old, {**repo, "nodeDetails": [{"id": "f-l", "name": "Legacy", "path": "/Legacy", "isFolder": True}]})):
        run(cm.create_config(DataSourceConfig(config_id=cid, project_id="default", source_type="alfresco",
                                              source_name=cid[-1], connection_params=cp)))
    scope = sm.registry.scope
    scope.set_rules("alfresco", "r", [("/Support", "f-su", True, True, {**ON, "autoSync": True})], owner=support)
    scope.set_rules("alfresco", "r", [("/Sales", "f-sa", True, True, {**ON, "autoSync": True}),
                                      ("/Sales/Q1.txt", "n-q1", False, False, {"autoSync": True})], owner=sales)
    scope.set_rules("alfresco", "r", [("/Legacy", "f-l", True, True, {**ON, "autoSync": True})])  # no follower named
    # a row inside support's folder sent by a sales run is resumed in support's sync
    scope.set_rules("alfresco", "r", [("/Support/Cases/c.txt", "n-c", False, False, {"autoSync": True})], owner=sales)
    rules = {r.item.path: r for r in scope.rules("alfresco:r", fresh=True)}
    assert rules["/Support/Cases/c.txt"].config_ids == [support]

    changed = {cfg.config_id: (outcome, cfg.connection_params) for cfg, outcome in run(cm.apply_rule_roots("alfresco"))}
    assert changed[support][0] == "updated"
    assert [nd["id"] for nd in changed[support][1]["nodeDetails"]] == ["f-su"]
    assert [nd["id"] for nd in changed[sales][1]["nodeDetails"]] == ["f-sa"]             # Q1.txt is inside /Sales
    assert old not in changed                                                           # claimed, roots the same
    assert {r.item.path: r for r in scope.rules("alfresco:r", fresh=True)}["/Legacy"].config_ids == [old]
    assert run(cm.apply_rule_roots("alfresco")) == []                                   # nothing changed since

    # sales stops following /Sales: it is left with nothing to follow
    scope.set_rules("alfresco", "r", [("/Sales", "f-sa", True, True, {"autoSync": False})], owner=sales)
    assert [(c.config_id, o) for c, o in run(cm.apply_rule_roots("alfresco"))] == [(sales, "empty")]
    # a new sync following the whole repository takes support's and the legacy sync's objects
    run(cm.update_config(sales, auto_sync=False))
    scope.set_rules("alfresco", "r", [("/", None, True, True, {"autoSync": True})], owner="whole")
    assert sorted((c.config_id, o) for c, o in run(cm.apply_rule_roots("alfresco"))) == [
        (support, "empty"), (old, "empty")]
