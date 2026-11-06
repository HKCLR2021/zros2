"""Temporary script to inspect Annotated and UnionType behavior."""

from typing import Annotated, get_args, get_origin

# Check how Annotated args behave in this Python version
tp = Annotated[Annotated[int, "a"], "b"]
print("get_origin:", get_origin(tp))
print("get_args:", get_args(tp))

# Check UnionType origin
print("int | None origin:", get_origin(int | None))
print("int | None origin name:", get_origin(int | None).__name__)
print("int | None origin:", get_origin(int | None))
print("int | None origin name:", get_origin(int | None).__name__)
