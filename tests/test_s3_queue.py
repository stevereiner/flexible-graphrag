"""Unit test for the shared SQS reader (incremental_updates/detectors/s3_queue.py): every S3 sync on a
queue gets each message, and the message is deleted once."""
import asyncio

import pytest

from incremental_updates.detectors.s3_queue import S3QueueFanout

pytestmark = pytest.mark.unit


class _Sqs:
    def __init__(self, messages):
        self.messages = list(messages)
        self.deleted = []

    def receive_message(self, **kw):
        batch, self.messages = self.messages[:10], self.messages[10:]
        return {"Messages": batch}

    def delete_message(self, QueueUrl, ReceiptHandle):
        self.deleted.append(ReceiptHandle)


def test_each_sync_on_the_queue_gets_every_message_and_it_is_deleted_once():
    sqs = _Sqs([{"ReceiptHandle": "h1", "Body": "{}"}, {"ReceiptHandle": "h2", "Body": "{}"}])
    fanout = S3QueueFanout("https://sqs/q-test", sqs)
    a, b = object(), object()

    async def run():
        inbox_a, inbox_b = fanout.register(a), fanout.register(b)
        got_a = [await asyncio.wait_for(inbox_a.get(), 5) for _ in range(2)]
        got_b = [await asyncio.wait_for(inbox_b.get(), 5) for _ in range(2)]
        await asyncio.sleep(0.2)
        fanout.unregister(a)
        fanout.unregister(b)
        return got_a, got_b

    got_a, got_b = asyncio.run(run())
    assert [m["ReceiptHandle"] for m in got_a] == ["h1", "h2"] == [m["ReceiptHandle"] for m in got_b]
    assert sorted(sqs.deleted) == ["h1", "h2"]
