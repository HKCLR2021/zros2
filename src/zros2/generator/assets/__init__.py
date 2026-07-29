"""Bundled generator assets."""

from pathlib import Path

BUILTIN_MSG_DIR = Path(__file__).resolve().parent / "builtin_msgs"

__all__ = ["BUILTIN_MSG_DIR"]
