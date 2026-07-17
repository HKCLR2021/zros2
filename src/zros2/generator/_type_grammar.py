"""Lark-based ROS 2 type expression parser — replaces all ad-hoc regex matching.

Grammar
-------
The parser recognises every valid ROS 2 type form::

    int32                         scalar primitive
    bool, byte, char, …           other primitives
    string                        unbounded string
    string<=255                   bounded string
    wstring                       unbounded wide string
    wstring<=10                   bounded wide string
    int32[]                       unbounded dynamic array
    float64[3]                    fixed-size array
    int32[<=5]                    bounded dynamic array
    string<=10[<=5]               bounded string in bounded array
    sequence<uint8>               unbounded sequence
    sequence<uint8,10>            bounded sequence
    std_msgs/String               nested type
    geometry_msgs/msg/Point       fully-qualified nested type
"""

from dataclasses import dataclass
from typing import cast

from lark import Lark, Token, Tree


# ═══════════════════════════════════════════════════════════════════════════
# Grammar
# ═══════════════════════════════════════════════════════════════════════════

_GRAMMAR = r"""
?start: type

type: sequence
    | base array_suffix?

base: PRIMITIVE
    | IDENTIFIER size_mod?

size_mod: "<=" size_expr

array_suffix: "[" "]"               -> unbounded
            | "[" size_expr "]"          -> fixed
            | "[" "<=" size_expr "]"     -> bounded

sequence: "sequence" "<" base ("," size_expr)? ">"

?size_expr: INT | IDENTIFIER

PRIMITIVE: "bool"|"byte"|"char"
         | "int8"|"uint8"|"int16"|"uint16"
         | "int32"|"uint32"|"int64"|"uint64"
         | "float32"|"float64"
IDENTIFIER: /[a-zA-Z_][\w\/]*/
INT: /[0-9]+/
%ignore /\s+/
"""


# ═══════════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class TypeInfo:
    """Structured representation of a ROS 2 type expression.

    Examples of what each combination produces::

        ``int32``               base="int32"
        ``string``              base="string"
        ``string<=10``          base="string",  string_max=10
        ``string<=MAX_LEN``     base="string",  string_max="MAX_LEN"
        ``int32[]``             base="int32",   kind="unbounded"
        ``float64[3]``          base="float64", kind="fixed",         array_size=3
        ``float64[SIZE]``       base="float64", kind="fixed",         array_size="SIZE"
        ``int32[<=5]``          base="int32",   kind="bounded",       array_max=5
        ``int32[<=MAX]``        base="int32",   kind="bounded",       array_max="MAX"
        ``sequence<uint8>``     base="uint8",   kind="unbounded_sequence"
        ``sequence<uint8,10>``  base="uint8",   kind="bounded_sequence", array_max=10
        ``sequence<uint8,N>``   base="uint8",   kind="bounded_sequence", array_max="N"
        ``string<=10[<=5]``     base="string",  string_max=10,         kind="bounded", array_max=5

    Size fields (``string_max``, ``array_size``, ``array_max``) hold either
    an ``int`` (for literal bounds) or a ``str`` (for constant references).
    """
    base_name: str
    is_bounded_string: bool = False
    string_max: int | str | None = None

    # One of: None, "unbounded", "fixed", "bounded",
    #         "unbounded_sequence", "bounded_sequence"
    kind: str | None = None
    array_size: int | str | None = None    # for fixed_array
    array_max: int | str | None = None     # for bounded_array / bounded_sequence


# ═══════════════════════════════════════════════════════════════════════════
# Parser (LALR, tree-walk)
# ═══════════════════════════════════════════════════════════════════════════

_PARSER = Lark(_GRAMMAR, parser="lalr")


def parse_type(type_str: str) -> TypeInfo:
    """Parse a ROS 2 type expression.

    Args:
        type_str: Raw type text from a ``.msg`` file, e.g. ``"uint8[]"``.

    Returns:
        A ``TypeInfo`` with the decomposed type.

    Raises:
        LarkError: The input is not valid ROS 2 type syntax.
    """
    tree = _PARSER.parse(type_str)
    return _walk(tree)


# ═══════════════════════════════════════════════════════════════════════════
# Internal tree walker
# ═══════════════════════════════════════════════════════════════════════════

def _walk(node: Tree | Token) -> TypeInfo:
    """Recursive tree → TypeInfo."""
    if isinstance(node, Token):
        return TypeInfo(base_name=str(node))

    data = node.data
    children = node.children

    if data == "type":
        return _walk_type(children)

    if data == "base":
        return _walk_base(children)

    if data == "sequence":
        return _walk_sequence(children)

    if data in ("unbounded", "fixed", "bounded"):
        return _walk_array(children, kind=data)

    # Fallback (shouldn't normally reach here)
    return TypeInfo(base_name=str(children[0]) if children else "")


def _walk_type(children: list[Tree | Token]) -> TypeInfo:
    """Walk a ``type`` node.

    Possible shapes::

        [Tree("base", ...)]                    — scalar / identifier / string
        [Tree("sequence", ...)]                — sequence
        [Tree("base", ...), Tree(arr_suffix)]  — base + array suffix
    """
    if len(children) == 1:
        child = children[0]
        if isinstance(child, Tree):
            if child.data == "sequence":
                return _walk_sequence(child.children)
            if child.data == "base":
                return _walk_base(child.children)
        return TypeInfo(base_name=str(child))

    # Two children: base + array suffix
    base_node = cast(Tree, children[0])
    suffix = children[1]
    info = _walk_base(base_node.children)
    arr = _walk(suffix)  # This retrieves kind/array_size/array_max
    info.kind = arr.kind
    info.array_size = arr.array_size
    info.array_max = arr.array_max
    return info


def _walk_base(children: list[Tree | Token]) -> TypeInfo:
    """Walk a ``base`` node.

    ``base`` is either a ``PRIMITIVE`` token, or an ``IDENTIFIER`` token
    optionally followed by a ``size_mod`` subtree for bounded strings::

        [Token(PRIMITIVE, "int32")]
        [Token(IDENTIFIER, "my_pkg/Type")]
        [Token(IDENTIFIER, "string"), Tree("size_mod", ["<=", INT | IDENTIFIER])]
    """
    first = children[0]
    if isinstance(first, Token):
        base_name = str(first)
        info = TypeInfo(base_name=base_name)
        if base_name in ("string", "wstring") and len(children) > 1:
            # Has size_mod child → Tree("size_mod", ["<=", size_token])
            size_tree = cast(Tree, children[1])
            # size_expr is inlined, so the value token is the last child
            info.is_bounded_string = True
            info.string_max = _resolve_size_value(cast(Token, size_tree.children[-1]))
        return info
    return TypeInfo(base_name=str(children[0]) if children else "")


def _resolve_size_value(token: Token) -> int | str:
    """Extract a size value from a ``size_expr`` token.

    ``INT`` tokens are converted to ``int``, ``IDENTIFIER`` tokens (constant
    references) are kept as their string name.
    """
    if token.type == "INT":
        return int(token)
    return str(token)


def _walk_sequence(children: list[Tree | Token]) -> TypeInfo:
    """Walk a ``sequence`` node.

    Shape::

        [Tree("base", ...)]              — unbounded sequence
        [Tree("base", ...), INT|IDENT]   — bounded sequence
    """
    base_info = _walk_base(cast(Tree, children[0]).children)
    base_info.kind = "bounded_sequence" if len(children) > 1 else "unbounded_sequence"
    if len(children) > 1:
        base_info.array_max = _resolve_size_value(cast(Token, children[1]))
    return base_info


def _walk_array(children: list[Tree | Token], *,
                kind: str) -> TypeInfo:
    """Walk an array-suffix node."""
    info = TypeInfo(base_name="")
    info.kind = kind
    if children:
        # fixed → [size_token]; bounded → ["<=", size_token];
        # the value token is always last because size_expr is inlined.
        val = _resolve_size_value(cast(Token, children[-1]))
        if kind == "fixed":
            info.array_size = val
        else:  # bounded
            info.array_max = val
    return info


# ═══════════════════════════════════════════════════════════════════════════
# Convenience
# ═══════════════════════════════════════════════════════════════════════════

ROS2_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "bool", "byte", "char",
    "int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64",
    "float32", "float64",
    "string", "wstring",
})
