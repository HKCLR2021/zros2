"""Unit tests for :class:`zros2._proxies.ZenohSessionProxy`."""

from unittest.mock import MagicMock

import pytest

from zros2._proxies import ZenohSessionProxy


class TestZenohSessionProxy:
    """Tests for the Zenoh session proxy."""

    def test_getattr_delegates(self):
        """Normal attribute access should pass through to the real session."""
        session = MagicMock()
        proxy = ZenohSessionProxy(session)
        result = proxy.get
        # Should return whatever session.get returns (a mock), not raise
        assert result is session.get

    def test_getattr_blocks_close(self):
        """Accessing 'close' should raise PermissionError."""
        session = MagicMock()
        proxy = ZenohSessionProxy(session)
        with pytest.raises(PermissionError, match="forbidden"):
            proxy.close  # noqa: B018

    def test_getattr_blocks_destroy(self):
        """Accessing 'destroy' should raise PermissionError."""
        session = MagicMock()
        proxy = ZenohSessionProxy(session)
        with pytest.raises(PermissionError, match="forbidden"):
            proxy.destroy  # noqa: B018

    def test_getattr_blocks_undeclare(self):
        """Accessing 'undeclare' should raise PermissionError."""
        session = MagicMock()
        proxy = ZenohSessionProxy(session)
        with pytest.raises(PermissionError, match="forbidden"):
            proxy.undeclare  # noqa: B018

    def test_setattr_raises_permission_error(self):
        """Setting an attribute on the proxy should raise PermissionError."""
        session = MagicMock()
        proxy = ZenohSessionProxy(session)
        with pytest.raises(PermissionError, match="Modifying"):
            proxy.foo = "bar"

    def test_del_does_not_raise(self):
        """Deleting the proxy should not raise an exception."""
        session = MagicMock()
        proxy = ZenohSessionProxy(session)
        del proxy  # Should not raise
