"""Generate service/action wrapper modules.

Service and action interfaces consist of several sub-types.  The generic AST
merger lives in :mod:`._merge`; this module owns the domain-specific wrapper
class (``Foo.Request`` / ``Foo.Goal``), the type registry call, and the
``.py``/``.pyi`` file pair.
"""

import ast
import pathlib

from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.semantics._action import ACTION_SUFFIXES
from zros2.generator.semantics._utilities import to_snake_case

from ._file import GeneratedFile
from ._registry import registry_import
from ._service_merge import merge_type_modules
from ._wrapper import wrapper_class_ast

# ---------------------------------------------------------------------------
# Suffix constants
# ---------------------------------------------------------------------------
# Service families have exactly two sub-types, owned here because they
# come from the ``.srv`` file itself (no IDL expansion).
# Action families have eight sub-types; the tuple is defined by
# :mod:`zros2.generator.semantics._action` (the IDL expansion spec) and
# re-exported so existing codegen imports keep working.

SRV_SUFFIXES = ("_Request", "_Response")


# ---------------------------------------------------------------------------
# Self-reference detection
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Wrapper class builder
# ---------------------------------------------------------------------------


def generate_service_wrappers(
    sub_dir: pathlib.Path,
    defn_by_name: dict[str, MsgDefinition],
    type_names: list[str],
    package: str,
    files: list[GeneratedFile],
    root_package: str = "",
    distro: str = "",
) -> list[str]:
    """Generate combined service modules (Request + Response in one file).

    **Pair-finding logic**
    The flat list of all generated type names is scanned for entries ending
    in ``_Request`` (the "leader" suffix).  For each candidate, a matching
    ``_Response`` is looked up in ``names_set``.  If the pair exists, a
    wrapper module is emitted; if the response half is missing the candidate
    is silently skipped.  This naturally handles packages that mix services
    and messages — only recognised pairs produce merged wrappers.

    **What is generated per service**
    For a service named ``Foo`` (fully qualified as ``package/srv/Foo``):

    - ``_foo.py`` — runtime module containing:
        * The ``Foo_Request`` class with its serialisation logic.
        * The ``Foo_Response`` class with its serialisation logic.
        * A ``Foo`` wrapper class exposing ``Foo.Request`` and ``Foo.Response``.
        * A ``register_service(ServiceTypes(Request=Foo_Request, Response=Foo_Response),
          "package/srv/Foo")`` call.

    - ``_foo.pyi`` — stub module with type annotations only.

    Args:
        sub_dir: Output directory for the generated files.
        defn_by_name: Mapping from type-name (e.g. ``"Foo_Request"``) to
            ``MsgDefinition``.
        type_names: Flat list of all generated type names in this package.
        package: ROS 2 package name (e.g. ``"my_package"``).
        files: Mutable list that generated-file records are appended to.
        root_package: Root Python package for relative imports.

    Returns:
        List of base names for which wrappers were generated (e.g.
        ``["Foo", "Bar"]``).
    """
    ri = registry_import(root_package)
    names_set = set(type_names)
    wrappers: list[str] = []
    for tn in type_names:
        if not tn.endswith("_Request"):
            continue
        base = tn[: -len("_Request")]
        if f"{base}_Response" not in names_set:
            # No matching _Response — skip silently; this is not a service.
            continue

        full_name = f"{package}/srv/{base}"
        snake = to_snake_case(base)
        req_defn = defn_by_name[f"{base}_Request"]
        resp_defn = defn_by_name[f"{base}_Response"]

        attr_names = ["Request", "Response"]
        type_class_names = [f"{base}_{n}" for n in attr_names]

        # Build the runtime wrapper class with default-value assignments.
        wrapper_cls = wrapper_class_ast(
            base,
            attr_names,
            type_class_names,
            has_defaults=True,
            full_name=full_name,
        )
        classvar_import = ast.ImportFrom(
            module="typing",
            names=[ast.alias(name="ClassVar")],
            level=0,
        )
        types_import = ast.ImportFrom(
            module="zros2.types",
            names=[ast.alias(name="ServiceTypes")],
            level=0,
        )
        reg_import = ast.ImportFrom(
            module=ri,
            names=[ast.alias(name="register_service", asname="_register_service")],
            level=0,
        )
        reg_call = ast.Expr(
            value=ast.Call(
                func=ast.Name(id="_register_service"),
                args=[
                    ast.Call(
                        func=ast.Name(id="ServiceTypes"),
                        args=[],
                        keywords=[
                            ast.keyword(
                                arg="Request", value=ast.Name(id=type_class_names[0])
                            ),
                            ast.keyword(
                                arg="Response", value=ast.Name(id=type_class_names[1])
                            ),
                        ],
                    ),
                    ast.Constant(value=full_name),
                ],
                keywords=[],
            )
        )

        content, stub = merge_type_modules(
            [req_defn, resp_defn],
            extra_py_stmts=[wrapper_cls, classvar_import, types_import],
            extra_pyi_stmts=[
                classvar_import,
                wrapper_class_ast(
                    base,
                    attr_names,
                    type_class_names,
                    has_defaults=False,
                    full_name=full_name,
                ),
            ],
            module_doc=f"Auto-generated ROS 2 service: {full_name}.",
            root_package=root_package,
            post_body_stmts=[reg_import, reg_call],
            source=f"{package}/srv/{base}.srv",
            distro=distro,
        )
        files.append(GeneratedFile(sub_dir / f"_{snake}.py", content))
        files.append(GeneratedFile(sub_dir / f"_{snake}.pyi", stub))
        wrappers.append(base)
    return wrappers


# ---------------------------------------------------------------------------
# Action wrapper generator
# ---------------------------------------------------------------------------


def generate_action_wrappers(
    sub_dir: pathlib.Path,
    defn_by_name: dict[str, MsgDefinition],
    type_names: list[str],
    package: str,
    files: list[GeneratedFile],
    root_package: str = "",
    distro: str = "",
) -> list[str]:
    """Generate combined action modules (all 8 sub-types + wrapper in one file).

    **Pair-finding logic**
    The flat list of all generated type names is scanned for entries ending
    in ``_SendGoal_Request`` (the "leader" suffix for action families).
    For each candidate, **all eight** ``ACTION_SUFFIXES`` are checked against
    ``names_set``.  If every suffix exists, a wrapper module is emitted; if
    any suffix is missing the candidate is silently skipped.  This guards
    against emitting a broken module when the IDL definitions are incomplete.

    **The 8 sub-types of a ROS 2 action**
    ROS 2 actions are built on top of two internal services (SendGoal and
    GetResult), plus three message types for goal, result, and feedback:

    +---------------------------+---------------------------------------+
    | Sub-type                  | Purpose                               |
    +===========================+=======================================+
    | ``Foo_Goal``              | Goal message fields                   |
    | ``Foo_Result``            | Result message fields                 |
    | ``Foo_Feedback``          | Feedback message fields               |
    | ``Foo_FeedbackMessage``   | Feedback wrapper (goal_id + feedback) |
    | ``Foo_SendGoal_Request``  | Request for the SendGoal service      |
    | ``Foo_SendGoal_Response`` | Response for the SendGoal service     |
    | ``Foo_GetResult_Request`` | Request for the GetResult service     |
    | ``Foo_GetResult_Response``| Response for the GetResult service    |
    +---------------------------+---------------------------------------+

    **What is generated per action**
    For an action named ``Foo`` (fully qualified as ``package/action/Foo``):

    - ``_foo.py`` — runtime module containing all 8 sub-types plus the
      wrapper class and a ``register_action`` call.
    - ``_foo.pyi`` — stub module with type annotations only.

    Args:
        sub_dir: Output directory for the generated files.
        defn_by_name: Mapping from type-name (e.g. ``"Foo_SendGoal_Request"``)
            to ``MsgDefinition``.
        type_names: Flat list of all generated type names in this package.
        package: ROS 2 package name (e.g. ``"my_package"``).
        files: Mutable list that generated-file records are appended to.
        root_package: Root Python package for relative imports.

    Returns:
        List of base names for which wrappers were generated (e.g.
        ``["Foo", "Bar"]``).
    """
    ri = registry_import(root_package)
    names_set = set(type_names)
    wrappers: list[str] = []
    for tn in type_names:
        if not tn.endswith("_SendGoal_Request"):
            continue
        base = tn[: -len("_SendGoal_Request")]
        # Validate that every expected action sub-type exists before
        # generating; skip silently if any are missing.
        if not all(f"{base}{s}" in names_set for s in ACTION_SUFFIXES):
            continue

        full_name = f"{package}/action/{base}"
        snake = to_snake_case(base)

        # Collect all 8 definitions in the canonical order from ACTION_SUFFIXES.
        orig_defns = [defn_by_name[f"{base}{s}"] for s in ACTION_SUFFIXES]
        # Strip leading underscore for public attribute names.
        # "_Goal" -> "Goal", "_SendGoal_Request" -> "SendGoal_Request", etc.
        attr_names = [s.lstrip("_") for s in ACTION_SUFFIXES]
        type_class_names = [f"{base}_{n}" for n in attr_names]

        # Build the runtime wrapper class with default-value assignments.
        wrapper_cls = wrapper_class_ast(
            base,
            attr_names,
            type_class_names,
            has_defaults=True,
            full_name=full_name,
        )
        classvar_import = ast.ImportFrom(
            module="typing",
            names=[ast.alias(name="ClassVar")],
            level=0,
        )
        types_import = ast.ImportFrom(
            module="zros2.types",
            names=[ast.alias(name="ActionTypes")],
            level=0,
        )
        reg_import = ast.ImportFrom(
            module=ri,
            names=[ast.alias(name="register_action", asname="_register_action")],
            level=0,
        )
        # Build a keyword argument for each sub-type attribute.
        reg_keywords = [
            ast.keyword(arg=name, value=ast.Name(id=cls_name))
            for name, cls_name in zip(attr_names, type_class_names)
        ]
        reg_call = ast.Expr(
            value=ast.Call(
                func=ast.Name(id="_register_action"),
                args=[
                    ast.Call(
                        func=ast.Name(id="ActionTypes"),
                        args=[],
                        keywords=reg_keywords,
                    ),
                    ast.Constant(value=full_name),
                ],
                keywords=[],
            )
        )

        content, stub = merge_type_modules(
            orig_defns,
            extra_py_stmts=[wrapper_cls, classvar_import, types_import],
            extra_pyi_stmts=[
                classvar_import,
                wrapper_class_ast(
                    base,
                    attr_names,
                    type_class_names,
                    has_defaults=False,
                    full_name=full_name,
                ),
            ],
            module_doc=f"Auto-generated ROS 2 action: {full_name}.",
            root_package=root_package,
            post_body_stmts=[reg_import, reg_call],
            source=f"{package}/action/{base}.action",
            distro=distro,
        )
        files.append(GeneratedFile(sub_dir / f"_{snake}.py", content))
        files.append(GeneratedFile(sub_dir / f"_{snake}.pyi", stub))
        wrappers.append(base)
    return wrappers
