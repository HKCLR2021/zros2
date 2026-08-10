"""Tests for ``zros2.asyncio.AsyncRobotClient`` liveliness query and watch."""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from zros2.asyncio import AsyncRobotClient
from zros2.asyncio._liveliness import _LIVELINESS_QUEUE_MAX
from zros2.discovery import LivelinessType, Qos


def _make_fake_liveliness() -> MagicMock:
    """Build a fake ``Liveliness`` context manager."""
    fake_liveliness = MagicMock()
    fake_liveliness.__enter__.return_value = fake_liveliness
    return fake_liveliness


class TestAsyncRobotClientQueryLiveliness:
    """``query_liveliness`` should query on a worker thread and return samples."""

    @pytest.mark.asyncio
    async def test_returns_alive_samples(self):
        """The samples from ``get`` should be returned as-is."""
        samples = [object(), object()]
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._liveliness.Liveliness") as liveliness_cls:
            fake_liveliness = _make_fake_liveliness()
            fake_liveliness.get.return_value = samples
            liveliness_cls.return_value = fake_liveliness
            result = await AsyncRobotClient(fake_proxy).query_liveliness(
                LivelinessType.SERVICE_SERVER
            )

        assert result == samples
        liveliness_cls.assert_called_once_with(
            fake_proxy, LivelinessType.SERVICE_SERVER, "*", "*", None
        )

    @pytest.mark.asyncio
    async def test_forwards_filters_and_namespace(self):
        """Filters and namespace should reach the liveliness construction."""
        qos = Qos.any()
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._liveliness.Liveliness") as liveliness_cls:
            liveliness_cls.return_value = _make_fake_liveliness()
            await AsyncRobotClient(fake_proxy).query_liveliness(
                LivelinessType.ACTION_SERVER,
                name="/fib",
                ros2_type="my_pkg/action/Fibonacci",
                qos=qos,
                namespace="robot_01",
            )

        liveliness_cls.assert_called_once_with(
            fake_proxy,
            LivelinessType.ACTION_SERVER,
            "robot_01/fib",
            "my_pkg/action/Fibonacci",
            qos,
        )

    @pytest.mark.asyncio
    async def test_runs_in_worker_thread(self):
        """The event loop should stay responsive while the query is in flight."""
        gate = threading.Event()
        fake_liveliness = _make_fake_liveliness()

        def _blocking_get() -> list[object]:
            gate.wait()
            return [object()]

        fake_liveliness.get.side_effect = _blocking_get
        with patch("zros2.asyncio._liveliness.Liveliness") as liveliness_cls:
            liveliness_cls.return_value = fake_liveliness
            query = asyncio.create_task(
                AsyncRobotClient(MagicMock()).query_liveliness(LivelinessType.PUBLISHER)
            )
            await asyncio.sleep(0)  # let the worker thread start
            assert not query.done()

            heartbeats = 0
            while not query.done() and heartbeats < 5:
                await asyncio.sleep(0.01)
                heartbeats += 1
            gate.set()
            assert len(await query) == 1
            assert heartbeats > 0  # the loop kept running while blocked


class TestAsyncRobotClientWatchLiveliness:
    """``watch_liveliness`` should bridge Zenoh-thread callbacks into the loop."""

    @pytest.mark.asyncio
    async def test_yields_subscribed_changes(self):
        """Samples pumped through the subscribe callback should be yielded."""
        sample = object()
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._liveliness.Liveliness") as liveliness_cls:
            liveliness_cls.return_value = _make_fake_liveliness()
            collected: list[object] = []

            async def _consume() -> None:
                async for s in AsyncRobotClient(fake_proxy).watch_liveliness(
                    LivelinessType.PUBLISHER
                ):
                    collected.append(s)
                    return

            consumer = asyncio.create_task(_consume())
            await asyncio.sleep(0)  # let the generator subscribe
            fake_liveliness = liveliness_cls.return_value
            callback = fake_liveliness.subscribe.call_args.args[0]
            callback(sample)
            await consumer

        assert collected == [sample]

    @pytest.mark.asyncio
    async def test_closes_subscription_on_early_exit(self):
        """Breaking out of the async-for should undeclare the subscriber."""
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._liveliness.Liveliness") as liveliness_cls:
            fake_liveliness = _make_fake_liveliness()
            fake_liveliness.__exit__.side_effect = lambda *args: fake_liveliness.close()
            liveliness_cls.return_value = fake_liveliness

            generator = AsyncRobotClient(fake_proxy).watch_liveliness(
                LivelinessType.PUBLISHER
            )

            async def _consume() -> None:
                async for _ in generator:
                    break

            consumer = asyncio.create_task(_consume())
            await asyncio.sleep(0)  # let the generator subscribe
            callback = fake_liveliness.subscribe.call_args.args[0]
            callback(object())
            await consumer
            await generator.aclose()

        fake_liveliness.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_changes_beyond_queue_capacity_are_dropped(self):
        """Changes beyond the queue capacity should be dropped, not raise."""
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._liveliness.Liveliness") as liveliness_cls:
            fake_liveliness = _make_fake_liveliness()
            liveliness_cls.return_value = fake_liveliness

            generator = AsyncRobotClient(fake_proxy).watch_liveliness(
                LivelinessType.PUBLISHER
            )
            count = 0

            async def _consume() -> None:
                nonlocal count
                async for _ in generator:
                    count += 1
                    if count == _LIVELINESS_QUEUE_MAX:
                        return

            consumer = asyncio.create_task(_consume())
            await asyncio.sleep(0)  # let the generator subscribe
            callback = fake_liveliness.subscribe.call_args.args[0]
            for _ in range(_LIVELINESS_QUEUE_MAX * 2):
                callback(object())
            await consumer
            await generator.aclose()

        assert count == _LIVELINESS_QUEUE_MAX
