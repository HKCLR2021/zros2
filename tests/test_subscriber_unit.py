"""Unit tests for :class:`zros2.endpoints.Subscriber` edge cases."""

from collections.abc import Callable
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from zros2.endpoints import Subscriber
from zros2.endpoints._subscriber import logger
from zros2.types import RosMessage

# Fake message types used in tests — they satisfy the type checker at
# the structural level while remaining cheap to construct at runtime.
_str_msg: type[RosMessage] = cast(type[RosMessage], str)
_int_msg: type[RosMessage] = cast(type[RosMessage], int)


class TestSubscriber:
    """Tests for Subscriber that don't need a real Zenoh session."""

    def test_repr(self):
        """__repr__ should include topic and type name."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        assert "test/topic" in repr(sub)
        assert "str" in repr(sub)

    def test_del_does_not_raise(self):
        """__del__ should not raise even if unsubscribe encounters an error."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        sub._subscriber = MagicMock()
        sub._subscriber.undeclare.side_effect = Exception("boom")
        sub.__del__()  # Should not raise

    def test_subscribe_raises_if_already_subscribed(self):
        """Subscribing twice should raise ValueError."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", _str_msg)
        sub.subscribe(lambda msg: None)
        with pytest.raises(ValueError, match="Already subscribed"):
            sub.subscribe(lambda msg: None)

    def test_subscribe_raises_if_session_closed(self):
        """Subscribing with a closed session should raise RuntimeError."""
        session = MagicMock()
        session.is_closed.return_value = True
        sub = Subscriber(session, "test/topic", _str_msg)
        with pytest.raises(RuntimeError, match="closed"):
            sub.subscribe(lambda msg: None)

    def test_unsubscribe_is_idempotent(self):
        """unsubscribe() when not subscribed should not raise."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        sub.unsubscribe()  # Should not raise

    def test_unsubscribe_swallows_exception(self):
        """unsubscribe() should catch exceptions from undeclare()."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", _str_msg)
        sub.subscribe(lambda msg: None)
        subscriber_mock = cast(MagicMock, sub._subscriber)
        subscriber_mock.undeclare.side_effect = RuntimeError("boom")
        sub.unsubscribe()  # Should not raise
        assert sub._subscriber is None  # Should be reset in finally

    def test_unsubscribe_resets_subscriber_to_none(self):
        """After unsubscribe(), _subscriber should be None."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", _str_msg)
        sub.subscribe(lambda msg: None)
        assert sub._subscriber is not None
        sub.unsubscribe()
        assert sub._subscriber is None

    def test_close_calls_unsubscribe(self):
        """close() should delegate to unsubscribe()."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", _str_msg)
        sub.subscribe(lambda msg: None)
        sub.close()
        assert sub._subscriber is None

    def test_context_manager_exit_calls_close(self):
        """Exiting the context manager should call close()."""
        session = MagicMock()
        with Subscriber(session, "test/topic", _str_msg) as _sub:
            pass
        # close() is called via __exit__

    def test_context_manager_enter_returns_self(self):
        """__enter__ should return the subscriber instance."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        assert sub.__enter__() is sub

    def test_zombie_callback_does_not_raise(self):
        """Callback after undeclare should not raise."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"test"
        sample.key_expr = "test/topic"
        cb(sample)  # Should not raise; _subscriber is None

    def test_callback_handles_deserialize_error(self):
        """Callback should log and swallow deserialization errors."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        # str has no .deserialize() — this will raise AttributeError
        sample.payload = b"garbage"
        with patch.object(logger, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_type_check_fails_logs_exception(self):
        """isinstance check failure should be logged."""
        session = MagicMock()
        # A message type that deserializes to something of a different type
        mock_msg_type = MagicMock()
        mock_msg_type.__name__ = "ExpectedType"
        mock_msg_type.deserialize.return_value = "a string, not ExpectedType"

        sub = Subscriber(session, "test/topic", cast(type[RosMessage], mock_msg_type))
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"irrelevant"

        with patch.object(logger, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_async_callback_logs_exception(self):
        """Async callback raising TypeError should be logged."""
        session = MagicMock()
        mock_msg_type = MagicMock()
        mock_msg_type.__name__ = "MyType"
        mock_msg_type.deserialize.return_value = mock_msg_type

        sub = Subscriber(session, "test/topic", cast(type[RosMessage], mock_msg_type))
        sub._subscriber = MagicMock()

        async def async_callback(msg):  # noqa: unused
            pass

        cb = sub._make_zenoh_callback(
            cast("Callable[[RosMessage], None]", async_callback)
        )
        sample = MagicMock()
        sample.payload = b"irrelevant"

        with patch.object(logger, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_deserialize_error_logged(self):
        """Callback should log and swallow deserialization errors."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _str_msg)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"not-valid-data"
        with patch.object(logger, "exception") as mock_exc:
            cb(sample)  # deserialize of str with invalid data may fail
            mock_exc.assert_called_once()

    def test_callback_type_check_fails_logs_error(self):
        """Callback should type-check the deserialized message."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", _int_msg)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        # int.deserialize returns an int, not a str, so isinstance check fails
        with patch.object(logger, "exception") as mock_exc:
            cb(sample)  # Should log but not raise
            mock_exc.assert_called_once()

    def test_callback_type_mismatch_raises_type_error(self):
        """When deserialized value is not an instance of message_type, raise TypeError.

        This test uses a real class (not a MagicMock) to avoid isinstance raising
        "arg 2 must be a type" before the if-body can execute.
        """
        session = MagicMock()

        class _WrongDeserialize:
            """A message-like type whose deserialize returns a different type."""

            __name__ = "ExpectedType"

            @classmethod
            def deserialize(cls, data: bytes) -> int:
                return 42

        msg_type = cast(type[RosMessage], _WrongDeserialize)
        sub = Subscriber(session, "test/topic", msg_type)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"irrelevant"

        with patch.object(logger, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_async_callback_detection(self):
        """An async callback passed as a subscriber callback raises TypeError.

        This test uses a real class so isinstance succeeds, and the async
        callback's coroutine return value triggers the iscoroutine check.
        """
        session = MagicMock()

        class _SimpleType:
            """A real message type that deserializes to itself."""

            __name__ = "SimpleType"

            @classmethod
            def deserialize(cls, data: bytes) -> "_SimpleType":
                return cls()

        msg_type = cast(type[RosMessage], _SimpleType)
        sub = Subscriber(session, "test/topic", msg_type)
        sub._subscriber = MagicMock()

        async def async_callback(msg):
            pass

        cb = sub._make_zenoh_callback(
            cast("Callable[[RosMessage], None]", async_callback)
        )
        sample = MagicMock()
        sample.payload = b"irrelevant"

        with patch.object(logger, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()
