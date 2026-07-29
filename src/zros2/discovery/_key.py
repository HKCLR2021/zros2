"""Builders and parsers for ROS 2 liveliness key expressions."""

import enum
from typing import ClassVar

from ._qos import Qos


class LivelinessType(enum.IntEnum):
    """ROS 2 entity types tracked through Zenoh liveliness tokens."""

    ALL = 0
    PLUGIN = 1
    PUBLISHER = 2
    SUBSCRIBER = 3
    SERVICE_SERVER = 4
    SERVICE_CLIENT = 5
    ACTION_SERVER = 6
    ACTION_CLIENT = 7


class LivelinessKey:
    """Build and parse key expressions used for entity discovery."""

    _SLASH_REPLACEMENT = "§"
    _KE_ALL = "@/{}/@ros2_lv/**"
    _KE_PLUGIN = "@/{}/@ros2_lv"
    _KE_PUBLISHER = "@/{}/@ros2_lv/MP/{}/{}/{}"
    _KE_SUBSCRIBER = "@/{}/@ros2_lv/MS/{}/{}/{}"
    _KE_SERVICE_SERVER = "@/{}/@ros2_lv/SS/{}/{}"
    _KE_SERVICE_CLIENT = "@/{}/@ros2_lv/SC/{}/{}"
    _KE_ACTION_SERVER = "@/{}/@ros2_lv/AS/{}/{}"
    _KE_ACTION_CLIENT = "@/{}/@ros2_lv/AC/{}/{}"

    _PREFIX_TO_TYPE: ClassVar[dict[str, "LivelinessType"]] = {
        "MP": LivelinessType.PUBLISHER,
        "MS": LivelinessType.SUBSCRIBER,
        "SS": LivelinessType.SERVICE_SERVER,
        "SC": LivelinessType.SERVICE_CLIENT,
        "AS": LivelinessType.ACTION_SERVER,
        "AC": LivelinessType.ACTION_CLIENT,
    }
    _TYPE_TO_PREFIX: ClassVar[dict["LivelinessType", str]] = {
        value: key for key, value in _PREFIX_TO_TYPE.items()
    }

    @classmethod
    def _escape_slashes(cls, value: str) -> str:
        """Replace slashes so a name fits in one key-expression segment."""
        return value.replace("/", cls._SLASH_REPLACEMENT)

    @classmethod
    def _unescape_slashes(cls, value: str) -> str:
        """Restore slashes in an encoded name."""
        return value.replace(cls._SLASH_REPLACEMENT, "/")

    @classmethod
    def build_all_ke(cls, zenoh_id: str = "*") -> str:
        """Build a key expression matching every liveliness token."""
        return cls._KE_ALL.format(zenoh_id)

    @classmethod
    def build_plugin_ke(cls, zenoh_id: str = "*") -> str:
        """Build a key expression matching the bridge plugin."""
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
        """Build a publisher liveliness key expression."""
        return cls._build_pubsub_ke(
            cls._KE_PUBLISHER,
            zenoh_id,
            topic,
            ros2_type,
            keyless,
            qos,
        )

    @classmethod
    def build_subscriber_ke(
        cls,
        zenoh_id: str,
        topic: str,
        ros2_type: str,
        keyless: bool = True,
        qos: Qos | str | None = None,
    ) -> str:
        """Build a subscriber liveliness key expression."""
        return cls._build_pubsub_ke(
            cls._KE_SUBSCRIBER,
            zenoh_id,
            topic,
            ros2_type,
            keyless,
            qos,
        )

    @classmethod
    def _build_pubsub_ke(
        cls,
        template: str,
        zenoh_id: str,
        name: str,
        ros2_type: str,
        keyless: bool,
        qos: Qos | str | None,
    ) -> str:
        encoded_name = cls._escape_slashes(name)
        encoded_type = cls._escape_slashes(ros2_type)
        qos_key = qos if isinstance(qos, str) else (qos or Qos()).to_key_expr(keyless)
        return template.format(zenoh_id, encoded_name, encoded_type, qos_key)

    @classmethod
    def build_service_server_ke(
        cls, zenoh_id: str, service_name: str, ros2_type: str
    ) -> str:
        """Build a service-server liveliness key expression."""
        return cls._build_named_ke(
            cls._KE_SERVICE_SERVER, zenoh_id, service_name, ros2_type
        )

    @classmethod
    def build_service_client_ke(
        cls, zenoh_id: str, service_name: str, ros2_type: str
    ) -> str:
        """Build a service-client liveliness key expression."""
        return cls._build_named_ke(
            cls._KE_SERVICE_CLIENT, zenoh_id, service_name, ros2_type
        )

    @classmethod
    def build_action_server_ke(
        cls, zenoh_id: str, action_name: str, ros2_type: str
    ) -> str:
        """Build an action-server liveliness key expression."""
        return cls._build_named_ke(
            cls._KE_ACTION_SERVER, zenoh_id, action_name, ros2_type
        )

    @classmethod
    def build_action_client_ke(
        cls, zenoh_id: str, action_name: str, ros2_type: str
    ) -> str:
        """Build an action-client liveliness key expression."""
        return cls._build_named_ke(
            cls._KE_ACTION_CLIENT, zenoh_id, action_name, ros2_type
        )

    @classmethod
    def _build_named_ke(
        cls,
        template: str,
        zenoh_id: str,
        name: str,
        ros2_type: str,
    ) -> str:
        return template.format(
            zenoh_id,
            cls._escape_slashes(name),
            cls._escape_slashes(ros2_type),
        )

    @classmethod
    def _split_ke(
        cls, key_expr: str, expected_prefix: str, num_parts: int
    ) -> list[str]:
        """Validate and split a liveliness key expression."""
        parts = key_expr.split("/")
        if len(parts) < 5 or parts[0] != "@" or parts[2] != "@ros2_lv":
            raise ValueError(
                f"Invalid liveliness key expression: '{key_expr}' — "
                "expected format @/{zenoh_id}/@ros2_lv/{prefix}/..."
            )
        if parts[3] != expected_prefix:
            raise ValueError(
                f"Expected prefix '{expected_prefix}', got '{parts[3]}' in '{key_expr}'"
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
        parts = cls._split_ke(key_expr, expected_prefix, 7)
        keyless, qos = Qos.from_key_expr(parts[6])
        return (
            parts[1],
            cls._unescape_slashes(parts[4]),
            cls._unescape_slashes(parts[5]),
            keyless,
            qos,
        )

    @classmethod
    def _parse_named_ke(
        cls, key_expr: str, expected_prefix: str
    ) -> tuple[str, str, str]:
        parts = cls._split_ke(key_expr, expected_prefix, 6)
        return (
            parts[1],
            cls._unescape_slashes(parts[4]),
            cls._unescape_slashes(parts[5]),
        )

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
        return cls._parse_named_ke(key_expr, "SS")

    @classmethod
    def parse_service_client_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse a service-client liveliness key expression."""
        return cls._parse_named_ke(key_expr, "SC")

    @classmethod
    def parse_action_server_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse an action-server liveliness key expression."""
        return cls._parse_named_ke(key_expr, "AS")

    @classmethod
    def parse_action_client_ke(cls, key_expr: str) -> tuple[str, str, str]:
        """Parse an action-client liveliness key expression."""
        return cls._parse_named_ke(key_expr, "AC")


__all__ = ["LivelinessKey", "LivelinessType"]
