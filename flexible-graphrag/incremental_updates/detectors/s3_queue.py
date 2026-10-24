"""One SQS reader per queue, shared by every S3 auto sync that uses the queue.

An SQS message goes to one receiver, and each S3Detector used to receive from the queue itself and
delete every message -- also those for another sync's prefix or bucket, which that sync then never
saw (only its periodic refresh caught the change, minutes later). The fan-out receives each message
once, hands a copy to every registered detector (each filters by its own bucket and prefix), and
then deletes it.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class S3QueueFanout:
    _instances: Dict[str, "S3QueueFanout"] = {}

    @classmethod
    def get(cls, queue_url: str, sqs_client) -> "S3QueueFanout":
        fanout = cls._instances.get(queue_url)
        if fanout is None:
            fanout = cls._instances[queue_url] = cls(queue_url, sqs_client)
        return fanout

    def __init__(self, queue_url: str, sqs_client):
        self.queue_url = queue_url
        self.sqs_client = sqs_client
        self._inboxes: Dict[int, asyncio.Queue] = {}
        self._task: Optional[asyncio.Task] = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="s3-sqs")

    def register(self, detector) -> asyncio.Queue:
        inbox = self._inboxes.setdefault(id(detector), asyncio.Queue())
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())
        logger.info(f"S3 queue {self.queue_url}: {len(self._inboxes)} sync(s) reading it")
        return inbox

    def unregister(self, detector) -> None:
        self._inboxes.pop(id(detector), None)
        if not self._inboxes and self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while self._inboxes:
            try:
                response = await asyncio.wait_for(loop.run_in_executor(self._executor, lambda: self.sqs_client.receive_message(
                    QueueUrl=self.queue_url, MaxNumberOfMessages=10, WaitTimeSeconds=20,
                    AttributeNames=["ApproximateReceiveCount"])), timeout=25.0)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"S3 queue {self.queue_url}: receive failed: {e}")
                await asyncio.sleep(5)
                continue
            for message in response.get("Messages", []):
                for inbox in list(self._inboxes.values()):
                    inbox.put_nowait(message)
                try:
                    await loop.run_in_executor(self._executor, lambda h=message["ReceiptHandle"]: self.sqs_client.delete_message(
                        QueueUrl=self.queue_url, ReceiptHandle=h))
                except Exception as e:
                    logger.error(f"S3 queue {self.queue_url}: failed to delete a message: {e}")
