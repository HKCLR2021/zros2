"""Unit tests for the semantic layer used by runtime and stub renderers."""

import math
import pathlib

import pytest

from zros2.generator.parsing import MsgDefinition, MsgField
from zros2.generator.parsing._types import parse_type
from zros2.generator.semantics._field_semantics import build_field_semantics
from zros2.generator.semantics._literal_values import (
    default_scalar,
    parse_literal,
    unquote,
)
from zros2.generator.semantics._native_types import native_stub_type, python_type
from zros2.generator.semantics._resolve_types import resolve_type
from zros2.generator.semantics._type_context import (
    build_type_context,
    constant_int_map,
    resolve_size,
)


class TestLiteralValues:
    def test_unquote(self):
        assert unquote('"hello"') == "hello"
        assert unquote("'hello'") == "hello"
        assert unquote("hello world") == "hello world"

    def test_parse_scalar_literals(self):
        assert parse_literal("42", parse_type("int32"), "x") == 42
        assert parse_literal("0x10", parse_type("int32"), "x") == 16
        assert parse_literal("true", parse_type("bool"), "x") is True
        assert parse_literal("false", parse_type("bool"), "x") is False
        assert parse_literal("hello world", parse_type("string"), "x") == "hello world"
        nan_value = parse_literal("nan", parse_type("float64"), "x")
        assert isinstance(nan_value, float)
        assert math.isnan(nan_value)

    def test_parse_invalid_literal(self):
        with pytest.raises(ValueError, match="invalid bool"):
            parse_literal("maybe", parse_type("bool"), "x")
        with pytest.raises(ValueError, match="invalid integer"):
            parse_literal("x", parse_type("int32"), "x")

    def test_default_scalar(self):
        assert default_scalar(parse_type("int32")) == 0
        assert default_scalar(parse_type("string")) == ""
        assert default_scalar(parse_type("bool")) is False
        with pytest.raises(ValueError, match="Unsupported scalar"):
            default_scalar(parse_type("time"))


class TestTypeContext:
    def test_constant_map_and_bounds(self):
        defn = MsgDefinition(
            package="pkg",
            type_name="M",
            type_kind="msg",
            constants=[
                MsgField(name="SIZE", type_str="int32", default="4", is_constant=True)
            ],
        )
        constants = constant_int_map(defn)
        assert constants == {"SIZE": 4}
        assert resolve_size("SIZE", constants, "x") == 4
        assert resolve_size(3, constants, "x") == 3
        with pytest.raises(ValueError, match="unknown constant"):
            resolve_size("MISSING", constants, "x")
        with pytest.raises(ValueError, match="negative bound"):
            resolve_size(-1, constants, "x")

        context = build_type_context(defn)
        assert context.constants["SIZE"] == 4
        assert context.bound("SIZE", "x") == 4
        assert context.resolve("int32").annotation_expr == "int32"


class TestFieldSemantics:
    def test_container_and_nested_flags(self):
        defn = MsgDefinition(
            package="pkg",
            type_name="M",
            type_kind="msg",
            fields=[
                MsgField(name="values", type_str="int32[]"),
                MsgField(name="header", type_str="std_msgs/msg/Header"),
            ],
        )
        context = build_type_context(defn)
        values = build_field_semantics(defn.fields[0], defn, "", context=context)
        header = build_field_semantics(defn.fields[1], defn, "", context=context)
        assert values.is_container is True
        assert values.is_nested is False
        assert values.native_type == "Sequence[int]"
        assert header.is_container is False
        assert header.is_nested is True
        assert header.native_type == "Header"

    def test_native_types(self):
        assert python_type(parse_type("int32"), resolve_type("int32")) == "int"
        assert python_type(parse_type("string"), resolve_type("string")) == "str"
        assert native_stub_type("int32[4]") == ("tuple[int, ...]", False)
        assert native_stub_type("int32[]") == ("Sequence[int]", True)


class TestLineBudgets:
    def test_codegen_modules_stay_small(self):
        root = pathlib.Path(__file__).resolve().parents[1] / "src/zros2/generator"
        budgets = {
            "codegen/_message/_assemble.py": 300,
            "codegen/_message/_plan.py": 300,
            "codegen/_message/_methods.py": 240,
            "codegen/_message/_defaults.py": 160,
            "codegen/_merge.py": 300,
            "codegen/_registry.py": 80,
            "codegen/_registry_common.py": 200,
            "codegen/_registry_messages.py": 200,
            "codegen/_registry_services.py": 160,
            "codegen/_registry_actions.py": 160,
            "codegen/_service_action.py": 360,
            "codegen/_stubs.py": 400,
            "pipeline/_generate.py": 270,
        }
        for rel, limit in budgets.items():
            lines = len((root / rel).read_text(encoding="utf-8").splitlines())
            assert lines < limit, f"{rel}: {lines} lines (budget {limit})"


class TestBoundResolution:
    def test_known_constant_bound(self):
        resolved = resolve_type("uint8[SIZE]", constants={"SIZE": 4})
        assert resolved.annotation_expr == "array[uint8, 4]"

    def test_unknown_constant_bound_raises(self):
        with pytest.raises(ValueError, match="unknown constant 'SIZE'"):
            resolve_type("uint8[SIZE]")

    def test_build_field_semantics_builds_context_when_omitted(self):
        defn = MsgDefinition(
            package="pkg",
            type_name="Demo",
            type_kind="msg",
            fields=[MsgField(name="data", type_str="uint8[SIZE]")],
            constants=[
                MsgField(
                    name="SIZE",
                    type_str="int32",
                    default="4",
                    is_constant=True,
                )
            ],
        )
        values = build_field_semantics(defn.fields[0], defn, "")
        assert values.resolved.annotation_expr == "array[uint8, 4]"
