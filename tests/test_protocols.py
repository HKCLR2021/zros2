"""Tests for zros2.types.protocols."""

from dataclasses import dataclass
from typing import Any, get_type_hints

from pycdr2 import IdlStruct
from pycdr2._main import IdlMeta
from pycdr2.types import int32, float64
from zros2.types import RosMessage
from zros2.types.protocols import RosService, RosAction


class TestRosMessageProtocol:
    """Verify that generated-like classes satisfy RosMessage."""

    def test_isinstance_check(self):
        """`isinstance` should work with @runtime_checkable."""
        ns: dict[str, Any] = dict(
            IdlMeta.__prepare__("Point", (IdlStruct,), typename="test/Point")
        )
        ns["__annotations__"] = {"x": int32, "y": float64}
        ns["x"] = 0
        ns["y"] = 0
        Point = dataclass(IdlMeta("Point", (IdlStruct,), ns))

        # Attach methods expected by RosMessage protocol
        def _to_dict(self):  # type: ignore[no-untyped-def]
            return {"x": self.x, "y": self.y}
        Point.to_dict = _to_dict  # type: ignore[attr-defined]
        Point.from_dict = classmethod(lambda cls, d: cls(d["x"], d["y"]))  # type: ignore[attr-defined]
        Point.from_attributes = classmethod(lambda cls, o: cls(o.x, o.y))  # type: ignore[attr-defined]

        p = Point(x=1, y=2)  # type: ignore[call-arg]
        assert isinstance(p, RosMessage), (
            "RosMessage should recognize IdlStruct dataclass instances"
        )

    def test_protocol_attributes(self):
        """RosMessage should define serialize, deserialize, from_dict, to_dict."""
        for attr in ("serialize", "deserialize", "from_dict", "from_attributes", "to_dict"):
            assert hasattr(RosMessage, attr), f"RosMessage missing {attr}"

    def test_service_annotation(self):
        """RosService should have Request and Response in type hints."""
        hints = get_type_hints(RosService)
        assert "Request" in hints
        assert "Response" in hints

    def test_action_annotations(self):
        """RosAction should have 8 action attributes in type hints."""
        hints = get_type_hints(RosAction)
        for attr in (
            "Goal",
            "Result",
            "Feedback",
            "FeedbackMessage",
            "SendGoal_Request",
            "SendGoal_Response",
            "GetResult_Request",
            "GetResult_Response",
        ):
            assert attr in hints, f"RosAction missing {attr} in hints"
