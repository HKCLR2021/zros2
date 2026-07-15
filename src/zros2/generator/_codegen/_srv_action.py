"""Code generation for combined ROS 2 service / action type modules.

Why this module exists
---------------------
ROS 2 services and actions consist of multiple sub-types that reference each
other's types.  For example, a service ``Foo`` generates ``Foo_Request`` and
``Foo_Response``. ``Foo_Request`` itself may need to
deserialise into ``Foo_Response`` fields, and vice versa.  If each sub-type
were written to its own ``.py`` file, they would circular-import at runtime.

The solution is to generate every sub-type independently, then *merge* all
of them together into a single ``.py`` file where they share one module scope
and can freely reference one another.  The same logic also produces the
corresponding ``.pyi`` stub file.

The merger performs several critical tasks:

* **Self-reference removal** — imports that reference another sub-type in the
  same merged file are dropped (otherwise they would be circular).
* **Import deduplication** — multiple sub-types may import the same external
  names (e.g. ``float64``, ``ClassVar``).  These are merged into one shared
  ``ImportFrom`` statement per module.
* **Wrapper injection** — a lightweight wrapper class with
  ``ClassVar[type[SubType]]`` annotations is appended so that users can write
  ``Foo.Request`` or ``Foo.Result`` instead of importing each sub-type
  separately.
* **Registration call** — a ``register_service`` / ``register_action`` call is
  appended so the type-map knows about the wrapper.

Order of generated statements in the merged file
-------------------------------------------------
1. Module docstring (the ``module_doc`` parameter).
2. All deduplicated external imports (``ImportFrom``, ``Import``).
3. Sub-type class definitions (and any helper classes / constants the
   per-type generator emits), **in the order the caller provided the
   definitions**.
4. Extra statements provided by the caller (wrapper class, ``ClassVar``
   import, etc.).
5. ``post_body_stmts`` — typically the ``register_service`` or
   ``register_action`` call.

Parallel ``.py`` and ``.pyi`` paths
------------------------------------
The core merge engine (``_merge_type_modules``) runs **twice** for each
service/action:

* **Runtime ``.py``** — sourced from ``generate_message_module`` (which
  produces working implementations with serialisation logic).
* **Stub ``.pyi``** — sourced from ``generate_stub_module`` (which produces
  type-hint stubs without runtime bodies).

The caller provides ``extra_py_stmts`` and ``extra_pyi_stmts`` so that each
path can inject the appropriate variant of the wrapper class (with or without
default-value assignments).
"""

import ast
import pathlib
from .._parser import MsgDefinition
from .._utilities import _generated_metadata_stmts, _header_comment, _to_snake_case
from ._msg import GeneratedFile, _registry_import, generate_message_module
from ._pyi import generate_stub_module


# ---------------------------------------------------------------------------
# Suffix constants
# ---------------------------------------------------------------------------
# These define which sub-type names belong to a service or action family.
# When scanning the flat list of all generated types, the wrapper generators
# look for a "leader" type (e.g. ``Foo_Request`` for services) and then
# validate that every suffix in the corresponding tuple exists.
#
# ``_SRV_SUFFIXES`` — every service has exactly two sub-types.
# ``_ACTION_SUFFIXES`` — every action has eight sub-types:
#   Goal, Result, Feedback, FeedbackMessage for the goal/result/feedback
#   message types, plus SendGoal_Request/Response and GetResult_Request/Response
#   for the two internal service pairs that ROS 2 actions are built on.

_SRV_SUFFIXES = ("_Request", "_Response")
_ACTION_SUFFIXES = (
    "_Goal",
    "_Result",
    "_Feedback",
    "_FeedbackMessage",
    "_SendGoal_Request",
    "_SendGoal_Response",
    "_GetResult_Request",
    "_GetResult_Response",
)


# ---------------------------------------------------------------------------
# Self-reference detection
# ---------------------------------------------------------------------------


def _is_local_import(stmt: ast.stmt, local_names: set[str]) -> bool:
    """Check if an ``ImportFrom`` targets a type defined in the same merged module.

    When ``_merge_type_modules`` combines several sub-types into one file,
    the per-type generator may emit an import like::

        from _foo import Foo_Request

    If ``Foo_Request`` is **one of the types being merged**, that import is
    a self-reference — the class is already defined in the same module — and
    must be dropped.  Leaving it would create a circular import at runtime.

    The check accounts for the convention that private helper classes are
    prefixed with ``_``.  The import name might be ``_Foo_Request`` while
    ``local_names`` contains the public name ``Foo_Request`` (without the
    underscore), or the alias in ``asname`` may carry the public name.
    Both cases are handled by stripping the leading ``_`` from the imported
    name and checking the ``asname`` directly.

    Args:
        stmt: An AST statement (typically from ``ast.ImportFrom``).
        local_names: Set of type-name strings being merged into the same
            file, e.g. ``{"Foo_Request", "Foo_Response"}``.

    Returns:
        ``True`` if the import is a self-reference and should be omitted
        from the merged output.
    """
    if not isinstance(stmt, ast.ImportFrom) or not stmt.names:
        return False
    name = stmt.names[0]
    return (name.name.lstrip("_") in local_names
            or (name.asname is not None and name.asname in local_names))


# ---------------------------------------------------------------------------
# Core merge engine
# ---------------------------------------------------------------------------


def _merge_type_modules(
    defns: list[MsgDefinition],
    extra_py_stmts: list[ast.stmt],
    extra_pyi_stmts: list[ast.stmt],
    module_doc: str,
    root_package: str,
    post_body_stmts: list[ast.stmt] | None = None,
    source: str | None = None,
    distro: str = "",
) -> tuple[str, str]:
    """Merge several ``MsgDefinition`` types into a single ``.py`` / ``.pyi``.

    **High-level goal**
    A service or action consists of multiple sub-types that reference each
    other (e.g. ``Foo_Request`` uses ``Foo_Response`` in its ``from_dict``).
    Generating them as separate files would create circular imports.  Instead,
    each sub-type is independently generated by ``generate_message_module``
    (for the runtime ``.py``) or ``generate_stub_module`` (for the type-hint
    ``.pyi``), and then *merged* into a single Python file where all sub-types
    coexist in the same namespace and can freely reference one another.

    **``local_names`` — self-referencing imports**
    The set of type-name strings being merged (e.g.
    ``{"Foo_Request", "Foo_Response"}``).  When the generated code for one
    sub-type contains an import targeting another sub-type in the same set,
    that import is a self-reference within the merged file and must be dropped
    — the target class is already defined in the same module.  Both
    ``_is_local_import`` and the ``_``-stripping in this check handle the
    convention where private helpers may be named ``_Foo_*`` while the public
    name is ``Foo_*``.

    **Import deduplication**
    Multiple sub-types often import from the same external module (e.g.
    ``from pycdr2.types import float64``, ``from typing import ClassVar``).
    A dict keyed by ``f"import_from:{stmt.module}"`` collects these; when a
    matching key already exists the new names are appended to the existing
    ``ImportFrom`` statement rather than duplicated.  This keeps the merged
    output clean.

    **Body concatenation**
    Each sub-type's generated AST module is walked.  ``ImportFrom`` and
    ``Import`` statements are absorbed into the deduplicated import dict;
    standalone docstring ``Expr(Constant)`` nodes are stripped (they belong
    to the individual generators, not the merged file); everything else —
    primarily ``ClassDef`` nodes for the sub-type itself, helper classes like
    ``_Foo_Request__from_dict``, and any module-level constants — is appended
    to a flat body list.  The result is one linear list of definitions in the
    order the caller provided ``defns``.

    **``.py`` vs ``.pyi`` split — passed as ``extra_py_stmts`` / ``extra_pyi_stmts``**
    The same merge logic runs twice: once with ``generate_message_module``
    output (producing ``.py``) and once with ``generate_stub_module`` output
    (producing ``.pyi``).  The caller also supplies extra statements that
    differ between the two:

    - ``extra_py_stmts`` — injected into the runtime ``.py``.  Typically
      includes the wrapper ``ClassVar[type[T]]`` class *with* default-value
      assignments, plus ``ClassVar`` and type-registry imports (e.g.
      ``ServiceTypes`` or ``ActionTypes``).
    - ``extra_pyi_stmts`` — injected into the stub ``.pyi``.  The same
      wrapper class but *without* default-value assignments (as is proper
      for stubs), plus the ``ClassVar`` import.

    Import statements within these extras are deduplicated into the same
    per-module dict; non-import AST nodes go into a separate ``extra_body``
    list placed after the merged sub-type definitions.

    **``post_body_stmts`` — registration call**
    For services and actions this carries the ``register_service`` /
    ``register_action`` call that ties the wrapper class to the ROS
    fully-qualified type name (e.g. ``my_package/srv/Foo``).  These
    statements are appended after everything else.

    **Order of the output module:**
    1. Module docstring.
    2. Deduplicated external imports.
    3. Merged sub-type class / helper definitions (``py_body``).
    4. Extra statements from the caller (wrapper class, etc.).
    5. ``post_body_stmts`` (registration call).

    Returns:
        ``(py_content, pyi_content)`` — each prefixed with ``_header_comment()``.
    """

    # Derive the set of public type names being merged (e.g. "Foo_Request").
    # This is used later to detect and drop self-referencing imports.
    local_names = {d.type_name.split("/")[-1] for d in defns}

    # Names of module-level metadata assignments that should be stripped
    # from individual sub-type modules (the merger re-adds them).
    _META_NAMES = frozenset({"__generated__", "__generator__", "__source__"})

    # ------------------------------------------------------------------
    # Runtime .py path
    # ------------------------------------------------------------------
    py_imports: dict[str, ast.stmt] = {}
    py_body: list[ast.stmt] = []

    for defn in defns:
        # Code-generate each sub-type independently, then merge its AST
        # into the combined module.
        module = ast.parse(generate_message_module(defn, root_package, distro=distro))
        for stmt in module.body:
            if isinstance(stmt, ast.ImportFrom):
                # Drop self-referencing imports (circular in a merged file).
                if _is_local_import(stmt, local_names):
                    continue
                # Deduplicate: merge new names into an existing ImportFrom
                # for the same module instead of adding a second statement.
                key = f"import_from:{stmt.module}"
                if key in py_imports:
                    existing = py_imports[key]
                    assert isinstance(existing, ast.ImportFrom)
                    existing_names = {n.name for n in existing.names}
                    for n in stmt.names:
                        if n.name not in existing_names:
                            existing.names.append(n)
                else:
                    py_imports[key] = stmt
            elif isinstance(stmt, ast.Import):
                # Plain ``import ...`` statements are deduplicated by their
                # unparsed string representation (simpler than ImportFrom).
                py_imports[ast.unparse(stmt)] = stmt
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                # Strip per-sub-type docstrings; the merged file has its own.
                continue
            elif (isinstance(stmt, ast.Assign) and stmt.targets
                  and isinstance(stmt.targets[0], ast.Name)
                  and stmt.targets[0].id in _META_NAMES):
                # Strip per-sub-type metadata; the merger re-adds it.
                continue
            else:
                # Everything else (ClassDef, FunctionDef, Assign, etc.)
                # goes into the merged body as-is.
                py_body.append(stmt)

    # Merge imports from extra_py_stmts into the same deduplicated dict.
    for stmt in extra_py_stmts:
        if isinstance(stmt, ast.ImportFrom):
            key = f"import_from:{stmt.module}"
            if key in py_imports:
                existing = py_imports[key]
                assert isinstance(existing, ast.ImportFrom)
                existing_names = {n.name for n in existing.names}
                for n in stmt.names:
                    if n.name not in existing_names:
                        existing.names.append(n)
            else:
                py_imports[key] = stmt
        elif isinstance(stmt, ast.Import):
            py_imports[ast.unparse(stmt)] = stmt
        # Non-ImportFrom/Import statements are collected separately below.

    # Non-import extras (wrapper class, etc.) go after the merged body.
    extra_body = [s for s in extra_py_stmts
                  if not isinstance(s, (ast.ImportFrom, ast.Import))]

    # ── Module-level metadata (inserted after imports) ──────────────────
    meta_stmts = _generated_metadata_stmts(source)

    # Assemble the final .py AST.
    py_ast = ast.Module(
        body=([ast.Expr(value=ast.Constant(value=module_doc))]
              + list(py_imports.values())
              + meta_stmts
              + py_body
              + extra_body
              + (post_body_stmts or [])),
        type_ignores=[],
    )
    ast.fix_missing_locations(py_ast)
    py_body_str = ast.unparse(py_ast)
    py_content = _header_comment(py_body_str, distro=distro) + py_body_str

    # ------------------------------------------------------------------
    # Stub .pyi path (same logic as .py, using stub generator)
    # ------------------------------------------------------------------
    pyi_imports: dict[str, ast.stmt] = {}
    pyi_body: list[ast.stmt] = []

    for defn in defns:
        # Same merge as above, but sourced from generate_stub_module instead.
        module = ast.parse(generate_stub_module(defn, root_package, distro=distro))
        for stmt in module.body:
            if isinstance(stmt, ast.ImportFrom):
                if _is_local_import(stmt, local_names):
                    continue
                key = f"import_from:{stmt.module}"
                if key in pyi_imports:
                    existing = pyi_imports[key]
                    assert isinstance(existing, ast.ImportFrom)
                    existing_names = {n.name for n in existing.names}
                    for n in stmt.names:
                        if n.name not in existing_names:
                            existing.names.append(n)
                else:
                    pyi_imports[key] = stmt
            elif isinstance(stmt, ast.Import):
                pyi_imports[ast.unparse(stmt)] = stmt
            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue
            elif (isinstance(stmt, ast.Assign) and stmt.targets
                  and isinstance(stmt.targets[0], ast.Name)
                  and stmt.targets[0].id in _META_NAMES):
                # Strip per-sub-type metadata; the merger re-adds it.
                continue
            else:
                pyi_body.append(stmt)

    # Merge imports from extra_pyi_stmts; non-import nodes go to extra body.
    pyi_extra_body: list[ast.stmt] = []
    for stmt in extra_pyi_stmts:
        if isinstance(stmt, ast.ImportFrom):
            key = f"import_from:{stmt.module}"
            if key in pyi_imports:
                existing = pyi_imports[key]
                assert isinstance(existing, ast.ImportFrom)
                existing_names = {n.name for n in existing.names}
                for n in stmt.names:
                    if n.name not in existing_names:
                        existing.names.append(n)
            else:
                pyi_imports[key] = stmt
        elif isinstance(stmt, ast.Import):
            pyi_imports[ast.unparse(stmt)] = stmt
        else:
            pyi_extra_body.append(stmt)

    pyi_ast = ast.Module(
        body=([ast.Expr(value=ast.Constant(value=f"Stub for {module_doc}."))]
              + list(pyi_imports.values())
              + meta_stmts + pyi_body + pyi_extra_body),
        type_ignores=[],
    )
    ast.fix_missing_locations(pyi_ast)
    pyi_body_str = ast.unparse(pyi_ast)
    pyi_content = _header_comment(pyi_body_str, distro=distro) + pyi_body_str

    return py_content, pyi_content


# ---------------------------------------------------------------------------
# Wrapper class builder
# ---------------------------------------------------------------------------


def _wrapper_class_ast(
    base: str,
    attr_names: list[str],
    type_class_names: list[str],
    *,
    has_defaults: bool,
) -> ast.ClassDef:
    """Build a ``ClassVar[type[SubType]]`` wrapper class AST node.

    The wrapper class provides a convenient namespace so users can write
    ``Foo.Request`` / ``Foo.Response`` / ``Foo.Goal`` / etc. instead of
    importing each sub-type individually.  It also serves as the handle that
    the ROS type-map uses for registration.

    The generated class looks like (runtime form)::

        class Foo:
            Request: ClassVar[type[Foo_Request]] = Foo_Request
            Response: ClassVar[type[Foo_Response]] = Foo_Response

    In the stub (``.pyi``) form the ``= Foo_Request`` assignments are omitted
    since stubs only need the type annotation.

    The pattern uses ``ClassVar[type[T]]`` to indicate that these are
    class-level attributes holding a reference to the sub-type class itself
    (not an instance of it).

    Args:
        base: The wrapper class name (e.g. ``"Foo"``).
        attr_names: The attribute names exposed on the wrapper, e.g.
            ``["Request", "Response"]`` or ``["Goal", "Result", ...]``.
        type_class_names: The corresponding generated class names, e.g.
            ``["Foo_Request", "Foo_Response"]``.
        has_defaults:
            ``True`` for the runtime ``.py`` — each annotated attribute gets
            ``= ClassName`` as its default value.
            ``False`` for the stub ``.pyi`` — only the annotation is emitted.

    Returns:
        An ``ast.ClassDef`` node that can be injected into the merged module.
    """
    body: list[ast.stmt] = []
    for attr, cls_name in zip(attr_names, type_class_names):
        ann = ast.Subscript(
            value=ast.Name(id="ClassVar"),
            slice=ast.Subscript(
                value=ast.Name(id="type"),
                slice=ast.Name(id=cls_name),
            ),
        )
        ann_assign = ast.AnnAssign(
            target=ast.Name(id=attr),
            annotation=ann,
            value=ast.Name(id=cls_name) if has_defaults else None,
            simple=1,
        )
        body.append(ann_assign)

    return ast.ClassDef(
        name=base, bases=[], keywords=[],
        body=body, decorator_list=[],
    )


# ---------------------------------------------------------------------------
# Service wrapper generator
# ---------------------------------------------------------------------------


def _generate_service_wrappers(
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
    ri = _registry_import(root_package)
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
        snake = _to_snake_case(base)
        req_defn = defn_by_name[f"{base}_Request"]
        resp_defn = defn_by_name[f"{base}_Response"]

        attr_names = ["Request", "Response"]
        type_class_names = [f"{base}_{n}" for n in attr_names]

        # Build the runtime wrapper class with default-value assignments.
        wrapper_cls = _wrapper_class_ast(
            base, attr_names, type_class_names, has_defaults=True,
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
            names=[ast.alias(name="register_service",
                            asname="_register_service")],
            level=0,
        )
        reg_call = ast.Expr(value=ast.Call(
            func=ast.Name(id="_register_service"),
            args=[
                ast.Call(func=ast.Name(id="ServiceTypes"), args=[],
                         keywords=[
                             ast.keyword(arg="Request",
                                         value=ast.Name(id=type_class_names[0])),
                             ast.keyword(arg="Response",
                                         value=ast.Name(id=type_class_names[1])),
                         ]),
                ast.Constant(value=full_name),
            ],
            keywords=[],
        ))

        content, stub = _merge_type_modules(
            [req_defn, resp_defn],
            extra_py_stmts=[wrapper_cls, classvar_import, types_import],
            extra_pyi_stmts=[
                classvar_import,
                _wrapper_class_ast(
                    base, attr_names, type_class_names, has_defaults=False,
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


def _generate_action_wrappers(
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
    For each candidate, **all eight** ``_ACTION_SUFFIXES`` are checked against
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
    | ``Foo_FeedbackMessage``   | Feedback wrapper (seq_id + feedback)  |
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
    ri = _registry_import(root_package)
    names_set = set(type_names)
    wrappers: list[str] = []
    for tn in type_names:
        if not tn.endswith("_SendGoal_Request"):
            continue
        base = tn[: -len("_SendGoal_Request")]
        # Validate that every expected action sub-type exists before
        # generating; skip silently if any are missing.
        if not all(f"{base}{s}" in names_set for s in _ACTION_SUFFIXES):
            continue

        full_name = f"{package}/action/{base}"
        snake = _to_snake_case(base)

        # Collect all 8 definitions in the canonical order from _ACTION_SUFFIXES.
        orig_defns = [defn_by_name[f"{base}{s}"] for s in _ACTION_SUFFIXES]
        # Strip leading underscore for public attribute names.
        # "_Goal" -> "Goal", "_SendGoal_Request" -> "SendGoal_Request", etc.
        attr_names = [s.lstrip("_") for s in _ACTION_SUFFIXES]
        type_class_names = [f"{base}_{n}" for n in attr_names]

        # Build the runtime wrapper class with default-value assignments.
        wrapper_cls = _wrapper_class_ast(
            base, attr_names, type_class_names, has_defaults=True,
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
            names=[ast.alias(name="register_action",
                            asname="_register_action")],
            level=0,
        )
        # Build a keyword argument for each sub-type attribute.
        reg_keywords = [
            ast.keyword(arg=name, value=ast.Name(id=cls_name))
            for name, cls_name in zip(attr_names, type_class_names)
        ]
        reg_call = ast.Expr(value=ast.Call(
            func=ast.Name(id="_register_action"),
            args=[
                ast.Call(
                    func=ast.Name(id="ActionTypes"),
                    args=[], keywords=reg_keywords,
                ),
                ast.Constant(value=full_name),
            ],
            keywords=[],
        ))

        content, stub = _merge_type_modules(
            orig_defns,
            extra_py_stmts=[wrapper_cls, classvar_import, types_import],
            extra_pyi_stmts=[
                classvar_import,
                _wrapper_class_ast(
                    base, attr_names, type_class_names, has_defaults=False,
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
