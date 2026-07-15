import enum
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

import zenoh

from ._proxies import ZenohSessionProxy

logger = logging.getLogger(__name__)


class LivelinessType(enum.IntEnum):
    """ROS 2 entity types tracked via Zenoh liveliness tokens.

    Each member corresponds to a ``ke_liveliness_*`` variant in the
    Rust ``liveliness_mgt.rs`` and determines the key-expression pattern
    used to declare / query that entity's liveliness.

    Attributes:
        ALL: Matches every liveliness token.
        PLUGIN: The bridge plugin itself.
        PUBLISHER: A ROS 2 publisher.
        SUBSCRIBER: A ROS 2 subscriber.
        SERVICE_SERVER: A ROS 2 service server.
        SERVICE_CLIENT: A ROS 2 service client.
        ACTION_SERVER: A ROS 2 action server.
        ACTION_CLIENT: A ROS 2 action client.
    """
    ALL = 0  # ke_liveliness_all
    PLUGIN = 1  # ke_liveliness_plugin
    PUBLISHER = 2  # ke_liveliness_pub
    SUBSCRIBER = 3  # ke_liveliness_sub
    SERVICE_SERVER = 4  # ke_liveliness_service_srv
    SERVICE_CLIENT = 5  # ke_liveliness_service_cli
    ACTION_SERVER = 6  # ke_liveliness_action_srv
    ACTION_CLIENT = 7  # ke_liveliness_action_cli


# Format: [K]:<ReliabilityKind>:<DurabilityKind>:<HistoryKind>,<HistoryDepth>[:<UserData>]
# See liveliness_mgt.rs ::qos_to_key_expr / key_expr_to_qos.


@dataclass
class Qos:
    """Quality-of-Service parameters for a liveliness token.

    The field values follow the cyclors DDS enumeration ordinals:

    * **reliability** – ``None`` (default) | ``0`` (BEST_EFFORT) | ``1`` (RELIABLE)
    * **durability**  – ``None`` (default) | ``0`` (VOLATILE) | ``1`` (TRANSIENT_LOCAL)
    * **history_kind** – ``None`` (default) | ``0`` (KEEP_LAST) | ``1`` (KEEP_ALL)
    * **history_depth** – depth for KEEP_LAST
    * **user_data** – optional opaque bytes
    """

    reliability: Optional[int] = None
    durability: Optional[int] = None
    history_kind: Optional[int] = None
    history_depth: Optional[int] = None
    user_data: Optional[bytes] = None

    def to_key_expr(self, keyless: bool = True) -> str:
        """Serialise this QoS into a key-expression-compatible string.

        The output follows the same colon-separated layout as the Rust
        ``qos_to_key_expr`` in ``liveliness_mgt.rs``.
        """
        parts: list[str] = ["", "", "", ""]

        if not keyless:
            parts[0] = "K"

        if self.reliability is not None:
            parts[1] = str(self.reliability)
        if self.durability is not None:
            parts[2] = str(self.durability)
        if self.history_kind is not None:
            parts[3] = f"{self.history_kind},{self.history_depth or 0}"
        if self.user_data is not None:
            parts.append(self.user_data.decode("utf-8", errors="replace"))

        return ":".join(parts)

    @classmethod
    def from_key_expr(cls, ke: str) -> tuple[bool, "Qos"]:
        """Parse a QoS key-expression back into a ``(keyless, Qos)`` pair."""
        elts = ke.split(":")
        keyless = elts[0] != "K"
        qos = cls()

        if len(elts) > 1 and elts[1]:
            qos.reliability = int(elts[1])
        if len(elts) > 2 and elts[2]:
            qos.durability = int(elts[2])
        if len(elts) > 3 and elts[3]:
            if "," in elts[3]:
                hk, hd = elts[3].split(",", 1)
                qos.history_kind = int(hk) if hk else None
                qos.history_depth = int(hd) if hd else None
            else:
                qos.history_kind = int(elts[3]) if elts[3] else None
        if len(elts) > 4 and elts[4]:
            qos.user_data = elts[4].encode("utf-8")

        return keyless, qos

    @staticmethod
    def any() -> str:
        """Return a wildcard QoS key expression that matches any QoS.

        Use this in builder methods when you want the QoS segment of the
        liveliness key expression to match any value (``*``).

        Example::

            _LivelinessKey.build_publisher_ke(
                "my_id", "/topic", "pkg/msg/T", qos=Qos.any(),
            )
            # => @/my_id/@ros2_lv/MP/topic/pkg/msg/T/*
        """
        return "*"


class _LivelinessKey:
    """Liveliness key-expression builders and parsers.

    Encapsulates the ``kedefine!`` templates and all ``new_ke_*`` /
    ``parse_ke_*`` functions from ``liveliness_mgt.rs`` as class methods.
    """

    _SLASH_REPLACEMENT = "§"

    # Key-expression templates (correspond to the kedefine! block).
    _KE_ALL = "@/{}/@ros2_lv/**"
    _KE_PLUGIN = "@/{}/@ros2_lv"
    _KE_PUBLISHER = "@/{}/@ros2_lv/MP/{}/{}/{}"
    _KE_SUBSCRIBER = "@/{}/@ros2_lv/MS/{}/{}/{}"
    _KE_SERVICE_SERVER = "@/{}/@ros2_lv/SS/{}/{}"
    _KE_SERVICE_CLIENT = "@/{}/@ros2_lv/SC/{}/{}"
    _KE_ACTION_SERVER = "@/{}/@ros2_lv/AS/{}/{}"
    _KE_ACTION_CLIENT = "@/{}/@ros2_lv/AC/{}/{}"

    # Mapping from two-letter KE prefix to LivelinessType (used by parse_ke_*).
    _PREFIX_TO_TYPE = {
        "MP": LivelinessType.PUBLISHER,
        "MS": LivelinessType.SUBSCRIBER,
        "SS": LivelinessType.SERVICE_SERVER,
        "SC": LivelinessType.SERVICE_CLIENT,
        "AS": LivelinessType.ACTION_SERVER,
        "AC": LivelinessType.ACTION_CLIENT,
    }
    # Inverse mapping from LivelinessType back to KE prefix (used by build_ke_*).
    _TYPE_TO_PREFIX = {v: k for k, v in _PREFIX_TO_TYPE.items()}

    # ── Helpers ──────────────────────────────────────────────────────

    @classmethod
    def _escape_slashes(cls, s: str) -> str:
        """Replace ``/`` with ``§`` so topic/type names fit in one KE segment."""
        return s.replace("/", cls._SLASH_REPLACEMENT)

    @classmethod
    def _unescape_slashes(cls, s: str) -> str:
        """Restore ``/`` from ``§``."""
        return s.replace(cls._SLASH_REPLACEMENT, "/")

    # ── Builders  (new_ke_liveliness_* equivalents) ──────────────────

    @classmethod
    def build_all_ke(cls, zenoh_id: str = "*") -> str:
        """Build ``ke_liveliness_all`` — matches every liveliness token."""
        return cls._KE_ALL.format(zenoh_id)

    @classmethod
    def build_plugin_ke(cls, zenoh_id: str = "*") -> str:
        """Build ``ke_liveliness_plugin`` — matches the bridge plugin itself."""
        return cls._KE_PLUGIN.format(zenoh_id)

    @classmethod
    def build_publisher_ke(
        cls,
        zenoh_id: str,
        topic: str,
        ros2_type: str,
        keyless: bool = True,
        qos: Qos | str | None = None,
    ) -> str:
        """Build ``ke_liveliness_pub`` — publisher liveliness key expression.

        Args:
            qos: A :class:`Qos` instance, the wildcard string ``"*"`` (from
                 :meth:`Qos.any`), or ``None`` (default empty QoS).
        """
        ke = cls._escape_slashes(topic)
        typ = cls._escape_slashes(ros2_type)
        if isinstance(qos, str):
            qos_ke = qos
        else:
            qos_ke = (qos or Qos()).to_key_expr(keyless)
        return cls._KE_PUBLISHER.format(zenoh_id, ke, typ, qos_ke)

    @classmethod
    def build_subscriber_ke(
        cls,
        zenoh_id: str,
        topic: str,
        ros2_type: str,
        keyless: bool = True,
        qos: Qos | str | None = None,
    ) -> str:
        """Build ``ke_liveliness_sub`` — subscriber liveliness key expression.

        Args:
            qos: A :class:`Qos` instance, the wildcard string ``"*"`` (from
                 :meth:`Qos.any`), or ``None`` (default empty QoS).
        """
        ke = cls._escape_slashes(topic)
        typ = cls._escape_slashes(ros2_type)
        if isinstance(qos, str):
            qos_ke = qos
        else:
            qos_ke = (qos or Qos()).to_key_expr(keyless)
        return cls._KE_SUBSCRIBER.format(zenoh_id, ke, typ, qos_ke)

    @classmethod
    def build_service_server_ke(cls, zenoh_id: str, service_name: str, ros2_type: str) -> str:
        """Build ``ke_liveliness_service_srv``."""
        ke = cls._escape_slashes(service_name)
        typ = cls._escape_slashes(ros2_type)
        return cls._KE_SERVICE_SERVER.format(zenoh_id, ke, typ)

    @classmethod
    def build_service_client_ke(cls, zenoh_id: str, service_name: str, ros2_type: str) -> str:
        """Build ``ke_liveliness_service_cli``."""
        ke = cls._escape_slashes(service_name)
        typ = cls._escape_slashes(ros2_type)
        return cls._KE_SERVICE_CLIENT.format(zenoh_id, ke, typ)

    @classmethod
    def build_action_server_ke(cls, zenoh_id: str, action_name: str, ros2_type: str) -> str:
        """Build ``ke_liveliness_action_srv``."""
        ke = cls._escape_slashes(action_name)
        typ = cls._escape_slashes(ros2_type)
        return cls._KE_ACTION_SERVER.format(zenoh_id, ke, typ)

    @classmethod
    def build_action_client_ke(cls, zenoh_id: str, action_name: str, ros2_type: str) -> str:
        """Build ``ke_liveliness_action_cli``."""
        ke = cls._escape_slashes(action_name)
        typ = cls._escape_slashes(ros2_type)
        return cls._KE_ACTION_CLIENT.format(zenoh_id, ke, typ)

    # ── Parsers  (parse_ke_liveliness_* equivalents) ─────────────────

    @classmethod
    def _split_ke(cls, key_expr: str, expected_prefix: str, num_parts: int) -> list[str]:
        """Low-level split of a liveliness key expression.

        Checks the structure::

            @ / {zenoh_id} / @ros2_lv / {expected_prefix} / ...
        """
        parts = key_expr.split("/")
        min_len = 5  # @ / zenoh_id / @ros2_lv / prefix / ke …
        if len(parts) < min_len or parts[0] != "@" or parts[2] != "@ros2_lv":
            raise ValueError(
                f"Invalid liveliness key expression: '{key_expr}' — "
                "expected format @/{zenoh_id}/@ros2_lv/{prefix}/..."
            )
        if parts[3] != expected_prefix:
            raise ValueError(
                f"Expected prefix '{expected_prefix}', got '{parts[3]}' "
                f"in '{key_expr}'"
            )
        if len(parts) < num_parts:
            raise ValueError(
                f"Expected at least {num_parts} segments in '{key_expr}', "
                f"got {len(parts)}"
            )
        return parts

    @classmethod
    def _parse_pubsub_ke(
        cls, key_expr: str, expected_prefix: str
    ) -> tuple[str, str, str, bool, Qos]:
        """Parse a publisher/subscriber liveliness key expression."""
        parts = cls._split_ke(key_expr, expected_prefix, 7)
        zenoh_id = parts[1]
        ke = cls._unescape_slashes(parts[4])
        typ = cls._unescape_slashes(parts[5])
        keyless, qos = Qos.from_key_expr(parts[6])
        return zenoh_id, ke, typ, keyless, qos

    @classmethod
    def _parse_srv_action_ke(cls, key_expr: str, expected_prefix: str) -> tuple[str, str, str]:
        """Parse a service/action liveliness key expression (no QoS)."""
        parts = cls._split_ke(key_expr, expected_prefix, 6)
        zenoh_id = parts[1]
        ke = cls._unescape_slashes(parts[4])
        typ = cls._unescape_slashes(parts[5])
        return zenoh_id, ke, typ

    @classmethod
    def parse_publisher_ke(cls, key_expr: str) -> tuple[str, str, str, bool, Qos]:
        """Parse a publisher liveliness key expression."""
        return cls._parse_pubsub_ke(key_expr, "MP")

    @classmethod
    def parse_subscriber_ke(cls, key_expr: str) -> tuple[str, str, str, bool, Qos]:
        """Parse a subscriber liveliness key expression."""
        return cls._parse_pubsub_ke(key_expr, "MS")

    @classmethod
    def parse_service_server_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse a service-server liveliness key expression."""
        return cls._parse_srv_action_ke(key_expr, "SS")

    @classmethod
    def parse_service_client_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse a service-client liveliness key expression."""
        return cls._parse_srv_action_ke(key_expr, "SC")

    @classmethod
    def parse_action_server_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse an action-server liveliness key expression."""
        return cls._parse_srv_action_ke(key_expr, "AS")

    @classmethod
    def parse_action_client_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse an action-client liveliness key expression."""
        return cls._parse_srv_action_ke(key_expr, "AC")


_ENTITY_BUILDER: dict[LivelinessType, Callable[..., str]] = {
    LivelinessType.PUBLISHER: _LivelinessKey.build_publisher_ke,
    LivelinessType.SUBSCRIBER: _LivelinessKey.build_subscriber_ke,
    LivelinessType.SERVICE_SERVER: _LivelinessKey.build_service_server_ke,
    LivelinessType.SERVICE_CLIENT: _LivelinessKey.build_service_client_ke,
    LivelinessType.ACTION_SERVER: _LivelinessKey.build_action_server_ke,
    LivelinessType.ACTION_CLIENT: _LivelinessKey.build_action_client_ke,
}


class Liveliness:
    """Monitor and query ROS 2 entity liveliness over Zenoh.

    Returned by :meth:`ZRosClient.create_liveliness`. The entity type,
    name, and ROS type are fixed at construction, so :meth:`get` and
    :meth:`subscribe` take only the callback (for subscribe).

    Usage::

        liv = client.create_liveliness(LivelinessType.SERVICE_SERVER,
                                       "/get_score")

        # One-shot: check if the server is online
        samples = liv.get()

        # Continuous: monitor server status
        sub = liv.subscribe(callback)
    """

    def __init__(
        self,
        zenoh_session: ZenohSessionProxy,
        entity: LivelinessType,
        name: str = "*",
        ros2_type: str = "*",
        qos: Qos | str = Qos.any(),
    ) -> None:
        builder = _ENTITY_BUILDER.get(entity)
        if builder is None:
            raise ValueError(
                f"Unsupported entity type {entity!r}. "
                f"Use one of: {', '.join(e.name for e in _ENTITY_BUILDER)}"
            )
        if entity in (LivelinessType.PUBLISHER, LivelinessType.SUBSCRIBER):
            self._ke = builder("*", name, ros2_type, qos=qos)
        else:
            self._ke = builder("*", name, ros2_type)
        self._zenoh_session = zenoh_session
        self._sub: zenoh.Subscriber | None = None

    def get(self) -> list[zenoh.Sample]:
        """One-shot query: return currently alive entities."""
        return list(self._zenoh_session.liveliness().get(self._ke))

    def subscribe(
        self,
        callback: Callable[[zenoh.Sample], Any],
    ) -> zenoh.Subscriber:
        """Subscribe to liveliness changes.

        The subscriber is tracked internally and will be cleaned up when
        :meth:`close` is called. Only one subscriber can be active at a time;
        calling this method again will replace the previous one.

        Args:
            callback: Handler called on each liveliness change.

        Returns:
            A :class:`zenoh.Subscriber` that must be kept alive. Call
            ``undeclare()`` to stop listening.
        """
        # Clean up any previous subscriber before creating a new one.
        self._close_subscriber()
        self._sub = self._zenoh_session.liveliness().declare_subscriber(self._ke, callback)
        return self._sub

    def close(self) -> None:
        """Undeclare the subscriber and release all resources.

        After calling this method, the instance should no longer be used.
        """
        self._close_subscriber()

    def _close_subscriber(self) -> None:
        """Undeclare the tracked subscriber, if any."""
        if self._sub is not None:
            try:
                self._sub.undeclare()
            except Exception:
                logger.warning("Failed to undeclare liveliness subscriber", exc_info=True)
            finally:
                self._sub = None

    def __enter__(self) -> "Liveliness":
        """Enter context manager."""
        return self

    def __exit__(self, *args: object) -> None:
        """Exit context manager and clean up resources."""
        self.close()
