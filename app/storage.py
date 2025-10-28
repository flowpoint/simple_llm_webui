from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from uuid import uuid4

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def utcnow() -> str:
    return datetime.utcnow().strftime(ISO_FORMAT)


def _append_jsonl(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


def _iter_jsonl(path: Path) -> Iterable[Dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


@dataclass
class ConversationMetadata:
    conversation_id: str
    path: Path
    last_modified: datetime


class ConversationStore:
    """
    Append-only conversation store backed by JSONL files on disk.
    """

    def __init__(self, root: Path) -> None:
        self.root = root / "conversations"
        self.root.mkdir(parents=True, exist_ok=True)

    def create_conversation(
        self,
        *,
        agent: str,
        system_prompt: str,
        model: str,
        temperature: float,
        context_size: int,
    ) -> str:
        conversation_id = uuid4().hex
        path = self._conversation_path(conversation_id)
        metadata_entry = {
            "id": uuid4().hex,
            "timestamp": utcnow(),
            "role": "system",
            "type": "metadata",
            "content": {
                "agent": agent,
                "system_prompt": system_prompt,
                "model": model,
                "temperature": temperature,
                "context_size": context_size,
            },
        }
        _append_jsonl(path, metadata_entry)
        return conversation_id

    def _conversation_path(self, conversation_id: str) -> Path:
        return self.root / f"conversation_{conversation_id}.jsonl"

    def append_entry(self, conversation_id: str, entry: Dict) -> None:
        entry.setdefault("id", uuid4().hex)
        entry.setdefault("timestamp", utcnow())
        _append_jsonl(self._conversation_path(conversation_id), entry)

    def list_conversations(self) -> List[ConversationMetadata]:
        items: List[ConversationMetadata] = []
        for file in sorted(self.root.glob("conversation_*.jsonl")):
            try:
                conversation_id = file.stem.split("_", 1)[1]
            except IndexError:
                continue
            stat = file.stat()
            items.append(
                ConversationMetadata(
                    conversation_id=conversation_id,
                    path=file,
                    last_modified=datetime.utcfromtimestamp(stat.st_mtime),
                )
            )
        items.sort(key=lambda item: item.last_modified, reverse=True)
        return items

    def load_conversation(self, conversation_id: str) -> List[Dict]:
        path = self._conversation_path(conversation_id)
        return list(_iter_jsonl(path))

    def append_user_message(self, conversation_id: str, content: str) -> str:
        message_id = uuid4().hex
        entry = {
            "id": message_id,
            "timestamp": utcnow(),
            "role": "user",
            "type": "message",
            "content": content,
        }
        _append_jsonl(self._conversation_path(conversation_id), entry)
        return message_id

    def append_label(
        self,
        conversation_id: str,
        target_id: str,
        reward: int,
        target_type: str,
    ) -> None:
        entry = {
            "id": uuid4().hex,
            "timestamp": utcnow(),
            "role": "system",
            "type": "label",
            "content": {
                "target": target_id,
                "target_type": target_type,
                "reward": reward,
            },
        }
        _append_jsonl(self._conversation_path(conversation_id), entry)

    def last_message_timestamp(self, conversation_id: str) -> Optional[datetime]:
        messages = self.load_conversation(conversation_id)
        for entry in reversed(messages):
            if entry["type"] in {"message", "tool_call", "tool_result", "reasoning"}:
                return datetime.strptime(entry["timestamp"], ISO_FORMAT)
        return None


class IndexStore:
    """
    Append-only index of conversation summaries and access metadata.

    When the file grows beyond `max_lines`, it is deduplicated and atomically rewritten.
    """

    def __init__(self, root: Path, max_lines: int = 16384) -> None:
        self.path = root / "index.jsonl"
        self.max_lines = max_lines
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._line_count = self._count_lines()

    def _count_lines(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as handle:
            return sum(1 for _ in handle)

    def append(self, payload: Dict) -> None:
        payload.setdefault("timestamp", utcnow())
        _append_jsonl(self.path, payload)
        self._line_count += 1
        if self._line_count > self.max_lines:
            self.prune()

    def latest_index(self) -> Dict[str, Dict]:
        latest: Dict[str, Dict] = {}
        for entry in _iter_jsonl(self.path):
            cid = entry.get("conversation_id")
            if not cid:
                continue
            record = latest.get(cid, {"conversation_id": cid})
            # Merge newer fields while retaining previous summary/title if omitted.
            for key, value in entry.items():
                if key in {"conversation_id"}:
                    continue
                record[key] = value
            record["timestamp"] = entry.get("timestamp", record.get("timestamp"))
            latest[cid] = record
        return latest

    def record_access(self, conversation_id: str) -> None:
        self.append(
            {
                "conversation_id": conversation_id,
                "kind": "access",
                "last_accessed": utcnow(),
            }
        )

    def record_summary(
        self,
        conversation_id: str,
        summary: str,
        title: str,
        last_accessed: Optional[str] = None,
    ) -> None:
        payload = {
            "conversation_id": conversation_id,
            "kind": "summary",
            "summary": summary,
            "title": title,
            "last_accessed": last_accessed or utcnow(),
        }
        self.append(payload)

    def prune(self) -> None:
        latest = self.latest_index()
        tmp_path = self.path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            for entry in latest.values():
                handle.write(json.dumps(entry))
                handle.write("\n")
        os.replace(tmp_path, self.path)
        self._line_count = len(latest)


def build_title(summary: Optional[str], fallback: str) -> str:
    if summary:
        return summary
    snippet = fallback.strip().splitlines()[0]
    return snippet[:80] + ("…" if len(snippet) > 80 else "")
