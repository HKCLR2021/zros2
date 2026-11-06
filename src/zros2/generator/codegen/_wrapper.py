"""Build the wrapper class exposed by generated service/action modules."""

import ast


def wrapper_class_ast(
    base: str,
    attr_names: list[str],
    type_class_names: list[str],
    *,
    has_defaults: bool,
    full_name: str = "",
) -> ast.ClassDef:
    """Build a ``ClassVar[type[SubType]]`` wrapper class AST node.

    The wrapper class provides a convenient namespace so users can write
    ``Foo.Request`` / ``Foo.Response`` / ``Foo.Goal`` / etc. instead of
    importing each sub-type individually.  It also serves as the handle that
    the ROS type-map uses for registration.

    The generated class looks like (runtime form)::

        class Foo:
            __ros_name__: str = "package/srv/Foo"
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
        full_name:
            The fully-qualified ROS 2 name (e.g. ``"package/srv/Foo"``).
            When provided, a ``__ros_name__`` class attribute is emitted.

    Returns:
        An ``ast.ClassDef`` node that can be injected into the merged module.
    """
    body: list[ast.stmt] = []
    if full_name:
        body.append(
            ast.AnnAssign(
                target=ast.Name(id="__ros_name__"),
                annotation=ast.Name(id="str"),
                value=ast.Constant(value=full_name),
                simple=1,
            )
        )
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
        name=base,
        bases=[],
        keywords=[],
        body=body,
        decorator_list=[],
    )


# ---------------------------------------------------------------------------
# Service wrapper generator
# ---------------------------------------------------------------------------


__all__ = ["wrapper_class_ast"]
