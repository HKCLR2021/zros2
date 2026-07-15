"""Component-level tests for ``zros2.generator._codegen._registry``.

Tests the pre-built registry AST in isolation:
- The ``_REGISTRY_AST`` module-level constant unparses to valid Python
- Each section builder produces the expected functions/types
"""

import ast

from zros2.generator._codegen._registry import (
    _REGISTRY_AST,
    _reg_header,
    _reg_message_section,
    _reg_service_section,
    _reg_action_section,
    _reg_helper,
)


def _unparse_stmts(stmts: list[ast.stmt]) -> str:
    """Unparse a list of statements, fixing locations first.

    Python 3.14+ ``ast.unparse`` requires ``lineno`` on ``FunctionDef``
    nodes.  Hand-built AST nodes from the section builders lack these
    attributes, so we call ``fix_missing_locations`` before unparsing.
    """
    mod = ast.Module(body=stmts, type_ignores=[])
    ast.fix_missing_locations(mod)
    return ast.unparse(mod)


# ======================================================================
# Section builders
# ======================================================================

class TestRegHeader:
    def test_returns_imports_and_docstring(self):
        stmts = _reg_header()
        code = _unparse_stmts(stmts)
        assert "Runtime type registry" in code
        assert "from typing import Any" in code
        assert "from zros2.types import" in code
        assert "ServiceTypes" in code
        assert "ActionTypes" in code
        assert "RosMessage" in code


class TestRegMessageSection:
    def test_has_types_dict(self):
        stmts = _reg_message_section()
        code = _unparse_stmts(stmts)
        assert "_TYPES: dict[str, type[RosMessage]]" in code

    def test_has_register_function(self):
        stmts = _reg_message_section()
        code = _unparse_stmts(stmts)
        assert "def register(cls: type[RosMessage], full_name: str) -> None:" in code
        assert "Register a message" in code

    def test_has_get_type_function(self):
        stmts = _reg_message_section()
        code = _unparse_stmts(stmts)
        assert "def get_type(name: str) -> type[RosMessage]:" in code
        assert "Look up a type" in code

    def test_has_has_type_function(self):
        stmts = _reg_message_section()
        code = _unparse_stmts(stmts)
        assert "def has_type(name: str) -> bool:" in code
        assert "Check whether a type" in code

    def test_has_iter_types_function(self):
        stmts = _reg_message_section()
        code = _unparse_stmts(stmts)
        assert "def iter_types() -> list[str]:" in code
        assert "Return a sorted list" in code


class TestRegServiceSection:
    def test_has_services_dict(self):
        stmts = _reg_service_section()
        code = _unparse_stmts(stmts)
        assert "_SERVICES: dict[str, ServiceTypes]" in code

    def test_has_register_service(self):
        stmts = _reg_service_section()
        code = _unparse_stmts(stmts)
        assert "def register_service" in code
        assert "Register a service type" in code

    def test_has_get_service(self):
        stmts = _reg_service_section()
        code = _unparse_stmts(stmts)
        assert "def get_service(name: str) -> ServiceTypes:" in code


class TestRegActionSection:
    def test_has_actions_dict(self):
        stmts = _reg_action_section()
        code = _unparse_stmts(stmts)
        assert "_ACTIONS: dict[str, ActionTypes]" in code

    def test_has_register_action(self):
        stmts = _reg_action_section()
        code = _unparse_stmts(stmts)
        assert "def register_action" in code

    def test_has_get_action(self):
        stmts = _reg_action_section()
        code = _unparse_stmts(stmts)
        assert "def get_action(name: str) -> ActionTypes:" in code


class TestRegHelper:
    def test_has_raise_not_found(self):
        stmts = _reg_helper()
        code = _unparse_stmts(stmts)
        # The ``registry`` parameter has annotation ``dict | None`` but no
        # default value.
        assert "def _raise_not_found(name: str, registry: dict | None) -> None:" in code


# ======================================================================
# _REGISTRY_AST — full module
# ======================================================================

class TestRegistryAST:
    def test_is_ast_module(self):
        assert isinstance(_REGISTRY_AST, ast.Module)

    def test_unparses_to_valid_python(self):
        code = ast.unparse(_REGISTRY_AST)
        compile(code, "<registry>", "exec")

    def test_contains_all_functions(self):
        code = ast.unparse(_REGISTRY_AST)
        assert "def register(" in code
        assert "def get_type(" in code
        assert "def has_type(" in code
        assert "def iter_types(" in code
        assert "def register_service(" in code
        assert "def get_service(" in code
        assert "def register_action(" in code
        assert "def get_action(" in code
        assert "def _raise_not_found(" in code

    def test_contains_all_dicts(self):
        code = ast.unparse(_REGISTRY_AST)
        assert "_TYPES" in code
        assert "_SERVICES" in code
        assert "_ACTIONS" in code

    def test_header_present(self):
        code = ast.unparse(_REGISTRY_AST)
        assert "Runtime type registry" in code

    def test_section_order(self):
        """Dicts should be defined before they're referenced by functions."""
        code = ast.unparse(_REGISTRY_AST)
        types_pos = code.index("_TYPES")
        register_pos = code.index("def register(")
        assert types_pos < register_pos
