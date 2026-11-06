"""Generic AST merging for service/action wrapper modules.

The merger is deliberately independent of service or action semantics: it
takes already-generated ``.py``/``.pyi`` modules, removes self-imports,
deduplicates imports, strips per-type metadata, and concatenates the bodies.
"""

import ast

from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.semantics._utilities import header_comment

from ._metadata import generated_metadata_stmts


def is_local_import(stmt: ast.stmt, local_names: set[str]) -> bool:
    """Check if an ``ImportFrom`` targets a type defined in the same merged module.

    ``merge_type_modules`` combines several sub-types into one file,
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
    return any(
        name.name.lstrip("_") in local_names
        or (name.asname is not None and name.asname in local_names)
        for name in stmt.names
    )


def strip_local_import(
    stmt: ast.ImportFrom,
    local_names: set[str],
) -> ast.ImportFrom | None:
    """Remove self-referencing names, preserving the other imported names."""
    kept = [
        name
        for name in stmt.names
        if name.name.lstrip("_") not in local_names
        and name.asname not in local_names
    ]
    if not kept:
        return None
    if len(kept) != len(stmt.names):
        stmt.names = kept
    return stmt


# ---------------------------------------------------------------------------
# Core merge engine
# ---------------------------------------------------------------------------


def merge_generated_sources(
    defns: list[MsgDefinition],
    py_sources: list[str],
    pyi_sources: list[str],
    extra_py_stmts: list[ast.stmt],
    extra_pyi_stmts: list[ast.stmt],
    module_doc: str,
    post_body_stmts: list[ast.stmt] | None = None,
    source: str | None = None,
    distro: str = "",
) -> tuple[str, str]:
    """Merge several ``MsgDefinition`` types into one ``.py`` / ``.pyi``.

    The merger generates each sub-type independently, removes imports that
    refer to another type in the same merged module, deduplicates imports,
    strips per-type metadata/docstrings, and appends wrapper/registration
    statements supplied by the caller.  The same merge runs twice: once with
    runtime modules and once with stub modules.

    Args:
        defns: Sub-type definitions to merge, in output order.
        py_sources: Pre-rendered runtime modules, one per definition.
        pyi_sources: Pre-rendered stub modules, one per definition.
        extra_py_stmts: Runtime-only statements (wrapper class, imports).
        extra_pyi_stmts: Stub-only statements.
        module_doc: Module docstring.
        post_body_stmts: Statements appended last (usually registry calls).
        source: Optional ROS source path for metadata.
        distro: ROS distro for the generated-file header.

    Returns:
        ``(py_content, pyi_content)``.
    """
    # Derive the set of public type names being merged (e.g. "Foo_Request").
    # This is used later to detect and drop self-referencing imports.
    if len(py_sources) != len(defns) or len(pyi_sources) != len(defns):
        raise ValueError("py_sources and pyi_sources must match defns length")
    local_names = {d.type_name.split("/")[-1] for d in defns}

    # Names of module-level metadata assignments that should be stripped
    # from individual sub-type modules (the merger re-adds them).
    _META_NAMES = frozenset({"__generated__", "__generator__", "__source__"})

    # ------------------------------------------------------------------
    # Runtime .py path
    # ------------------------------------------------------------------
    py_imports: dict[str, ast.stmt] = {}
    py_body: list[ast.stmt] = []

    for py_source in py_sources:
        module = ast.parse(py_source)
        for stmt in module.body:
            if isinstance(stmt, ast.ImportFrom):
                # Drop self-referencing names (circular in a merged file)
                # while preserving any non-local names in the same import.
                stmt = strip_local_import(stmt, local_names)
                if stmt is None:
                    continue
                # Deduplicate: merge new names into an existing ImportFrom
                # for the same module instead of adding a second statement.
                key = f"import_from:{stmt.level}:{stmt.module}"
                if key in py_imports:
                    existing = py_imports[key]
                    if not isinstance(existing, ast.ImportFrom):
                        raise TypeError("merged import key does not hold an ImportFrom")
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
            elif (
                isinstance(stmt, ast.Assign)
                and stmt.targets
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id in _META_NAMES
            ):
                # Strip per-sub-type metadata; the merger re-adds it.
                continue
            else:
                # Everything else (ClassDef, FunctionDef, Assign, etc.)
                # goes into the merged body as-is.
                py_body.append(stmt)

    # Merge imports from extra_py_stmts into the same deduplicated dict.
    for stmt in extra_py_stmts:
        if isinstance(stmt, ast.ImportFrom):
            key = f"import_from:{stmt.level}:{stmt.module}"
            if key in py_imports:
                existing = py_imports[key]
                if not isinstance(existing, ast.ImportFrom):
                    raise TypeError("merged import key does not hold an ImportFrom")
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
    extra_body = [
        s for s in extra_py_stmts if not isinstance(s, (ast.ImportFrom, ast.Import))
    ]

    # ── Module-level metadata (inserted after imports) ──────────────────
    meta_stmts = generated_metadata_stmts(source)

    # Assemble the final .py AST.
    py_ast = ast.Module(
        body=(
            [ast.Expr(value=ast.Constant(value=module_doc))]
            + list(py_imports.values())
            + meta_stmts
            + py_body
            + extra_body
            + (post_body_stmts or [])
        ),
        type_ignores=[],
    )
    ast.fix_missing_locations(py_ast)
    py_body_str = ast.unparse(py_ast)
    py_content = header_comment(py_body_str, distro=distro) + py_body_str

    # ------------------------------------------------------------------
    # Stub .pyi path (same logic as .py, using stub generator)
    # ------------------------------------------------------------------
    pyi_imports: dict[str, ast.stmt] = {}
    pyi_body: list[ast.stmt] = []

    for pyi_source in pyi_sources:
        module = ast.parse(pyi_source)
        for stmt in module.body:
            if isinstance(stmt, ast.ImportFrom):
                stmt = strip_local_import(stmt, local_names)
                if stmt is None:
                    continue
                key = f"import_from:{stmt.level}:{stmt.module}"
                if key in pyi_imports:
                    existing = pyi_imports[key]
                    if not isinstance(existing, ast.ImportFrom):
                        raise TypeError("merged import key does not hold an ImportFrom")
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
            elif (
                isinstance(stmt, ast.Assign)
                and stmt.targets
                and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id in _META_NAMES
            ):
                # Strip per-sub-type metadata; the merger re-adds it.
                continue
            else:
                pyi_body.append(stmt)

    # Merge imports from extra_pyi_stmts; non-import nodes go to extra body.
    pyi_extra_body: list[ast.stmt] = []
    for stmt in extra_pyi_stmts:
        if isinstance(stmt, ast.ImportFrom):
            key = f"import_from:{stmt.level}:{stmt.module}"
            if key in pyi_imports:
                existing = pyi_imports[key]
                if not isinstance(existing, ast.ImportFrom):
                    raise TypeError("merged import key does not hold an ImportFrom")
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
        body=(
            [ast.Expr(value=ast.Constant(value=f"Stub for {module_doc}."))]
            + list(pyi_imports.values())
            + meta_stmts
            + pyi_body
            + pyi_extra_body
        ),
        type_ignores=[],
    )
    ast.fix_missing_locations(pyi_ast)
    pyi_body_str = ast.unparse(pyi_ast)
    pyi_content = header_comment(pyi_body_str, distro=distro) + pyi_body_str

    return py_content, pyi_content
