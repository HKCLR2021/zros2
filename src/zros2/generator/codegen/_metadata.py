"""Generate module-level metadata AST nodes.

This lives in codegen rather than semantics because it builds ``ast`` nodes.
"""

import ast


def generated_metadata_stmts(source: str | None = None) -> list[ast.stmt]:
    """Return module-level metadata assignments for generated files."""
    from zros2.generator.semantics._utilities import _PKG_VERSION

    pkg_version = _PKG_VERSION
    stmts: list[ast.stmt] = [
        ast.Assign(
            targets=[ast.Name(id="__generated__")],
            value=ast.Constant(value=True),
        ),
        ast.Assign(
            targets=[ast.Name(id="__generator__")],
            value=ast.Constant(value=f"zros2-gen v{pkg_version}"),
        ),
    ]
    if source is not None:
        stmts.append(
            ast.Assign(
                targets=[ast.Name(id="__source__")],
                value=ast.Constant(value=source),
            )
        )
    return stmts


__all__ = ["generated_metadata_stmts"]
