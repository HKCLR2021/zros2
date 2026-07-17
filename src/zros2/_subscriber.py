"""Subscriber — receive ROS messages from Zenoh topics.

Provides subscription management with automatic deserialization
of messages and invocation of a user-provided callback.
Thread-safe with an internal lock.
"""

import logging
import threading
from asyncio import iscoroutine
from typing import Callable, Generic, Optional

import zenoh

from .types._base import _MsgT
from ._proxies import ZenohSessionProxy


class Subscriber(Generic[_MsgT]):
    """Context-managed subscriber for Zenoh topics.

    Args:
        zenoh_session: Active Zenoh session.
        topic: Zenoh topic to subscribe to.
        message_type: Expected message type with ``deserialize``.
    """

    def __init__(
            self,
            zenoh_session: ZenohSessionProxy,
            topic: str,
            message_type: type[_MsgT],
    ) -> None:
        self._topic = topic
        self._message_type = message_type
        self._zenoh_session = zenoh_session
        self._lock = threading.RLock()
        self._subscriber: Optional[zenoh.Subscriber] = None

    # ── Context Manager Protocol ─────────────────────────────────────

    def __enter__(self) -> "Subscriber[_MsgT]":
        """Enter the context manager.

        Returns:
            Subscriber: The Subscriber instance.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager — automatically closes subscription."""
        self.close()

    def __del__(self) -> None:
        """Attempt cleanup on object deletion (best-effort)."""
        try:
            self.unsubscribe()
        except Exception:
            pass

    def __repr__(self) -> str:
        return (
            f"Subscriber(topic='{self._topic}', "
            f"type={self._message_type.__name__})"
        )

    # ── Subscription Management ──────────────────────────────────────

    def subscribe(self, callback: Callable[[_MsgT], None]) -> None:
        """Register a callback and start subscribing to the topic.

        Messages are deserialized and passed directly to the user
        callback as a typed dataclass instance.

        Args:
            callback: Function to invoke for each received message.

        Raises:
            ValueError: If already subscribed.
            RuntimeError: If Zenoh session is closed.
        """
        with self._lock:
            if self._subscriber is not None:
                raise ValueError(
                    f"Already subscribed to '{self._topic}'. "
                    "Call unsubscribe() first."
                )
            if self._zenoh_session.is_closed():
                raise RuntimeError(
                    f"Zenoh session is closed for topic '{self._topic}'"
                )

            wrapped_callback = self._make_zenoh_callback(callback)
            self._subscriber = self._zenoh_session.declare_subscriber(
                self._topic, wrapped_callback,
            )
            logging.debug(
                "Subscribed to topic '%s' (type: %s)",
                self._topic, self._message_type.__name__,
            )

    def unsubscribe(self) -> None:
        """Stop subscribing and release resources.

        Idempotent — safe to call if not currently subscribed.
        """
        if self._subscriber is not None:
            try:
                self._subscriber.undeclare()
                logging.debug(f"Unsubscribed from topic '{self._topic}'")
            except Exception:
                logging.exception(
                    f"Failed to unsubscribe from topic '{self._topic}'"
                )
            finally:
                self._subscriber = None

    def close(self) -> None:
        """Close the subscription.

        Alias for ``unsubscribe()``.
        """
        self.unsubscribe()

    # ── Internal Helpers ─────────────────────────────────────────────

    def _make_zenoh_callback(
            self,
            user_callback: Callable[[_MsgT], None],
    ) -> Callable[[zenoh.Sample], None]:
        """Create a Zenoh-compatible callback wrapper.

        Handles deserialization, type checking, and error logging.
        Passes the raw dataclass instance (not a dict) to the user callback.

        Args:
            user_callback: User-provided callback receiving a typed message.

        Returns:
            Wrapped callback compatible with ``zenoh.Subscriber``.
        """
        message_type = self._message_type
        _logger = logging.getLogger(__name__)

        def zenoh_callback(sample: zenoh.Sample) -> None:
            """Zenoh sample handler.

            Steps:
                1. Extract payload as bytes.
                2. Deserialize using ``message_type.deserialize()``.
                3. Validate type.
                4. Invoke user callback with the raw dataclass.
            """
            if self._subscriber is None:
                _logger.debug(
                    "Callback fired for topic '%s' after subscriber was "
                    "undeclared (type: %s, key_expr: %s) — possible zombie",
                    self._topic, message_type.__name__, sample.key_expr,
                )

            try:
                payload_bytes = bytes(sample.payload)
                message = message_type.deserialize(payload_bytes)

                if not isinstance(message, message_type):
                    raise TypeError(
                        f"Expected {message_type.__name__}, "
                        f"got {type(message).__name__}"
                    )

                result = user_callback(message)  # pass raw dataclass

                if iscoroutine(result):
                    raise TypeError(
                        f"Async function passed as callback for topic "
                        f"'{self._topic}'. Subscriber callbacks must be "
                        "synchronous."
                    )

            except Exception:
                logging.exception(
                    "Failed to process callback on topic '%s'",
                    self._topic,
                )

        return zenoh_callback
