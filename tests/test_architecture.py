"""Import-direction guardrails for the generator package.

The generator has a deliberately one-way dependency chain::

    parsing -> semantics -> codegen -> pipeline

This test parses imports (rather than importing modules) so violations are
reported with file/line context and do not depend on import side effects.
"""

import ast
import pathlib

GENERATOR = pathlib.Path(__file__).resolve().parents[1] / "src/zros2/generator"
PACKAGE_ROOT = "zros2.generator"


def _module_name(path: pathlib.Path) -> str:
    return ".".join(path.relative_to(GENERATOR.parents[1]).with_suffix("").parts)


def _import_targets(path: pathlib.Path, node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.level == 0:
        return [node.module] if node.module else []
    package = _module_name(path).split(".")[:-1]
    trim = node.level - 1
    if trim > len(package):
        return []
    base = package[: len(package) - trim]
    if node.module:
        base = [*base, *node.module.split(".")]
    return [".".join(base)]


def _layer(path: pathlib.Path) -> str:
    return path.relative_to(GENERATOR).parts[0]


def test_generator_import_direction() -> None:
    violations: list[str] = []
    for path in sorted(GENERATOR.rglob("*.py")):
        layer = _layer(path)
        module = _module_name(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in _import_targets(path, node):
                if layer == "parsing" and target.startswith(
                    (
                        f"{PACKAGE_ROOT}.semantics",
                        f"{PACKAGE_ROOT}.codegen",
                        f"{PACKAGE_ROOT}.pipeline",
                    )
                ):
                    violations.append(f"{module}:{node.lineno}: {target}")
                elif layer == "semantics" and target.startswith(
                    (f"{PACKAGE_ROOT}.codegen", f"{PACKAGE_ROOT}.pipeline")
                ):
                    violations.append(f"{module}:{node.lineno}: {target}")
                elif layer == "semantics" and target == "ast":
                    violations.append(f"{module}:{node.lineno}: semantics must not import ast")
                elif layer == "codegen" and target.startswith(f"{PACKAGE_ROOT}.pipeline"):
                    violations.append(f"{module}:{node.lineno}: {target}")
                elif (
                    path.name == "_stubs.py"
                    and target == f"{PACKAGE_ROOT}.codegen._message"
                ):
                    violations.append(
                        f"{module}:{node.lineno}: stubs must not import message private helpers"
                    )

    assert not violations, "generator import-direction violations:\n" + "\n".join(
        violations
    )


RUNTIME = GENERATOR.parent


def _runtime_layer(path: pathlib.Path) -> str:
    return path.relative_to(RUNTIME).parts[0]


def _runtime_targets(path: pathlib.Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for target in _import_targets(path, node):
            if target.startswith("zros2"):
                result.append((node.lineno, target))
    return result


def test_runtime_import_layers() -> None:
    """Runtime packages must only depend on lower-level building blocks."""
    rules = {
        "types": (
            "zros2.asyncio",
            "zros2.endpoints",
            "zros2.discovery",
            "zros2._client",
            "zros2._action_msgs",
        ),
        "discovery": ("zros2.asyncio", "zros2.endpoints", "zros2._client"),
        "endpoints": ("zros2.asyncio", "zros2.discovery", "zros2._client"),
        "_action_msgs": (
            "zros2.asyncio",
            "zros2.endpoints",
            "zros2.discovery",
            "zros2._client",
        ),
        "exceptions": ("zros2.",),
        "_namespace": ("zros2.",),
        "_session": ("zros2.",),
    }
    violations: list[str] = []
    for path in sorted(RUNTIME.rglob("*.py")):
        layer = _runtime_layer(path)
        if layer in ("generator", "asyncio") or path.name == "__init__.py":
            continue
        if layer not in rules:
            continue
        for line, target in _runtime_targets(path):
            if target == f"zros2.{layer}" or target.startswith(f"zros2.{layer}."):
                continue
            if any(target.startswith(prefix) for prefix in rules[layer]):
                violations.append(f"{path.relative_to(RUNTIME)}:{line}: {target}")

    assert not violations, "runtime import-direction violations:\n" + "\n".join(
        violations
    )


def test_no_parent_relative_imports() -> None:
    """Only same-package (``from .x``) relative imports are allowed."""
    violations: list[str] = []
    for path in sorted(RUNTIME.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level >= 2:
                violations.append(
                    f"{path.relative_to(RUNTIME)}:{node.lineno}: {ast.unparse(node)}"
                )
    assert not violations, "parent-relative imports are forbidden:\n" + "\n".join(
        violations
    )


def test_merge_engine_has_no_renderer_dependency() -> None:
    """The generic merger must not import message/stub renderers."""
    path = GENERATOR / "codegen/_merge.py"
    forbidden = (
        "zros2.generator.codegen._message",
        "zros2.generator.codegen._stubs",
    )
    violations = [
        f"{path.relative_to(GENERATOR.parents[1])}:{line}: {target}"
        for line, target in _runtime_targets(path)
        if target.startswith(forbidden)
    ]
    assert not violations, "merge engine renderer dependency:\n" + "\n".join(violations)
