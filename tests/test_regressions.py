"""Regression tests for the correctness bugs found during the 2.0 review.

Each test is intentionally small and executes generated code (rather than
only inspecting source text) so field-name collisions, constant bounds,
defaults, and container normalization stay fixed.
"""

import importlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import threading
from unittest.mock import MagicMock

from zros2._namespace import join_name
from zros2.endpoints import Action, ServiceClient
from zros2.endpoints._action import GoalHandle
from zros2.endpoints._action_keys import ActionChannel, action_key
from zros2.generator.codegen import generate_message_module
from zros2.generator.parsing import MsgDefinition, MsgField
from zros2.generator.pipeline import generate_all
from zros2.generator.pipeline._writer import write_generated_files

from ._test_msgs import ExampleService, StringMsg
from .test_action_unit import _mock_action


def _load_generated(source: str, name: str, ns: dict | None = None) -> type:
    """Load one generated module from a temporary file."""
    with tempfile.TemporaryDirectory(suffix="_zros2_regression") as tmp:
        path = pathlib.Path(tmp) / "generated.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"_reg_{name}", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        if ns:
            module.__dict__.update(ns)
        spec.loader.exec_module(module)
        return getattr(module, name)


def _clean(code: str) -> str:
    """Drop imports that need a full generated package tree."""
    kept: list[str] = []
    for line in code.splitlines():
        if line.startswith("from ") and not any(
            line.startswith(f"from {prefix}")
            for prefix in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


class TestNameNormalization:
    """ROS names use ``/chatter``; Zenoh keys must use ``chatter``."""

    def test_join_name_strips_both_sides(self):
        assert join_name("", "/chatter") == "chatter"
        assert join_name("/robot_01/", "/chatter/") == "robot_01/chatter"

    def test_direct_endpoints_normalize_names(self):
        session = MagicMock()
        session.is_closed.return_value = False
        from zros2.endpoints import Publisher, Subscriber

        publisher = Publisher(session, "/chatter", StringMsg)
        assert publisher._topic == "chatter"
        session.declare_publisher.assert_called_once_with("chatter")
        subscriber = Subscriber(session, "/battery", StringMsg)
        assert subscriber._topic == "battery"
        service = ServiceClient(session, "/add", ExampleService)
        assert service._service_name == "add"
        action = Action(session, "/fib", _mock_action, timeout=1000)
        assert action._action_name == "fib"

    def test_action_key_normalizes(self):
        assert action_key("/fib", ActionChannel.SEND_GOAL) == "fib/_action/send_goal"


class TestGeneratedCodeRegressions:
    """Execute generated code for the cases that previously raised."""

    def test_field_name_matches_type_constructor(self):
        defn = MsgDefinition(
            package="t",
            type_name="Seq",
            type_kind="msg",
            fields=[
                MsgField(name="sequence", type_str="int32[]"),
                MsgField(name="array", type_str="uint8[4]"),
            ],
        )
        Seq = _load_generated(_clean(generate_message_module(defn)), "Seq")
        msg = Seq(sequence=[1, 2], array=(1, 2, 3, 4))
        assert Seq.deserialize(msg.serialize()).sequence == [1, 2]
        assert msg.to_dict() == {"sequence": [1, 2], "array": [1, 2, 3, 4]}

    def test_constant_sized_array_instantiates(self):
        defn = MsgDefinition(
            package="t",
            type_name="Fixed",
            type_kind="msg",
            constants=[
                MsgField(name="SIZE", type_str="int32", default="4", is_constant=True)
            ],
            fields=[MsgField(name="data", type_str="uint8[SIZE]")],
        )
        Fixed = _load_generated(_clean(generate_message_module(defn)), "Fixed")
        assert Fixed().data == b"\x00\x00\x00\x00"
        assert Fixed(data=b"abcd").serialize()
        assert Fixed.SIZE == 4

    def test_string_constant_and_string_default(self):
        defn = MsgDefinition(
            package="t",
            type_name="Text",
            type_kind="msg",
            constants=[
                MsgField(
                    name="GREETING",
                    type_str="string",
                    default="hello world",
                    is_constant=True,
                )
            ],
            fields=[
                MsgField(name="name", type_str="string", default="anonymous"),
            ],
        )
        Text = _load_generated(_clean(generate_message_module(defn)), "Text")
        assert Text.GREETING == "hello world"
        assert Text().name == "anonymous"

    def test_field_type_default_is_honored(self):
        defn = MsgDefinition(
            package="t",
            type_name="Defaults",
            type_kind="msg",
            fields=[
                MsgField(name="count", type_str="int32", default="7"),
                MsgField(name="enabled", type_str="bool", default="true"),
            ],
        )
        Defaults = _load_generated(_clean(generate_message_module(defn)), "Defaults")
        assert Defaults().count == 7
        assert Defaults().enabled is True

    def test_containers_are_normalized_and_roundtrip(self):
        defn = MsgDefinition(
            package="t",
            type_name="Containers",
            type_kind="msg",
            fields=[
                MsgField(name="values", type_str="float64[]"),
                MsgField(name="fixed", type_str="uint8[4]"),
            ],
        )
        Cls = _load_generated(_clean(generate_message_module(defn)), "Containers")
        msg = Cls(values=[1.0], fixed=(1, 2, 3, 4))
        assert msg == Cls.deserialize(msg.serialize())
        assert msg.to_dict() == {"values": [1.0], "fixed": [1, 2, 3, 4]}
        assert json.dumps(msg.to_dict())

    def test_from_attributes_converts_nested_arrays(self):
        inner = MsgDefinition(
            package="nest",
            type_name="Inner",
            type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        outer = MsgDefinition(
            package="nest",
            type_name="Outer",
            type_kind="msg",
            fields=[MsgField(name="items", type_str="nest/msg/Inner[]")],
        )
        Inner = _load_generated(_clean(generate_message_module(inner)), "Inner")
        Outer = _load_generated(
            _clean(generate_message_module(outer)), "Outer", {"Inner": Inner}
        )
        from types import SimpleNamespace

        source = SimpleNamespace(items=[SimpleNamespace(x=1), SimpleNamespace(x=2)])
        converted = Outer.from_attributes(source)
        assert [item.x for item in converted.items] == [1, 2]

        missing = Outer.from_attributes(SimpleNamespace(items=None))
        assert missing.items == []

    def test_nested_default_is_not_shared(self, tmp_path: pathlib.Path):
        inner = MsgDefinition(
            package="nest",
            type_name="Inner",
            type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        outer = MsgDefinition(
            package="nest",
            type_name="Outer",
            type_kind="msg",
            fields=[MsgField(name="inner", type_str="nest/msg/Inner")],
        )
        files = generate_all(
            {"nest/msg/Inner": inner, "nest/msg/Outer": outer},
            tmp_path / "out",
            root_package="out",
        )
        write_generated_files(files)
        sys.path.insert(0, str(tmp_path))
        try:
            Outer = importlib.import_module("out.nest.msg._outer").Outer
            first = Outer()
            second = Outer()
            assert first.inner is not second.inner
            first.inner.x = 99
            assert second.inner.x == 0
        finally:
            sys.path.remove(str(tmp_path))
            for name in list(sys.modules):
                if name == "out" or name.startswith("out."):
                    del sys.modules[name]


class TestGoalIdAndCleanup:
    def test_get_result_does_not_hold_action_lock(self):
        """get_result must not block feedback/status/cancel for its duration."""
        from .test_action_unit import _mock_action

        session = MagicMock()
        session.is_closed.return_value = False
        reply = MagicMock()
        reply.ok.payload = b""
        started = threading.Event()
        release = threading.Event()
        calls = 0

        def _get(*args: object, **kwargs: object):
            nonlocal calls
            calls += 1
            if calls == 1:
                return iter([reply])
            started.set()
            release.wait(2)
            return iter([reply])

        session.get.side_effect = _get
        action = Action(session, "act", _mock_action, timeout=1000)
        events: list[object] = []
        action.feedback_callback = events.append
        handle = action.send_goal()

        worker = threading.Thread(target=action.get_result, args=(handle,))
        worker.start()
        try:
            assert started.wait(1)
            # If get_result kept the action lock, this acquisition would fail.
            assert action._lock.acquire(timeout=0.5)
            action._lock.release()
            feedback = MagicMock()
            feedback.goal_id = handle.goal_id
            action._forward_feedback(feedback)
            assert events == [feedback]
        finally:
            release.set()
            worker.join(2)

    def test_goal_handle_normalizes_to_bytes(self):
        handle = GoalHandle(goal_id=tuple(range(16)), accepted=True)  # type: ignore[arg-type]
        assert handle.goal_id == bytes(range(16))

    def test_get_result_removes_active_goal(self):
        session = MagicMock()
        session.is_closed.return_value = False
        reply = MagicMock()
        reply.ok.payload = b""
        session.get.side_effect = lambda *args, **kwargs: iter([reply])
        action = Action(session, "act", _mock_action, timeout=1000)
        handle = action.send_goal()
        action.get_result(handle)
        assert action._active_goal_ids == set()


class TestRegistryAndRootPackage:
    def test_root_package_registers_types(self, tmp_path: pathlib.Path):
        defn = MsgDefinition(
            package="pkg",
            type_name="Point",
            type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        out = tmp_path / "zmsgs"
        files = generate_all(
            {"pkg/msg/Point": defn}, out, root_package="zmsgs"
        )
        write_generated_files(files)
        sys.path.insert(0, str(tmp_path))
        try:
            pkg = importlib.import_module("zmsgs")
            assert pkg.get_type("pkg/msg/Point").__name__ == "Point"
            assert "pkg/msg/Point" in pkg.iter_types()
        finally:
            sys.path.remove(str(tmp_path))
            for name in list(sys.modules):
                if name == "zmsgs" or name.startswith("zmsgs."):
                    del sys.modules[name]

    def test_root_package_creates_matching_directory(self, tmp_path: pathlib.Path):
        defn = MsgDefinition(
            package="pkg",
            type_name="Point",
            type_kind="msg",
            fields=[MsgField(name="x", type_str="int32")],
        )
        out = tmp_path / "generated"
        files = generate_all({"pkg/msg/Point": defn}, out, root_package="demo")
        write_generated_files(files)
        assert (out / "demo" / "pkg" / "msg" / "_point.py").is_file()
        sys.path.insert(0, str(out))
        try:
            demo = importlib.import_module("demo")
            assert demo.get_type("pkg/msg/Point").__name__ == "Point"
        finally:
            sys.path.remove(str(out))
            for name in list(sys.modules):
                if name == "demo" or name.startswith("demo."):
                    del sys.modules[name]
