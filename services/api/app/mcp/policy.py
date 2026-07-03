"""Safety classification for MCP tools with optional annotations."""

from __future__ import annotations


WRITE_MARKERS = (
    "create", "update", "delete", "remove", "lock", "book", "reserve",
    "send", "submit", "write", "upload", "cancel", "schedule", "set_",
)


def classify_tool(name: str, annotations: dict | None = None) -> tuple[bool, bool]:
    annotations = annotations or {}
    destructive = bool(annotations.get("destructiveHint", False))
    if "readOnlyHint" in annotations:
        read_only = bool(annotations["readOnlyHint"])
    else:
        lowered = name.casefold().split("__")[-1]
        read_only = not any(marker in lowered for marker in WRITE_MARKERS)
    return read_only, destructive or not read_only
