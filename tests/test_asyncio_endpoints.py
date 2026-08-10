"""Tests for the asyncio publisher / subscriber endpoints."""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from tests._test_msgs import IntMsg
from zros2.asyncio import AsyncPublisher, AsyncSubscriber
from zros2.asyncio._subscriber import _SUBSCRIBER_QUEUE_MAX


class TestAsyncPublisher:
    """``AsyncPublisher`` should offload blocking work to worker threads."""

    def test_constructor_delegates_to_sync_publisher(self):
        """The sync Publisher should be created with the given arguments."""
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._publisher.Publisher") as publisher_cls:
            AsyncPublisher(fake_proxy, "/topic", IntMsg)
            publisher_cls.assert_called_once_with(fake_proxy, "/topic", IntMsg)

    @pytest.mark.asyncio
    async def test_publish_runs_in_worker_thread(self):
        """The event loop should stay responsive while publish blocks."""
        gate = threading.Event()
        with patch("zros2.asyncio._publisher.Publisher") as publisher_cls:
            fake_publisher = MagicMock()
            fake_publisher.publish.side_effect = lambda data: gate.wait()
            publisher_cls.return_value = fake_publisher

            publisher = AsyncPublisher(MagicMock(), "/topic", IntMsg)
            message = IntMsg(data=7)
            publish_task = asyncio.create_task(publisher.publish(message))
            await asyncio.sleep(0)  # let the worker thread start
            assert not publish_task.done()

            heartbeats = 0
            while not publish_task.done() and heartbeats < 5:
                await asyncio.sleep(0.01)
                heartbeats += 1
            gate.set()
            await publish_task
            assert heartbeats > 0  # the loop kept running while blocked

        fake_publisher.publish.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_aclose_undeclares_publisher(self):
        """aclose should undeclare the wrapped publisher."""
        with patch("zros2.asyncio._publisher.Publisher") as publisher_cls:
            fake_publisher = MagicMock()
            publisher_cls.return_value = fake_publisher

            publisher = AsyncPublisher(MagicMock(), "/topic", IntMsg)
            await publisher.aclose()
            await publisher.aclose()  # idempotent — must not raise

        fake_publisher.destroy.assert_called()

    @pytest.mark.asyncio
    async def test_context_manager_closes(self):
        """Exiting the async context manager should undeclare."""
        with patch("zros2.asyncio._publisher.Publisher") as publisher_cls:
            fake_publisher = MagicMock()
            publisher_cls.return_value = fake_publisher

            async with AsyncPublisher(MagicMock(), "/topic", IntMsg):
                pass

        fake_publisher.destroy.assert_called_once_with()


class TestAsyncSubscriber:
    """``AsyncSubscriber`` should bridge Zenoh-thread callbacks into the loop."""

    def _make_subscriber(self) -> tuple[AsyncSubscriber[IntMsg], MagicMock]:
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._subscriber.Subscriber") as subscriber_cls:
            fake_subscriber = MagicMock()
            subscriber_cls.return_value = fake_subscriber
            subscriber = AsyncSubscriber(fake_proxy, "/topic", IntMsg)
        return subscriber, fake_subscriber

    @pytest.mark.asyncio
    async def test_yields_subscribed_messages(self):
        """Messages pumped through the subscribe callback should be yielded."""
        subscriber, fake_subscriber = self._make_subscriber()
        message = IntMsg(data=1)
        collected: list[IntMsg] = []

        async def _consume() -> None:
            async for msg in subscriber:
                collected.append(msg)
                return

        consumer = asyncio.create_task(_consume())
        await asyncio.sleep(0)  # let the first __anext__ subscribe
        callback = fake_subscriber.subscribe.call_args.args[0]
        callback(message)
        await consumer

        assert collected == [message]

    @pytest.mark.asyncio
    async def test_subscribe_is_idempotent(self):
        """Calling subscribe() twice should declare only once."""
        subscriber, fake_subscriber = self._make_subscriber()

        await subscriber.subscribe()
        await subscriber.subscribe()

        fake_subscriber.subscribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_aclose_unsubscribes(self):
        """aclose should undeclare the subscription and end the stream."""
        subscriber, fake_subscriber = self._make_subscriber()
        await subscriber.subscribe()

        await subscriber.aclose()
        await subscriber.aclose()  # idempotent

        fake_subscriber.unsubscribe.assert_called_once()
        collected = []

        async def _consume() -> None:
            async for _ in subscriber:
                collected.append(_)

        await _consume()
        assert collected == []

    @pytest.mark.asyncio
    async def test_aclose_releases_pending_wait(self):
        """A pending __anext__ should end with StopAsyncIteration on aclose."""
        subscriber, _ = self._make_subscriber()

        pending = asyncio.create_task(subscriber.__anext__())
        await asyncio.sleep(0)  # let it subscribe and await the queue
        await subscriber.aclose()
        with pytest.raises(StopAsyncIteration):
            await pending

    @pytest.mark.asyncio
    async def test_messages_beyond_queue_capacity_are_dropped(self):
        """Messages beyond the queue capacity should be dropped, not raise."""
        subscriber, fake_subscriber = self._make_subscriber()
        count = 0

        async def _consume() -> None:
            nonlocal count
            async for _ in subscriber:
                count += 1
                if count == _SUBSCRIBER_QUEUE_MAX:
                    return

        consumer = asyncio.create_task(_consume())
        await asyncio.sleep(0)  # let the first __anext__ subscribe
        callback = fake_subscriber.subscribe.call_args.args[0]
        for _ in range(_SUBSCRIBER_QUEUE_MAX * 2):
            callback(IntMsg())
        await consumer
        await subscriber.aclose()

        assert count == _SUBSCRIBER_QUEUE_MAX

    @pytest.mark.asyncio
    async def test_messages_after_close_are_dropped(self):
        """Callbacks firing after aclose should be ignored, not raise."""
        subscriber, fake_subscriber = self._make_subscriber()
        await subscriber.subscribe()
        await subscriber.aclose()

        callback = fake_subscriber.subscribe.call_args.args[0]
        callback(IntMsg())  # must not raise

    @pytest.mark.asyncio
    async def test_context_manager_subscribes_and_closes(self):
        """The async context manager should subscribe eagerly and close."""
        subscriber, fake_subscriber = self._make_subscriber()

        async with subscriber:
            fake_subscriber.subscribe.assert_called_once()

        fake_subscriber.unsubscribe.assert_called_once()


class TestAsyncRobotClientPubSub:
    """``AsyncRobotClient`` factory methods should forward namespaces."""

    def test_create_publisher_joins_namespace(self):
        """The topic should be namespaced and the endpoint returned."""
        from zros2.asyncio import AsyncRobotClient

        fake_proxy = MagicMock()
        with patch("zros2.asyncio._async_client.AsyncPublisher") as publisher_cls:
            publisher_cls.return_value = "publisher"
            result = AsyncRobotClient(fake_proxy).create_publisher(
                "/chatter", IntMsg, namespace="robot_01"
            )

        assert result == "publisher"
        publisher_cls.assert_called_once_with(fake_proxy, "robot_01/chatter", IntMsg)

    def test_create_subscriber_joins_namespace(self):
        """The topic should be namespaced and the endpoint returned."""
        from zros2.asyncio import AsyncRobotClient

        fake_proxy = MagicMock()
        with patch("zros2.asyncio._async_client.AsyncSubscriber") as subscriber_cls:
            subscriber_cls.return_value = "subscriber"
            result = AsyncRobotClient(fake_proxy).create_subscriber(
                "/battery", IntMsg, namespace="robot_01"
            )

        assert result == "subscriber"
        subscriber_cls.assert_called_once_with(fake_proxy, "robot_01/battery", IntMsg)
