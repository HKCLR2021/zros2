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

?base: PRIMITIVE
     | string_type
     | wstring_type
     | IDENTIFIER

string_type: STRING_KW bounded_size?
wstring_type: WSTRING_KW bounded_size?
bounded_size: "<=" INT

array_suffix: "[" "]"          -> unbounded
            | "[" INT "]"      -> fixed
            | "[" "<=" INT "]" -> bounded

sequence: "sequence" "<" base ("," INT)? ">"

PRIMITIVE: "bool"|"byte"|"char"
         | "int8"|"uint8"|"int16"|"uint16"
         | "int32"|"uint32"|"int64"|"uint64"
         | "float32"|"float64"
STRING_KW: "string"
WSTRING_KW: "wstring"
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
        ``int32[]``             base="int32",   kind="unbounded_array"
        ``float64[3]``          base="float64", kind="fixed_array",      array_size=3
        ``int32[<=5]``          base="int32",   kind="bounded_array",    array_max=5
        ``sequence<uint8>``     base="uint8",   kind="unbounded_sequence"
        ``sequence<uint8,10>``  base="uint8",   kind="bounded_sequence", array_max=10
        ``string<=10[<=5]``     base="string",  string_max=10,           kind="bounded_array", array_max=5
    """
    base_name: str
    is_bounded_string: bool = False
    string_max: int | None = None

    # One of: None, "unbounded_array", "fixed_array", "bounded_array",
    #         "unbounded_sequence", "bounded_sequence"
    kind: str | None = None
    array_size: int | None = None   # for fixed_array
    array_max: int | None = None    # for bounded_array / bounded_sequence


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
        # Leaf: primitive, string keyword, or identifier
        return TypeInfo(base_name=str(node))

    data = node.data
    children = node.children

    if data == "type":
        return _walk_type(children)

    if data == "string_type":
        return _walk_string_type(children, is_wstring=False)
    if data == "wstring_type":
        return _walk_string_type(children, is_wstring=True)
    if data == "bounded_size":
        # Should not appear as top-level; handled by string_type walker
        return TypeInfo(base_name="")

    if data == "sequence":
        return _walk_sequence(children)

    if data in ("unbounded", "fixed", "bounded"):
        # Array suffix — also not top-level; see _walk_type
        return _walk_array(children, kind=data)

    # Fallback (shouldn't normally reach here)
    return TypeInfo(base_name=str(children[0]) if children else "")


def _walk_type(children: list[Tree | Token]) -> TypeInfo:
    """Walk a ``type`` node.

    Possible shapes::

        [Token]                          — bare scalar / identifier
        [Tree("string_type"|...)]        — string/wstring type
        [Tree("sequence")]               — sequence
        [Token, Tree("unbounded"|...)]   — scalar + array suffix
        [Tree("string_type"|...), Tree("unbounded"|...)] — string + array
    """
    if len(children) == 1:
        child = children[0]
        if isinstance(child, Token):
            return TypeInfo(base_name=str(child))
        return _walk(child)

    # Two children: base + array suffix
    base, suffix = children
    info = _walk_base(base)
    arr = _walk(suffix)  # This retrieves kind/array_size/array_max
    # Copy array info from the temporary TypeInfo
    info.kind = arr.kind
    info.array_size = arr.array_size
    info.array_max = arr.array_max
    return info


def _walk_base(node: Tree | Token) -> TypeInfo:
    """Walk a ``base`` child (may be inlined)."""
    if isinstance(node, Token):
        return TypeInfo(base_name=str(node))
    return _walk(node)


def _walk_string_type(children: list[Tree | Token], *,
                      is_wstring: bool) -> TypeInfo:
    """Walk a ``string_type / wstring_type`` node."""
    base = "wstring" if is_wstring else "string"
    info = TypeInfo(base_name=base)

    if len(children) > 1:
        # Has bounded_size child → Tree("bounded_size", [INT])
        size_tree = cast(Tree, children[1])
        info.is_bounded_string = True
        info.string_max = int(cast(Token, size_tree.children[0]))

    return info


def _walk_sequence(children: list[Tree | Token]) -> TypeInfo:
    """Walk a ``sequence`` node.

    Shape::

        [base_token]              — unbounded sequence
        [base_token, INT]         — bounded sequence
    """
    base_info = _walk_base(children[0])
    base_info.kind = "bounded_sequence" if len(children) > 1 else "unbounded_sequence"
    if len(children) > 1:
        base_info.array_max = int(cast(Token, children[1]))
    return base_info


def _walk_array(children: list[Tree | Token], *,
                kind: str) -> TypeInfo:
    """Walk an array-suffix node."""
    info = TypeInfo(base_name="")
    info.kind = kind
    if children:
        val = int(cast(Token, children[0]))
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
