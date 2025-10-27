"""
Custom tool registry hook.

Define `register_tools(registry)` to add project-specific tools.
"""
from __future__ import annotations

from typing import Any, Dict

from app.llm import ToolRegistry


def register_tools(registry: ToolRegistry) -> None:
    """
    Register additional tools for llama.cpp to invoke.

    Add your custom logic here. This default implementation is a placeholder
    that demonstrates how to integrate with the registry.
    """

    def noop(_: Dict[str, Any]) -> Dict[str, str]:
        return {"message": "No custom tools registered yet."}

    registry.register(
        name="noop",
        description="Default placeholder tool that confirms the plumbing works.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=noop,
    )
