"""Compare hardcoded vs reflective from_dict/to_dict performance.

Strategy: generate each message type via `generate_message_module`, load the
resulting source through importlib, then benchmark the hardcoded methods
head-to-head against the reflective utility functions.
"""

import importlib.util
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from zros2.generator.codegen._message import generate_message_module
from zros2.generator.parsing._models import MsgDefinition, MsgField

# ── Reflective helpers (benchmark reference) ─────────────────────────
# These mimic the generated hardcoded methods for comparison.
# They are defined locally because the reflective utility functions
# were removed from zros2.types._utils in favor of generated methods.


def _ref_to_dict(obj: Any) -> dict[str, object]:
    """Reflective to_dict using dataclass fields."""
    from dataclasses import fields

    return {f.name: getattr(obj, f.name) for f in fields(obj)}


def _ref_from_dict(cls: type, data: dict[str, object]) -> object:
    """Reflective from_dict using dataclass fields."""
    from dataclasses import fields

    kwargs: dict[str, object] = {}
    for f in fields(cls):
        kwargs[f.name] = data[f.name]
    return cls(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Generated module loader — uses importlib instead of exec
# ═══════════════════════════════════════════════════════════════════════
#
# Generated source is written to a temporary directory and loaded via
# importlib.  For cross-module references (e.g. inner → outer), the
# dependency's class is injected into the module namespace before
# execution.  The temp directory lives inside a ``with`` block so
# files are cleaned up immediately after loading.

_generated_base: Path


def _write_and_load(source: str, name: str, ns: dict | None = None) -> type:
    """Write generated source to a temp file and import it via importlib.

    Args:
        source: Stripped Python source (only resolvable imports remain).
        name: The class name to extract from the loaded module.
        ns: Optional namespace to inject into the module's ``__dict__``
            before execution (used for cross-type references).

    Returns:
        The class defined in the generated module.
    """
    mod_name = f"_cmp_{name}"
    mod_file = _generated_base / f"{mod_name}.py"
    mod_file.write_text(source)

    spec = importlib.util.spec_from_file_location(mod_name, str(mod_file))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to create module spec for {mod_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module

    if ns is not None:
        module.__dict__.update(ns)

    spec.loader.exec_module(module)

    cls_ = getattr(module, name)
    if ns is not None:
        ns[name] = cls_
    return cls_


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


def _cls_name(defn: MsgDefinition) -> str:
    """Derive the Python class name from a message definition."""
    return defn.type_name.split("/")[-1].replace("-", "_")


def _gen_class(defn: MsgDefinition, extra_ns: dict | None = None) -> type:
    """Generate code, load via importlib, return the class.

    If *extra_ns* is provided, the class is also stored there.
    """
    code = generate_message_module(defn)
    cleaned = _clean(code)
    cls_ = _write_and_load(cleaned, _cls_name(defn), extra_ns)
    return cls_


def _gen_pair(defn_a: MsgDefinition, defn_b: MsgDefinition) -> tuple[type, type]:
    """Generate two classes where *defn_b* references *defn_a*.

    Both modules are loaded into the same temporary directory so that
    cross-module references resolve via the pre-populated namespace.
    """
    name_a = _cls_name(defn_a)
    name_b = _cls_name(defn_b)

    code_a = _clean(generate_message_module(defn_a))
    code_b = _clean(generate_message_module(defn_b))

    # Type A has no dependencies — load it first
    cls_a = _write_and_load(code_a, name_a)
    # Type B references Type A — inject it into the module namespace
    cls_b = _write_and_load(code_b, name_b, {name_a: cls_a})
    return cls_a, cls_b


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
    print(
        f"  {label:30s}  {hard_ns:8.0f} ns  {ref_ns:8.0f} ns  {ref_ns / hard_ns:5.1f}×"
    )


# ═══════════════════════════════════════════════════════════════════════
# Benchmark body — runs inside a with block so temp files are cleaned up
# ═══════════════════════════════════════════════════════════════════════

with tempfile.TemporaryDirectory(suffix="_zros2_bench") as _tmp:
    _generated_base = Path(_tmp)
    sys.path.insert(0, str(_generated_base))

    # ═══════════════════════════════════════════════════════════════
    # Dimension 1 — Field count
    # ═══════════════════════════════════════════════════════════════

    _header("Dimension 1 — Field count")

    for n_fields, fields in [
        (1, [MsgField(name="val", type_str="int32")]),
        (
            3,
            [
                MsgField(name="a", type_str="int32"),
                MsgField(name="b", type_str="float64"),
                MsgField(name="c", type_str="string"),
            ],
        ),
        (8, [MsgField(name=f"f{i}", type_str="int32") for i in range(8)]),
        (
            15,
            [
                MsgField(
                    name=f"f{i}",
                    type_str=(
                        "int32" if i % 3 == 0 else "float64" if i % 3 == 1 else "string"
                    ),
                )
                for i in range(15)
            ],
        ),
    ]:
        Cls = _gen_class(
            MsgDefinition(
                package="bench",
                type_name=f"F{n_fields}",
                type_kind="msg",
                fields=fields,
            )
        )

        kwargs = {}
        for f in fields:
            kwargs[f.name] = (
                42
                if "int" in f.type_str
                else (3.14 if "float" in f.type_str else "hello")
            )
        obj = Cls(**kwargs)
        data = dict(kwargs)

        N = 50000
        _ = _ref_from_dict(Cls, data)
        _ = _ref_to_dict(obj)

        print(f"\n  {n_fields} field{'s' if n_fields > 1 else ''}:")
        _row(
            "to_dict",
            _bench(lambda o=obj: o.to_dict(), N),
            _bench(lambda o=obj: _ref_to_dict(o), N),
        )
        _row(
            "from_dict",
            _bench(lambda c=Cls, d=data: c.from_dict(d), N),
            _bench(lambda c=Cls, d=data: _ref_from_dict(c, d), N),
        )

    # ═══════════════════════════════════════════════════════════════
    # Dimension 2 — Arrays
    # ═══════════════════════════════════════════════════════════════

    _header("Dimension 2 — Arrays")

    Arr = _gen_class(
        MsgDefinition(
            package="bench",
            type_name="Arr",
            type_kind="msg",
            fields=[
                MsgField(name="values", type_str="float64[]"),
                MsgField(name="id", type_str="int32"),
            ],
        )
    )
    obj_arr = Arr(values=[1.0, 2.0, 3.0, 4.0, 5.0], id=42)
    data_arr = {"values": [1.0, 2.0, 3.0, 4.0, 5.0], "id": 42}
    N = 50000
    _ = _ref_from_dict(Arr, data_arr)
    _ = _ref_to_dict(obj_arr)

    print("\n  Arr { values: float64[5], id: int32 }:")
    _row(
        "to_dict",
        _bench(lambda: obj_arr.to_dict(), N),
        _bench(lambda: _ref_to_dict(obj_arr), N),
    )
    _row(
        "from_dict",
        _bench(lambda: Arr.from_dict(data_arr), N),
        _bench(lambda: _ref_from_dict(Arr, data_arr), N),
    )

    # ═══════════════════════════════════════════════════════════════
    # Dimension 3 — Nesting
    # ═══════════════════════════════════════════════════════════════

    _header("Dimension 3 — Nesting")

    Inner, Outer = _gen_pair(
        MsgDefinition(
            package="bench",
            type_name="Inner",
            type_kind="msg",
            fields=[
                MsgField(name="x", type_str="float64"),
                MsgField(name="y", type_str="float64"),
            ],
        ),
        MsgDefinition(
            package="bench",
            type_name="Outer",
            type_kind="msg",
            fields=[
                MsgField(name="inner", type_str="bench/Inner"),
                MsgField(name="label", type_str="string"),
            ],
        ),
    )

    obj_nest = Outer(inner=Inner(x=1.0, y=2.0), label="pt")
    data_nest = {"inner": {"x": 1.0, "y": 2.0}, "label": "pt"}
    N = 20000
    _ = _ref_from_dict(Outer, data_nest)
    _ = _ref_to_dict(obj_nest)

    print("\n  Outer { inner: Inner, label: str }:")
    _row(
        "to_dict",
        _bench(lambda: obj_nest.to_dict(), N),
        _bench(lambda: _ref_to_dict(obj_nest), N),
    )
    _row(
        "from_dict",
        _bench(lambda: Outer.from_dict(data_nest), N),
        _bench(lambda: _ref_from_dict(Outer, data_nest), N),
    )
