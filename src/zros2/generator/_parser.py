"""ROS 2 .msg / .srv / .action file parser.

Line-oriented, **zero-regex** parser built on string methods + Lark for type
expressions.  Handles every syntax form described in the ROS 2 interface
definition spec.
"""

import pathlib
from dataclasses import dataclass, field
from typing import Iterator

from lark import LarkError

from ._type_grammar import ROS2_PRIMITIVE_TYPES, parse_type


# ═══════════════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class MsgField:
    """A single field or constant in a ROS 2 message definition."""

    name: str
    type_str: str          # Raw type as written in the .msg file
    default: str | None = None
    is_constant: bool = False


@dataclass
class MsgDefinition:
    """A parsed ROS 2 message/service/action section."""

    package: str
    type_name: str
    type_kind: str         # "msg", "srv", or "action"
    fields: list[MsgField] = field(default_factory=list)
    constants: list[MsgField] = field(default_factory=list)
    full_name: str = ""

    def __post_init__(self) -> None:
        if not self.full_name:
            self.full_name = f"{self.package}/{self.type_kind}/{self.type_name}"


# ═══════════════════════════════════════════════════════════════════════════
# Inline comment stripping
# ═══════════════════════════════════════════════════════════════════════════

def _strip_inline_comment(line: str) -> str:
    """Strip a trailing ``#`` comment from *line*.

    Respects single- and double-quoted strings (including ``\\``-escaped
    quotes), so comments inside string literals are NOT stripped.

    Returns the cleaned line (right-stripped).  If the line becomes empty
    after stripping, returns ``""``.
    """
    out: list[str] = []
    i = 0
    in_sq = False   # inside single quote
    in_dq = False   # inside double quote
    escape = False

    while i < len(line):
        ch = line[i]

        if escape:
            out.append(ch)
            escape = False
            i += 1
            continue

        if ch == "\\":
            out.append(ch)
            escape = True
            i += 1
            continue

        if ch == '"' and not in_sq:
            in_dq = not in_dq
            out.append(ch)
            i += 1
            continue

        if ch == "'" and not in_dq:
            in_sq = not in_sq
            out.append(ch)
            i += 1
            continue

        if ch == "#" and not in_sq and not in_dq:
            break   # start of comment — discard rest of line

        out.append(ch)
        i += 1

    return "".join(out).rstrip()


# ═══════════════════════════════════════════════════════════════════════════
# Name validation
# ═══════════════════════════════════════════════════════════════════════════

_PYTHON_KEYWORDS: frozenset[str] = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
})


def _is_valid_field_name(name: str) -> bool:
    """Validate a ROS 2 field name per the interface spec.

    Rules (from the ROS 2 documentation):

    * start with an alphabetic character (not underscore)
    * only lowercase alphanumeric + underscore
    * no trailing underscore
    * no consecutive underscores (``__``)
    * additionally, reject Python keywords so the generated code is valid.
    """
    if not name:
        return False
    if not name[0].isalpha():
        return False
    if name != name.lower():
        return False
    if name.endswith("_"):
        return False
    if "__" in name:
        return False
    if name in _PYTHON_KEYWORDS:
        return False
    for ch in name:
        if not (ch.isalnum() or ch == "_"):
            return False
    return True


def _is_valid_constant_name(name: str) -> bool:
    """Validate a ROS 2 constant name.

    Rules: UPPERCASE, start with alphabetic, contain only uppercase ASCII
    letters, digits and underscores.
    """
    if not name:
        return False
    if not name[0].isalpha():
        return False
    if name != name.upper():
        return False
    for ch in name:
        if not (ch.isupper() or ch.isdigit() or ch == "_"):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Line-level tokeniser
# ═══════════════════════════════════════════════════════════════════════════

def _tokenise_field_line(line: str) -> MsgField:
    """Parse a single non-comment, non-empty ``.msg`` line.

    Grammar for a line::

        field:    TYPE NAME [VALUE …]
        constant: TYPE NAME=VALUE

    Per the ROS 2 interface spec:

    * **Fields** use a space between the name and the default value.
    * **Constants** have ``=`` immediately after the name (no space before
      the ``=``).

    For real-world leniency, ``TYPE name = value`` is also accepted as a
    field with a default value (the ``=`` is simply stripped).

    Raises:
        ValueError: If the line cannot be parsed, with a message explaining
            why. This replaces the old silent-``None`` behaviour — an
            unparseable field line is always a user error.
    """
    stripped = line.lstrip()
    if not stripped:
        raise ValueError("empty line after stripping inline comment")

    # ── Type ──────────────────────────────────────────────────────────
    # Find the first whitespace to separate the type token.
    idx = stripped.find(" ")
    if idx < 0:
        raise ValueError(
            f"missing field name after type (line is just '{stripped}')"
        )
    raw_type = stripped[:idx]
    rest = stripped[idx:].strip()
    if not rest:
        raise ValueError(
            f"type '{raw_type}' is not followed by a field name"
        )

    # ── Validate type via Lark grammar ────────────────────────────────
    # (catches nonsense like "foo@bar" early)
    try:
        parse_type(raw_type)
    except LarkError as exc:
        raise ValueError(
            f"'{raw_type}' is not a valid ROS 2 type: {exc}"
        ) from exc

    # ── Constant detection ────────────────────────────────────────────
    # Syntax: NAME=value or NAME = value
    eq_idx = rest.find("=")
    if eq_idx >= 0:
        name = rest[:eq_idx].rstrip()
        value = rest[eq_idx + 1:].strip()
        # Valid constant: UPPERCASE name + primitive type
        if _is_valid_constant_name(name) and raw_type in ROS2_PRIMITIVE_TYPES:
            return MsgField(name=name, type_str=raw_type,
                            default=value, is_constant=True)
        # Not a valid constant (e.g. lowercase name like "string desc=---").
        # Treat as field with default =value (lenient parse).
        if _is_valid_field_name(name):
            return MsgField(name=name, type_str=raw_type,
                            default=value, is_constant=False)
        raise ValueError(
            f"'{name}' is not a valid field or constant name "
            f"(constants must be UPPER_CASE on primitive types; "
            f"fields must be lower_snake_case)"
        )

    # ── Field ─────────────────────────────────────────────────────────
    # Split on first space to separate name from optional default value.
    rest_parts = rest.split(maxsplit=1)
    name = rest_parts[0]

    if not _is_valid_field_name(name):
        raise ValueError(
            f"'{name}' is not a valid field name "
            f"(must start with a letter, be lower_snake_case, "
            f"no trailing/duplicate underscores, not a Python keyword)"
        )

    default: str | None = None
    if len(rest_parts) > 1:
        raw_default = rest_parts[1].strip()
        # Lenient: strip leading "=" (common practice: "name = value")
        if raw_default.startswith("= "):
            raw_default = raw_default[2:].strip()
        elif raw_default.startswith("="):
            raw_default = raw_default[1:].strip()
        default = raw_default if raw_default else None

    return MsgField(name=name, type_str=raw_type,
                    default=default, is_constant=False)


# ═══════════════════════════════════════════════════════════════════════════
# Section splitting (srv / action)
# ═══════════════════════════════════════════════════════════════════════════

def _split_sections(text: str, maxsplit: int = 1) -> list[str]:
    """Split *text* on ``---`` lines, returning at most *maxsplit*+1 sections.

    Only matches ``---`` when it appears on a line by itself (possibly
    surrounded by whitespace), which is the correct behaviour per the
    ROS 2 spec.
    """
    lines = text.splitlines(keepends=True)
    sections: list[str] = []
    current: list[str] = []
    count = 0

    for line in lines:
        if count < maxsplit and line.strip() == "---":
            sections.append("".join(current))
            current = []
            count += 1
        else:
            current.append(line)

    sections.append("".join(current))
    return sections


# ═══════════════════════════════════════════════════════════════════════════
# High-level parsers
# ═══════════════════════════════════════════════════════════════════════════

def parse_msg_text(text: str, *, package: str = "",
                   type_name: str = "", type_kind: str = "msg") -> MsgDefinition:
    """Parse a ROS 2 message definition string.

    Args:
        text: Raw ``.msg`` (or srv/action section) text.
        package: Package name.
        type_name: Message type name (file stem).
        type_kind: ``"msg"``, ``"srv"`` or ``"action"``.

    Returns:
        A ``MsgDefinition``.
    """
    defn = MsgDefinition(package=package, type_name=type_name,
                         type_kind=type_kind)

    lines = text.splitlines()
    for lineno, line in enumerate(lines, start=1):
        raw = line.strip()

        # Skip empty lines and full-line comments
        if not raw or raw.startswith("#"):
            continue

        # Strip inline comments
        clean = _strip_inline_comment(raw)
        if not clean:
            continue

        try:
            field = _tokenise_field_line(clean)
        except ValueError as exc:
            kind = {"msg": "message", "srv": "service",
                    "action": "action"}.get(type_kind, "message")
            raise ValueError(
                f"{kind} '{defn.full_name}' line {lineno}: {exc}"
            ) from exc

        if field.is_constant:
            defn.constants.append(field)
        else:
            defn.fields.append(field)

    return defn


def parse_msg_file(file_path: pathlib.Path, package: str) -> MsgDefinition:
    """Parse a single ``.msg`` file."""
    text = file_path.read_text(encoding="utf-8")
    try:
        return parse_msg_text(text, package=package,
                              type_name=file_path.stem, type_kind="msg")
    except ValueError as exc:
        raise ValueError(f"{file_path}: {exc}") from exc


def parse_srv_file(file_path: pathlib.Path,
                   package: str) -> tuple[MsgDefinition, MsgDefinition]:
    """Parse a single ``.srv`` file into request / response.

    Returns:
        ``(request, response)`` pair of ``MsgDefinition``.
    """
    text = file_path.read_text(encoding="utf-8")
    parts = _split_sections(text, maxsplit=1)

    if len(parts) < 2:
        raise ValueError(
            f"Invalid .srv file {file_path.name}: "
            f"missing '---' separator between request and response"
        )

    base_name = file_path.stem
    try:
        request = parse_msg_text(
            parts[0], package=package,
            type_name=f"{base_name}_Request", type_kind="srv",
        )
        response = parse_msg_text(
            parts[1], package=package,
            type_name=f"{base_name}_Response", type_kind="srv",
        )
    except ValueError as exc:
        raise ValueError(f"{file_path}: {exc}") from exc
    return request, response


def parse_action_file(file_path: pathlib.Path,
                      package: str) -> tuple[MsgDefinition, ...]:
    """Parse a single ``.action`` file.

    Returns **seven** ``MsgDefinition`` entries:

    ``(Goal, Result, SendGoal_Request, SendGoal_Response,
      GetResult_Request, GetResult_Response, Feedback)``
    """
    text = file_path.read_text(encoding="utf-8")
    parts = _split_sections(text, maxsplit=2)

    if len(parts) < 3:
        raise ValueError(
            f"Invalid .action file {file_path.name}: "
            f"expected two '---' separators (goal / result / feedback)"
        )

    goal_text, result_text, feedback_text = (
        p.strip() for p in parts
    )
    base_name = file_path.stem

    try:
        definitions = {
            f"{base_name}_Goal": parse_msg_text(
                goal_text, package=package,
                type_name=f"{base_name}_Goal", type_kind="action",
            ),
            f"{base_name}_Result": parse_msg_text(
                result_text, package=package,
                type_name=f"{base_name}_Result", type_kind="action",
            ),
            f"{base_name}_Feedback": parse_msg_text(
                feedback_text, package=package,
                type_name=f"{base_name}_Feedback", type_kind="action",
            ),
            # ── FeedbackMessage ───────────────────────────────────────────
            f"{base_name}_FeedbackMessage": parse_msg_text(
                f"uint8[16] goal_id\n"
                f"{package}/action/{base_name}_Feedback feedback",
                package=package,
                type_name=f"{base_name}_FeedbackMessage",
                type_kind="action",
            ),
            # ── SendGoal_Request ──────────────────────────────────────────
            f"{base_name}_SendGoal_Request": parse_msg_text(
                f"uint8[16] goal_id\n"
                f"{package}/action/{base_name}_Goal goal",
                package=package,
                type_name=f"{base_name}_SendGoal_Request",
                type_kind="action",
            ),
            # ── SendGoal_Response ─────────────────────────────────────────
            f"{base_name}_SendGoal_Response": parse_msg_text(
                "bool accepted\nbuiltin_interfaces/msg/Time stamp",
                package=package,
                type_name=f"{base_name}_SendGoal_Response",
                type_kind="action",
            ),
            # ── GetResult_Request ─────────────────────────────────────────
            f"{base_name}_GetResult_Request": parse_msg_text(
                "uint8[16] goal_id",
                package=package,
                type_name=f"{base_name}_GetResult_Request",
                type_kind="action",
            ),
            # ── GetResult_Response ────────────────────────────────────────
            f"{base_name}_GetResult_Response": parse_msg_text(
                f"int8 status\n"
                f"{package}/action/{base_name}_Result result",
                package=package,
                type_name=f"{base_name}_GetResult_Response",
                type_kind="action",
            ),
        }
    except ValueError as exc:
        raise ValueError(f"{file_path}: {exc}") from exc

    # Remap namespaces from /msg/ (default in parse_msg_text) to /action/
    for defn in definitions.values():
        defn.full_name = defn.full_name.replace("/msg/", "/action/")
        defn.type_kind = "action"

    return tuple(definitions.values())


# ═══════════════════════════════════════════════════════════════════════════
# Discovery helpers
# ═══════════════════════════════════════════════════════════════════════════

def iter_msg_files(msg_dir: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Yield ``(package_name, file_path)`` for every ``.msg`` file found."""
    if not msg_dir.is_dir():
        return
    package = msg_dir.parent.name if msg_dir.parent.name else msg_dir.name
    for path in sorted(msg_dir.glob("*.msg")):
        yield package, path


def iter_srv_files(srv_dir: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Yield ``(package_name, file_path)`` for every ``.srv`` file found."""
    if not srv_dir.is_dir():
        return
    package = srv_dir.parent.name if srv_dir.parent.name else srv_dir.name
    for path in sorted(srv_dir.glob("*.srv")):
        yield package, path


def iter_action_files(action_dir: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Yield ``(package_name, file_path)`` for every ``.action`` file found."""
    if not action_dir.is_dir():
        return
    package = action_dir.parent.name if action_dir.parent.name else action_dir.name
    for path in sorted(action_dir.glob("*.action")):
        yield package, path


def find_msg_dirs(base_paths: list[pathlib.Path]) -> list[pathlib.Path]:
    """Collect all existing ``msg/`` subdirectories from the given base paths."""
    dirs: list[pathlib.Path] = []
    for base in base_paths:
        if not base.is_dir():
            continue
        msg_dir = base / "msg"
        if msg_dir.is_dir():
            dirs.append(base)
        else:
            for pkg_dir in sorted(base.iterdir()):
                if pkg_dir.is_dir() and (pkg_dir / "msg").is_dir():
                    dirs.append(pkg_dir)
    return dirs
