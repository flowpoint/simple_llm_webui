from __future__ import annotations

from dataclasses import dataclass
import json
import re
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
        max_tokens: Optional[int] = None,
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
        if max_tokens:
            payload["max_tokens"] = max_tokens

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


def unpack_assistant_message(message: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
    """
    Normalise assistant payloads into readable text, reasoning snippets, and
    structured reasoning content emitted by llama.cpp.
    """
    reasoning_segments: List[str] = []
    text_segments: List[str] = []

    chain_pattern = re.compile(r"<(think|reasoning|thought)>(.*?)</\\1>", re.IGNORECASE | re.DOTALL)

    def strip_chain_markup(text: str) -> str:
        if not text:
            return ""

        def _capture(match: re.Match[str]) -> str:
            snippet = (match.group(2) or "").strip()
            if snippet:
                reasoning_segments.append(snippet)
            return ""

        cleaned = chain_pattern.sub(_capture, text)
        return cleaned

    def append_reasoning(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                reasoning_segments.append(cleaned)
            return
        if isinstance(value, dict):
            append_reasoning(value.get("text") or value.get("content"))
            return
        if isinstance(value, list):
            for item in value:
                append_reasoning(item)
            return
        reasoning_segments.append(str(value))

    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                cleaned = strip_chain_markup(str(block))
                if cleaned.strip():
                    text_segments.append(cleaned.strip())
                continue
            block_type = block.get("type")
            if block_type in {"reasoning", "analysis"}:
                append_reasoning(block.get("text") or block.get("content"))
            elif block_type == "text":
                cleaned = strip_chain_markup(block.get("text", ""))
                if cleaned.strip():
                    text_segments.append(cleaned.strip())
            elif block_type == "tool_call":
                # tool calls are handled separately by the worker
                continue
            else:
                cleaned = strip_chain_markup(json.dumps(block))
                if cleaned.strip():
                    text_segments.append(cleaned.strip())
    elif isinstance(content, str):
        cleaned = strip_chain_markup(content)
        if cleaned.strip():
            text_segments.append(cleaned.strip())
    elif content is None:
        pass
    else:
        cleaned = strip_chain_markup(json.dumps(content))
        if cleaned.strip():
            text_segments.append(cleaned.strip())

    # Some llama.cpp variants return a dedicated 'reasoning' field.
    reasoning_field = message.get("reasoning")
    append_reasoning(reasoning_field)

    def normalise_reasoning_content(value: Any) -> List[str]:
        normalised: List[str] = []

        def _collect(item: Any) -> None:
            if item is None:
                return
            if isinstance(item, str):
                text = item.strip()
                if text:
                    normalised.append(text)
                return
            if isinstance(item, dict):
                for key in ("text", "content", "message"):
                    if key in item:
                        _collect(item[key])
                        return
                try:
                    normalised.append(json.dumps(item, ensure_ascii=False))
                except TypeError:
                    normalised.append(str(item))
                return
            if isinstance(item, list):
                for sub in item:
                    _collect(sub)
                return
            normalised.append(str(item))

        _collect(value)
        return [entry for entry in normalised if entry.strip()]

    reasoning_content = normalise_reasoning_content(message.get("reasoning_content"))

    text = "\n".join(segment for segment in text_segments if segment)
    reasoning_output = [segment.strip() for segment in reasoning_segments if segment and segment.strip()]
    return text.strip(), reasoning_output, reasoning_content


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
