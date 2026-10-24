"""Unit tests for Box auto sync (BoxDetector): selected files, the followed folders, files moved out,
and the Box path the periodic refresh compares."""
import asyncio
from types import SimpleNamespace as NS

import pytest

from incremental_updates.detectors.base import ChangeType
from incremental_updates.detectors.box_detector import BoxDetector
from incremental_updates.recovery import source_moved

pytestmark = pytest.mark.unit


def _detector(**config):
    d = BoxDetector({"folder_id": "100", "client_id": "c", "client_secret": "s", **config})
    d.folder_cache = {"100": True, "101": True}
    d.config_id = "cfg"
    return d


def _event(event_type, file_id="f1", parent="101", kind="file", name="a.txt"):
    return NS(event_type=NS(value=event_type), created_at=None,
              source=NS(type=NS(value=kind), id=file_id, name=name, parent=NS(id=parent) if parent else None, size=1, etag="1"))


class _States:
    def __init__(self, states):
        self.states = states

    async def get_state_by_source_id(self, config_id, source_id):
        return self.states.get(source_id)


def test_the_box_path_is_the_one_its_state_records():
    file = NS(name="a.txt", path_collection=NS(entries=[NS(name="All Files"), NS(name="sample-docs"), NS(name="Sub")]))
    assert BoxDetector._box_path(file) == "All Files/sample-docs/Sub/a.txt"


def test_selected_files_only():
    d = _detector(box_file_ids=["f1"])
    assert asyncio.run(d._parse_event(_event("ITEM_MODIFY", "f1", parent="999"))) is not None  # moved anywhere: still selected
    assert asyncio.run(d._parse_event(_event("ITEM_UPLOAD", "f2"))) is None                    # next to it, not selected


def test_followed_folders_and_a_file_moved_out():
    d = _detector()
    assert asyncio.run(d._parse_event(_event("ITEM_UPLOAD", "f2", parent="101"))).change_type == ChangeType.CREATE
    assert asyncio.run(d._parse_event(_event("ITEM_UPLOAD", "f2", parent="999"))) is None
    d.state_manager = _States({"f1": NS(source_path="All Files/m/Sub/a.txt", auto_sync=None)})
    gone = asyncio.run(d._parse_event(_event("ITEM_MOVE", "f1", parent="999")))
    assert gone.change_type == ChangeType.DELETE and gone.metadata.extra["file_id"] == "f1"
    d.state_manager = _States({"f1": NS(source_path="All Files/m/Sub/a.txt", auto_sync=False)})
    assert asyncio.run(d._parse_event(_event("ITEM_MOVE", "f1", parent="999"))) is None  # kept with its auto sync off


def test_the_refresh_compares_box_paths():
    class BoxDetector:  # what recovery.py keys on
        pass
    meta = NS(path="a.txt", extra={"file_id": "f1", "file_path": "All Files/m/Deeper/a.txt"})
    assert source_moved(BoxDetector(), meta, NS(source_path="All Files/m/Deep/a.txt"))
    assert not source_moved(BoxDetector(), meta, NS(source_path="All Files/m/Deeper/a.txt"))
