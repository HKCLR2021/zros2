"""Compare hardcoded vs reflective from_dict/to_dict performance.

Strategy: generate each message type via `generate_message_module`, exec the
resulting source in a controlled namespace, then benchmark the hardcoded methods
head-to-head against the reflective utility functions.
"""

import ast
import time
import sys

from zros2.generator._codegen._msg import generate_message_module
from zros2.generator._parser import MsgDefinition, MsgField
from zros2.types.utils import to_dict as ref_to_dict, from_dict as ref_from_dict


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _clean(code: str) -> str:
    """Remove lines that import external (non-pycdr2/non-zros2/non-stdlib) modules.

    Keeps: ``from typing ...``, ``from dataclasses ...``, ``from pycdr2 ...``,
    ``from zros2 ...``, and everything that is not an import statement.
    Drops: ``from bench.msg._inner import Inner`` etc.
    """
    kept: list[str] = []
    for line in code.splitlines():
        if line.startswith("from ") and not any(
            line.startswith(f"from {p}")
            for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def _gen_class(defn: MsgDefinition, extra_ns: dict | None = None) -> type:
    """Generate code, compile & exec, return the class.

    If *extra_ns* is provided, exec into that namespace (for cross-references).
    """
    code = generate_message_module(defn)
    cleaned = _clean(code)
    ns: dict = {}
    exec(compile(ast.parse(cleaned), "<gen>", "exec"), ns)
    if extra_ns is not None:
        extra_ns.update(ns)
    class_name = defn.type_name.split("/")[-1].replace("-", "_")
    return ns[class_name]


def _gen_pair(
    defn_a: MsgDefinition, defn_b: MsgDefinition,
) -> tuple[type, type]:
    """Generate two classes where *defn_b* references *defn_a*.

    Execs both in the same namespace so cross-module references resolve.
    """
    code_a = generate_message_module(defn_a)
    code_b = generate_message_module(defn_b)

    ns: dict = {}
    exec(compile(ast.parse(_clean(code_a)), "<gen_a>", "exec"), ns)
    exec(compile(ast.parse(_clean(code_b)), "<gen_b>", "exec"), ns)

    name_a = defn_a.type_name.split("/")[-1].replace("-", "_")
    name_b = defn_b.type_name.split("/")[-1].replace("-", "_")
    return ns[name_a], ns[name_b]


def _bench(fn, N: int):
    for _ in range(200):
        fn()
    t0 = time.perf_counter()
    for _ in range(N):
        fn()
    t1 = time.perf_counter()
    return (t1 - t0) / N * 1e9


def _header(title: str):
    print()
    print("═" * 65)
    print(f"  {title}")
    print("═" * 65)


def _row(label: str, hard_ns: float, ref_ns: float):
    print(f"  {label:30s}  {hard_ns:8.0f} ns  {ref_ns:8.0f} ns  {ref_ns/hard_ns:5.1f}×")


# ═══════════════════════════════════════════════════════════════════════
# Dimension 1 — Field count
# ═══════════════════════════════════════════════════════════════════════

_header("Dimension 1 — Field count")

for n_fields, fields in [
    (1, [MsgField(name="val", type_str="int32")]),
    (3, [MsgField(name="a", type_str="int32"), MsgField(name="b", type_str="float64"), MsgField(name="c", type_str="string")]),
    (8, [MsgField(name=f"f{i}", type_str="int32") for i in range(8)]),
    (15, [MsgField(name=f"f{i}", type_str=("int32" if i % 3 == 0 else "float64" if i % 3 == 1 else "string")) for i in range(15)]),
]:
    Cls = _gen_class(MsgDefinition(package="bench", type_name=f"F{n_fields}", type_kind="msg", fields=fields))

    kwargs = {}
    for f in fields:
        kwargs[f.name] = 42 if "int" in f.type_str else (3.14 if "float" in f.type_str else "hello")
    obj = Cls(**kwargs)
    data = dict(kwargs)

    N = 50000
    _ = ref_from_dict(Cls, data); _ = ref_to_dict(obj)

    print(f"\n  {n_fields} field{'s' if n_fields > 1 else ''}:")
    _row("to_dict", _bench(lambda: obj.to_dict(), N), _bench(lambda: ref_to_dict(obj), N))
    _row("from_dict", _bench(lambda: Cls.from_dict(data), N), _bench(lambda: ref_from_dict(Cls, data), N))


# ═══════════════════════════════════════════════════════════════════════
# Dimension 2 — Arrays
# ═══════════════════════════════════════════════════════════════════════

_header("Dimension 2 — Arrays")

Arr = _gen_class(MsgDefinition(
    package="bench", type_name="Arr", type_kind="msg",
    fields=[MsgField(name="values", type_str="float64[]"), MsgField(name="id", type_str="int32")],
))
obj_arr = Arr(values=[1.0, 2.0, 3.0, 4.0, 5.0], id=42)
data_arr = {"values": [1.0, 2.0, 3.0, 4.0, 5.0], "id": 42}
N = 50000
_ = ref_from_dict(Arr, data_arr); _ = ref_to_dict(obj_arr)

print("\n  Arr { values: float64[5], id: int32 }:")
_row("to_dict", _bench(lambda: obj_arr.to_dict(), N), _bench(lambda: ref_to_dict(obj_arr), N))
_row("from_dict", _bench(lambda: Arr.from_dict(data_arr), N), _bench(lambda: ref_from_dict(Arr, data_arr), N))


# ═══════════════════════════════════════════════════════════════════════
# Dimension 3 — Nesting
# ═══════════════════════════════════════════════════════════════════════

_header("Dimension 3 — Nesting")

Inner, Outer = _gen_pair(
    MsgDefinition(package="bench", type_name="Inner", type_kind="msg", fields=[
        MsgField(name="x", type_str="float64"), MsgField(name="y", type_str="float64"),
    ]),
    MsgDefinition(package="bench", type_name="Outer", type_kind="msg", fields=[
        MsgField(name="inner", type_str="bench/Inner"), MsgField(name="label", type_str="string"),
    ]),
)

obj_nest = Outer(inner=Inner(x=1.0, y=2.0), label="pt")
data_nest = {"inner": {"x": 1.0, "y": 2.0}, "label": "pt"}
N = 20000
_ = ref_from_dict(Outer, data_nest); _ = ref_to_dict(obj_nest)

print("\n  Outer { inner: Inner, label: str }:")
_row("to_dict", _bench(lambda: obj_nest.to_dict(), N), _bench(lambda: ref_to_dict(obj_nest), N))
_row("from_dict", _bench(lambda: Outer.from_dict(data_nest), N), _bench(lambda: ref_from_dict(Outer, data_nest), N))
