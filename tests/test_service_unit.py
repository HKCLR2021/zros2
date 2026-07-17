"""Unit tests for :class:`zros2._service.ServiceClient` edge cases."""

from unittest.mock import MagicMock, patch

import pytest
import zenoh

from zros2._service import ServiceClient
from zros2.exceptions import ServiceInvokeException, ServiceNotAvailableException

from ._test_msgs import IntMsg, PairMsg


class _ExampleService:
    """Minimal service type matching expected protocol."""
    Request = IntMsg
    Response = PairMsg


class TestServiceClient:
    """Tests for ServiceClient that don't need a real Zenoh session."""

    def test_send_request_raises_if_session_closed(self):
        """Sending a request with a closed session should raise RuntimeError."""
        session = MagicMock()
        session.is_closed.return_value = True
        client = ServiceClient(session, "test/srv", _ExampleService)
        with pytest.raises(RuntimeError, match="closed"):
            client.send_request(IntMsg(data=1), timeout=100)

    def test_send_request_with_none_payload(self):
        """Sending a request with None payload should not serialize."""
        session = MagicMock()
        session.is_closed.return_value = False
        # Mock the get call to return an empty iterator (service unavailable)
        session.get.return_value = iter([])
        client = ServiceClient(session, "test/srv", _ExampleService)
        with pytest.raises(ServiceNotAvailableException):
            client.send_request(None, timeout=100)
        # payload should be None (not serialized)
        session.get.assert_called_once()
        assert session.get.call_args[1]["payload"] is None

    def test_send_request_handles_error_reply(self):
        """A reply with ok=False should raise ServiceInvokeException."""
        session = MagicMock()
        session.is_closed.return_value = False
        # Create a mock error reply
        err_reply = MagicMock()
        err_reply.ok = False
        err_reply.err.payload.to_string.return_value = "test error"
        session.get.return_value = iter([err_reply])

        client = ServiceClient(session, "test/srv", _ExampleService)
        with pytest.raises(ServiceInvokeException, match="test error"):
            client.send_request(IntMsg(data=1), timeout=100)

    def test_send_request_handles_zenoh_error(self):
        """A zenoh.ZError from get() should raise ServiceInvokeException."""
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.side_effect = zenoh.ZError("connection lost")

        client = ServiceClient(session, "test/srv", _ExampleService)
        with pytest.raises(ServiceInvokeException, match="connection lost"):
            client.send_request(IntMsg(data=1), timeout=100)

    def test_send_request_handles_empty_replies(self):
        """No replies should raise ServiceNotAvailableException."""
        session = MagicMock()
        session.is_closed.return_value = False
        session.get.return_value = iter([])

        client = ServiceClient(session, "test/srv", _ExampleService)
        with pytest.raises(ServiceNotAvailableException):
            client.send_request(IntMsg(data=1), timeout=100)

    def test_send_request_success(self):
        """A successful reply should be deserialized and returned."""
        session = MagicMock()
        session.is_closed.return_value = False

        # Build a real serialized response
        payload_bytes = PairMsg(value=42, label="ok").serialize()

        # Mock a successful reply — need to set .ok to an object with .payload
        ok_reply = MagicMock()
        ok_reply.ok = MagicMock()
        ok_reply.ok.payload = payload_bytes
        session.get.return_value = iter([ok_reply])

        client = ServiceClient(session, "test/srv", _ExampleService)
        result = client.send_request(IntMsg(data=99), timeout=100)

        assert isinstance(result, PairMsg)
        assert result.value == 42
        assert result.label == "ok"
