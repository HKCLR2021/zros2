"""Quality-of-service values used in liveliness key expressions."""

from dataclasses import dataclass


@dataclass
class Qos:
    """Quality-of-service parameters for a liveliness token."""

    reliability: int | None = None
    durability: int | None = None
    history_kind: int | None = None
    history_depth: int | None = None
    user_data: bytes | None = None

    def to_key_expr(self, keyless: bool = True) -> str:
        """Serialize this QoS into a key-expression-compatible string."""
        parts: list[str] = ["", "", "", ""]

        if not keyless:
            parts[0] = "K"
        if self.reliability is not None:
            parts[1] = str(self.reliability)
        if self.durability is not None:
            parts[2] = str(self.durability)
        if self.history_kind is not None:
            parts[3] = f"{self.history_kind},{self.history_depth or 0}"
        if self.user_data is not None:
            parts.append(self.user_data.decode("utf-8", errors="replace"))

        return ":".join(parts)

    @classmethod
    def from_key_expr(cls, key_expr: str) -> tuple[bool, "Qos"]:
        """Parse a QoS key expression into a ``(keyless, Qos)`` pair."""
        elements = key_expr.split(":")
        keyless = elements[0] != "K"
        qos = cls()

        if len(elements) > 1 and elements[1]:
            qos.reliability = int(elements[1])
        if len(elements) > 2 and elements[2]:
            qos.durability = int(elements[2])
        if len(elements) > 3 and elements[3]:
            if "," in elements[3]:
                history_kind, history_depth = elements[3].split(",", 1)
                qos.history_kind = int(history_kind) if history_kind else None
                qos.history_depth = int(history_depth) if history_depth else None
            else:
                qos.history_kind = int(elements[3])
        if len(elements) > 4 and elements[4]:
            qos.user_data = elements[4].encode("utf-8")

        return keyless, qos

    @staticmethod
    def any() -> str:
        """Return a wildcard key expression that matches any QoS."""
        return "*"


__all__ = ["Qos"]
