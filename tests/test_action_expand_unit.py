"""Tests for ROS 2 action IDL expansion (``semantics._action``)."""

from zros2.generator.parsing._models import ActionSource, MsgDefinition, MsgField
from zros2.generator.parsing._parser import parse_action_file
from zros2.generator.semantics._action import (
    ACTION_SPEC,
    ACTION_SUFFIXES,
    ACTION_WIRE_SUFFIXES,
    GOAL_ID_TYPE,
    expand_action,
)


def _source(
    package: str = "pkg",
    name: str = "Foo",
    *,
    goal_fields: list[MsgField] | None = None,
    result_fields: list[MsgField] | None = None,
    feedback_fields: list[MsgField] | None = None,
) -> ActionSource:
    def _section(suffix: str, fields: list[MsgField] | None) -> MsgDefinition:
        return MsgDefinition(
            package=package,
            type_name=f"{name}{suffix}",
            type_kind="action",
            fields=list(fields or []),
        )

    return ActionSource(
        package=package,
        type_name=name,
        goal=_section("_Goal", goal_fields),
        result=_section("_Result", result_fields),
        feedback=_section("_Feedback", feedback_fields),
    )


class TestActionSpec:
    def test_eight_types(self):
        assert len(ACTION_SPEC) == 8
        assert len(ACTION_SUFFIXES) == 8

    def test_three_user_facing(self):
        user = [s.suffix for s in ACTION_SPEC if s.user_facing]
        assert user == ["_Goal", "_Result", "_Feedback"]

    def test_five_wire_suffixes(self):
        assert ACTION_WIRE_SUFFIXES == (
            "_FeedbackMessage",
            "_SendGoal_Request",
            "_SendGoal_Response",
            "_GetResult_Request",
            "_GetResult_Response",
        )

    def test_goal_id_type(self):
        assert GOAL_ID_TYPE == "uint8[16]"


class TestExpandAction:
    def test_yields_eight_definitions(self):
        expanded = expand_action(_source())
        assert len(expanded) == 8

    def test_preserves_user_sections(self):
        source = _source(
            goal_fields=[MsgField(name="order", type_str="int32")],
            result_fields=[MsgField(name="sequence", type_str="int32[]")],
            feedback_fields=[MsgField(name="progress", type_str="float32")],
        )
        expanded = {d.type_name: d for d in expand_action(source)}
        assert expanded["Foo_Goal"] is source.goal
        assert expanded["Foo_Result"] is source.result
        assert expanded["Foo_Feedback"] is source.feedback
        assert expanded["Foo_Goal"].fields[0].name == "order"

    def test_send_goal_request_fields(self):
        expanded = {
            d.type_name: d for d in expand_action(_source(package="pkg", name="Bar"))
        }
        fields = {f.name: f.type_str for f in expanded["Bar_SendGoal_Request"].fields}
        assert fields == {
            "goal_id": GOAL_ID_TYPE,
            "goal": "pkg/action/Bar_Goal",
        }

    def test_feedback_message_fields(self):
        expanded = {d.type_name: d for d in expand_action(_source())}
        fields = {f.name: f.type_str for f in expanded["Foo_FeedbackMessage"].fields}
        assert fields == {
            "goal_id": GOAL_ID_TYPE,
            "feedback": "pkg/action/Foo_Feedback",
        }

    def test_send_goal_response_fields(self):
        expanded = {d.type_name: d for d in expand_action(_source())}
        fields = {f.name: f.type_str for f in expanded["Foo_SendGoal_Response"].fields}
        assert fields == {
            "accepted": "bool",
            "stamp": "builtin_interfaces/msg/Time",
        }

    def test_get_result_types(self):
        expanded = {d.type_name: d for d in expand_action(_source(name="Do"))}
        req = {f.name: f.type_str for f in expanded["Do_GetResult_Request"].fields}
        res = {f.name: f.type_str for f in expanded["Do_GetResult_Response"].fields}
        assert req == {"goal_id": GOAL_ID_TYPE}
        assert res == {
            "status": "int8",
            "result": "pkg/action/Do_Result",
        }

    def test_full_name_uses_action(self):
        for defn in expand_action(_source(package="test", name="Fib")):
            assert defn.full_name.startswith("test/action/")
            assert defn.type_kind == "action"

    def test_expand_after_parse(self, tmp_path):
        path = tmp_path / "Fibonacci.action"
        path.write_text("int32 order\n---\nint32[] sequence\n---\nint32[] sequence\n")
        source = parse_action_file(path, "test")
        names = [d.type_name for d in expand_action(source)]
        assert names == [
            "Fibonacci_Goal",
            "Fibonacci_Result",
            "Fibonacci_Feedback",
            "Fibonacci_FeedbackMessage",
            "Fibonacci_SendGoal_Request",
            "Fibonacci_SendGoal_Response",
            "Fibonacci_GetResult_Request",
            "Fibonacci_GetResult_Response",
        ]


def test_generator_public_api() -> None:
    import zros2.generator as gen

    assert "ActionSource" in gen.__all__
    assert "expand_action" in gen.__all__
    assert gen.expand_action is expand_action
    assert gen.ActionSource is ActionSource
