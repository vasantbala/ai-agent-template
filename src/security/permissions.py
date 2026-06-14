from __future__ import annotations


class ToolPermissionError(Exception):
    pass


class ToolPermissionGuard:
    def __init__(self, allowed_tools: list[str]) -> None:
        self._allowed = set(allowed_tools)  # empty set = allow all

    def check(self, tool_name: str) -> None:
        if self._allowed and tool_name not in self._allowed:
            raise ToolPermissionError(
                f"Tool '{tool_name}' is not permitted; allowed: {sorted(self._allowed)}"
            )
