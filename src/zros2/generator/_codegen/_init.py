"""
``__init__.py`` generation for generated ROS 2 Python packages.

The functions in this module produce two levels of init file:

1. A *subdirectory index* (``msg/__init__.py``, ``srv/__init__.py``, etc.) that
   re-exports every ROS 2 type defined in that subdirectory.  For ``msg``
   subdirectories it also emits registration calls so the types can be looked up
   by their fully-qualified ROS 2 name at run time.

2. A *package-level* ``__init__.py`` (e.g. ``my_interfaces/__init__.py``) that
   simply imports each subdirectory (``msg``, ``srv``, …) so that the standard
   ROS 2 ``from package.msg import Foo`` pattern works.

Both functions build their output with the ``ast`` module rather than string
templating; this keeps the codegen consistent across all back-end modules and
avoids ad-hoc formatting logic in this layer.
"""

import ast

from ._msg import _registry_import
from .._utilities import _generated_metadata_stmts, _header_comment, _to_snake_case


def generate_init_module(
    package: str,
    subdir: str,
    type_names: list[str],
    root_package: str = "",
    type_to_file: dict[str, str] | None = None,
    distro: str = "",
) -> str:
    """Generate an ``__init__.py`` that re-exports all types in a subdirectory.

    The produced file lives at e.g. ``<package>/msg/__init__.py`` and does two
    things:

    1. For every type defined in that subdirectory, emit a ``from ._foo import
       Foo`` so that callers can write ``from package.msg import Foo``.

    2. If the subdirectory is ``msg``, also register each type with the
       run-time type registry so that the ROS 2 type name
       (``package/msg/Foo``) can be resolved to the Python class at run time.

    When *type_names* is empty the output is a minimal placeholder — a docstring
    comment and a ``pass`` — so the module is still importable.
    """
    body: list[ast.stmt] = []

    if not type_names:
        # Emit a stub so the directory remains a valid Python package even
        # when it contains no definitions (e.g. an empty ``msg/``).
        body.append(ast.Expr(value=ast.Constant(
            value=f"Auto-generated ROS 2 type index for {package}/{subdir}.",
        )))
        body.append(ast.Pass())
    else:
        # Opening docstring identifying the generated file.
        body.append(ast.Expr(value=ast.Constant(
            value=f"Auto-generated ROS 2 type index for {package}/{subdir}.",
        )))

        # Map a type name to the file stem that contains it.  When the caller
        # provides an explicit lookup table we honour it; otherwise we derive
        # the stem from the type name via the standard snake-case convention.
        def _file_stem(name: str) -> str:
            if type_to_file and name in type_to_file:
                return type_to_file[name]
            return f"_{_to_snake_case(name)}"

        # Re-export every type from its individual module.
        for name in sorted(type_names):
            body.append(ast.ImportFrom(
                module=f".{_file_stem(name)}",
                names=[ast.alias(name=name)],
                level=0,
            ))

        # The ``msg`` subdirectory is special: generated message types must be
        # registered with the run-time lookup table so that ROS 2 string names
        # (e.g. ``"std_msgs/msg/String"``) can be resolved to Python classes
        # dynamically.  The import path depends on whether this is a built-in
        # package or a user package (controlled by *root_package*).
        if subdir == "msg":
            ri = _registry_import(root_package)
            body.append(ast.ImportFrom(
                module=ri,
                names=[ast.alias(name="register", asname="_register")],
                level=0,
            ))
            for name in sorted(type_names):
                full_name = f"{package}/{subdir}/{name}"
                body.append(ast.Expr(value=ast.Call(
                    func=ast.Name(id="_register"),
                    args=[
                        ast.Name(id=name),
                        ast.Constant(value=full_name),
                    ],
                    keywords=[],
                )))

    # ── Module-level metadata (inserted after imports) ──────────────────
    meta = _generated_metadata_stmts()
    insert_pos = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, (ast.ImportFrom, ast.Import)):
            insert_pos = i + 1
    for i, s in enumerate(meta):
        body.insert(insert_pos + i, s)

    # Assemble the AST, fix node locations so ``ast.unparse`` produces valid
    # code (``fix_missing_locations`` supplies ``lineno`` / ``col_offset``),
    # then prepend the standard header comment (license, generation notice).
    module = ast.fix_missing_locations(ast.Module(
        body=body, type_ignores=[],
    ))
    content = ast.unparse(module)
    return _header_comment(content, distro=distro) + content


def generate_package_init(package: str, subdirs: list[str], distro: str = "") -> str:
    """Generate a package-level ``__init__.py``.

    This produces the top-most init file (e.g. ``my_interfaces/__init__.py``)
    that imports every sub-package produced by the code generator — typically
    ``msg``, ``srv``, and ``action``.  The resulting package tree mirrors the
    layout of a conventional ROS 2 Python package so that end users can write:

        from my_interfaces.msg import Foo
        from my_interfaces.srv import Bar

    Each sub-package import is emitted as ``from . import msg`` (etc.),
    deduplicated via *set*, and kept in alphabetical order for deterministic
    output.
    """
    body: list[ast.stmt] = []
    body.append(ast.Expr(value=ast.Constant(
        value=f"Package: {package}.",
    )))
    for sd in sorted(set(subdirs)):
        body.append(ast.ImportFrom(
            module=".",
            names=[ast.alias(name=sd)],
            level=0,
        ))

    # ── Module-level metadata (inserted after imports) ──────────────────
    meta = _generated_metadata_stmts()
    insert_pos = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, (ast.ImportFrom, ast.Import)):
            insert_pos = i + 1
    for i, s in enumerate(meta):
        body.insert(insert_pos + i, s)

    module = ast.fix_missing_locations(ast.Module(
        body=body, type_ignores=[],
    ))
    content = ast.unparse(module)
    return _header_comment(content, distro=distro) + content
