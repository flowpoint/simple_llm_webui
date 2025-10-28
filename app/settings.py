import json
from pathlib import Path
from typing import Any, Dict


DEFAULT_SETTINGS: Dict[str, Any] = {
    "system_prompt": "You are a helpful assistant.",
    "llama_cpp": {
        "base_url": "http://localhost:8080/v1/chat/completions",
        "api_key": "",
        "model": "ggml-model-q4",
    },
    "agents": [
        {
            "name": "General Assistant",
            "description": "Default helper for broad tasks.",
            "system_prompt": "You are a general purpose assistant.",
            "model": "ggml-model-q4",
            "temperature": 0.2,
            "context_size": 4096,
        },
        {
            "name": "Researcher",
            "description": "Summarise findings concisely with citations when possible.",
            "system_prompt": "You are a research assistant who cites credible evidence briefly.",
            "model": "ggml-model-q4",
            "temperature": 0.2,
            "context_size": 4096,
        },
        {
            "name": "Debugger",
            "description": "Diagnose and fix software issues step by step.",
            "system_prompt": "You analyse logs and code to find defects and explain fixes.",
            "model": "ggml-model-q4",
            "temperature": 0.2,
            "context_size": 4096,
        },
        {
            "name": "Creative Writer",
            "description": "Produce imaginative prose or dialogue with vivid details.",
            "system_prompt": "You craft creative writing with strong imagery and pacing.",
            "model": "ggml-model-q4",
            "temperature": 0.2,
            "context_size": 4096,
        },
    ],
}


class SettingsManager:
    """
    Handles loading and persisting the editable configuration file.

    The file is stored as pretty-printed JSON so contributors can edit it by hand.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._settings: Dict[str, Any] | None = None
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def settings(self) -> Dict[str, Any]:
        if self._settings is None:
            self._settings = self._load_from_disk()
        return self._settings

    def _load_from_disk(self) -> Dict[str, Any]:
        if not self.path.exists():
            self._write(DEFAULT_SETTINGS)
            return json.loads(json.dumps(DEFAULT_SETTINGS))
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        # Merge with defaults to backfill new keys without overwriting manual edits.
        merged = json.loads(json.dumps(DEFAULT_SETTINGS))
        _deep_update(merged, data)
        return merged

    def save(self, payload: Dict[str, Any]) -> None:
        config = json.loads(json.dumps(self.settings))
        _deep_update(config, payload)
        self._write(config)
        self._settings = config

    def reload(self) -> Dict[str, Any]:
        self._settings = self._load_from_disk()
        return self._settings

    def _write(self, data: Dict[str, Any]) -> None:
        # Persist as stable, human-readable JSON.
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")


def _deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    """
    Recursively update a mapping, preserving nested structures.
    """
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
