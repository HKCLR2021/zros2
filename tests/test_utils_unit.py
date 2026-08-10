"""Unit tests for ``zros2/types/utils.py`` internal helper functions.

Covers ``from_attributes``, ``_unwrap_optional``, ``_unannotate``,
``_check_type``, and ``_type_name`` with edge cases for full branch coverage.
"""

import types
from dataclasses import dataclass
from typing import Annotated, Any
from unittest.mock import patch

import pytest

from zros2.types._utils import (
    _check_type,
    _type_name,
    _unannotate,
    _unwrap_optional,
    from_attributes,
)

# ======================================================================
# Test helpers — minimal dataclasses for ``from_attributes``
# ======================================================================


@dataclass
class _InnerMsg:
    """A message type used as a nested dataclass field."""

    value: str

    def serialize(self) -> bytes:
        return b""

    @classmethod
    def deserialize(cls, data: bytes) -> Any:
        return cls(value="")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        return cls(value=data["value"])

    @classmethod
    def from_attributes(cls, obj: Any) -> Any:
        return from_attributes(cls, obj)

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value}


@dataclass
class _OuterMsg:
    """Message with a nested dataclass field and a plain string field."""

    inner: _InnerMsg
    name: str

    def serialize(self) -> bytes:
        return b""

    @classmethod
    def deserialize(cls, data: bytes) -> Any:
        return cls(inner=_InnerMsg(value=""), name="")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        return cls(inner=data["inner"], name=data["name"])

    @classmethod
    def from_attributes(cls, obj: Any) -> Any:
        return from_attributes(cls, obj)

    def to_dict(self) -> dict[str, Any]:
        return {"inner": self.inner, "name": self.name}


@dataclass
class _MsgWithOptional:
    """Message with an optional nested dataclass field."""

    inner: _InnerMsg | None = None
    name: str = ""

    def serialize(self) -> bytes:
        return b""

    @classmethod
    def deserialize(cls, data: bytes) -> Any:
        return cls(inner=None, name="")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        return cls(inner=data.get("inner"), name=data["name"])

    @classmethod
    def from_attributes(cls, obj: Any) -> Any:
        return from_attributes(cls, obj)

    def to_dict(self) -> dict[str, Any]:
        return {"inner": self.inner, "name": self.name}


# ======================================================================
# from_attributes  (lines 27–79)
# ======================================================================


class TestFromAttributes:
    """``from_attributes`` — nested dataclass field handling and errors."""

    def test_value_none_for_nested_field(self):
        """When a nested dataclass field has value ``None``, set it to ``None``."""
        obj = type("Obj", (), {"inner": None, "name": "test"})()
        result = from_attributes(_MsgWithOptional, obj)
        assert result.inner is None
        assert result.name == "test"

    def test_value_is_already_correct_type(self):
        """When value is already an instance of the inner dataclass, use it directly."""
        inner = _InnerMsg(value="hello")
        obj = type("Obj", (), {"inner": inner, "name": "test"})()
        result = from_attributes(_OuterMsg, obj)
        assert result.inner is inner
        assert result.name == "test"

    def test_value_is_convertible_object(self):
        """When value has matching attrs, recursively convert via ``from_attributes``."""
        inner_obj = type("InnerObj", (), {"value": "nested"})()
        obj = type("Obj", (), {"inner": inner_obj, "name": "test"})()
        result = from_attributes(_OuterMsg, obj)
        assert isinstance(result.inner, _InnerMsg)
        assert result.inner.value == "nested"
        assert result.name == "test"

    def test_value_is_primitive_raises_type_error(self):
        """When a nested dataclass field receives a primitive, raise ``TypeError``."""
        obj = type("Obj", (), {"inner": 42, "name": "test"})()
        with pytest.raises(TypeError, match="Expected _InnerMsg for field 'inner'"):
            from_attributes(_OuterMsg, obj)

    def test_plain_field_valid_type(self):
        """A non-dataclass field with a valid type passes the ``_check_type`` check."""
        obj = type("Obj", (), {"value": "hello"})()
        result = from_attributes(_InnerMsg, obj)
        assert result.value == "hello"

    def test_plain_field_invalid_type_raises(self):
        """A non-dataclass field with incompatible type raises ``TypeError``."""
        obj = type("Obj", (), {"value": 42})()
        with pytest.raises(TypeError, match="Expected type str for field 'value'"):
            from_attributes(_InnerMsg, obj)

    def test_missing_field_raises_key_error(self):
        """When *obj* lacks a required field, raise ``KeyError``."""
        obj = type("Obj", (), {"name": "test"})()
        with pytest.raises(KeyError, match="Missing required field 'inner'"):
            from_attributes(_OuterMsg, obj)

    def test_non_dataclass_asserts(self):
        """Passing a non-dataclass type triggers ``AssertionError``."""
        with pytest.raises(AssertionError):
            from_attributes(int, None)  # type: ignore[arg-type]

    def test_type_field_none_fallback_patched(self):
        """When a field has no type hint, the raw value passes through (defensive).

        Force this by patching ``_get_cached_hints`` to omit one field so
        ``hints.get(f.name)`` returns ``None``.
        """

        @dataclass
        class _Plain:
            x: int
            y: str

        partial_hints = {"x": int}  # deliberately omit "y"

        with patch("zros2.types._utils._get_cached_hints", return_value=partial_hints):
            obj = type("Obj", (), {"x": 10, "y": "hello"})()
            result = from_attributes(_Plain, obj)  # type: ignore[arg-type]
            assert result.x == 10
            assert result.y == "hello"


# ======================================================================
# _unwrap_optional  (lines 97–104)
# ======================================================================


class TestUnwrapOptional:
    """``_unwrap_optional`` — unwrapping ``Optional[T]`` / ``T | None``."""

    def test_unwraps_optional_with_none(self):
        """``int | None`` (``types.UnionType``) unwraps to ``int``."""
        result = _unwrap_optional(int | None)
        assert result is int

    def test_returns_plain_type_as_is(self):
        """A non-optional type is returned unchanged."""
        result = _unwrap_optional(str)
        assert result is str

    def test_multi_arg_uniontype_with_none_not_unwrapped(self):
        """``str | int | None`` has >1 non-``None`` arg, so unchanged."""
        tp = str | int | None
        result = _unwrap_optional(tp)
        assert result is tp

    def test_typing_union_with_none_and_multi_args(self):
        """``str | int | None`` via ``typing.Union`` has >1 non-``None`` arg, so unchanged."""
        tp = str | int | None
        result = _unwrap_optional(tp)
        assert result is tp


# ======================================================================
# _unannotate  (lines 107–112)
# ======================================================================


class TestUnannotate:
    """``_unannotate`` — peeling ``Annotated`` wrappers."""

    def test_peels_annotated(self):
        """``Annotated[int, 'meta']`` peels to ``int``."""
        result = _unannotate(Annotated[int, "metadata"])
        assert result is int

    def test_returns_plain_type_as_is(self):
        """A non-``Annotated`` type is returned unchanged."""
        result = _unannotate(float)
        assert result is float

    def test_nested_annotated_peels_once(self):
        """Only the outer ``Annotated`` layer is peeled.

        Note: Python 3.14+ flattens ``get_args`` for nested ``Annotated``,
        so ``get_args(tp)[0]`` returns ``int`` rather than
        ``Annotated[int, 'a']``.  The function still correctly removes one
        ``Annotated`` layer; the inner type is what remains.
        """
        inner = _unannotate(Annotated[Annotated[int, "a"], "b"])
        assert inner is int


# ======================================================================
# _check_type  (lines 115–130)
# ======================================================================


class TestCheckType:
    """``_check_type`` — isinstance with fallback for generic aliases."""

    def test_expected_is_any(self):
        """``Any`` matches any value unconditionally."""
        assert _check_type(42, Any) is True
        assert _check_type(None, Any) is True
        assert _check_type("hello", Any) is True

    def test_plain_type_match(self):
        """Direct isinstance succeeds for plain types."""
        assert _check_type(42, int) is True
        assert _check_type("hello", str) is True

    def test_plain_type_no_match(self):
        """Direct isinstance returns ``False`` for incompatible types."""
        assert _check_type(42, str) is False
        assert _check_type("hello", int) is False

    def test_type_error_falls_back_to_origin_match(self):
        """When ``isinstance`` raises ``TypeError``, fall back to origin check.

        Simulate the raise by patching ``isinstance`` in the utils module
        only for the specific generic alias ``list[int]``.
        """
        original_isinstance = isinstance

        def _raising_isinstance(value: Any, expected: Any) -> bool:
            if expected is list[int]:
                raise TypeError("parameterized generic")
            return original_isinstance(value, expected)

        with patch("zros2.types._utils.isinstance", _raising_isinstance):
            # ``isinstance([1, 2], list[int])`` raises → origin is ``list`` →
            # ``isinstance([1, 2], list)`` → ``True``
            assert _check_type([1, 2], list[int]) is True

    def test_type_error_fallback_origin_no_match(self):
        """When origin check also fails, return ``False``."""
        original_isinstance = isinstance

        def _raising_isinstance(value: Any, expected: Any) -> bool:
            if expected is list[int]:
                raise TypeError("parameterized generic")
            return original_isinstance(value, expected)

        with patch("zros2.types._utils.isinstance", _raising_isinstance):
            # 42 is not a list, so even the origin check fails
            assert _check_type(42, list[int]) is False

    def test_type_error_no_origin_returns_true_defensive(self):
        """When expected has no origin and isinstance fails, return ``True``."""

        def _always_raising_isinstance(*args: Any, **kwargs: Any) -> bool:
            raise TypeError("mock")

        with patch("zros2.types._utils.isinstance", _always_raising_isinstance):
            # ``isinstance(42, int)`` raises → origin of ``int`` is ``None``
            # → defensive ``return True``
            assert _check_type(42, int) is True


# ======================================================================
# _type_name  (lines 133–142)
# ======================================================================


class TestTypeName:
    """``_type_name`` — human-readable names including generics."""

    def test_plain_type(self):
        """Plain types return their ``__name__``."""
        assert _type_name(str) == "str"
        assert _type_name(int) == "int"
        assert _type_name(float) == "float"

    def test_generic_list(self):
        """``list[int]`` renders as ``list[int]``."""
        assert _type_name(list[int]) == "list[int]"

    def test_generic_dict(self):
        """``dict[str, int]`` renders as ``dict[str, int]``."""
        assert _type_name(dict[str, int]) == "dict[str, int]"

    def test_generic_optional(self):
        """``int | None`` renders as ``Union[int]`` (``None`` filtered out)."""
        assert _type_name(int | None) == "Union[int]"

    def test_generic_uniontype_with_none(self):
        """``int | None`` renders as ``Union[int]``.

        In Python 3.14+ both ``int | None`` and ``Optional[int]`` share
        the same origin (``typing.Union``), so their printed name is
        identical.
        """
        assert _type_name(int | None) == "Union[int]"

    def test_generic_nested(self):
        """``list[list[int]]`` renders as ``list[list[int]]``."""
        assert _type_name(list[list[int]]) == "list[list[int]]"

    def test_generic_empty_args(self):
        """Origin with empty args returns the origin name (defensive branch).

        A ``types.GenericAlias`` constructed without type arguments reaches
        the ``return origin.__name__`` path because ``get_args`` returns ``()``.
        """
        ga = types.GenericAlias(list, ())
        result = _type_name(ga)
        assert result == "list"
