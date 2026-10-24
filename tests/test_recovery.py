"""Unit tests for catching up with missed events in the periodic refresh (incremental_updates/recovery.py)."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from incremental_updates.detectors import FileMetadata
from incremental_updates.recovery import (
    RecoveryTracker, as_datetime, guard_in_flight, predates_stream, process_args, source_changed,
    moved_out, source_moved,
)

pytestmark = pytest.mark.unit


def test_modification_times_in_every_format_the_sources_use():
    t = datetime(2026, 10, 18, 12, 30, 5, tzinfo=timezone.utc)
    for value in ("2026-10-18T12:30:05Z", "2026-10-18T12:30:05+00:00", "2026-10-18T12:30:05.000+0000",
                  "2026-10-18 12:30:05+00:00", "2026-10-18T12:30:05", t, t.timestamp(), t.timestamp() * 1000):
        assert as_datetime(value) == t, value
    assert as_datetime(None) is None and as_datetime("") is None and as_datetime("not a time") is None


def _meta(modified=None, ordinal=1, **extra):
    return FileMetadata(source_type="x", path="p", ordinal=ordinal, modified_timestamp=modified, extra=extra)


def test_changed_only_when_the_source_is_really_newer():
    state = SimpleNamespace(modified_timestamp="2026-10-18T12:30:05.000+0000", ordinal=5_000_000)
    assert not source_changed(_meta("2026-10-18 12:30:05.400000+00:00"), state)   # same time, other format
    assert source_changed(_meta("2026-10-18T13:00:00Z"), state)
    assert not source_changed(_meta("2026-10-18T12:00:00Z"), state)               # older
    assert not source_changed(_meta("garbled"), state)                            # can't tell: no
    # only a date recorded (an API ingest of GCS / Azure): changed on a later day only
    dated = SimpleNamespace(modified_timestamp="2026-07-13", ordinal=1)
    assert not source_changed(_meta("2026-07-13T04:18:06.609000+00:00"), dated)
    assert source_changed(_meta("2026-07-14T00:00:01+00:00"), dated)
    # a listing without times (S3): its ordinal is the object's LastModified
    assert source_changed(_meta(None, ordinal=9_000_000), SimpleNamespace(modified_timestamp=None, ordinal=5_000_000))
    assert not source_changed(_meta(None, ordinal=5_500_000), SimpleNamespace(modified_timestamp=None, ordinal=5_000_000))
    # a listing with times whose ordinal is "now" (Alfresco) never counts as changed by ordinal
    assert not source_changed(_meta("garbled", ordinal=10**18), SimpleNamespace(modified_timestamp=None, ordinal=1))


def test_a_change_waits_for_the_grace_period():
    tracker = RecoveryTracker(grace=0.05)
    key = ("cfg", "new", "a.txt")
    assert not tracker.ready(key)          # first refresh: noted
    assert not tracker.ready(key)          # still within the grace period
    import time
    time.sleep(0.06)
    assert tracker.ready(key)              # a later refresh takes it
    assert not tracker.ready(key)          # and starts over if it shows up again


def test_a_change_from_before_the_event_stream_is_taken_at_once():
    live = datetime(2026, 10, 18, 16, 28, 11, tzinfo=timezone.utc)
    detector = SimpleNamespace(_events_live_since=live)
    assert predates_stream(detector, _meta("2026-10-18T16:27:58.000+0000"))       # added before the stream
    assert not predates_stream(detector, _meta("2026-10-18T16:28:30.000+0000"))   # its event may still come
    assert not predates_stream(detector, _meta(None))                            # can't tell
    assert not predates_stream(SimpleNamespace(), _meta("2026-10-18T16:27:58Z"))  # stream not started yet

    class S3Detector:
        _events_live_since = live
    assert predates_stream(S3Detector(), _meta(None, ordinal=int(live.timestamp() * 1_000_000) - 5_000_000))


def test_a_file_listed_at_another_path_was_moved():
    class AlfrescoDetector: pass
    class NuxeoDetector: pass
    state = SimpleNamespace(source_path="/Shared/R/Deep/r2.txt")
    alf = lambda path: FileMetadata(source_type="alfresco", path=path, ordinal=1)
    assert source_moved(AlfrescoDetector(), alf("/Shared/R/Deeper/r2.txt"), state)       # its folder renamed
    assert not source_moved(AlfrescoDetector(), alf("/Shared/R/Deep/r2.txt"), state)
    assert not source_moved(AlfrescoDetector(), alf("/Company Home/Shared/R/Deep/r2.txt"), state)  # same place
    nux = FileMetadata(source_type="nuxeo", path="nuxeo://u1", ordinal=1, extra={"file_path": "/default-domain/ws/b.txt"})
    assert source_moved(NuxeoDetector(), nux, SimpleNamespace(source_path="/default-domain/ws/a.txt"))
    assert not source_moved(SimpleNamespace(), alf("/x"), state)                           # other sources: not told


def test_moved_out_only_when_it_moved_and_is_followed():
    state = SimpleNamespace(source_path="/Shared/M/Sub/new1.txt", auto_sync=None)
    assert moved_out(state, "/Shared/M/Other/new1.txt")
    assert not moved_out(state, "/Company Home/Shared/M/Sub/new1.txt")              # where it was
    assert not moved_out(SimpleNamespace(source_path="/Shared/M/Sub/new1.txt", auto_sync=False),
                         "/Shared/M/Other/new1.txt")                                 # kept, auto sync off
    assert not moved_out(None, "/x")


def test_backend_call_arguments_per_detector():
    def det(name, **attrs):
        return type(name, (), attrs)()
    drive = _meta(file_id="f1", file_name="a.txt")
    assert process_args(det("GoogleDriveDetector"), drive) == ("f1", "a.txt")
    box = FileMetadata(source_type="box", path="b.txt", ordinal=1, extra={"file_id": "9"})
    assert process_args(det("BoxDetector"), box) == ("9", "b.txt")
    s3 = FileMetadata(source_type="s3", path="bucket-1/docs/c.txt", ordinal=1, extra={"s3_uri": "s3://bucket-1/docs/c.txt"})
    assert process_args(det("S3Detector", bucket="bucket-1"), s3) == ("docs/c.txt",)
    alf = FileMetadata(source_type="alfresco", path="/Shared/T/d.txt", ordinal=1, extra={"node_id": "n1"})
    assert process_args(det("AlfrescoDetector"), alf) == ("n1", "d.txt", "/Shared/T/d.txt")
    nux = FileMetadata(source_type="nuxeo", path="nuxeo://u1", ordinal=1,
                       extra={"node_id": "u1", "name": "e.txt", "file_path": "/ws/e.txt"})
    assert process_args(det("NuxeoDetector"), nux) == ("u1", "e.txt", "/ws/e.txt")
    assert process_args(det("SomethingElse"), drive) is None


def test_one_ingest_per_file_at_a_time():
    calls = []

    class Detector:
        async def _process_via_backend(self, file_id, filename):
            calls.append(file_id)
            await asyncio.sleep(0.05)

    d = Detector()
    guard_in_flight(d)
    guard_in_flight(d)  # once only

    async def run():
        await asyncio.gather(d._process_via_backend("f1", "a"), d._process_via_backend("f1", "a"),
                             d._process_via_backend("f2", "b"))
        await d._process_via_backend("f1", "a")   # after the first finished: runs again
    asyncio.run(run())
    assert calls == ["f1", "f2", "f1"]
