"""Subscriber endpoint for receiving ROS messages over Zenoh."""

import logging
import threading
import types
from asyncio import iscoroutine
from collections.abc import Callable
from contextlib import suppress
from typing import Any

import zenoh

from .._session import ZenohSessionProxy
from ..types import RosMessage

logger = logging.getLogger(__name__)


class Subscriber[MsgT: RosMessage]:
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
        message_type: type[MsgT],
    ) -> None:
        self._topic = topic
        self._message_type = message_type
        self._zenoh_session = zenoh_session
        self._lock = threading.RLock()
        self._subscriber: zenoh.Subscriber[Any] | None = None

    def __enter__(self) -> "Subscriber[MsgT]":
        """Enter the context manager.

        Returns:
            Subscriber: The Subscriber instance.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Exit the context manager and automatically close the subscription."""
        self.close()

    def __del__(self) -> None:
        """Attempt cleanup on object deletion (best-effort)."""
        with suppress(Exception):
            self.unsubscribe()

    def __repr__(self) -> str:
        return f"Subscriber(topic='{self._topic}', type={self._message_type.__name__})"

    def subscribe(self, callback: Callable[[MsgT], None]) -> None:
        """Register a callback and start subscribing to the topic.

        Args:
            callback: Function to invoke for each received message.

        Raises:
            ValueError: If already subscribed.
            RuntimeError: If Zenoh session is closed.
        """
        with self._lock:
            if self._subscriber is not None:
                raise ValueError(
                    f"Already subscribed to '{self._topic}'. Call unsubscribe() first."
                )
            if self._zenoh_session.is_closed():
                raise RuntimeError(f"Zenoh session is closed for topic '{self._topic}'")

            wrapped_callback = self._make_zenoh_callback(callback)
            self._subscriber = self._zenoh_session.declare_subscriber(
                self._topic,
                wrapped_callback,
            )
            logger.debug(
                "Subscribed to topic '%s' (type: %s)",
                self._topic,
                self._message_type.__name__,
            )

    def unsubscribe(self) -> None:
        """Stop subscribing and release resources.

        Idempotent — safe to call if not currently subscribed.
        """
        if self._subscriber is not None:
            try:
                self._subscriber.undeclare()
                logger.debug("Unsubscribed from topic '%s'", self._topic)
            except Exception:
                logger.exception("Failed to unsubscribe from topic '%s'", self._topic)
            finally:
                self._subscriber = None

    def close(self) -> None:
        """Close the subscription."""
        self.unsubscribe()

    def _make_zenoh_callback(
        self,
        user_callback: Callable[[MsgT], None],
    ) -> Callable[[zenoh.Sample], None]:
        """Create a Zenoh-compatible callback wrapper."""
        message_type = self._message_type

        def zenoh_callback(sample: zenoh.Sample) -> None:
            if self._subscriber is None:
                logger.debug(
                    "Callback fired for topic '%s' after subscriber was "
                    "undeclared (type: %s, key_expr: %s) — possible zombie",
                    self._topic,
                    message_type.__name__,
                    sample.key_expr,
                )

            try:
                payload_bytes = bytes(sample.payload)
                message = message_type.deserialize(payload_bytes)

                if not isinstance(message, message_type):
                    raise TypeError(
                        f"Expected {message_type.__name__}, "
                        f"got {type(message).__name__}"
                    )

                result = user_callback(message)
                if iscoroutine(result):
                    raise TypeError(
                        f"Async function passed as callback for topic "
                        f"'{self._topic}'. Subscriber callbacks must be synchronous."
                    )
            except Exception:
                logger.exception(
                    "Failed to process callback on topic '%s'",
                    self._topic,
                )

        return zenoh_callback


__all__ = ["Subscriber"]
