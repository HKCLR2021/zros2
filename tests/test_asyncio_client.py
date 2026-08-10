"""Tests for the ``zros2.asyncio.AsyncRobotClient`` constructor normalization."""

from unittest.mock import MagicMock

from zros2 import ZRosClient
from zros2.asyncio import AsyncRobotClient


class TestAsyncRobotClientConstruction:
    """``AsyncRobotClient`` should normalize any input to a session proxy once."""

    def test_keeps_bare_session_proxy(self):
        """A bare session proxy should be stored as-is."""
        fake_proxy = MagicMock()

        assert AsyncRobotClient(fake_proxy)._session is fake_proxy

    def test_unwraps_zros_client_to_session(self):
        """A ZRosClient should be unwrapped to its session proxy."""
        fake_proxy = MagicMock()
        fake_client = MagicMock(spec=ZRosClient)
        fake_client.session = fake_proxy

        assert AsyncRobotClient(fake_client)._session is fake_proxy

    def test_capabilities_are_exposed_as_methods(self):
        """The public surface should be the class plus the action events."""
        from zros2 import asyncio as aio_zros2

        assert set(aio_zros2.__all__) == {
            "ActionFeedback",
            "ActionResult",
            "AsyncPublisher",
            "AsyncRobotClient",
            "AsyncSubscriber",
        }
        for name in (
            "invoke_service",
            "invoke_action",
            "query_liveliness",
            "watch_liveliness",
            "create_publisher",
            "create_subscriber",
        ):
            assert callable(getattr(AsyncRobotClient, name))
