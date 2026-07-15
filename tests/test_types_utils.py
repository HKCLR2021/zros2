"""Tests for zros2.types.utils (from_dict / to_dict)."""

from dataclasses import dataclass, field
from typing import Any, ClassVar
from zros2.types.utils import from_dict, to_dict


class _RosMessageStub:
    """Minimal ``RosMessage`` protocol implementation for test dataclasses."""

    def serialize(self) -> bytes:
        return b""

    @classmethod
    def deserialize(cls, data: bytes) -> Any:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        raise NotImplementedError

    @classmethod
    def from_attributes(cls, obj: Any) -> Any:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return {}


@dataclass
class _CycleNode(_RosMessageStub):
    """Self-referencing dataclass for circular reference tests."""
    name: str
    child: '_CycleNode'


@dataclass
class _CycleBranch(_RosMessageStub):
    """Self-referencing dataclass with sequence for circular reference tests."""
    label: str
    branches: 'list[_CycleBranch]'


@dataclass
class Header(_RosMessageStub):
    seq: int
    frame_id: str


@dataclass
class Pose(_RosMessageStub):
    x: float
    y: float
    z: float


@dataclass
class PointCloud(_RosMessageStub):
    header: Header
    points: list[Pose]
    label: str


class TestFromDict:
    def test_simple_dataclass(self):
        result = from_dict(Header, {"seq": 42, "frame_id": "map"})
        assert isinstance(result, Header)
        assert result.seq == 42
        assert result.frame_id == "map"

    def test_nested_dataclass(self):
        data = {
            "header": {"seq": 1, "frame_id": "odom"},
            "points": [
                {"x": 1.0, "y": 2.0, "z": 3.0},
                {"x": 4.0, "y": 5.0, "z": 6.0},
            ],
            "label": "test",
        }
        result = from_dict(PointCloud, data)
        assert isinstance(result, PointCloud)
        assert isinstance(result.header, Header)
        assert result.header.seq == 1
        assert len(result.points) == 2
        assert isinstance(result.points[0], Pose)
        assert result.points[0].x == 1.0

    def test_missing_field_raises(self):
        import pytest
        with pytest.raises(KeyError):
            from_dict(Header, {"seq": 1})

    def test_none_value(self):
        @dataclass
        class OptionalField(_RosMessageStub):
            name: str
            value: int | None = None

        result = from_dict(OptionalField, {"name": "test", "value": None})
        assert result.value is None

    # ── Type validation: leaf fields ────────────────────────────
    def test_leaf_type_mismatch(self):
        """str passed for int field should raise TypeError."""
        import pytest
        with pytest.raises(TypeError, match="field 'seq'"):
            from_dict(Header, {"seq": "not_an_int", "frame_id": "map"})

    def test_nested_field_with_non_dict_value(self):
        """Non-dict value passed for a nested dataclass field should raise TypeError."""
        import pytest
        with pytest.raises(TypeError, match="field 'header'"):
            from_dict(PointCloud, {
                "header": 42,
                "points": [],
                "label": "x",
            })

    def test_nested_field_type_mismatch_inside(self):
        """Wrong type inside a nested dataclass should be caught recursively."""
        import pytest
        with pytest.raises(TypeError, match="field 'seq'"):
            from_dict(PointCloud, {
                "header": {"seq": "wrong", "frame_id": "map"},
                "points": [],
                "label": "x",
            })

    # ── Type validation: sequence fields ────────────────────────
    def test_sequence_field_not_iterable(self):
        """Non-sequence value for a list field should raise TypeError."""
        import pytest
        with pytest.raises(TypeError, match="field 'points'"):
            from_dict(PointCloud, {
                "header": {"seq": 1, "frame_id": "map"},
                "points": "not_a_list",
                "label": "x",
            })

    def test_sequence_item_type_mismatch(self):
        """Non-dict non-dataclass item inside a list of dataclass should raise TypeError."""
        import pytest
        with pytest.raises(TypeError, match="items of field 'points'"):
            from_dict(PointCloud, {
                "header": {"seq": 1, "frame_id": "map"},
                "points": [42],
                "label": "x",
            })

    def test_sequence_item_nested_type_mismatch(self):
        """Dict item with wrong inner type inside a list of dataclass."""
        import pytest
        with pytest.raises(TypeError, match="field 'x'"):
            from_dict(PointCloud, {
                "header": {"seq": 1, "frame_id": "map"},
                "points": [{"x": "bad", "y": 2.0, "z": 3.0}],
                "label": "x",
            })

    # ── Type validation: non-dataclass ──────────────────────────
    def test_non_dataclass_type_raises(self):
        """Passing a non-dataclass type as cls should raise TypeError."""
        import pytest
        with pytest.raises(TypeError, match="Expected a ROS message type"):
            from_dict(int, {"x": 1})

    # ── Optional fields ─────────────────────────────────────────
    def test_optional_field_wrong_type(self):
        """Optional[int] with a str value should raise TypeError."""
        import pytest
        @dataclass
        class Opt(_RosMessageStub):
            val: int | None = None
        with pytest.raises(TypeError, match="field 'val'"):
            from_dict(Opt, {"val": "wrong"})

    # ── Circular reference ────────────────────────────────────────
    def test_direct_circular_reference(self):
        """A dict containing itself should raise RecursionError."""
        import pytest
        data: dict[str, Any] = {"name": "root", "child": {}}
        data["child"] = data  # self-reference
        with pytest.raises(RecursionError, match="Circular reference"):
            from_dict(_CycleNode, data)

    def test_indirect_circular_reference(self):
        """A chain of dicts that loops back should raise RecursionError."""
        import pytest
        leaf: dict[str, Any] = {"label": "leaf", "branches": []}
        middle: dict[str, Any] = {"label": "middle", "branches": [leaf]}
        # point leaf back to middle, creating a cycle
        leaf["branches"].append(middle)

        with pytest.raises(RecursionError, match="Circular reference"):
            from_dict(_CycleBranch, middle)


class TestToDict:
    def test_simple_dataclass(self):
        obj = Header(seq=1, frame_id="map")
        result = to_dict(obj)
        assert result == {"seq": 1, "frame_id": "map"}

    def test_nested_dataclass(self):
        obj = PointCloud(
            header=Header(seq=1, frame_id="odom"),
            points=[Pose(1.0, 2.0, 3.0), Pose(4.0, 5.0, 6.0)],
            label="test",
        )
        result = to_dict(obj)
        assert result == {
            "header": {"seq": 1, "frame_id": "odom"},
            "points": [
                {"x": 1.0, "y": 2.0, "z": 3.0},
                {"x": 4.0, "y": 5.0, "z": 6.0},
            ],
            "label": "test",
        }

    def test_roundtrip(self):
        original = PointCloud(
            header=Header(seq=1, frame_id="odom"),
            points=[Pose(1.0, 2.0, 3.0)],
            label="roundtrip",
        )
        data = to_dict(original)
        restored = from_dict(PointCloud, data)
        assert restored == original
