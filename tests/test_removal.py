"""Unit tests for removing a repository selection from the stores (incremental_updates/removal.py)
and how ingest status reports what is left afterwards."""
from types import SimpleNamespace

import pytest

from incremental_updates.ingest_status import REMOVED, Datasource, Item, Root, check_ingest_status
from incremental_updates.removal import (
    StateRow, configs_present, configured_stores, item_matches, select_rows,
)

pytestmark = pytest.mark.unit


def row(doc_id, path, source_id=None, config_id="c1", **synced):
    return StateRow(doc_id, config_id, source_id, path,
                    {t: synced.get(t, True) for t in ("vector", "search", "graph")})


def test_file_matches_by_node_id_even_after_a_move():
    r = row("c1:alfresco://n1", "/Company Home/Sites/old/a.pdf", source_id="n1")
    assert item_matches(Item("/Sites/new/a.pdf", False, "n1"), r, recursive=False)
    assert not item_matches(Item("/Sites/old/a.pdf", False, "n2"), r, recursive=False)


def test_file_without_id_matches_by_path_with_company_home_dropped():
    r = row("c1:x", "/Company Home/Sites/a.pdf")
    assert item_matches(Item("/Sites/a.pdf", False), r, recursive=False)


def test_folder_depth_follows_recursive():
    direct = row("c1:1", "/Sites/f/a.pdf")
    deep = row("c1:2", "/Sites/f/sub/b.pdf")
    other = row("c1:3", "/Sites/ff/c.pdf")  # prefix of the name, not below the folder
    folder = Item("/Sites/f", True)
    assert [r.doc_id for r in select_rows([folder], [direct, deep, other], False)[0]] == ["c1:1"]
    assert [r.doc_id for r in select_rows([folder], [direct, deep, other], True)[0]] == ["c1:1", "c1:2"]


def test_configs_present_ignores_rows_with_nothing_left():
    rows = [row("c1:1", "/f/a.pdf", vector=False, search=False, graph=False),
            row("c2:1", "/f/a.pdf", config_id="c2", graph=False)]
    assert configs_present([Item("/f", True)], rows) == [{"c2"}]


def test_configured_stores_honours_none():
    s = SimpleNamespace(vector_db="qdrant", search_db=SimpleNamespace(value="none"),
                        pg_graph_db="none", rdf_graph_db="fuseki")
    assert configured_stores(s) == {"vector": True, "search": False, "graph": True}
    s.rdf_graph_db = "none"
    assert configured_stores(s)["graph"] is False


def _ds(config_id, auto_sync, root="/f"):
    return Datasource(config_id, "alfresco", "x", "", True, False,
                      [Root(root, True)], auto_sync=auto_sync)


def test_ingest_status_drops_an_ingest_only_source_whose_documents_were_removed():
    items = [Item("/f", True)]
    ingest_only = _ds("c1", auto_sync=False)
    assert check_ingest_status(items, [ingest_only], {}, present=[{"c1"}])[0]["status"] == "synced"
    assert check_ingest_status(items, [ingest_only], {}, present=[set()])[0]["status"] == "none"
    # An auto-sync still covers the folder: its detector owns what is below it.
    assert check_ingest_status(items, [_ds("c2", True)], {}, present=[set()])[0]["status"] == "synced"


def test_ingest_status_marks_an_auto_synced_file_removed_from_every_store():
    item = Item("/f/a.pdf", False, "n1")
    indexed = {"n1": [{"config_id": "c2", "vector_synced_at": False,
                       "search_synced_at": False, "graph_synced_at": False}]}
    result = check_ingest_status([item], [_ds("c2", True)], indexed, present=[set()])[0]
    assert result["status"] == REMOVED
    assert result["indexed"] == {"vector": False, "search": False, "graph": False}


def test_stores_holding_reports_what_is_left_below_a_folder():
    from incremental_updates.removal import stores_holding
    rows = [row("c1:1", "/f/a.pdf", graph=False), row("c1:2", "/f/sub/b.pdf", graph=True)]
    assert stores_holding(Item("/f", True), rows, recursive=False) == \
        {"vector": True, "search": True, "graph": False}
    assert stores_holding(Item("/f", True), rows, recursive=True)["graph"] is True
    assert stores_holding(Item("/g", True), rows, recursive=True) is None


def test_trim_roots_multiselect_and_path():
    from incremental_updates.removal import trim_roots
    cp = {"path": "/Shared", "nodeIds": ["n1", "n2"],
          "nodeDetails": [{"id": "n1", "path": "/Shared/a.txt"}, {"id": "n2", "path": "/Shared/b.txt"}]}
    new, left, changed = trim_roots(cp, [Item("/Shared/a.txt", False, "n1")])
    assert (left, changed, new["nodeIds"], [d["id"] for d in new["nodeDetails"]]) == (1, True, ["n2"], ["n2"])
    assert trim_roots(cp, [Item("/Shared/c.txt", False, "n9")])[1:] == (2, False)
    # a path datasource: its one root is its path (Company Home prefix ignored)
    assert trim_roots({"path": "/Company Home/Shared/GraphRAG"}, [Item("/Shared/GraphRAG", True)])[1:] == (0, True)
    # a file inside a synced folder is not a root: the folder keeps syncing
    assert trim_roots({"path": "/Shared/GraphRAG"}, [Item("/Shared/GraphRAG/a.txt", False, "n1")])[1:] == (1, False)


def test_add_roots_puts_a_resumed_row_back():
    from incremental_updates.removal import add_roots
    cp = {"nodeIds": ["n2"], "nodeDetails": [{"id": "n2", "path": "/Shared/b.txt"}]}
    new, added = add_roots(cp, [Item("/Shared/a.txt", False, "n1"), Item("/Shared/b.txt", False, "n2")])
    assert added == 1 and new["nodeIds"] == ["n2", "n1"]
    assert new["nodeDetails"][1] == {"id": "n1", "name": "a.txt", "path": "/Shared/a.txt",
                                     "isFile": True, "isFolder": False}
    assert cp["nodeIds"] == ["n2"] and len(cp["nodeDetails"]) == 1  # input untouched
    # a datasource rooted at its path already watches everything below it
    assert add_roots({"path": "/Shared"}, [Item("/Shared/a.txt", False, "n1")])[1] == 0


def test_ingest_status_reports_per_document_auto_sync():
    item = Item("/f/a.pdf", False, "n1")
    on = {"n1": [{"config_id": "c2", "auto_sync": True, "vector_synced_at": True,
                  "search_synced_at": True, "graph_synced_at": True}]}
    off = {"n1": [{**on["n1"][0], "auto_sync": False}]}
    assert check_ingest_status([item], [_ds("c2", True)], on)[0]["auto_sync"] is True
    assert check_ingest_status([item], [_ds("c2", True)], off)[0]["auto_sync"] is False
    assert check_ingest_status([item], [_ds("c1", False)], on)[0]["auto_sync"] is False


def test_upload_rows_match_their_document_state_row():
    from types import SimpleNamespace
    from incremental_updates.ingest_status import fs_item, fs_key
    from incremental_updates.removal import StateRow, item_matches
    path = r"C:\newdev3\flexible-graphrag\flexible-graphrag\uploads\cmispress.txt"
    row = StateRow(doc_id="c1:" + fs_key(path), config_id="c1", source_id=fs_key(path),
                   source_path=fs_key(path), synced={"vector": True, "search": True, "graph": False})
    item = fs_item(path)
    assert item.id == fs_key(path) and item_matches(item, row, False)
    other = fs_item(r"C:\newdev3\flexible-graphrag\flexible-graphrag\uploads\other.txt")
    assert not item_matches(other, row, False)
    # an upload datasource's roots are its paths (not one "/" root matching everything)
    ds = Datasource.from_config(SimpleNamespace(config_id="c1", source_type="filesystem",
                                                connection_params={"paths": [path]}, auto_sync=False))
    assert [r.node_id for r in ds.roots] == [fs_key(path)]
    result = check_ingest_status([other], [ds], {}, False)[0]
    assert result["status"] == "none"
