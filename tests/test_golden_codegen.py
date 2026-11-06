"""Golden tests for the generated message and stub source.

These snapshots deliberately compare normalized generated source, not only
"compiles" or "runs", so refactors that are supposed to preserve output are
caught immediately.  Timestamps are removed; all other bytes are compared.
"""

import os
import pathlib

from zros2.generator.codegen import generate_message_module
from zros2.generator.codegen._stubs import generate_stub_module
from zros2.generator.parsing import MsgDefinition, MsgField

GOLDEN_DIR = pathlib.Path(__file__).with_name("golden")


def _definitions() -> dict[str, MsgDefinition]:
    return {
        "simple": MsgDefinition(
            package="golden",
            type_name="Simple",
            type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="values", type_str="int32[]"),
                MsgField(name="fixed", type_str="uint8[4]"),
                MsgField(name="name", type_str="string<=16"),
            ],
        ),
        "nested": MsgDefinition(
            package="golden",
            type_name="Nested",
            type_kind="msg",
            fields=[
                MsgField(name="header", type_str="std_msgs/msg/Header"),
                MsgField(name="label", type_str="string"),
            ],
        ),
        "collision": MsgDefinition(
            package="golden",
            type_name="Collision",
            type_kind="msg",
            fields=[
                MsgField(name="sequence", type_str="int32[]"),
                MsgField(name="array", type_str="uint8[4]"),
            ],
        ),
        "constants": MsgDefinition(
            package="golden",
            type_name="Constants",
            type_kind="msg",
            constants=[
                MsgField(name="SIZE", type_str="int32", default="4", is_constant=True),
                MsgField(
                    name="GREETING",
                    type_str="string",
                    default="hello world",
                    is_constant=True,
                ),
            ],
            fields=[
                MsgField(name="data", type_str="uint8[SIZE]"),
                MsgField(name="count", type_str="int32", default="7"),
                MsgField(name="label", type_str="string", default="anonymous"),
            ],
        ),
    }


def _normalize(source: str) -> str:
    lines = []
    for line in source.splitlines():
        if line.startswith("# Generated at:"):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def _fixtures() -> dict[str, str]:
    result: dict[str, str] = {}
    for name, defn in _definitions().items():
        result[f"{name}.py.txt"] = _normalize(generate_message_module(defn))
        result[f"{name}.pyi.txt"] = _normalize(generate_stub_module(defn))
    return result


def test_generated_source_matches_golden():
    fixtures = _fixtures()
    update = os.environ.get("UPDATE_GOLDEN") == "1"
    if update:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        for name, source in fixtures.items():
            (GOLDEN_DIR / name).write_text(source, encoding="utf-8")
        return

    expected_names = set(fixtures)
    actual_names = {path.name for path in GOLDEN_DIR.glob("*") if path.is_file()}
    assert actual_names == expected_names, (
        f"golden files mismatch: missing={expected_names - actual_names}, "
        f"extra={actual_names - expected_names}"
    )

    for name, expected in fixtures.items():
        actual = (GOLDEN_DIR / name).read_text(encoding="utf-8")
        assert actual == expected, f"golden mismatch: {name}"
