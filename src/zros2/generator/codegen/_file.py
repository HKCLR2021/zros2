"""Generated-file DTO shared by codegen and the write pipeline."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratedFile:
    """A source file produced by the generator, ready to write to disk."""

    path: Path
    content: str

    def __iter__(self) -> Iterator[Path | str]:
        return iter((self.path, self.content))


__all__ = ["GeneratedFile"]
