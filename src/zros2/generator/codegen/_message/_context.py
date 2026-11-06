"""Per-message generation context."""

from dataclasses import dataclass

from zros2.generator.parsing._models import MsgDefinition
from zros2.generator.semantics._type_context import TypeContext, build_type_context


@dataclass(frozen=True)
class MessageContext:
    """Inputs shared by field planning, methods, and module assembly."""

    defn: MsgDefinition
    root_package: str
    type_context: TypeContext
    class_name: str
    class_token: str

    @classmethod
    def build(cls, defn: MsgDefinition, root_package: str) -> "MessageContext":
        """Build a context for *defn*."""
        class_name = defn.type_name.split("/")[-1].replace("-", "_")
        if not class_name or not class_name[0].isalpha():
            raise ValueError(
                f"Invalid type_name '{defn.type_name}' — "
                f"could not derive a valid Python class name"
            )
        return cls(
            defn=defn,
            root_package=root_package,
            type_context=build_type_context(defn, root_package),
            class_name=class_name,
            class_token="".join(
                ch if ch.isalnum() or ch == "_" else "_" for ch in class_name
            ),
        )


__all__ = ["MessageContext"]
