"""Built-in action protocol message types (``action_msgs`` / ``CancelGoal``).

The zros2 generator does not emit the ROS 2 ``action_msgs`` types (they
are part of every action interface but are not shipped as generated
modules), so the action client defines them here.  They are plain
pycdr2 ``IdlStruct`` classes and structurally satisfy
:class:`zros2.types.RosMessage`, giving CDR layouts compatible with
ROS 2's DDS implementation (the ``00 01 00 00`` encapsulation header
included by pycdr2 is standard CDR_LE).

The ROS 2 definitions they mirror:

* ``action_msgs/msg/GoalInfo`` — goal UUID + creation time
* ``action_msgs/msg/GoalStatus`` — per-goal lifecycle status
* ``action_msgs/msg/GoalStatusArray`` — status topic payload
* ``action_msgs/srv/CancelGoal`` — cancel request / response pair

``GoalInfo.goal_id`` is declared as ``array[uint8, 16]`` instead of the
``unique_identifier_msgs/UUID`` message — the CDR encoding is identical
(16 raw bytes) and it avoids a second built-in type.

The layout mirrors the zros2 generator's output (``@dataclass(init=False)``
with a hand-written ``__init__``) so the built-ins behave identically to
generated messages.  Class-level field annotations use native Python
types so static checkers accept the classes, while the explicit
``__annotations__`` dict keeps the pycdr2 CDR types that drive the wire
encoding — the same split the generator makes between its ``.pyi``
stubs and runtime modules.
"""

import dataclasses
from collections.abc import Sequence
from typing import ClassVar, cast

from pycdr2 import IdlStruct
from pycdr2.types import array, int8, int32, sequence, uint8, uint32

from .types._utils import from_attributes as _from_attributes


@dataclasses.dataclass(init=False)
class Time(IdlStruct):
    """``builtin_interfaces/msg/Time`` — seconds + nanoseconds."""

    sec: int = 0
    nanosec: int = 0

    __annotations__ = {"sec": int32, "nanosec": uint32}  # pyright: ignore[reportUnannotatedClassAttribute]

    def __init__(self, *, sec: int = 0, nanosec: int = 0) -> None:
        self.sec = sec
        self.nanosec = nanosec

    def to_dict(self) -> dict[str, object]:
        return {"sec": self.sec, "nanosec": self.nanosec}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "Time":
        return Time(sec=cast(int, data["sec"]), nanosec=cast(int, data["nanosec"]))

    @classmethod
    def from_attributes(cls: type["Time"], obj: object) -> "Time":
        return _from_attributes(cls, obj)


@dataclasses.dataclass(init=False)
class GoalInfo(IdlStruct):
    """``action_msgs/msg/GoalInfo`` — goal UUID and creation time."""

    goal_id: tuple[int, ...] = (0,) * 16
    stamp: Time = dataclasses.field(default_factory=Time)

    __annotations__ = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "goal_id": array[uint8, 16],
        "stamp": Time,
    }

    def __init__(
        self,
        *,
        goal_id: tuple[int, ...] = (0,) * 16,
        stamp: Time | None = None,
    ) -> None:
        self.goal_id = goal_id
        self.stamp = stamp if stamp is not None else Time()

    def to_dict(self) -> dict[str, object]:
        return {"goal_id": list(self.goal_id), "stamp": self.stamp.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GoalInfo":
        return GoalInfo(
            goal_id=cast(tuple[int, ...], data["goal_id"]),
            stamp=Time.from_dict(cast(dict[str, object], data["stamp"])),
        )

    @classmethod
    def from_attributes(cls: type["GoalInfo"], obj: object) -> "GoalInfo":
        return _from_attributes(cls, obj)


@dataclasses.dataclass(init=False)
class GoalStatus(IdlStruct):
    """``action_msgs/msg/GoalStatus`` — goal reference plus lifecycle status."""

    STATUS_UNKNOWN: ClassVar[int] = 0
    STATUS_ACCEPTED: ClassVar[int] = 1
    STATUS_EXECUTING: ClassVar[int] = 2
    STATUS_CANCELING: ClassVar[int] = 3
    STATUS_SUCCEEDED: ClassVar[int] = 4
    STATUS_CANCELED: ClassVar[int] = 5
    STATUS_ABORTED: ClassVar[int] = 6

    goal_info: GoalInfo = dataclasses.field(default_factory=GoalInfo)
    status: int = 0

    __annotations__ = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "goal_info": GoalInfo,
        "status": int8,
    }

    def __init__(self, *, goal_info: GoalInfo | None = None, status: int = 0) -> None:
        self.goal_info = goal_info if goal_info is not None else GoalInfo()
        self.status = status

    def to_dict(self) -> dict[str, object]:
        return {"goal_info": self.goal_info.to_dict(), "status": self.status}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GoalStatus":
        return GoalStatus(
            goal_info=GoalInfo.from_dict(cast(dict[str, object], data["goal_info"])),
            status=cast(int, data["status"]),
        )

    @classmethod
    def from_attributes(cls: type["GoalStatus"], obj: object) -> "GoalStatus":
        return _from_attributes(cls, obj)


@dataclasses.dataclass(init=False)
class GoalStatusArray(IdlStruct):
    """``action_msgs/msg/GoalStatusArray`` — payload of the status topic."""

    status_list: Sequence[GoalStatus] = ()

    __annotations__ = {"status_list": sequence[GoalStatus]}  # pyright: ignore[reportUnannotatedClassAttribute]

    def __init__(self, *, status_list: Sequence[GoalStatus] = ()) -> None:
        self.status_list = status_list

    def to_dict(self) -> dict[str, object]:
        return {"status_list": list(self.status_list)}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GoalStatusArray":
        return GoalStatusArray(
            status_list=cast(Sequence[GoalStatus], data["status_list"])
        )

    @classmethod
    def from_attributes(cls: type["GoalStatusArray"], obj: object) -> "GoalStatusArray":
        return _from_attributes(cls, obj)


@dataclasses.dataclass(init=False)
class CancelGoal_Request(IdlStruct):
    """``action_msgs/srv/CancelGoal_Request`` — goal to cancel.

    An all-zero ``goal_id`` (``cancel_all_goals``) is the ROS 2 wildcard
    that cancels every active goal.
    """

    goal_info: GoalInfo = dataclasses.field(default_factory=GoalInfo)

    __annotations__ = {"goal_info": GoalInfo}  # pyright: ignore[reportUnannotatedClassAttribute]

    def __init__(self, *, goal_info: GoalInfo | None = None) -> None:
        self.goal_info = goal_info if goal_info is not None else GoalInfo()

    def to_dict(self) -> dict[str, object]:
        return {"goal_info": self.goal_info.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CancelGoal_Request":
        return CancelGoal_Request(
            goal_info=GoalInfo.from_dict(cast(dict[str, object], data["goal_info"]))
        )

    @classmethod
    def from_attributes(
        cls: type["CancelGoal_Request"], obj: object
    ) -> "CancelGoal_Request":
        return _from_attributes(cls, obj)


@dataclasses.dataclass(init=False)
class CancelGoal_Response(IdlStruct):
    """``action_msgs/srv/CancelGoal_Response`` — cancel result."""

    ERROR_NONE: ClassVar[int] = 0
    ERROR_REJECTED: ClassVar[int] = 1
    ERROR_UNKNOWN_GOAL: ClassVar[int] = 2
    ERROR_GOAL_TERMINATED: ClassVar[int] = 3

    return_code: int = 0
    goals_canceling: Sequence[GoalInfo] = ()

    __annotations__ = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "return_code": int8,
        "goals_canceling": sequence[GoalInfo],
    }

    def __init__(
        self,
        *,
        return_code: int = 0,
        goals_canceling: Sequence[GoalInfo] = (),
    ) -> None:
        self.return_code = return_code
        self.goals_canceling = goals_canceling

    def to_dict(self) -> dict[str, object]:
        return {
            "return_code": self.return_code,
            "goals_canceling": list(self.goals_canceling),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CancelGoal_Response":
        return CancelGoal_Response(
            return_code=cast(int, data["return_code"]),
            goals_canceling=cast(Sequence[GoalInfo], data["goals_canceling"]),
        )

    @classmethod
    def from_attributes(
        cls: type["CancelGoal_Response"], obj: object
    ) -> "CancelGoal_Response":
        return _from_attributes(cls, obj)


__all__ = [
    "CancelGoal_Request",
    "CancelGoal_Response",
    "GoalInfo",
    "GoalStatus",
    "GoalStatusArray",
]
