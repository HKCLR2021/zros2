"""Tests for ``zros2.asyncio.AsyncRobotClient.invoke_service``."""

import asyncio
import threading
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from zros2.asyncio import AsyncRobotClient
from zros2.exceptions import ServiceInvokeException, ServiceNotAvailableException
from zros2.types import RosService


class _FakeServiceType:
    """Placeholder service type — ``ServiceClient`` is mocked away."""


def _mock_service() -> type[RosService[Any, Any]]:
    """Return the placeholder type cast to the RosService protocol."""
    return cast(type[RosService[Any, Any]], _FakeServiceType)


def _make_fake_service(response: Any = None) -> MagicMock:
    """Build a fake service client whose ``send_request`` returns ``response``."""
    fake_service = MagicMock()
    fake_service.send_request.return_value = response
    return fake_service


class TestAsyncRobotClientService:
    """``invoke_service`` over the threaded ``ServiceClient`` endpoint."""

    @pytest.mark.asyncio
    async def test_returns_response(self):
        """The response from send_request should be returned as-is."""
        response = object()
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._service.ServiceClient") as service_cls:
            service_cls.return_value = _make_fake_service(response=response)
            result = await AsyncRobotClient(fake_proxy).invoke_service(
                "test/srv", _mock_service()
            )

        assert result is response
        service_cls.assert_called_once_with(fake_proxy, "test/srv", _mock_service())

    @pytest.mark.asyncio
    async def test_forwards_body_timeout_and_namespace(self):
        """Arguments should reach the endpoint construction and send_request."""
        body = object()
        fake_proxy = MagicMock()
        with patch("zros2.asyncio._service.ServiceClient") as service_cls:
            service_cls.return_value = _make_fake_service()
            await AsyncRobotClient(fake_proxy).invoke_service(
                "test/srv",
                _mock_service(),
                body=body,
                timeout=5000,
                namespace="robot_01",
            )

        service_cls.assert_called_once_with(
            fake_proxy, "robot_01/test/srv", _mock_service()
        )
        service_cls.return_value.send_request.assert_called_once_with(body, 5000)

    @pytest.mark.asyncio
    async def test_runs_in_worker_thread(self):
        """The event loop should stay responsive while the call is in flight."""
        gate = threading.Event()
        fake_service = _make_fake_service()

        def _blocking_send(payload: Any, timeout: Any) -> str:
            gate.wait()
            return "done"

        fake_service.send_request.side_effect = _blocking_send
        with patch("zros2.asyncio._service.ServiceClient") as service_cls:
            service_cls.return_value = fake_service
            invocation = asyncio.create_task(
                AsyncRobotClient(MagicMock()).invoke_service("test/srv", _mock_service())
            )
            await asyncio.sleep(0)  # let the worker thread start
            assert not invocation.done()

            heartbeats = 0
            while not invocation.done() and heartbeats < 5:
                await asyncio.sleep(0.01)
                heartbeats += 1
            gate.set()
            assert (await invocation) == "done"
            assert heartbeats > 0  # the loop kept running while blocked

    @pytest.mark.asyncio
    async def test_service_exceptions_propagate(self):
        """Service exceptions from send_request should propagate unchanged."""
        fake_service = _make_fake_service()
        fake_service.send_request.side_effect = ServiceNotAvailableException("gone")
        with patch("zros2.asyncio._service.ServiceClient") as service_cls:
            service_cls.return_value = fake_service

            with pytest.raises(ServiceNotAvailableException, match="gone"):
                await AsyncRobotClient(MagicMock()).invoke_service(
                    "test/srv", _mock_service()
                )

    @pytest.mark.asyncio
    async def test_invoke_exceptions_propagate(self):
        """ServiceInvokeException from send_request should propagate unchanged."""
        fake_service = _make_fake_service()
        fake_service.send_request.side_effect = ServiceInvokeException("nope")
        with patch("zros2.asyncio._service.ServiceClient") as service_cls:
            service_cls.return_value = fake_service

            with pytest.raises(ServiceInvokeException, match="nope"):
                await AsyncRobotClient(MagicMock()).invoke_service(
                    "test/srv", _mock_service()
                )
