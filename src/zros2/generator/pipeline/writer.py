"""Write generated source files to disk."""

import pathlib

from ..codegen.message import GeneratedFile


def write_generated_files(files: list[GeneratedFile]) -> list[pathlib.Path]:
    """Write generated files to disk, creating parent directories as needed."""
    written: list[pathlib.Path] = []
    for generated in files:
        generated.path.parent.mkdir(parents=True, exist_ok=True)
        generated.path.write_text(generated.content.lstrip("\n"), encoding="utf-8")
        written.append(generated.path)
    return written


__all__ = ["write_generated_files"]
