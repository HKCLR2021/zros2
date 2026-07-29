"""Generator orchestration — type grouping, code generation, registry assembly.

This module owns the **six-stage generation pipeline** that turns a merged
type dictionary into a list of ``GeneratedFile`` objects ready to be written
to disk.  It is the only module in ``pipeline/`` that touches the ``codegen/``
layer.
"""

import ast
import pathlib

from ..codegen.message import GeneratedFile, generate_message_module
from ..codegen.package_init import generate_init_module, generate_package_init
from ..codegen.registry import REGISTRY_AST
from ..codegen.service_action import (
    ACTION_SUFFIXES,
    SRV_SUFFIXES,
    generate_action_wrappers,
    generate_service_wrappers,
)
from ..codegen.stubs import generate_stub_module
from ..parsing.models import MsgDefinition
from ..semantics.utilities import (
    generated_metadata_stmts,
    header_comment,
    to_snake_case,
)

# ── 6-stage generation ─────────────────────────────────────────────


def generate_all(
    types: dict[str, MsgDefinition],
    output_dir: pathlib.Path,
    root_package: str = "",
    distro: str = "",
) -> list[GeneratedFile]:
    """Generate Python source files for all parsed types.

    The overall flow has six stages:
      1. Group parsed types by package and kind (msg / srv / action).
      2. Generate individual ``_.py`` / ``_.pyi`` files for message types (and for
         root-level service/action types whose sub-types are **skipped**).
      3. Generate combined service wrapper files (each file bundles Foo_Request,
         Foo_Response, and Foo into one module).
      4. Generate combined action wrapper files (each file bundles all sub-types
         plus the action super-class).
      5. Generate ``__init__.py`` for each sub-directory, re-exporting only the
         publicly-relevant names (msg exports everything; srv exports all types;
         action filters out internal transport sub-types).
      6. Assemble the runtime registry (``get_type``, ``has_type``, ``get_service``,
         ``get_action``) from a pre-built AST and wire it into the root package init.
    """
    files: list[GeneratedFile] = []

    # ------------------------------------------------------------------
    # Step 1: Group definitions by package -> kind (msg / srv / action)
    # ------------------------------------------------------------------
    packages: dict[str, dict[str, list[MsgDefinition]]] = {}
    for defn in types.values():
        pkg = defn.package
        kind = defn.type_kind
        packages.setdefault(pkg, {}).setdefault(kind, []).append(defn)

    for pkg, subdirs in packages.items():
        pkg_dir = output_dir / pkg
        pkg_init = generate_package_init(pkg, sorted(subdirs.keys()), distro=distro)
        files.append(GeneratedFile(pkg_dir / "__init__.py", pkg_init))

        for subdir, defns in subdirs.items():
            sub_dir = pkg_dir / subdir
            type_names: list[str] = []
            defn_by_name: dict[str, MsgDefinition] = {}
            type_to_file: dict[str, str] = {}

            # ------------------------------------------------------------------
            # Step 2: Generate individual message-type files
            #
            # Service and action definitions are split into multiple sub-types
            # (e.g. Foo_Request / Foo_Response for services, Foo_Goal / Foo_Result
            # for actions). These sub-types are NOT emitted as individual modules
            # because they will be inlined inside the combined wrapper file
            # (Step 3/4). The ``skip_suffixes`` tuple controls which type-name
            # endings cause a definition to be skipped during this pass.
            # ------------------------------------------------------------------
            skip_suffixes: tuple[str, ...] = ()
            if subdir == "srv":
                skip_suffixes = SRV_SUFFIXES
            elif subdir == "action":
                skip_suffixes = ACTION_SUFFIXES

            # For each definition, emit a dedicated ``_.py`` (and ``_.pyi``) module,
            # **unless** it is a service/action sub-type that will be inlined in
            # the wrapper file (see skip_suffixes above).
            for defn in defns:
                type_name = defn.type_name.split("/")[-1]
                snake_name = to_snake_case(type_name)
                defn_by_name[type_name] = defn
                type_names.append(type_name)

                if any(type_name.endswith(s) for s in skip_suffixes):
                    continue

                content = generate_message_module(
                    defn, root_package=root_package, distro=distro
                )
                files.append(
                    GeneratedFile(
                        sub_dir / f"_{snake_name}.py",
                        content,
                    )
                )

                stub = generate_stub_module(
                    defn, root_package=root_package, distro=distro
                )
                files.append(
                    GeneratedFile(
                        sub_dir / f"_{snake_name}.pyi",
                        stub,
                    )
                )

            # ------------------------------------------------------------------
            # Step 3: Generate combined service wrapper files (srv only)
            #
            # A single ``_foo.py`` file bundles the Foo class (the service
            # super-class) together with Foo_Request and Foo_Response. The
            # sub-types were *skipped* during individual generation above.
            # ------------------------------------------------------------------
            wrapper_names: list[str] = []
            if subdir == "srv":
                wrapper_names = generate_service_wrappers(
                    sub_dir,
                    defn_by_name,
                    type_names,
                    pkg,
                    files,
                    root_package=root_package,
                    distro=distro,
                )
                # Build type_to_file mapping: tells __init__.py that sub-types
                # like Foo_Request live in ``._foo`` instead of their own module.
                for w in wrapper_names:
                    snake = to_snake_case(w)
                    for s in SRV_SUFFIXES:
                        type_to_file[f"{w}{s}"] = f"_{snake}"
            # ------------------------------------------------------------------
            # Step 4: Generate combined action wrapper files (action only)
            #
            # Similar to services, a single ``_foo.py`` file contains the action
            # super-class, Goal / Result / Feedback, and the internal transport
            # types (FeedbackMessage, SendGoal_*, GetResult_*). Sub-types that
            # were skipped above are inlined here.
            # ------------------------------------------------------------------
            elif subdir == "action":
                wrapper_names = generate_action_wrappers(
                    sub_dir,
                    defn_by_name,
                    type_names,
                    pkg,
                    files,
                    root_package=root_package,
                    distro=distro,
                )
                for w in wrapper_names:
                    snake = to_snake_case(w)
                    for s in ACTION_SUFFIXES:
                        type_to_file[f"{w}{s}"] = f"_{snake}"

            # ------------------------------------------------------------------
            # Step 5: Determine which names to export in ``__init__.py``
            #
            # The export list differs by kind, reflecting ROS conventions:
            #   - msg  – export everything normally (all field types re-exported).
            #   - srv  – export all types (wrapper + sub-types like Foo_Request)
            #            so that users can ``from pkg.srv import Foo_Request``.
            #   - action – export only the wrapper class and the three user-facing
            #            sub-types (Goal, Result, Feedback). Internal transport
            #            types (_FeedbackMessage, _SendGoal_Request/Response,
            #            _GetResult_Request/Response) are deliberately excluded
            #            because users are not expected to construct them directly.
            # ------------------------------------------------------------------
            if subdir == "srv":
                all_names = type_names + wrapper_names
            elif subdir == "action":
                all_names = [
                    tn
                    for tn in type_names
                    if not tn.endswith("_FeedbackMessage")
                    and not tn.endswith("_SendGoal_Request")
                    and not tn.endswith("_SendGoal_Response")
                    and not tn.endswith("_GetResult_Request")
                    and not tn.endswith("_GetResult_Response")
                ] + wrapper_names
            else:
                all_names = type_names.copy()

            init_content = generate_init_module(
                pkg,
                subdir,
                all_names,
                root_package=root_package,
                type_to_file=type_to_file or None,
                distro=distro,
            )
            files.append(
                GeneratedFile(
                    sub_dir / "__init__.py",
                    init_content,
                )
            )

    # ------------------------------------------------------------------
    # Step 6: Assemble the runtime registry and root package init
    #
    # _REGISTRY_AST is a pre-built AST (from ._registry) containing the
    # get_type(), has_type(), iter_types(), get_service(), and get_action()
    # functions. We unparse it and prepend the license header, then append
    # a convenience import in the root __init__.py so these functions are
    # accessible at the package level.
    # ------------------------------------------------------------------
    # Insert metadata after imports in the registry AST
    body = list(REGISTRY_AST.body)
    meta_stmts = generated_metadata_stmts()
    insert_pos = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, (ast.ImportFrom, ast.Import)):
            insert_pos = i + 1
    for i, s in enumerate(meta_stmts):
        body.insert(insert_pos + i, s)
    reg_ast = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(reg_ast)
    reg_body = ast.unparse(reg_ast)
    registry_content = header_comment(reg_body, distro=distro) + reg_body
    files.append(GeneratedFile(output_dir / "_registry.py", registry_content))

    # -- Root __init__.py (exposes registry functions at the package root) --
    _update_root_init(files, output_dir, distro=distro)

    return files


def _update_root_init(
    files: list[GeneratedFile],
    output_dir: pathlib.Path,
    distro: str = "",
) -> None:
    """Add or update the root ``__init__.py`` to re-export ``_registry``."""
    root_init = output_dir / "__init__.py"
    imp = "from ._registry import has_type, get_type, get_service, get_action, iter_types  # noqa: F401"
    # Find existing root __init__ (if any), or create a placeholder
    for i, f in enumerate(files):
        if f.path == root_init:
            # Already have one — append the registry import if missing.
            if imp not in f.content:
                files[i] = GeneratedFile(f.path, f.content + f"\n{imp}\n")
            return

    # Create a minimal root __init__ that imports the registry.
    # Include a package docstring so the module is self-describing.
    package_name = output_dir.name
    meta = ast.unparse(
        ast.fix_missing_locations(
            ast.Module(body=generated_metadata_stmts(), type_ignores=[])
        )
    ).strip()
    docstring = f'"""Package: {package_name}."""'
    body_content = f"{docstring}\n{imp}\n{meta}\n"
    content = header_comment(body_content, distro=distro) + body_content
    files.append(GeneratedFile(root_init, content))


__all__ = [
    "generate_all",
]
