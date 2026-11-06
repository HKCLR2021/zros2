"""Generate the root package ``__init__.py`` for a generated tree."""

import ast
import pathlib
from collections.abc import Mapping, Sequence

from zros2.generator.semantics._utilities import header_comment

from ._file import GeneratedFile
from ._metadata import generated_metadata_stmts


def generate_root_init(
    files: list[GeneratedFile],
    package_root: pathlib.Path,
    packages: Mapping[str, Mapping[str, Sequence[object]]] | None = None,
    distro: str = "",
) -> None:
    """Add or update the root ``__init__.py``.

    The root package must import every generated sub-package eagerly.  The
    sub-package ``msg/__init__.py`` files perform the registry registration;
    without these imports ``get_type()`` is empty until the user happens to
    import a specific sub-package.
    """
    packages = packages or {}
    root_init = package_root / "__init__.py"
    registry_names = (
        "has_type",
        "get_type",
        "get_service",
        "get_action",
        "iter_types",
    )
    imp = "from ._registry import " + ", ".join(
        f"{name} as {name}" for name in registry_names
    )
    pkg_import = "from . import " + ", ".join(
        f"{name} as {name}" for name in sorted(packages)
    )
    imports = []
    for line in (pkg_import, imp):
        if line not in ("", "from . import "):
            imports.append(line)
    block = "\n".join(imports)
    # Find existing root __init__ (if any), or create a placeholder
    for i, f in enumerate(files):
        if f.path == root_init:
            # Already have one — append imports that are missing.
            missing = [line for line in imports if line not in f.content]
            if missing:
                files[i] = GeneratedFile(f.path, f.content + "\n" + "\n".join(missing) + "\n")
            return

    # Create a minimal root __init__ that imports the registry.
    # Include a package docstring so the module is self-describing.
    package_name = package_root.name
    meta = ast.unparse(
        ast.fix_missing_locations(
            ast.Module(body=generated_metadata_stmts(), type_ignores=[])
        )
    ).strip()
    docstring = f'"""Package: {package_name}."""'
    body_content = f"{docstring}\n{block}\n{meta}\n"
    content = header_comment(body_content, distro=distro) + body_content
    files.append(GeneratedFile(root_init, content))


__all__ = ["generate_root_init"]
