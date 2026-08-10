"""Data models for parsed ROS 2 interface definitions (IR).

The ``MsgField`` and ``MsgDefinition`` dataclasses are the **intermediate
representation (IR)** produced by the parsing layer and consumed by all
downstream layers (semantics, codegen, pipeline).
"""

from dataclasses import dataclass, field


@dataclass
class MsgField:
    """A single field or constant in a ROS 2 message definition."""

    name: str
    type_str: str  # Raw type as written in the .msg file
    default: str | None = None
    is_constant: bool = False


@dataclass
class MsgDefinition:
    """A parsed ROS 2 message/service/action section (IR node)."""

    package: str
    type_name: str
    type_kind: str  # "msg", "srv", or "action"
    fields: list[MsgField] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    constants: list[MsgField] = field(default_factory=list)  # pyright: ignore[reportUnknownVariableType]
    full_name: str = ""

    def __post_init__(self) -> None:
        if not self.full_name:
            self.full_name = f"{self.package}/{self.type_kind}/{self.type_name}"


__all__ = [
    "MsgDefinition",
    "MsgField",
]
