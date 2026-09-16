"""ROS 2 action IDL expansion.

``.action`` files contain three user sections (goal / result / feedback).
ROS 2 interface generation then synthesizes five transport types
(``FeedbackMessage``, ``SendGoal_*``, ``GetResult_*``).  This module is
the single source of truth for that expansion: parsing never encodes
wire fields, and codegen / pipeline read the suffix tables from here.

``GOAL_ID_TYPE`` is a CDR-compatible stand-in for
``unique_identifier_msgs/UUID`` (a struct whose only field is
``uint8[16] uuid``).  Changing the on-wire identity of ``goal_id``
means changing this constant — not the parser.
"""

from dataclasses import dataclass

from ..parsing._models import ActionSource, MsgDefinition, MsgField

# CDR-compatible stand-in for unique_identifier_msgs/UUID.
GOAL_ID_TYPE = "uint8[16]"


@dataclass(frozen=True)
class ActionTypeSpec:
    """One of the eight types that make up a generated ROS 2 action.

    Attributes:
        suffix: Type-name suffix, e.g. ``"_SendGoal_Request"``.
        user_facing: Whether the type is re-exported from ``action/__init__.py``.
        section: ``ActionSource`` attribute holding the file section, or
            ``None`` for a synthesized transport type.
        fields: ``(type_str, field_name)`` templates for synthesized types.
            ``{package}`` and ``{name}`` are interpolated from the source.
            Empty when ``section`` is set.
    """

    suffix: str
    user_facing: bool
    section: str | None = None
    fields: tuple[tuple[str, str], ...] = ()


ACTION_SPEC: tuple[ActionTypeSpec, ...] = (
    ActionTypeSpec("_Goal", True, section="goal"),
    ActionTypeSpec("_Result", True, section="result"),
    ActionTypeSpec("_Feedback", True, section="feedback"),
    ActionTypeSpec(
        "_FeedbackMessage",
        False,
        fields=(
            (GOAL_ID_TYPE, "goal_id"),
            ("{package}/action/{name}_Feedback", "feedback"),
        ),
    ),
    ActionTypeSpec(
        "_SendGoal_Request",
        False,
        fields=(
            (GOAL_ID_TYPE, "goal_id"),
            ("{package}/action/{name}_Goal", "goal"),
        ),
    ),
    ActionTypeSpec(
        "_SendGoal_Response",
        False,
        fields=(
            ("bool", "accepted"),
            ("builtin_interfaces/msg/Time", "stamp"),
        ),
    ),
    ActionTypeSpec(
        "_GetResult_Request",
        False,
        fields=((GOAL_ID_TYPE, "goal_id"),),
    ),
    ActionTypeSpec(
        "_GetResult_Response",
        False,
        fields=(
            ("int8", "status"),
            ("{package}/action/{name}_Result", "result"),
        ),
    ),
)

ACTION_SUFFIXES: tuple[str, ...] = tuple(spec.suffix for spec in ACTION_SPEC)
ACTION_WIRE_SUFFIXES: tuple[str, ...] = tuple(
    spec.suffix for spec in ACTION_SPEC if not spec.user_facing
)


def expand_action(source: ActionSource) -> tuple[MsgDefinition, ...]:
    """Expand a parsed ``.action`` file into the eight ROS 2 action types.

    The three user sections are returned as-is.  The five transport types
    are built from :data:`ACTION_SPEC` field templates, not by parsing
    synthetic ``.msg`` text.

    Args:
        source: Goal / result / feedback sections from
            :func:`~zros2.generator.parsing.parse_action_file`.

    Returns:
        Eight ``MsgDefinition`` values in :data:`ACTION_SPEC` order.
    """
    expanded: list[MsgDefinition] = []
    for spec in ACTION_SPEC:
        if spec.section is not None:
            expanded.append(getattr(source, spec.section))
            continue
        type_name = f"{source.type_name}{spec.suffix}"
        fields = [
            MsgField(
                name=field_name,
                type_str=type_str.format(
                    package=source.package,
                    name=source.type_name,
                ),
            )
            for type_str, field_name in spec.fields
        ]
        expanded.append(
            MsgDefinition(
                package=source.package,
                type_name=type_name,
                type_kind="action",
                fields=fields,
            )
        )
    return tuple(expanded)


__all__ = [
    "ACTION_SPEC",
    "ACTION_SUFFIXES",
    "ACTION_WIRE_SUFFIXES",
    "GOAL_ID_TYPE",
    "ActionTypeSpec",
    "expand_action",
]
