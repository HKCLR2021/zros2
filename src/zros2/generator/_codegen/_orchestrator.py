"""Generator orchestration — collects types, validates, batches, writes."""

import ast
import pathlib
import re

from .._parser import (
    MsgDefinition,
    iter_msg_files,
    iter_srv_files,
    iter_action_files,
    parse_msg_file,
    parse_srv_file,
    parse_action_file,
    ROS2_PRIMITIVE_TYPES,
)
from .._utilities import _generated_metadata_stmts, _header_comment, _to_snake_case
from ._msg import generate_message_module, GeneratedFile
from ._pyi import generate_stub_module
from ._init import generate_init_module, generate_package_init
from ._srv_action import (
    _generate_service_wrappers,
    _generate_action_wrappers,
    _SRV_SUFFIXES,
    _ACTION_SUFFIXES,
)
from ._registry import _REGISTRY_AST

# -- Builtin message discovery --

BUILTIN_MSG_DIR = pathlib.Path(__file__).resolve().parent.parent / "builtin_msgs"

DISTRO_MAP: dict[str, str] = {
    "humble": "humble",
    "iron": "iron",
    "jazzy": "jazzy",
    "kilted": "kilted",
    "lyrical": "lyrical",
}

VALID_DISTROS: tuple[str, ...] = tuple(DISTRO_MAP)


def builtin_msg_dirs(distro: str) -> list[pathlib.Path]:
    """Return the package directories for a given ROS 2 distro's builtin types."""
    if distro not in DISTRO_MAP:
        return []
    distro_dir = BUILTIN_MSG_DIR / DISTRO_MAP[distro]
    if not distro_dir.is_dir():
        return []
    return sorted(distro_dir.iterdir())


# -- Dependency validation --


def _strip_wrappers(raw: str) -> str:
    """Strip array/sequence/bounded_str wrappers to get the inner type name."""
    m = re.match(r"^(\w[\w/]*)\[\d*\]$", raw)
    if m:
        return m.group(1)
    m = re.match(r"^(\w[\w/]*)\[\]$", raw)
    if m:
        return m.group(1)
    m = re.match(r"^sequence<(\w[\w/]*)", raw)
    if m:
        return m.group(1)
    m = re.match(r"^string<=?\d+$", raw)
    if m:
        return "string"
    return raw


def _resolve_full_name(raw_type: str, current_package: str) -> str:
    """Resolve a raw type string to a fully qualified ``package/msg/TypeName``."""
    base = _strip_wrappers(raw_type.strip())
    if not base:
        return ""
    if base in ROS2_PRIMITIVE_TYPES or base in (
        "bool", "str", "int", "float", "time", "duration",
    ):
        return ""
    if "/msg/" in base or "/srv/" in base or "/action/" in base:
        return base
    if "/" not in base:
        return f"{current_package}/msg/{base}"
    if base.count("/") == 1:
        pkg, name = base.split("/", 1)
        return f"{pkg}/msg/{name}"
    return base


def validate_dependencies(types: dict[str, MsgDefinition]) -> None:
    """Check that every non-primitive type reference in *types* exists.

    Raises:
        ValueError: With a message listing every missing dependency.
    """
    missing: list[tuple[str, str, str]] = []
    for name, defn in types.items():
        for field in defn.fields:
            full = _resolve_full_name(field.type_str, defn.package)
            if not full:
                continue
            if full not in types:
                missing.append((name, field.name, full))
    if missing:
        lines = [
            f"  {owner}: field '{field}' -> {typ}"
            for owner, field, typ in missing
        ]
        msg = (
            "Missing type dependencies -- make sure all required packages\n"
            "are included in --msg-dirs or are part of the selected ROS 2 "
            "distro:\n\n"
            + "\n".join(lines)
        )
        raise ValueError(msg)


# -- Type collection --


def collect_all_types(
    msg_dirs: list[pathlib.Path],
) -> dict[str, MsgDefinition]:
    """Scan directories for all .msg, .srv, .action files and parse them."""
    types: dict[str, MsgDefinition] = {}

    for pkg_dir in msg_dirs:
        package = pkg_dir.name

        # -- Messages --
        msg_dir = pkg_dir / "msg"
        for _, file_path in iter_msg_files(msg_dir):
            defn = parse_msg_file(file_path, package)
            types[defn.full_name] = defn

        # -- Services --
        srv_dir = pkg_dir / "srv"
        for _, file_path in iter_srv_files(srv_dir):
            request, response = parse_srv_file(file_path, package)
            types[request.full_name] = request
            types[response.full_name] = response

        # -- Actions --
        action_dir = pkg_dir / "action"
        for _, file_path in iter_action_files(action_dir):
            for defn in parse_action_file(file_path, package):
                types[defn.full_name] = defn

    return types


# -- Batch generation --


def _update_root_init(files: list[GeneratedFile], output_dir: pathlib.Path,
                     distro: str = "") -> None:
    """Inject ``get_type`` / ``has_type`` / ``iter_types`` into the root ``__init__.py``."""
    reg_import = ast.ImportFrom(
        module="._registry",
        names=[
            ast.alias(name="get_type"),
            ast.alias(name="has_type"),
            ast.alias(name="iter_types"),
            ast.alias(name="get_service"),
            ast.alias(name="get_action"),
        ],
        level=0,
    )
    init_path = output_dir / "__init__.py"
    for gf in files:
        if gf.path == init_path:
            # Preserve the header comment block (ast.parse discards comments).
            parts = gf.content.split("\n\n", 1)
            header_block = parts[0] if len(parts) > 1 else ""

            tree = ast.parse(gf.content)
            has_reg = any(
                isinstance(stmt, ast.ImportFrom)
                and stmt.module == "._registry"
                for stmt in tree.body
            )
            if not has_reg:
                tree.body.insert(0, reg_import)
                # Insert metadata after imports, before other statements
                meta_stmts = _generated_metadata_stmts()
                # Find first non-import position
                insert_pos = 1  # after reg_import
                while insert_pos < len(tree.body) and isinstance(
                    tree.body[insert_pos], (ast.ImportFrom, ast.Import)
                ):
                    insert_pos += 1
                for i, s in enumerate(meta_stmts):
                    tree.body.insert(insert_pos + i, s)
                ast.fix_missing_locations(tree)
                new_content = ast.unparse(tree)
                if header_block:
                    new_content = header_block + "\n\n" + new_content
                idx = files.index(gf)
                files[idx] = GeneratedFile(init_path, new_content)
            return
    module = ast.fix_missing_locations(ast.Module(
        body=[
            ast.Expr(value=ast.Constant(
                value=f"Package: {output_dir.name}.",
            )),
            reg_import,
        ]
        + _generated_metadata_stmts(),
        type_ignores=[],
    ))
    init_content = ast.unparse(module)
    files.append(GeneratedFile(
        init_path,
        _header_comment(init_content, distro=distro) + init_content,
    ))


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
                skip_suffixes = _SRV_SUFFIXES
            elif subdir == "action":
                skip_suffixes = _ACTION_SUFFIXES

            # For each definition, emit a dedicated ``_.py`` (and ``_.pyi``) module,
            # **unless** it is a service/action sub-type that will be inlined in
            # the wrapper file (see skip_suffixes above).
            for defn in defns:
                type_name = defn.type_name.split("/")[-1]
                snake_name = _to_snake_case(type_name)
                defn_by_name[type_name] = defn
                type_names.append(type_name)

                if any(type_name.endswith(s) for s in skip_suffixes):
                    continue

                content = generate_message_module(defn, root_package=root_package, distro=distro)
                files.append(GeneratedFile(
                    sub_dir / f"_{snake_name}.py", content,
                ))

                stub = generate_stub_module(defn, root_package=root_package, distro=distro)
                files.append(GeneratedFile(
                    sub_dir / f"_{snake_name}.pyi", stub,
                ))

            # ------------------------------------------------------------------
            # Step 3: Generate combined service wrapper files (srv only)
            #
            # A single ``_foo.py`` file bundles the Foo class (the service
            # super-class) together with Foo_Request and Foo_Response. The
            # sub-types were *skipped* during individual generation above.
            # ------------------------------------------------------------------
            wrapper_names: list[str] = []
            if subdir == "srv":
                wrapper_names = _generate_service_wrappers(
                    sub_dir, defn_by_name, type_names, pkg, files,
                    root_package=root_package,
                    distro=distro,
                )
                # Build type_to_file mapping: tells __init__.py that sub-types
                # like Foo_Request live in ``._foo`` instead of their own module.
                for w in wrapper_names:
                    snake = _to_snake_case(w)
                    for s in _SRV_SUFFIXES:
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
                wrapper_names = _generate_action_wrappers(
                    sub_dir, defn_by_name, type_names, pkg, files,
                    root_package=root_package,
                    distro=distro,
                )
                for w in wrapper_names:
                    snake = _to_snake_case(w)
                    for s in _ACTION_SUFFIXES:
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
                    tn for tn in type_names
                    if not tn.endswith("_FeedbackMessage")
                    and not tn.endswith("_SendGoal_Request")
                    and not tn.endswith("_SendGoal_Response")
                    and not tn.endswith("_GetResult_Request")
                    and not tn.endswith("_GetResult_Response")
                ] + wrapper_names
            else:
                all_names = type_names.copy()

            init_content = generate_init_module(
                pkg, subdir, all_names,
                root_package=root_package,
                type_to_file=type_to_file or None,
                distro=distro,
            )
            files.append(GeneratedFile(
                sub_dir / "__init__.py", init_content,
            ))

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
    body = list(_REGISTRY_AST.body)
    meta_stmts = _generated_metadata_stmts()
    insert_pos = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, (ast.ImportFrom, ast.Import)):
            insert_pos = i + 1
    for i, s in enumerate(meta_stmts):
        body.insert(insert_pos + i, s)
    reg_ast = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(reg_ast)
    reg_body = ast.unparse(reg_ast)
    registry_content = _header_comment(reg_body, distro=distro) + reg_body
    files.append(GeneratedFile(output_dir / "_registry.py", registry_content))

    # -- Root __init__.py (exposes registry functions at the package root) --
    _update_root_init(files, output_dir, distro=distro)

    return files


# -- File writer --


def write_generated_files(files: list[GeneratedFile]) -> list[pathlib.Path]:
    """Write generated files to disk, creating parent directories as needed."""
    written: list[pathlib.Path] = []
    for gf in files:
        gf.path.parent.mkdir(parents=True, exist_ok=True)
        gf.path.write_text(gf.content.lstrip("\n"), encoding="utf-8")
        written.append(gf.path)
    return written
