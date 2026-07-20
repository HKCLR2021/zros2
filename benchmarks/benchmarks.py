"""Benchmarks for from_dict / to_dict and message construction.

Uses **codegen-generated message types** with hardcoded to_dict/from_dict,
eliminating all runtime reflection.  Run with::

    pytest benchmarks/benchmarks.py --benchmark-only
    pytest benchmarks/benchmarks.py --benchmark-histogram=bench_hist
"""

import ast
from dataclasses import dataclass, field
from typing import Any, ClassVar

from zros2.generator._codegen._msg import generate_message_module
from zros2.generator._parser import MsgDefinition, MsgField


# ═══════════════════════════════════════════════════════════════════════
# Helper: generate a message class via the codegen
# ═══════════════════════════════════════════════════════════════════════

def _gen(name: str, fields: list[MsgField],
         root_package: str = "") -> type:
    """Generate, compile and return a message class with hardcoded methods."""
    if root_package:
        defn = MsgDefinition(
            package=root_package, type_name=name,
            type_kind="msg", fields=fields,
        )
    else:
        defn = MsgDefinition(
            package="bench", type_name=name,
            type_kind="msg", fields=fields,
        )
    code = generate_message_module(defn, root_package=root_package)

    # Strip imports that won't resolve outside a full ROS package tree
    kept: list[str] = []
    for line in code.splitlines():
        if line.startswith("from ") and not any(
            line.startswith(f"from {p}")
            for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
        ):
            continue
        kept.append(line)
    cleaned = "\n".join(kept)

    ns: dict = {}
    exec(compile(ast.parse(cleaned), f"<gen_{name}>", "exec"), ns)
    return ns[name]


def _gen_pair(base_pkg: str,
              name_a: str, fields_a: list[MsgField],
              name_b: str, fields_b: list[MsgField],
              ) -> tuple[type, type]:
    """Generate two classes where the second references the first.

    Execs both in the same namespace so cross-module references resolve.
    """
    defn_a = MsgDefinition(
        package=base_pkg, type_name=name_a,
        type_kind="msg", fields=fields_a,
    )
    defn_b = MsgDefinition(
        package=base_pkg, type_name=name_b,
        type_kind="msg", fields=fields_b,
    )

    def _clean(defn: MsgDefinition) -> str:
        code = generate_message_module(defn)
        kept: list[str] = []
        for line in code.splitlines():
            if line.startswith("from ") and not any(
                line.startswith(f"from {p}")
                for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
            ):
                continue
            kept.append(line)
        return "\n".join(kept)

    ns: dict = {}
    exec(compile(ast.parse(_clean(defn_a)), f"<gen_{name_a}>", "exec"), ns)
    exec(compile(ast.parse(_clean(defn_b)), f"<gen_{name_b}>", "exec"), ns)
    return ns[name_a], ns[name_b]


# ═══════════════════════════════════════════════════════════════════════
# Dimension 1 — Data size
# ═══════════════════════════════════════════════════════════════════════

Msg10B = _gen("Msg10B", [
    MsgField(name="id", type_str="int32"),
    MsgField(name="code", type_str="int32"),
])
Msg512B = _gen("Msg512B", [
    MsgField(name="id", type_str="int32"),
    MsgField(name="data", type_str="string"),
])
Msg1KB = _gen("Msg1KB", [
    MsgField(name="id", type_str="int32"),
    MsgField(name="data", type_str="string"),
])
Msg1MB = _gen("Msg1MB", [
    MsgField(name="data", type_str="string"),
])

_PAYLOAD_512B = "x" * 500
_PAYLOAD_1KB = "x" * 1000
_PAYLOAD_1MB = "x" * 1_000_000


# ═══════════════════════════════════════════════════════════════════════
# Dimension 2 — Field count (flat messages)
# ═══════════════════════════════════════════════════════════════════════

Fields1 = _gen("Fields1", [MsgField(name="f0", type_str="int32")])
Fields3 = _gen("Fields3", [
    MsgField(name="f0", type_str="int32"),
    MsgField(name="f1", type_str="string"),
    MsgField(name="f2", type_str="float64"),
])
Fields8 = _gen("Fields8", [
    MsgField(name=f"f{i}", type_str=(
        "int32" if i % 3 == 0 else
        "float64" if i % 3 == 1 else
        "string"
    )) for i in range(8)
])
Fields15 = _gen("Fields15", [
    MsgField(name=f"f{i}", type_str=(
        "int32" if i % 3 == 0 else
        "float64" if i % 3 == 1 else
        "string"
    )) for i in range(15)
])

_FIELDS3_VALUES = {"f0": 42, "f1": "hello", "f2": 3.14}
_FIELDS8_VALUES = {f"f{i}": (
    42 if i % 3 == 0 else
    3.14 if i % 3 == 1 else
    "hello"
) for i in range(8)}
_FIELDS15_VALUES = {f"f{i}": (
    42 if i % 3 == 0 else
    3.14 if i % 3 == 1 else
    "hello"
) for i in range(15)}


# ═══════════════════════════════════════════════════════════════════════
# Dimension 3 — Nesting
# ═══════════════════════════════════════════════════════════════════════
#
# All nested types share a single namespace so cross-references resolve.

_NEST_NS: dict = {}


def _gen_nest(name: str, fields: list[MsgField]) -> type:
    defn = MsgDefinition(package="nest", type_name=name, type_kind="msg", fields=fields)
    code = generate_message_module(defn)
    kept: list[str] = []
    for line in code.splitlines():
        if line.startswith("from ") and not any(
            line.startswith(f"from {p}")
            for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
        ):
            continue
        kept.append(line)
    exec(compile(ast.parse("\n".join(kept)), f"<{name}>", "exec"), _NEST_NS)
    return _NEST_NS[name]


_leaf_fields = [MsgField(name="x", type_str="float64"), MsgField(name="y", type_str="float64"), MsgField(name="label", type_str="string")]

Inner = _gen_nest("Inner", _leaf_fields)
NestL1 = _gen_nest("NestL1", [MsgField(name="inner", type_str="nest/Inner"), MsgField(name="id", type_str="int32")])
NestMid = _gen_nest("NestMid", [MsgField(name="inner", type_str="nest/Inner"), MsgField(name="value", type_str="float64")])
NestDeep = _gen_nest("NestDeep", [MsgField(name="mid", type_str="nest/NestMid"), MsgField(name="tag", type_str="string")])
_Inner3 = _gen_nest("Inner3", _leaf_fields)
NestWide = _gen_nest("NestWide", [
    MsgField(name="left", type_str="nest/Inner3"),
    MsgField(name="right", type_str="nest/Inner3"),
    MsgField(name="center", type_str="nest/Inner3"),
    MsgField(name="id", type_str="int32"),
])
_InnerL = _gen_nest("InnerL", _leaf_fields)
NestList = _gen_nest("NestList", [
    MsgField(name="items", type_str="sequence<nest/InnerL>"),
    MsgField(name="id", type_str="int32"),
])


def _inner_dict(**overrides: Any) -> dict[str, Any]:
    base = {"x": 1, "y": 2.0, "label": "pt"}
    base.update(overrides)
    return base


def _inner_obj(**overrides: Any) -> Any:
    return Inner(x=overrides.get("x", 1),
                 y=overrides.get("y", 2.0),
                 label=overrides.get("label", "pt"))


_NEST_L1_DICT: dict[str, Any] = {"id": 42, "inner": _inner_dict()}
_NEST_L1_OBJ = NestL1(id=42, inner=_inner_obj())

_NEST_DEEP_DICT: dict[str, Any] = {
    "tag": "root",
    "mid": {"value": 1.5, "inner": _inner_dict()},
}
_NEST_DEEP_OBJ = NestDeep(
    tag="root",
    mid=NestMid(value=1.5, inner=_inner_obj()),
)

_NEST_WIDE_DICT: dict[str, Any] = {
    "id": 7,
    "left": _inner_dict(x=1),
    "right": _inner_dict(x=2),
    "center": _inner_dict(x=3),
}
_NEST_WIDE_OBJ = NestWide(
    id=7,
    left=_inner_obj(x=1),
    right=_inner_obj(x=2),
    center=_inner_obj(x=3),
)

_NEST_LIST_DICT: dict[str, Any] = {
    "id": 99,
    "items": [_inner_dict(x=i) for i in range(5)],
}
_NEST_LIST_OBJ = NestList(
    id=99,
    items=[_inner_obj() for _ in range(5)],
)


# ═══════════════════════════════════════════════════════════════════════
# Benchmark classes
# ═══════════════════════════════════════════════════════════════════════

# ── Data-size tests ───────────────────────────────────────────────

class TestSize:
    """Benchmark across different payload sizes (10 B → 1 MB)."""

    # --- Construction ---
    def test_con_10b(self, benchmark):
        benchmark(Msg10B, id=42, code=1)

    def test_con_512b(self, benchmark):
        benchmark(Msg512B, id=42, data=_PAYLOAD_512B)

    def test_con_1kb(self, benchmark):
        benchmark(Msg1KB, id=42, data=_PAYLOAD_1KB)

    def test_con_1mb(self, benchmark):
        benchmark(Msg1MB, data=_PAYLOAD_1MB)

    # --- to_dict ---
    def test_tod_10b(self, benchmark):
        benchmark(Msg10B(id=42, code=1).to_dict)

    def test_tod_512b(self, benchmark):
        benchmark(Msg512B(id=42, data=_PAYLOAD_512B).to_dict)

    def test_tod_1kb(self, benchmark):
        benchmark(Msg1KB(id=42, data=_PAYLOAD_1KB).to_dict)

    def test_tod_1mb(self, benchmark):
        benchmark(Msg1MB(data=_PAYLOAD_1MB).to_dict)

    # --- from_dict ---
    def test_frd_10b(self, benchmark):
        benchmark(Msg10B.from_dict, {"id": 42, "code": 1})

    def test_frd_512b(self, benchmark):
        benchmark(Msg512B.from_dict, {"id": 42, "data": _PAYLOAD_512B})

    def test_frd_1kb(self, benchmark):
        benchmark(Msg1KB.from_dict, {"id": 42, "data": _PAYLOAD_1KB})

    def test_frd_1mb(self, benchmark):
        benchmark(Msg1MB.from_dict, {"data": _PAYLOAD_1MB})

    # --- Round-trip ---
    def test_rt_10b(self, benchmark):
        data: dict[str, Any] = {"id": 42, "code": 1}
        benchmark(lambda: Msg10B.from_dict(data).to_dict())

    def test_rt_512b(self, benchmark):
        data: dict[str, Any] = {"id": 42, "data": _PAYLOAD_512B}
        benchmark(lambda: Msg512B.from_dict(data).to_dict())

    def test_rt_1kb(self, benchmark):
        data: dict[str, Any] = {"id": 42, "data": _PAYLOAD_1KB}
        benchmark(lambda: Msg1KB.from_dict(data).to_dict())

    def test_rt_1mb(self, benchmark):
        data: dict[str, Any] = {"data": _PAYLOAD_1MB}
        benchmark(lambda: Msg1MB.from_dict(data).to_dict())


# ── Field-count tests ────────────────────────────────────────────

class TestFields:
    """Benchmark across flat messages with 1, 3, 8, 15 fields."""

    # --- Construction ---
    def test_con_1f(self, benchmark):
        benchmark(Fields1, f0=42)

    def test_con_3f(self, benchmark):
        benchmark(Fields3, **_FIELDS3_VALUES)

    def test_con_8f(self, benchmark):
        benchmark(Fields8, **_FIELDS8_VALUES)

    def test_con_15f(self, benchmark):
        benchmark(Fields15, **_FIELDS15_VALUES)

    # --- to_dict ---
    def test_tod_1f(self, benchmark):
        benchmark(Fields1(f0=42).to_dict)

    def test_tod_3f(self, benchmark):
        benchmark(Fields3(**_FIELDS3_VALUES).to_dict)

    def test_tod_8f(self, benchmark):
        benchmark(Fields8(**_FIELDS8_VALUES).to_dict)

    def test_tod_15f(self, benchmark):
        benchmark(Fields15(**_FIELDS15_VALUES).to_dict)

    # --- from_dict ---
    def test_frd_1f(self, benchmark):
        benchmark(Fields1.from_dict, {"f0": 42})

    def test_frd_3f(self, benchmark):
        benchmark(Fields3.from_dict, dict(_FIELDS3_VALUES))

    def test_frd_8f(self, benchmark):
        benchmark(Fields8.from_dict, dict(_FIELDS8_VALUES))

    def test_frd_15f(self, benchmark):
        benchmark(Fields15.from_dict, dict(_FIELDS15_VALUES))

    # --- Round-trip ---
    def test_rt_1f(self, benchmark):
        data: dict[str, Any] = {"f0": 42}
        benchmark(lambda: Fields1.from_dict(data).to_dict())

    def test_rt_3f(self, benchmark):
        data = dict(_FIELDS3_VALUES)
        benchmark(lambda: Fields3.from_dict(data).to_dict())

    def test_rt_8f(self, benchmark):
        data = dict(_FIELDS8_VALUES)
        benchmark(lambda: Fields8.from_dict(data).to_dict())

    def test_rt_15f(self, benchmark):
        data = dict(_FIELDS15_VALUES)
        benchmark(lambda: Fields15.from_dict(data).to_dict())


# ── Nesting tests ────────────────────────────────────────────────

class TestNest:
    """Benchmark across nesting patterns: L1, deep, wide, list."""

    # --- Construction ---
    def test_con_l1(self, benchmark):
        benchmark(NestL1, id=42, inner=_inner_obj())

    def test_con_deep(self, benchmark):
        benchmark(NestDeep, tag="root",
                  mid=NestMid(value=1.5, inner=_inner_obj()))

    def test_con_wide(self, benchmark):
        benchmark(NestWide, id=7,
                  left=_inner_obj(x=1),
                  right=_inner_obj(x=2),
                  center=_inner_obj(x=3))

    def test_con_list(self, benchmark):
        benchmark(NestList, id=99,
                  items=[_inner_obj() for _ in range(5)])

    # --- to_dict ---
    def test_tod_l1(self, benchmark):
        benchmark(_NEST_L1_OBJ.to_dict)

    def test_tod_deep(self, benchmark):
        benchmark(_NEST_DEEP_OBJ.to_dict)

    def test_tod_wide(self, benchmark):
        benchmark(_NEST_WIDE_OBJ.to_dict)

    def test_tod_list(self, benchmark):
        benchmark(_NEST_LIST_OBJ.to_dict)

    # --- from_dict ---
    def test_frd_l1(self, benchmark):
        benchmark(NestL1.from_dict, _NEST_L1_DICT)

    def test_frd_deep(self, benchmark):
        benchmark(NestDeep.from_dict, _NEST_DEEP_DICT)

    def test_frd_wide(self, benchmark):
        benchmark(NestWide.from_dict, _NEST_WIDE_DICT)

    def test_frd_list(self, benchmark):
        benchmark(NestList.from_dict, _NEST_LIST_DICT)

    # --- Round-trip ---
    def test_rt_l1(self, benchmark):
        data = dict(_NEST_L1_DICT)
        benchmark(lambda: NestL1.from_dict(data).to_dict())

    def test_rt_deep(self, benchmark):
        data = dict(_NEST_DEEP_DICT)
        benchmark(lambda: NestDeep.from_dict(data).to_dict())

    def test_rt_wide(self, benchmark):
        data = dict(_NEST_WIDE_DICT)
        benchmark(lambda: NestWide.from_dict(data).to_dict())

    def test_rt_list(self, benchmark):
        data = dict(_NEST_LIST_DICT)
        benchmark(lambda: NestList.from_dict(data).to_dict())


# ═══════════════════════════════════════════════════════════════════════
# Dimension 4 — Deep nesting at scale (dynamic generation)
# ═══════════════════════════════════════════════════════════════════════
#
# Instead of hand-writing dozens of types for 1/3/8/15 levels, generate
# them dynamically via the codegen, sharing a single namespace so that
# each level's type references the previous level's type by name.

_DEEP_NS: dict = {}


def _gen_deep(name: str, fields: list[MsgField], pkg: str = "deep") -> type:
    defn = MsgDefinition(package=pkg, type_name=name, type_kind="msg", fields=fields)
    code = generate_message_module(defn)
    kept: list[str] = []
    for line in code.splitlines():
        if line.startswith("from ") and not any(
            line.startswith(f"from {p}")
            for p in ("typing", "dataclasses", "pycdr2", "zros2", "collections")
        ):
            continue
        kept.append(line)
    exec(compile(ast.parse("\n".join(kept)), f"<{name}>", "exec"), _DEEP_NS)
    return _DEEP_NS[name]


# ── Leaf type used by all patterns ────────────────────────────────

_DEEP_LEAF = _gen_deep("DeepLeaf", [MsgField(name="val", type_str="int32")])


# ── Pattern 1: Chain ──────────────────────────────────────────────

def _make_chain_types(levels: int) -> tuple[type, ...]:
    """Return (Leaf, L2, L3, ..., L<levels>)."""
    types = [_DEEP_LEAF]
    for i in range(2, levels + 1):
        prev = types[-1]
        prev_name = prev.__name__
        typ = _gen_deep(f"ChainL{i}", [
            MsgField(name="child", type_str=f"deep/{prev_name}"),
            MsgField(name="val", type_str="int32"),
        ])
        types.append(typ)
    return tuple(types)


def _chain_dict(levels: int, val: int = 1) -> dict[str, Any]:
    if levels <= 1:
        return {"val": val}
    return {"child": _chain_dict(levels - 1, val), "val": val}


def _chain_obj(chain_type: type, levels: int, val: int = 1) -> Any:
    if levels <= 1:
        return chain_type(val=val)
    child_type = _DEEP_NS[chain_type.__annotations__["child"].__name__]
    return chain_type(child=_chain_obj(child_type, levels - 1, val), val=val)


_CHAIN_TYPES: dict[int, type] = {}
_CHAIN_DICTS: dict[int, dict[str, Any]] = {}
_CHAIN_OBJS: dict[int, Any] = {}
for depth in (1, 3, 8, 15):
    types = _make_chain_types(depth)
    _CHAIN_TYPES[depth] = types[-1]
    _CHAIN_DICTS[depth] = _chain_dict(depth)
    _CHAIN_OBJS[depth] = _chain_obj(types[-1], depth)


# ── Pattern 2: List chain ─────────────────────────────────────────

def _make_list_chain_types(levels: int) -> tuple[type, ...]:
    """Return (Leaf, L2, L3, ..., L<levels>) for list-chain."""
    types = [_DEEP_LEAF]
    for i in range(2, levels + 1):
        prev = types[-1]
        prev_name = prev.__name__
        typ = _gen_deep(f"ListChainL{i}", [
            MsgField(name="items", type_str=f"sequence<deep/{prev_name}>"),
            MsgField(name="val", type_str="int32"),
        ])
        types.append(typ)
    return tuple(types)


def _list_chain_dict(levels: int, val: int = 1,
                     items_per_level: int = 2) -> dict[str, Any]:
    if levels <= 1:
        return {"val": val}
    items = [_list_chain_dict(levels - 1, val + i, items_per_level)
             for i in range(items_per_level)]
    return {"items": items, "val": val}


def _list_chain_obj(top_type: type, levels: int, val: int = 1,
                    items_per_level: int = 2) -> Any:
    if levels <= 1:
        return top_type(val=val)
    # pycdr2 wraps sequence annotations as Annotated[Sequence[InnerType], ...]
    annot_items = top_type.__annotations__["items"]
    inner_type = annot_items.__args__[0].__args__[0]  # Sequence[InnerType] → InnerType
    inner_type_name = inner_type.__name__
    inner_cls = _DEEP_NS[inner_type_name]
    items = [_list_chain_obj(inner_cls, levels - 1, val + i, items_per_level)
             for i in range(items_per_level)]
    return top_type(items=items, val=val)


_LIST_CHAIN_TYPES: dict[int, type] = {}
_LIST_CHAIN_DICTS: dict[int, dict[str, Any]] = {}
_LIST_CHAIN_OBJS: dict[int, Any] = {}
for depth in (1, 3, 8, 15):
    types = _make_list_chain_types(depth)
    _LIST_CHAIN_TYPES[depth] = types[-1]
    _LIST_CHAIN_DICTS[depth] = _list_chain_dict(depth)
    _LIST_CHAIN_OBJS[depth] = _list_chain_obj(types[-1], depth)


# ── Pattern 3: Mixed chain (object + list per level) ──────────────

def _make_mixed_types(levels: int) -> tuple[type, ...]:
    types = [_DEEP_LEAF]
    sub_types: list[type] = []
    for i in range(2, levels + 1):
        prev = types[-1]
        prev_name = prev.__name__
        sub = _gen_deep(f"MixSubL{i}", [MsgField(name="val", type_str="int32")])
        sub_types.append(sub)
        typ = _gen_deep(f"MixL{i}", [
            MsgField(name="child", type_str=f"deep/{prev_name}"),
            MsgField(name="items", type_str=f"sequence<deep/MixSubL{i}>"),
            MsgField(name="val", type_str="int32"),
        ])
        types.append(typ)
    return tuple(types)


def _mixed_dict(levels: int, val: int = 1,
                items_per_level: int = 2) -> dict[str, Any]:
    if levels <= 1:
        return {"val": val}
    return {
        "child": _mixed_dict(levels - 1, val, items_per_level),
        "items": [{"val": val + i} for i in range(items_per_level)],
        "val": val,
    }


def _mixed_obj(top_type: type, levels: int, val: int = 1,
               items_per_level: int = 2) -> Any:
    if levels <= 1:
        return top_type(val=val)
    hints = top_type.__annotations__
    # child is a bare class reference (no Annotated wrapper for nested msgs)
    inner_child = _DEEP_NS[hints["child"].__name__]
    # items is Annotated[Sequence[InnerType], ...]
    inner_item_type = hints["items"].__args__[0].__args__[0]
    inner_item = _DEEP_NS[inner_item_type.__name__]
    items = [inner_item(val=val + i) for i in range(items_per_level)]
    return top_type(
        child=_mixed_obj(inner_child, levels - 1, val, items_per_level),
        items=items,
        val=val,
    )


_MIXED_TYPES: dict[int, type] = {}
_MIXED_DICTS: dict[int, dict[str, Any]] = {}
_MIXED_OBJS: dict[int, Any] = {}
for depth in (1, 3, 8, 15):
    types = _make_mixed_types(depth)
    _MIXED_TYPES[depth] = types[-1]
    _MIXED_DICTS[depth] = _mixed_dict(depth)
    _MIXED_OBJS[depth] = _mixed_obj(types[-1], depth)


# ── Deep nesting benchmark class ──────────────────────────────────

class TestDeepNest:
    """Benchmark across 1/3/8/15 levels for three nesting patterns."""

    # ── CHAIN ──────────────────────────────────────────────────────

    def test_chain_con_l1(self, benchmark):
        benchmark(_CHAIN_TYPES[1], val=1)

    def test_chain_con_l3(self, benchmark):
        benchmark(_CHAIN_TYPES[3], **_CHAIN_DICTS[3])

    def test_chain_con_l8(self, benchmark):
        benchmark(_CHAIN_TYPES[8], **_CHAIN_DICTS[8])

    def test_chain_con_l15(self, benchmark):
        benchmark(_CHAIN_TYPES[15], **_CHAIN_DICTS[15])

    def test_chain_tod_l1(self, benchmark):
        benchmark(_CHAIN_OBJS[1].to_dict)

    def test_chain_tod_l3(self, benchmark):
        benchmark(_CHAIN_OBJS[3].to_dict)

    def test_chain_tod_l8(self, benchmark):
        benchmark(_CHAIN_OBJS[8].to_dict)

    def test_chain_tod_l15(self, benchmark):
        benchmark(_CHAIN_OBJS[15].to_dict)

    def test_chain_frd_l1(self, benchmark):
        benchmark(_CHAIN_TYPES[1].from_dict, _CHAIN_DICTS[1])

    def test_chain_frd_l3(self, benchmark):
        benchmark(_CHAIN_TYPES[3].from_dict, _CHAIN_DICTS[3])

    def test_chain_frd_l8(self, benchmark):
        benchmark(_CHAIN_TYPES[8].from_dict, _CHAIN_DICTS[8])

    def test_chain_frd_l15(self, benchmark):
        benchmark(_CHAIN_TYPES[15].from_dict, _CHAIN_DICTS[15])

    def test_chain_rt_l1(self, benchmark):
        benchmark(lambda: _CHAIN_TYPES[1].from_dict(_CHAIN_DICTS[1]).to_dict())

    def test_chain_rt_l3(self, benchmark):
        benchmark(lambda: _CHAIN_TYPES[3].from_dict(_CHAIN_DICTS[3]).to_dict())

    def test_chain_rt_l8(self, benchmark):
        benchmark(lambda: _CHAIN_TYPES[8].from_dict(_CHAIN_DICTS[8]).to_dict())

    def test_chain_rt_l15(self, benchmark):
        benchmark(lambda: _CHAIN_TYPES[15].from_dict(_CHAIN_DICTS[15]).to_dict())

    # ── LIST ───────────────────────────────────────────────────────

    def test_list_con_l1(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[1], val=1)

    def test_list_con_l3(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[3], **_LIST_CHAIN_DICTS[3])

    def test_list_con_l8(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[8], **_LIST_CHAIN_DICTS[8])

    def test_list_con_l15(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[15], **_LIST_CHAIN_DICTS[15])

    def test_list_tod_l1(self, benchmark):
        benchmark(_LIST_CHAIN_OBJS[1].to_dict)

    def test_list_tod_l3(self, benchmark):
        benchmark(_LIST_CHAIN_OBJS[3].to_dict)

    def test_list_tod_l8(self, benchmark):
        benchmark(_LIST_CHAIN_OBJS[8].to_dict)

    def test_list_tod_l15(self, benchmark):
        benchmark(_LIST_CHAIN_OBJS[15].to_dict)

    def test_list_frd_l1(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[1].from_dict, _LIST_CHAIN_DICTS[1])

    def test_list_frd_l3(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[3].from_dict, _LIST_CHAIN_DICTS[3])

    def test_list_frd_l8(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[8].from_dict, _LIST_CHAIN_DICTS[8])

    def test_list_frd_l15(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[15].from_dict, _LIST_CHAIN_DICTS[15])

    def test_list_rt_l1(self, benchmark):
        benchmark(lambda: _LIST_CHAIN_TYPES[1].from_dict(_LIST_CHAIN_DICTS[1]).to_dict())

    def test_list_rt_l3(self, benchmark):
        benchmark(lambda: _LIST_CHAIN_TYPES[3].from_dict(_LIST_CHAIN_DICTS[3]).to_dict())

    def test_list_rt_l8(self, benchmark):
        benchmark(lambda: _LIST_CHAIN_TYPES[8].from_dict(_LIST_CHAIN_DICTS[8]).to_dict())

    def test_list_rt_l15(self, benchmark):
        benchmark(lambda: _LIST_CHAIN_TYPES[15].from_dict(_LIST_CHAIN_DICTS[15]).to_dict())

    # ── MIXED ──────────────────────────────────────────────────────

    def test_mix_con_l1(self, benchmark):
        benchmark(_MIXED_TYPES[1], val=1)

    def test_mix_con_l3(self, benchmark):
        benchmark(_MIXED_TYPES[3], **_MIXED_DICTS[3])

    def test_mix_con_l8(self, benchmark):
        benchmark(_MIXED_TYPES[8], **_MIXED_DICTS[8])

    def test_mix_con_l15(self, benchmark):
        benchmark(_MIXED_TYPES[15], **_MIXED_DICTS[15])

    def test_mix_tod_l1(self, benchmark):
        benchmark(_MIXED_OBJS[1].to_dict)

    def test_mix_tod_l3(self, benchmark):
        benchmark(_MIXED_OBJS[3].to_dict)

    def test_mix_tod_l8(self, benchmark):
        benchmark(_MIXED_OBJS[8].to_dict)

    def test_mix_tod_l15(self, benchmark):
        benchmark(_MIXED_OBJS[15].to_dict)

    def test_mix_frd_l1(self, benchmark):
        benchmark(_MIXED_TYPES[1].from_dict, _MIXED_DICTS[1])

    def test_mix_frd_l3(self, benchmark):
        benchmark(_MIXED_TYPES[3].from_dict, _MIXED_DICTS[3])

    def test_mix_frd_l8(self, benchmark):
        benchmark(_MIXED_TYPES[8].from_dict, _MIXED_DICTS[8])

    def test_mix_frd_l15(self, benchmark):
        benchmark(_MIXED_TYPES[15].from_dict, _MIXED_DICTS[15])

    def test_mix_rt_l1(self, benchmark):
        benchmark(lambda: _MIXED_TYPES[1].from_dict(_MIXED_DICTS[1]).to_dict())

    def test_mix_rt_l3(self, benchmark):
        benchmark(lambda: _MIXED_TYPES[3].from_dict(_MIXED_DICTS[3]).to_dict())

    def test_mix_rt_l8(self, benchmark):
        benchmark(lambda: _MIXED_TYPES[8].from_dict(_MIXED_DICTS[8]).to_dict())

    def test_mix_rt_l15(self, benchmark):
        benchmark(lambda: _MIXED_TYPES[15].from_dict(_MIXED_DICTS[15]).to_dict())
