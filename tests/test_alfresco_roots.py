"""Unit tests for which Alfresco events an auto sync follows (AlfrescoDetector._in_roots)."""
import pytest

from incremental_updates.detectors.alfresco_detector import AlfrescoDetector

pytestmark = pytest.mark.unit


def _detector(**config):
    return AlfrescoDetector({"url": "http://localhost:8080", "username": "u", "password": "p", **config})


DETAILS = [{"id": "file-a", "name": "a.txt", "isFile": True, "isFolder": False},
           {"id": "folder-sub", "name": "Sub", "isFile": False, "isFolder": True}]


def test_selected_file_and_folder_not_recursive():
    d = _detector(path="/Shared/M", nodeDetails=DETAILS, recursive=False)
    assert d._in_roots("file-a", ["folder-m"])                       # the selected file
    assert d._in_roots("n1", ["folder-sub", "folder-m"])             # a direct child of the selected folder
    assert not d._in_roots("n2", ["folder-deep", "folder-sub"])      # two levels down: not recursive
    assert not d._in_roots("n3", ["folder-m"])                       # next to the selection, not selected


def test_selected_folder_recursive():
    d = _detector(path="/Shared/M", nodeDetails=DETAILS, recursive=True)
    assert d._in_roots("n2", ["folder-deep", "folder-sub", "folder-m"])
    assert not d._in_roots("n3", ["folder-m"])


def test_folder_by_path_when_nothing_is_selected():
    d = _detector(path="/Shared/M", recursive=False)
    d._monitored_folder_id = "folder-m"
    assert d._in_roots("n1", ["folder-m"])
    assert not d._in_roots("n2", ["folder-sub", "folder-m"])
    d.recursive = True
    assert d._in_roots("n2", ["folder-sub", "folder-m"])


def test_unknown_hierarchy_or_no_roots_is_followed():
    assert _detector(path="/Shared/M", nodeDetails=DETAILS)._in_roots("n9", [])
    assert _detector(path="/")._in_roots("n9", ["anything"])


def _event(name="a.txt", modified="2026-10-18T16:00:00.000+0000", parent="folder-m"):
    return {"node_id": "n1", "name": name, "modified_at": modified, "primary_hierarchy": [parent, "root"]}


def test_an_update_repeating_the_last_event_is_a_duplicate():
    d = _detector(path="/Shared/M")
    d._remember(_event(), 100.0)
    assert d._is_duplicate(_event(), 105.0)                                    # the same notification again
    assert d._is_duplicate(_event(modified="2026-10-18T16:00:01.000+0000"), 105.0)  # the UPDATE right after a CREATE
    assert not d._is_duplicate(_event(modified="2026-10-18T16:00:30.000+0000"), 130.0)  # a later edit
    assert not d._is_duplicate(_event(name="a-renamed.txt"), 105.0)          # a rename
    assert not d._is_duplicate(_event(parent="folder-other"), 105.0)         # a move
    assert not d._is_duplicate(_event(), 200.0)                              # long after


def test_a_selected_node_is_listed_under_its_current_name_and_path():
    from types import SimpleNamespace
    from sources.alfresco import AlfrescoSource
    entry = SimpleNamespace(name="a-renamed.txt", path=SimpleNamespace(name="/Company Home/Shared/M/Other"))
    assert AlfrescoSource._current_name_path(entry, "a.txt", "/Shared/M/a.txt") == ("a-renamed.txt", "/Shared/M/Other/a-renamed.txt")
    assert AlfrescoSource._current_name_path(SimpleNamespace(name="a.txt", path=None), "a.txt", "/Shared/M/a.txt") == ("a.txt", "/Shared/M/a.txt")


def test_a_folder_rename_or_move_is_told_apart():
    from incremental_updates.detectors.alfresco_broadcaster import folder_change
    folder = {"isFolder": True, "name": "Deeper", "primaryHierarchy": ["root-r", "shared"]}
    assert folder_change("org.alfresco.event.node.Updated", folder, {"name": "Deep"}) == "renamed"
    assert folder_change("org.alfresco.event.node.Updated", folder, {"primaryHierarchy": ["other", "shared"]}) == "moved"
    assert folder_change("org.alfresco.event.node.Updated", folder, {"properties": {"cm:title": "x"}}) == ""
    assert folder_change("org.alfresco.event.node.Created", folder, {}) == ""
    assert folder_change("org.alfresco.event.node.Updated", dict(folder, isFolder=False), {"name": "Deep"}) == ""
