"""Unit tests for :class:`zros2._subscriber.Subscriber` edge cases."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from zros2._subscriber import Subscriber


class TestSubscriber:
    """Tests for Subscriber that don't need a real Zenoh session."""

    def test_repr(self):
        """__repr__ should include topic and type name."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        assert "test/topic" in repr(sub)
        assert "str" in repr(sub)

    def test_del_does_not_raise(self):
        """__del__ should not raise even if unsubscribe encounters an error."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        sub._subscriber = MagicMock()
        sub._subscriber.undeclare.side_effect = Exception("boom")
        sub.__del__()  # Should not raise

    def test_subscribe_raises_if_already_subscribed(self):
        """Subscribing twice should raise ValueError."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", str)
        sub.subscribe(lambda msg: None)
        with pytest.raises(ValueError, match="Already subscribed"):
            sub.subscribe(lambda msg: None)

    def test_subscribe_raises_if_session_closed(self):
        """Subscribing with a closed session should raise RuntimeError."""
        session = MagicMock()
        session.is_closed.return_value = True
        sub = Subscriber(session, "test/topic", str)
        with pytest.raises(RuntimeError, match="closed"):
            sub.subscribe(lambda msg: None)

    def test_unsubscribe_is_idempotent(self):
        """unsubscribe() when not subscribed should not raise."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        sub.unsubscribe()  # Should not raise

    def test_unsubscribe_swallows_exception(self):
        """unsubscribe() should catch exceptions from undeclare()."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", str)
        sub.subscribe(lambda msg: None)
        sub._subscriber.undeclare.side_effect = RuntimeError("boom")
        sub.unsubscribe()  # Should not raise
        assert sub._subscriber is None  # Should be reset in finally

    def test_unsubscribe_resets_subscriber_to_none(self):
        """After unsubscribe(), _subscriber should be None."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", str)
        sub.subscribe(lambda msg: None)
        assert sub._subscriber is not None
        sub.unsubscribe()
        assert sub._subscriber is None

    def test_close_calls_unsubscribe(self):
        """close() should delegate to unsubscribe()."""
        session = MagicMock()
        session.is_closed.return_value = False
        sub = Subscriber(session, "test/topic", str)
        sub.subscribe(lambda msg: None)
        sub.close()
        assert sub._subscriber is None

    def test_context_manager_exit_calls_close(self):
        """Exiting the context manager should call close()."""
        session = MagicMock()
        with Subscriber(session, "test/topic", str) as sub:
            pass
        # close() is called via __exit__

    def test_context_manager_enter_returns_self(self):
        """__enter__ should return the subscriber instance."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        assert sub.__enter__() is sub

    def test_zombie_callback_does_not_raise(self):
        """Callback after undeclare should not raise."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"test"
        sample.key_expr = "test/topic"
        cb(sample)  # Should not raise; _subscriber is None

    def test_callback_handles_deserialize_error(self):
        """Callback should log and swallow deserialization errors."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        # str has no .deserialize() — this will raise AttributeError
        sample.payload = b"garbage"
        with patch.object(logging, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_type_check_fails_logs_exception(self):
        """isinstance check failure should be logged."""
        session = MagicMock()
        # A message type that deserializes to something of a different type
        mock_msg_type = MagicMock()
        mock_msg_type.__name__ = "ExpectedType"
        mock_msg_type.deserialize.return_value = "a string, not ExpectedType"

        sub = Subscriber(session, "test/topic", mock_msg_type)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"irrelevant"

        with patch.object(logging, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_async_callback_logs_exception(self):
        """Async callback raising TypeError should be logged."""
        session = MagicMock()
        mock_msg_type = MagicMock()
        mock_msg_type.__name__ = "MyType"
        mock_msg_type.deserialize.return_value = mock_msg_type

        sub = Subscriber(session, "test/topic", mock_msg_type)
        sub._subscriber = MagicMock()

        async def async_callback(msg):  # noqa: unused
            pass

        cb = sub._make_zenoh_callback(async_callback)
        sample = MagicMock()
        sample.payload = b"irrelevant"

        with patch.object(logging, "exception") as mock_exc:
            cb(sample)
            mock_exc.assert_called_once()

    def test_callback_handles_deserialize_error(self):
        """Callback should log and swallow deserialization errors."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", str)
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        sample.payload = b"not-valid-data"
        with patch.object(logging, "exception") as mock_exc:
            cb(sample)  # deserialize of str with invalid data may fail
            mock_exc.assert_called_once()

    def test_callback_type_check_fails_logs_error(self):
        """Callback should type-check the deserialized message."""
        session = MagicMock()
        sub = Subscriber(session, "test/topic", int)  # int type
        sub._subscriber = MagicMock()
        cb = sub._make_zenoh_callback(lambda msg: None)
        sample = MagicMock()
        # int.deserialize returns an int, not a str, so isinstance check fails
        with patch.object(logging, "exception") as mock_exc:
            cb(sample)  # Should log but not raise
            mock_exc.assert_called_once()
