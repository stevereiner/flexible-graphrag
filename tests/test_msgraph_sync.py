"""Unit tests for OneDrive / SharePoint auto sync (MicrosoftGraphDetector): folder scope of the
drive-wide delta stream, documents moved out, and what the periodic refresh compares."""
import asyncio
from types import SimpleNamespace

import pytest

from incremental_updates.detectors import FileMetadata
from incremental_updates.detectors.base import ChangeType
from incremental_updates.detectors.msgraph_detector import MicrosoftGraphDetector
from incremental_updates.recovery import process_args, source_moved

pytestmark = pytest.mark.unit


def _detector(**config):
    return MicrosoftGraphDetector({"client_id": "c", "client_secret": "s", "tenant_id": "t",
                                   "site_name": "site", **config})


def _item(name, folder, modified="2026-10-18T12:00:05+00:00"):
    return {"id": f"id-{name}", "name": name, "file": {"mimeType": "text/plain"},
            "createdDateTime": "2026-10-18T12:00:00+00:00", "lastModifiedDateTime": modified,
            "parentReference": {"path": f"/drives/d1/root:{folder}"}}


def test_only_the_sync_folder_is_followed():
    d = _detector(folder_path="test")
    assert d._base_path() == "/test"
    assert d._in_folder("/test/a.txt") and d._in_folder("/test/Sub/b.txt")
    assert not d._in_folder("/other/a.txt") and not d._in_folder("/testing/a.txt") and not d._in_folder(None)
    assert _detector()._in_folder("/anything/a.txt")  # the whole drive


def test_delta_items_carry_their_drive_path():
    event = _detector(folder_path="test")._parse_drive_item(_item("a.txt", "/test/Sub"))
    assert event.metadata.path.endswith("://id-a.txt")
    assert event.metadata.extra["file_path"] == "/test/Sub/a.txt" and event.metadata.extra["folder_path"] == "/test/Sub"


class _States:
    def __init__(self, states):
        self.states = states

    async def get_state(self, doc_id):
        return self.states.get(doc_id)


def test_a_followed_document_moved_out_of_the_folder_is_removed():
    d = _detector(folder_path="test")
    d.config_id = "cfg"
    event = d._parse_drive_item(_item("a.txt", "/elsewhere"))
    d.state_manager = _States({f"cfg:{event.metadata.path}": SimpleNamespace(source_path="/test/a.txt", auto_sync=None)})
    gone = asyncio.run(d._moved_out_event(event))
    assert gone.change_type == ChangeType.DELETE and gone.metadata.extra["file_id"] == "id-a.txt"
    d.state_manager = _States({})                                       # not followed: nothing to remove
    assert asyncio.run(d._moved_out_event(event)) is None
    d.state_manager = _States({f"cfg:{event.metadata.path}": SimpleNamespace(source_path="/test/a.txt", auto_sync=False)})
    assert asyncio.run(d._moved_out_event(event)) is None               # kept with its auto sync off


def test_the_refresh_compares_paths_and_re_ingests_with_the_detector_arguments():
    class MicrosoftGraphDetector:  # what recovery.py keys on
        pass
    meta = FileMetadata(source_type="msgraph", path="sharepoint://id-a", ordinal=1, extra={
        "file_id": "id-a", "file_name": "a.txt", "file_path": "/test/Sub/a.txt", "folder_path": "/test/Sub"})
    assert process_args(MicrosoftGraphDetector(), meta) == ("id-a", "a.txt", "/test/Sub/a.txt", "/test/Sub")
    assert source_moved(MicrosoftGraphDetector(), meta, SimpleNamespace(source_path="/test/a.txt"))
    assert not source_moved(MicrosoftGraphDetector(), meta, SimpleNamespace(source_path="/test/Sub/a.txt"))


def test_without_change_polling_every_change_is_the_refreshs():
    d = _detector(folder_path="test", enable_change_polling=False)
    d._running, d.graph_client = True, object()  # started

    async def run():
        async for _ in d.get_changes():
            pass
    asyncio.run(run())
    assert d._events_live_since.year == 9999
