"""Benchmarks for from_dict / to_dict and message construction.

Covers three dimensions of performance:

* **Data size** — 10 B, 512 B, 1 KB, 1 MB string payloads
* **Field count** — flat messages with 1, 3, 8, 15 fields
* **Nesting depth** — shallow (1 level), deep (3 levels), wide (3 branches),
  and list-of-struct nesting

Run with::

    pytest tests/test_benchmarks.py --benchmark-only
    pytest tests/test_benchmarks.py --benchmark-histogram=bench_hist
"""

from dataclasses import dataclass, field
from typing import Any, ClassVar

from zros2.types.utils import from_dict, to_dict


# ── Helper: minimal RosMessage protocol stub ───────────────────────

class _RosMessageStub:
    """Minimal ``RosMessage`` protocol implementation for benchmark dataclasses."""

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


# ═══════════════════════════════════════════════════════════════════
# Dimension 1 — Data size
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Msg10B(_RosMessageStub):
    """~10 B payload."""
    id: int = 0
    code: int = 0


@dataclass
class Msg512B(_RosMessageStub):
    """~512 B payload."""
    id: int = 0
    data: str = ""


@dataclass
class Msg1KB(_RosMessageStub):
    """~1 KB payload."""
    id: int = 0
    data: str = ""


@dataclass
class Msg1MB(_RosMessageStub):
    """~1 MB payload."""
    data: str = ""


# ── Payload constants ─────────────────────────────────────────────

_PAYLOAD_512B = "x" * 500       # ≈ 512 B
_PAYLOAD_1KB = "x" * 1000       # ≈ 1 KB
_PAYLOAD_1MB = "x" * 1_000_000  # ≈ 1 MB


# ═══════════════════════════════════════════════════════════════════
# Dimension 2 — Field count (flat messages)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Fields1(_RosMessageStub):
    f0: int = 0


@dataclass
class Fields3(_RosMessageStub):
    f0: int = 0
    f1: str = ""
    f2: float = 0.0


@dataclass
class Fields8(_RosMessageStub):
    f0: int = 0
    f1: str = ""
    f2: float = 0.0
    f3: int = 0
    f4: str = ""
    f5: float = 0.0
    f6: int = 0
    f7: str = ""


@dataclass
class Fields15(_RosMessageStub):
    f0: int = 0
    f1: str = ""
    f2: float = 0.0
    f3: int = 0
    f4: str = ""
    f5: float = 0.0
    f6: int = 0
    f7: str = ""
    f8: float = 0.0
    f9: int = 0
    f10: str = ""
    f11: float = 0.0
    f12: int = 0
    f13: str = ""
    f14: float = 0.0


_FIELDS3_VALUES = {"f0": 42, "f1": "hello", "f2": 3.14}
_FIELDS8_VALUES = {
    "f0": 1, "f1": "a", "f2": 0.1,
    "f3": 2, "f4": "b", "f5": 0.2,
    "f6": 3, "f7": "c",
}
_FIELDS15_VALUES = {
    "f0": 1, "f1": "a", "f2": 0.1,
    "f3": 2, "f4": "b", "f5": 0.2,
    "f6": 3, "f7": "c", "f8": 0.3,
    "f9": 4, "f10": "d", "f11": 0.4,
    "f12": 5, "f13": "e", "f14": 0.5,
}


# ═══════════════════════════════════════════════════════════════════
# Dimension 3 — Nesting
# ═══════════════════════════════════════════════════════════════════

# ── Shared leaf type ─────────────────────────────────────────────

@dataclass
class Inner(_RosMessageStub):
    """Leaf struct used by all nesting tests."""
    x: int = 0
    y: float = 0.0
    label: str = ""


# ── Single-level nesting ─────────────────────────────────────────

@dataclass
class NestL1(_RosMessageStub):
    """Outer → Inner (1 level)."""
    inner: Inner = field(default_factory=Inner)
    id: int = 0


# ── Deep nesting (3 levels) ──────────────────────────────────────

@dataclass
class NestMid(_RosMessageStub):
    """Mid → Inner (leaf)."""
    inner: Inner = field(default_factory=Inner)
    value: float = 0.0


@dataclass
class NestDeep(_RosMessageStub):
    """Outer → Mid → Inner (3 levels)."""
    mid: NestMid = field(default_factory=NestMid)
    tag: str = ""


# ── Wide nesting (3 inner branches) ──────────────────────────────

@dataclass
class NestWide(_RosMessageStub):
    """Outer with 3 inner struct fields."""
    left: Inner = field(default_factory=Inner)
    right: Inner = field(default_factory=Inner)
    center: Inner = field(default_factory=Inner)
    id: int = 0


# ── List-of-struct nesting ───────────────────────────────────────

@dataclass
class NestList(_RosMessageStub):
    """Outer with list[Inner]."""
    items: list[Inner] = field(default_factory=list)
    id: int = 0


# ── Nesting dict / instance factories ────────────────────────────

def _inner_dict(**overrides: Any) -> dict[str, Any]:
    base = {"x": 1, "y": 2.0, "label": "pt"}
    base.update(overrides)
    return base


def _inner_obj(**overrides: Any) -> Inner:
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


# ═══════════════════════════════════════════════════════════════════
# Benchmark classes
# ═══════════════════════════════════════════════════════════════════

def _size_benchmark_name(name: str) -> str:
    return name


def _fields_benchmark_name(name: str) -> str:
    return name


def _nest_benchmark_name(name: str) -> str:
    return name


# ── Data-size tests (moved from original) ────────────────────────

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
        benchmark(to_dict, Msg10B(id=42, code=1))

    def test_tod_512b(self, benchmark):
        benchmark(to_dict, Msg512B(id=42, data=_PAYLOAD_512B))

    def test_tod_1kb(self, benchmark):
        benchmark(to_dict, Msg1KB(id=42, data=_PAYLOAD_1KB))

    def test_tod_1mb(self, benchmark):
        benchmark(to_dict, Msg1MB(data=_PAYLOAD_1MB))

    # --- from_dict ---
    def test_frd_10b(self, benchmark):
        benchmark(from_dict, Msg10B, {"id": 42, "code": 1})

    def test_frd_512b(self, benchmark):
        benchmark(from_dict, Msg512B, {"id": 42, "data": _PAYLOAD_512B})

    def test_frd_1kb(self, benchmark):
        benchmark(from_dict, Msg1KB, {"id": 42, "data": _PAYLOAD_1KB})

    def test_frd_1mb(self, benchmark):
        benchmark(from_dict, Msg1MB, {"data": _PAYLOAD_1MB})

    # --- Round-trip ---
    def test_rt_10b(self, benchmark):
        data: dict[str, Any] = {"id": 42, "code": 1}
        benchmark(lambda: to_dict(from_dict(Msg10B, data)))

    def test_rt_512b(self, benchmark):
        data: dict[str, Any] = {"id": 42, "data": _PAYLOAD_512B}
        benchmark(lambda: to_dict(from_dict(Msg512B, data)))

    def test_rt_1kb(self, benchmark):
        data: dict[str, Any] = {"id": 42, "data": _PAYLOAD_1KB}
        benchmark(lambda: to_dict(from_dict(Msg1KB, data)))

    def test_rt_1mb(self, benchmark):
        data: dict[str, Any] = {"data": _PAYLOAD_1MB}
        benchmark(lambda: to_dict(from_dict(Msg1MB, data)))


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
        benchmark(to_dict, Fields1(f0=42))

    def test_tod_3f(self, benchmark):
        benchmark(to_dict, Fields3(**_FIELDS3_VALUES))

    def test_tod_8f(self, benchmark):
        benchmark(to_dict, Fields8(**_FIELDS8_VALUES))

    def test_tod_15f(self, benchmark):
        benchmark(to_dict, Fields15(**_FIELDS15_VALUES))

    # --- from_dict ---
    def test_frd_1f(self, benchmark):
        benchmark(from_dict, Fields1, {"f0": 42})

    def test_frd_3f(self, benchmark):
        benchmark(from_dict, Fields3, dict(_FIELDS3_VALUES))

    def test_frd_8f(self, benchmark):
        benchmark(from_dict, Fields8, dict(_FIELDS8_VALUES))

    def test_frd_15f(self, benchmark):
        benchmark(from_dict, Fields15, dict(_FIELDS15_VALUES))

    # --- Round-trip ---
    def test_rt_1f(self, benchmark):
        data: dict[str, Any] = {"f0": 42}
        benchmark(lambda: to_dict(from_dict(Fields1, data)))

    def test_rt_3f(self, benchmark):
        data = dict(_FIELDS3_VALUES)
        benchmark(lambda: to_dict(from_dict(Fields3, data)))

    def test_rt_8f(self, benchmark):
        data = dict(_FIELDS8_VALUES)
        benchmark(lambda: to_dict(from_dict(Fields8, data)))

    def test_rt_15f(self, benchmark):
        data = dict(_FIELDS15_VALUES)
        benchmark(lambda: to_dict(from_dict(Fields15, data)))


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
        benchmark(to_dict, _NEST_L1_OBJ)

    def test_tod_deep(self, benchmark):
        benchmark(to_dict, _NEST_DEEP_OBJ)

    def test_tod_wide(self, benchmark):
        benchmark(to_dict, _NEST_WIDE_OBJ)

    def test_tod_list(self, benchmark):
        benchmark(to_dict, _NEST_LIST_OBJ)

    # --- from_dict ---
    def test_frd_l1(self, benchmark):
        benchmark(from_dict, NestL1, _NEST_L1_DICT)

    def test_frd_deep(self, benchmark):
        benchmark(from_dict, NestDeep, _NEST_DEEP_DICT)

    def test_frd_wide(self, benchmark):
        benchmark(from_dict, NestWide, _NEST_WIDE_DICT)

    def test_frd_list(self, benchmark):
        benchmark(from_dict, NestList, _NEST_LIST_DICT)

    # --- Round-trip ---
    def test_rt_l1(self, benchmark):
        data = dict(_NEST_L1_DICT)
        benchmark(lambda: to_dict(from_dict(NestL1, data)))

    def test_rt_deep(self, benchmark):
        data = dict(_NEST_DEEP_DICT)
        benchmark(lambda: to_dict(from_dict(NestDeep, data)))

    def test_rt_wide(self, benchmark):
        data = dict(_NEST_WIDE_DICT)
        benchmark(lambda: to_dict(from_dict(NestWide, data)))

    def test_rt_list(self, benchmark):
        data = dict(_NEST_LIST_DICT)
        benchmark(lambda: to_dict(from_dict(NestList, data)))


# ═══════════════════════════════════════════════════════════════════
# Dimension 4 — Deep nesting at scale (dynamic generation)
# ═══════════════════════════════════════════════════════════════════
#
# Instead of hand-writing dozens of dataclass types for 1/3/8/15
# levels of nesting, we generate them dynamically.  Three patterns:
#
#   CHAIN  — pure object chain: A { child: B { child: C { … } } }
#   LIST   — list at each level: A { items: list[B { items: list[C …] }] }
#   MIXED  — object + list:      A { child: B, items: list[Leaf] }


def _dataclass(
    name: str, bases: tuple[type, ...], ns: dict[str, Any], /,
) -> type:
    """Shorthand: create a named ``@dataclass`` type."""
    return dataclass(type(name, bases, ns))


# ── Leaf type used by all patterns ────────────────────────────────

_DEEP_LEAF = _dataclass("DeepLeaf", (_RosMessageStub,), {
    "__annotations__": {"val": int},
    "val": 0,
})


# ── Pattern 1: Pure object chain ──────────────────────────────────
#   ChainL3 { child: ChainL2 { child: ChainLeaf … } }

def _make_chain_types(levels: int) -> tuple[type, ...]:
    """Return (Leaf, L2, L3, ..., L<levels>)."""
    types = [_DEEP_LEAF]
    for i in range(2, levels + 1):
        prev = types[-1]
        types.append(_dataclass(
            f"ChainL{i}", (_RosMessageStub,), {
                "__annotations__": {"child": prev, "val": int},
                "child": field(default_factory=prev),
                "val": 0,
            },
        ))
    return tuple(types)


def _chain_dict(levels: int, val: int = 1) -> dict[str, Any]:
    """Build a nested dict representing a chain of *levels* depth."""
    if levels <= 1:
        return {"val": val}
    return {"child": _chain_dict(levels - 1, val), "val": val}


def _chain_obj(chain_type: type, levels: int, val: int = 1) -> Any:
    """Build a nested object representing a chain of *levels* depth."""
    if levels <= 1:
        return chain_type(val=val)
    return chain_type(child=_chain_obj(
        chain_type.__annotations__["child"], levels - 1, val), val=val)


# Pre-build types and test data for depths 1, 3, 8, 15
_CHAIN_TYPES: dict[int, type] = {}
_CHAIN_DICTS: dict[int, dict[str, Any]] = {}
_CHAIN_OBJS: dict[int, Any] = {}
for depth in (1, 3, 8, 15):
    types = _make_chain_types(depth)
    _CHAIN_TYPES[depth] = types[-1]
    _CHAIN_DICTS[depth] = _chain_dict(depth)
    _CHAIN_OBJS[depth] = _chain_obj(types[-1], depth)


# ── Pattern 2: List chain ─────────────────────────────────────────
#   ListChainL3 { items: list[ListChainL2 { items: list[ListChainLeaf] }] }

def _make_list_chain_types(levels: int) -> tuple[type, ...]:
    """Return (Leaf, L2, L3, ..., L<levels>) for list-chain."""
    types = [_DEEP_LEAF]
    for i in range(2, levels + 1):
        prev = types[-1]
        types.append(_dataclass(
            f"ListChainL{i}", (_RosMessageStub,), {
                "__annotations__": {"items": list[prev], "val": int},
                "items": field(default_factory=list),
                "val": 0,
            },
        ))
    return tuple(types)


def _list_chain_dict(levels: int, val: int = 1,
                     items_per_level: int = 2) -> dict[str, Any]:
    """Nested dict for list-chain."""
    if levels <= 1:
        return {"val": val}
    items = [_list_chain_dict(levels - 1, val + i, items_per_level)
             for i in range(items_per_level)]
    return {"items": items, "val": val}


def _list_chain_obj(top_type: type, levels: int, val: int = 1,
                    items_per_level: int = 2) -> Any:
    """Nested object for list-chain."""
    if levels <= 1:
        return top_type(val=val)
    inner_type = top_type.__annotations__["items"].__args__[0]
    items = [_list_chain_obj(inner_type, levels - 1, val + i, items_per_level)
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
#   MixL3 {
#       child: MixL2 { child: MixLeaf, items: list[MixSubL2] }
#       items: list[MixSubL3]
#   }
#
# At each level the node carries BOTH a single ``child`` (extending
# the chain) AND a ``items`` list of independent sub-leaves.

def _make_mixed_types(levels: int) -> tuple[type, ...]:
    """Return (Leaf, L2, L3, ..., L<levels>) for mixed chain.

    A parallel set of ``MixSubL<N>`` types is created for the
    ``items`` list at each level.
    """
    types = [_DEEP_LEAF]
    sub_types: list[type] = []
    for i in range(2, levels + 1):
        prev = types[-1]
        sub = _dataclass(
            f"MixSubL{i}", (_RosMessageStub,), {
                "__annotations__": {"val": int},
                "val": 0,
            },
        )
        sub_types.append(sub)
        types.append(_dataclass(
            f"MixL{i}", (_RosMessageStub,), {
                "__annotations__": {
                    "child": prev,
                    "items": list[sub],
                    "val": int,
                },
                "child": field(default_factory=prev),
                "items": field(default_factory=list),
                "val": 0,
            },
        ))
    return tuple(types)


def _mixed_dict(levels: int, val: int = 1,
                items_per_level: int = 2) -> dict[str, Any]:
    """Nested dict for mixed chain."""
    if levels <= 1:
        return {"val": val}
    return {
        "child": _mixed_dict(levels - 1, val, items_per_level),
        "items": [{"val": val + i} for i in range(items_per_level)],
        "val": val,
    }


def _mixed_obj(top_type: type, levels: int, val: int = 1,
               items_per_level: int = 2) -> Any:
    """Nested object for mixed chain."""
    if levels <= 1:
        return top_type(val=val)
    hints = top_type.__annotations__
    inner_child = hints["child"]
    inner_item = hints["items"].__args__[0]
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

    # ── CHAIN: pure object chain ──────────────────────────────────

    def test_chain_con_l1(self, benchmark):
        benchmark(_CHAIN_TYPES[1], val=1)

    def test_chain_con_l3(self, benchmark):
        benchmark(_CHAIN_TYPES[3], **_CHAIN_DICTS[3])

    def test_chain_con_l8(self, benchmark):
        benchmark(_CHAIN_TYPES[8], **_CHAIN_DICTS[8])

    def test_chain_con_l15(self, benchmark):
        benchmark(_CHAIN_TYPES[15], **_CHAIN_DICTS[15])

    def test_chain_tod_l1(self, benchmark):
        benchmark(to_dict, _CHAIN_OBJS[1])

    def test_chain_tod_l3(self, benchmark):
        benchmark(to_dict, _CHAIN_OBJS[3])

    def test_chain_tod_l8(self, benchmark):
        benchmark(to_dict, _CHAIN_OBJS[8])

    def test_chain_tod_l15(self, benchmark):
        benchmark(to_dict, _CHAIN_OBJS[15])

    def test_chain_frd_l1(self, benchmark):
        benchmark(from_dict, _CHAIN_TYPES[1], _CHAIN_DICTS[1])

    def test_chain_frd_l3(self, benchmark):
        benchmark(from_dict, _CHAIN_TYPES[3], _CHAIN_DICTS[3])

    def test_chain_frd_l8(self, benchmark):
        benchmark(from_dict, _CHAIN_TYPES[8], _CHAIN_DICTS[8])

    def test_chain_frd_l15(self, benchmark):
        benchmark(from_dict, _CHAIN_TYPES[15], _CHAIN_DICTS[15])

    def test_chain_rt_l1(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _CHAIN_TYPES[1], _CHAIN_DICTS[1])))

    def test_chain_rt_l3(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _CHAIN_TYPES[3], _CHAIN_DICTS[3])))

    def test_chain_rt_l8(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _CHAIN_TYPES[8], _CHAIN_DICTS[8])))

    def test_chain_rt_l15(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _CHAIN_TYPES[15], _CHAIN_DICTS[15])))

    # ── LIST: list at each level ──────────────────────────────────

    def test_list_con_l1(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[1], val=1)

    def test_list_con_l3(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[3], **_LIST_CHAIN_DICTS[3])

    def test_list_con_l8(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[8], **_LIST_CHAIN_DICTS[8])

    def test_list_con_l15(self, benchmark):
        benchmark(_LIST_CHAIN_TYPES[15], **_LIST_CHAIN_DICTS[15])

    def test_list_tod_l1(self, benchmark):
        benchmark(to_dict, _LIST_CHAIN_OBJS[1])

    def test_list_tod_l3(self, benchmark):
        benchmark(to_dict, _LIST_CHAIN_OBJS[3])

    def test_list_tod_l8(self, benchmark):
        benchmark(to_dict, _LIST_CHAIN_OBJS[8])

    def test_list_tod_l15(self, benchmark):
        benchmark(to_dict, _LIST_CHAIN_OBJS[15])

    def test_list_frd_l1(self, benchmark):
        benchmark(from_dict, _LIST_CHAIN_TYPES[1], _LIST_CHAIN_DICTS[1])

    def test_list_frd_l3(self, benchmark):
        benchmark(from_dict, _LIST_CHAIN_TYPES[3], _LIST_CHAIN_DICTS[3])

    def test_list_frd_l8(self, benchmark):
        benchmark(from_dict, _LIST_CHAIN_TYPES[8], _LIST_CHAIN_DICTS[8])

    def test_list_frd_l15(self, benchmark):
        benchmark(from_dict, _LIST_CHAIN_TYPES[15], _LIST_CHAIN_DICTS[15])

    def test_list_rt_l1(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _LIST_CHAIN_TYPES[1], _LIST_CHAIN_DICTS[1])))

    def test_list_rt_l3(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _LIST_CHAIN_TYPES[3], _LIST_CHAIN_DICTS[3])))

    def test_list_rt_l8(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _LIST_CHAIN_TYPES[8], _LIST_CHAIN_DICTS[8])))

    def test_list_rt_l15(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _LIST_CHAIN_TYPES[15], _LIST_CHAIN_DICTS[15])))

    # ── MIXED: object + list per level ────────────────────────────

    def test_mix_con_l1(self, benchmark):
        benchmark(_MIXED_TYPES[1], val=1)

    def test_mix_con_l3(self, benchmark):
        benchmark(_MIXED_TYPES[3], **_MIXED_DICTS[3])

    def test_mix_con_l8(self, benchmark):
        benchmark(_MIXED_TYPES[8], **_MIXED_DICTS[8])

    def test_mix_con_l15(self, benchmark):
        benchmark(_MIXED_TYPES[15], **_MIXED_DICTS[15])

    def test_mix_tod_l1(self, benchmark):
        benchmark(to_dict, _MIXED_OBJS[1])

    def test_mix_tod_l3(self, benchmark):
        benchmark(to_dict, _MIXED_OBJS[3])

    def test_mix_tod_l8(self, benchmark):
        benchmark(to_dict, _MIXED_OBJS[8])

    def test_mix_tod_l15(self, benchmark):
        benchmark(to_dict, _MIXED_OBJS[15])

    def test_mix_frd_l1(self, benchmark):
        benchmark(from_dict, _MIXED_TYPES[1], _MIXED_DICTS[1])

    def test_mix_frd_l3(self, benchmark):
        benchmark(from_dict, _MIXED_TYPES[3], _MIXED_DICTS[3])

    def test_mix_frd_l8(self, benchmark):
        benchmark(from_dict, _MIXED_TYPES[8], _MIXED_DICTS[8])

    def test_mix_frd_l15(self, benchmark):
        benchmark(from_dict, _MIXED_TYPES[15], _MIXED_DICTS[15])

    def test_mix_rt_l1(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _MIXED_TYPES[1], _MIXED_DICTS[1])))

    def test_mix_rt_l3(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _MIXED_TYPES[3], _MIXED_DICTS[3])))

    def test_mix_rt_l8(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _MIXED_TYPES[8], _MIXED_DICTS[8])))

    def test_mix_rt_l15(self, benchmark):
        benchmark(lambda: to_dict(from_dict(
            _MIXED_TYPES[15], _MIXED_DICTS[15])))
