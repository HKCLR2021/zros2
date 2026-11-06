"""Render and merge service/action sub-type families."""

import ast

from zros2.generator.parsing._models import MsgDefinition

from ._merge import merge_generated_sources
from ._message import generate_message_module
from ._stubs import generate_stub_module


def merge_type_modules(
    defns: list[MsgDefinition],
    extra_py_stmts: list[ast.stmt],
    extra_pyi_stmts: list[ast.stmt],
    module_doc: str,
    root_package: str,
    post_body_stmts: list[ast.stmt] | None = None,
    source: str | None = None,
    distro: str = "",
) -> tuple[str, str]:
    """Render a service/action family and merge it with the generic engine."""
    py_sources = [
        generate_message_module(defn, root_package, distro=distro) for defn in defns
    ]
    pyi_sources = [
        generate_stub_module(defn, root_package, distro=distro) for defn in defns
    ]
    return merge_generated_sources(
        defns,
        py_sources,
        pyi_sources,
        extra_py_stmts,
        extra_pyi_stmts,
        module_doc,
        post_body_stmts,
        source,
        distro,
    )


__all__ = ["merge_type_modules"]
