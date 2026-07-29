"""Generator orchestration pipeline."""

from ..assets import BUILTIN_MSG_DIR
from ..parsing.discovery import (
    VALID_DISTROS,
    builtin_msg_dirs,
    collect_all_types,
    validate_dependencies,
)
from .generate import generate_all
from .plan import GenerationPlan, build_plan, execute_plan
from .writer import write_generated_files

__all__ = [
    "BUILTIN_MSG_DIR",
    "VALID_DISTROS",
    "GenerationPlan",
    "build_plan",
    "builtin_msg_dirs",
    "collect_all_types",
    "execute_plan",
    "generate_all",
    "validate_dependencies",
    "write_generated_files",
]
