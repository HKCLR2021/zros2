"""Unit tests for :class:`zros2.endpoints.Publisher` edge cases."""

from typing import cast
from unittest.mock import MagicMock

import pytest

from zros2.endpoints import Publisher
from zros2.types import RosMessage

_str_msg: type[RosMessage] = cast(type[RosMessage], str)


class TestPublisher:
    """Tests for Publisher that don't need a real Zenoh session."""

    def test_publish_after_destroy_raises_error(self):
        """Publishing after destroy() should raise RuntimeError."""
        session = MagicMock()
        pub = Publisher(session, "test/topic", _str_msg)
        pub.destroy()
        with pytest.raises(RuntimeError, match="destroyed"):
            pub.publish(cast(RosMessage, "data"))

    def test_destroy_is_idempotent(self):
        """Calling destroy() multiple times should not raise."""
        session = MagicMock()
        pub = Publisher(session, "test/topic", _str_msg)
        pub.destroy()
        pub.destroy()  # Second call should not raise

    def test_destroy_swallows_exception_from_undeclare(self):
        """destroy() should catch and swallow exceptions from undeclare()."""
        session = MagicMock()
        pub = Publisher(session, "test/topic", _str_msg)
        publisher_mock = cast(MagicMock, pub._publisher)
        publisher_mock.undeclare.side_effect = RuntimeError("boom")
        pub.destroy()  # Should not raise
        assert pub._publisher is None  # Should be reset in finally

    def test_destroy_sets_publisher_to_none_on_success(self):
        """After destroy(), publisher should be None."""
        session = MagicMock()
        pub = Publisher(session, "test/topic", _str_msg)
        assert pub._publisher is not None
        pub.destroy()
        assert pub._publisher is None

    def test_context_manager_exit_calls_destroy(self):
        """Exiting the context manager should call destroy()."""
        session = MagicMock()
        with Publisher(session, "test/topic", _str_msg) as pub:
            assert pub._publisher is not None
        # After exiting, publisher should be cleaned up
        assert pub._publisher is None
