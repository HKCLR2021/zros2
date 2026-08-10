"""Runtime contract tests — every zros2 runtime symbol the generator
hardcodes must actually exist in the installed runtime.

The code generator emits imports like ``from zros2.types import
ServiceTypes`` and ``from zros2.types._utils import from_attributes`` as
plain strings.  If the runtime renames or moves one of those symbols,
component tests that only assert on generated *content* still pass while
generated code breaks at runtime.  These tests re-resolve every hardcoded
reference against the real ``zros2`` package so the contract fails loudly
at test time instead.

``RUNTIME_CONTRACT`` below is the explicit whitelist: any new hardcoded
``zros2.*`` import introduced by the generator must be added here, and any
runtime-side rename must update it.  That is the point — the table is the
single place where the two sides are declared to agree.
"""

import ast
import dataclasses
import importlib
import importlib.util
import pathlib
import sys
import tempfile
import types
from typing import get_type_hints

from zros2.generator.codegen._message import GeneratedFile, generate_message_module
from zros2.generator.codegen._registry import REGISTRY_AST
from zros2.generator.codegen._service_action import (
    ACTION_SUFFIXES,
    generate_action_wrappers,
    generate_service_wrappers,
)
from zros2.generator.parsing._models import MsgDefinition, MsgField
from zros2.generator.pipeline._generate import generate_all
from zros2.types import (
    ActionTypes,
    RosAction,
    RosActionView,
    RosMessage,
    RosService,
    ServiceTypes,
)

# ── The contract ─────────────────────────────────────────────────────
# module path → names the generator is allowed to hardcode from it.
RUNTIME_CONTRACT: dict[str, frozenset[str]] = {
    "zros2.types": frozenset({"RosMessage", "ServiceTypes", "ActionTypes"}),
    "zros2.types._utils": frozenset({"from_attributes"}),
}

# Registry functions the generator emits calls to / re-exports from the
# root ``__init__.py`` (see ``pipeline/_generate.py`` ``_update_root_init``).
_REGISTRY_FUNCTIONS: frozenset[str] = frozenset(
    {
        "register",
        "register_service",
        "register_action",
        "get_type",
        "has_type",
        "iter_types",
        "get_service",
        "get_action",
    }
)


def _point_defn() -> MsgDefinition:
    return MsgDefinition(
        package="pkg",
        type_name="Point",
        type_kind="msg",
        fields=[MsgField(name="x", type_str="float64")],
    )


def _srv_files() -> list[str]:
    """Generate the merged service wrapper module sources."""
    defns = {
        "Echo_Request": MsgDefinition(
            package="pkg", type_name="Echo_Request", type_kind="srv"
        ),
        "Echo_Response": MsgDefinition(
            package="pkg", type_name="Echo_Response", type_kind="srv"
        ),
    }
    files: list[GeneratedFile] = []
    generate_service_wrappers(pathlib.Path("srv"), defns, list(defns), "pkg", files)
    return [f.content for f in files]


def _action_files() -> list[str]:
    """Generate the merged action wrapper module sources."""
    defns = {
        f"Do{s}": MsgDefinition(package="pkg", type_name=f"Do{s}", type_kind="action")
        for s in ACTION_SUFFIXES
    }
    files: list[GeneratedFile] = []
    generate_action_wrappers(pathlib.Path("action"), defns, list(defns), "pkg", files)
    return [f.content for f in files]


def _all_generated_sources() -> list[str]:
    """Return every generator output that hardcodes zros2 runtime imports."""
    return [
        generate_message_module(_point_defn()),
        *(_srv_files() + _action_files()),
        ast.unparse(REGISTRY_AST),
    ]


def _zros2_imports(source: str) -> set[tuple[str, str]]:
    """Extract ``(module, name)`` pairs from ``from zros2.* import ...``."""
    tree = ast.parse(source)
    refs: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("zros2")
        ):
            for alias in node.names:
                refs.add((node.module, alias.name))
    return refs


def _load_module(
    source: str, name: str, *, with_registry: bool = False
) -> types.ModuleType:
    """Write *source* to a temp file and import it via importlib.

    ``with_registry`` also writes a real ``_registry.py`` (from
    ``REGISTRY_AST``) next to it so merged srv/action modules can resolve
    their ``from _registry import register_*`` imports for real.
    """
    with tempfile.TemporaryDirectory(suffix="_zros2_contract") as tmp:
        base = pathlib.Path(tmp)
        if with_registry:
            (base / "_registry.py").write_text(
                ast.unparse(REGISTRY_AST), encoding="utf-8"
            )
        mod_name = f"_contract_{name}"
        mod_file = base / f"{mod_name}.py"
        mod_file.write_text(source, encoding="utf-8")

        sys.path.insert(0, str(base))
        try:
            spec = importlib.util.spec_from_file_location(mod_name, str(mod_file))
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Failed to create module spec for {mod_name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            return module
        finally:
            sys.modules.pop(mod_name, None)
            sys.path.remove(str(base))


# ======================================================================
# Static import contract
# ======================================================================


class TestStaticImportContract:
    def test_generated_zros2_imports_are_whitelisted_and_exist(self):
        """Every ``zros2.*`` import the generator emits must be whitelisted
        and resolvable in the installed runtime."""
        refs: set[tuple[str, str]] = set()
        for source in _all_generated_sources():
            refs |= _zros2_imports(source)
        assert refs, "generated sources should reference the zros2 runtime"

        whitelist = {
            (module, name)
            for module, names in RUNTIME_CONTRACT.items()
            for name in names
        }
        unknown = refs - whitelist
        assert not unknown, (
            f"generator hardcodes zros2 references missing from RUNTIME_CONTRACT: "
            f"{sorted(unknown)}"
        )

        for module, name in sorted(whitelist):
            mod = importlib.import_module(module)
            assert hasattr(mod, name), (
                f"contract violation: generator hardcodes {module}.{name} "
                f"which no longer exists in the runtime"
            )

    def test_generated_sources_cover_all_contract_entries(self):
        """The whitelist must not silently drift from what is generated."""
        refs: set[tuple[str, str]] = set()
        for source in _all_generated_sources():
            refs |= _zros2_imports(source)
        assert RUNTIME_CONTRACT["zros2.types._utils"] <= {
            name for module, name in refs if module == "zros2.types._utils"
        }


class TestRegistryContract:
    def test_registry_ast_defines_root_init_functions(self):
        """``_update_root_init`` re-exports these names from ``_registry``."""
        defined = {
            node.name
            for node in ast.walk(REGISTRY_AST)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = _REGISTRY_FUNCTIONS - defined
        assert not missing, (
            f"generated root __init__.py re-exports {sorted(_REGISTRY_FUNCTIONS)} "
            f"but REGISTRY_AST does not define: {sorted(missing)}"
        )


# ======================================================================
# Container field contract
# ======================================================================


def _call_keywords(source: str, func_name: str) -> set[str]:
    """Extract keyword argument names of the first ``func_name(...)`` call."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func_name
            and node.args
            and isinstance(node.args[0], ast.Call)
        ):
            return {kw.arg for kw in node.args[0].keywords if kw.arg is not None}
    return set()


class TestContainerFieldContract:
    def test_service_container_fields_match_generated_keywords(self):
        """``ServiceTypes(Request=..., Response=...)`` keywords are the
        dataclass field names — a runtime rename breaks generated calls."""
        sources = _srv_files()
        assert sources
        keywords = set().union(
            *(_call_keywords(s, "_register_service") for s in sources)
        )
        assert keywords
        assert keywords == {f.name for f in dataclasses.fields(ServiceTypes)}

    def test_action_container_fields_match_generated_keywords(self):
        """``ActionTypes`` keyword contract, mirroring the service case."""
        sources = _action_files()
        assert sources
        keywords = set().union(
            *(_call_keywords(s, "_register_action") for s in sources)
        )
        assert keywords
        assert keywords == {f.name for f in dataclasses.fields(ActionTypes)}


# ======================================================================
# Protocol contract
# ======================================================================


class TestProtocolContract:
    def test_generated_message_satisfies_ros_message(self):
        """Generated message classes must fulfil the RosMessage protocol."""
        module = _load_module(generate_message_module(_point_defn()), "point")
        point_cls = module.Point
        assert isinstance(point_cls(), RosMessage)
        for attr in (
            "serialize",
            "deserialize",
            "from_dict",
            "from_attributes",
            "to_dict",
        ):
            assert callable(getattr(point_cls, attr)), f"Point missing {attr}"

    def test_generated_service_wrapper_exposes_protocol_members(self):
        """The service wrapper class must expose every RosService member."""
        module = _load_module(_srv_files()[0], "echo", with_registry=True)
        for attr in get_type_hints(RosService):
            member = getattr(module.Echo, attr, None)
            assert isinstance(member, type), (
                f"service wrapper Echo missing ClassVar '{attr}' as a class"
            )

    def test_generated_action_wrapper_exposes_protocol_members(self):
        """The action wrapper class must expose every RosAction member."""
        module = _load_module(_action_files()[0], "do", with_registry=True)
        for attr in get_type_hints(RosAction):
            member = getattr(module.Do, attr, None)
            assert isinstance(member, type), (
                f"action wrapper Do missing ClassVar '{attr}' as a class"
            )

    def test_generated_action_wrapper_satisfies_view_protocol(self):
        """The action wrapper must expose every RosActionView member."""
        module = _load_module(_action_files()[0], "do_view", with_registry=True)
        for attr in get_type_hints(RosActionView):
            assert isinstance(getattr(module.Do, attr, None), type), (
                f"action wrapper Do missing RosActionView member '{attr}'"
            )


# ======================================================================
# End-to-end: generate → write → import → registry lookup
# ======================================================================


class TestEndToEnd:
    def test_generated_package_registers_types(self, tmp_path):
        """A generated package must import and register real types."""
        types: dict[str, MsgDefinition] = {
            "pkg/msg/Point": _point_defn(),
            "pkg/srv/Echo_Request": MsgDefinition(
                package="pkg", type_name="Echo_Request", type_kind="srv"
            ),
            "pkg/srv/Echo_Response": MsgDefinition(
                package="pkg", type_name="Echo_Response", type_kind="srv"
            ),
        }
        files = generate_all(types, tmp_path)
        for f in files:
            f.path.parent.mkdir(parents=True, exist_ok=True)
            f.path.write_text(f.content, encoding="utf-8")

        sys.path.insert(0, str(tmp_path))
        try:
            # The package tree only exists at runtime — import dynamically.
            importlib.import_module("pkg")  # triggers registration
            registry = importlib.import_module("_registry")
            pkg_msg = importlib.import_module("pkg.msg")
            pkg_srv = importlib.import_module("pkg.srv")

            assert registry.has_type("pkg/msg/Point")
            assert registry.get_type("pkg/msg/Point") is pkg_msg.Point

            service = registry.get_service("pkg/srv/Echo")
            assert service.Request is pkg_srv.Echo_Request
            assert service.Response is pkg_srv.Echo_Response
        finally:
            sys.path.remove(str(tmp_path))
            for name in list(sys.modules):
                if name == "_registry" or name == "pkg" or name.startswith("pkg."):
                    del sys.modules[name]
