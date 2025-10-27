from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests


class LlamaCppError(RuntimeError):
    """Raised when the llama.cpp backend returns an error or malformed response."""


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Any]

    def to_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """
    Registry of callable tools exposed to the language model.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], Any],
    ) -> None:
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def definitions(self) -> List[Dict[str, Any]]:
        return [tool.to_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        if name not in self._tools:
            raise LlamaCppError(f"Tool '{name}' is not registered.")
        return self._tools[name].handler(arguments)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._tools)


class LlamaCppClient:
    """
    Minimal HTTP client for llama.cpp's OpenAI-compatible chat endpoint.
    """

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url
        self.api_key = api_key

    def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.2,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice:
            payload["tool_choice"] = tool_choice

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = requests.post(
            self.base_url,
            headers=headers,
            data=json.dumps(payload),
            timeout=120,
        )
        if response.status_code >= 400:
            raise LlamaCppError(
                f"Llama.cpp returned {response.status_code}: {response.text}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise LlamaCppError("Failed to decode llama.cpp response as JSON.") from exc


def unpack_assistant_message(message: Dict[str, Any]) -> Tuple[str, List[str]]:
    """
    Normalise assistant payloads into readable text and reasoning snippets.
    """
    reasoning_segments: List[str] = []
    text_segments: List[str] = []

    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                text_segments.append(str(block))
                continue
            block_type = block.get("type")
            if block_type in {"reasoning", "analysis"}:
                reasoning_segments.append(str(block.get("text") or block.get("content") or ""))
            elif block_type == "text":
                text_segments.append(block.get("text", ""))
            elif block_type == "tool_call":
                # tool calls are handled separately by the worker
                continue
            else:
                text_segments.append(json.dumps(block))
    elif isinstance(content, str):
        text_segments.append(content)
    elif content is None:
        pass
    else:
        text_segments.append(json.dumps(content))

    # Some llama.cpp variants return a dedicated 'reasoning' field.
    reasoning_field = message.get("reasoning")
    if isinstance(reasoning_field, str) and reasoning_field.strip():
        reasoning_segments.append(reasoning_field)

    text = "\n".join(segment for segment in text_segments if segment)
    return text.strip(), [segment.strip() for segment in reasoning_segments if segment]


def register_default_tools(registry: ToolRegistry) -> None:
    """
    Register example tools that can be extended or replaced by contributors.
    """

    def ping_tool(_: Dict[str, Any]) -> Dict[str, str]:
        return {"status": "ok"}

    registry.register(
        name="ping",
        description="Returns a simple liveness response.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=ping_tool,
    )

    def extract_field(payload: Dict[str, Any]) -> Dict[str, Any]:
        source = payload.get("source", "")
        field = payload.get("field")
        if not isinstance(source, str):
            raise LlamaCppError("extract_field expects a string 'source'.")
        if not field:
            raise LlamaCppError("extract_field requires the 'field' argument.")
        result = {}
        for line in source.splitlines():
            if line.lower().startswith(str(field).lower()):
                result[field] = line.split(":", 1)[-1].strip()
                break
        return result or {field: None}

    registry.register(
        name="extract_field",
        description="Extract a field value from a multi-line string containing 'Field: value' entries.",
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "field": {"type": "string"},
            },
            "required": ["source", "field"],
        },
        handler=extract_field,
    )
