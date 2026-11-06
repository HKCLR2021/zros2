"""Convert already-parsed Python literal values into AST expressions."""

import ast
import math


def literal_ast(value: object) -> ast.expr:
    """Build an AST literal, including NaN/Infinity helper calls."""
    if isinstance(value, float):
        if math.isnan(value):
            return ast.Call(
                func=ast.Name(id="float"),
                args=[ast.Constant(value="nan")],
                keywords=[],
            )
        if math.isinf(value):
            text = "inf" if value > 0 else "-inf"
            return ast.Call(
                func=ast.Name(id="float"),
                args=[ast.Constant(value=text)],
                keywords=[],
            )
        return ast.Constant(value=float(value))
    if isinstance(value, (str, int, bool, bytes)):
        return ast.Constant(value=value)
    raise TypeError(f"Unsupported literal type: {type(value).__name__}")


__all__ = ["literal_ast"]
