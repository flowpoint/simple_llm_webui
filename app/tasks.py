from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing as mp
import queue
import time
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from .llm import LlamaCppClient, LlamaCppError, ToolRegistry, register_default_tools, unpack_assistant_message
from .settings import SettingsManager
from .storage import ConversationStore, IndexStore, build_title, utcnow


PRIORITY_HIGH = 0
PRIORITY_NORMAL = 5
PRIORITY_LOW = 10

logger = logging.getLogger("webui.worker")


@dataclass
class TaskRecord:
    id: str
    kind: str
    conversation_id: Optional[str]
    priority: int
    status: str = "queued"
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    description: str = ""
    detail: Optional[str] = None
    agent: Optional[str] = None
    started_at: Optional[str] = None


def _ensure_jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if hasattr(value, "dict"):
            return value.dict()
        return str(value)


class TaskService:
    """
    Coordinates task submission and status tracking between the FastAPI app and the worker process.
    """

    def __init__(self, data_dir: Path, settings_path: Path) -> None:
        self.data_dir = data_dir
        self.settings_path = settings_path
        self.task_queue: mp.Queue = mp.Queue()
        self.event_queue: mp.Queue = mp.Queue()
        self._counter = count()
        self._process: Optional[mp.Process] = None
        self._tasks: Dict[str, TaskRecord] = {}
        self._needs_summary: Set[str] = set()
        self._lock = mp.Lock()

    def start(self) -> None:
        if self._process and self._process.is_alive():
            return
        logger.info("Starting worker process.")
        self._process = mp.Process(
            target=_worker_main,
            args=(
                self.task_queue,
                self.event_queue,
                str(self.data_dir),
                str(self.settings_path),
            ),
            daemon=True,
        )
        self._process.start()

    def stop(self) -> None:
        if not self._process:
            return
        logger.info("Stopping worker process.")
        self.enqueue_raw(
            kind="shutdown",
            priority=PRIORITY_HIGH,
            conversation_id=None,
            payload={},
            description="Shutdown worker.",
        )
        self._process.join(timeout=5)
        if self._process.is_alive():
            self._process.terminate()
        self._process = None

    def enqueue_completion(
        self,
        conversation_id: str,
        agent: str,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        context_size: Optional[int] = None,
    ) -> str:
        payload = {
            "agent": agent,
            "model": model,
            "temperature": temperature,
            "context_size": context_size,
        }
        return self.enqueue_raw(
            kind="completion",
            priority=PRIORITY_NORMAL,
            conversation_id=conversation_id,
            payload=payload,
            description=f"Generate reply ({agent}{f' · {model}' if model else ''})",
            agent=agent,
        )

    def enqueue_summary(self, conversation_id: str, priority: int = PRIORITY_LOW) -> Optional[str]:
        if conversation_id in self._needs_summary:
            self._needs_summary.remove(conversation_id)
        return self.enqueue_raw(
            kind="summarize",
            priority=priority,
            conversation_id=conversation_id,
            payload={},
            description="Refresh summary",
        )

    def enqueue_raw(
        self,
        *,
        kind: str,
        priority: int,
        conversation_id: Optional[str],
        payload: Dict[str, Any],
        description: str,
        agent: Optional[str] = None,
    ) -> str:
        self.start()
        task_id = uuid4().hex
        created = utcnow()
        record = TaskRecord(
            id=task_id,
            kind=kind,
            conversation_id=conversation_id,
            priority=priority,
            created_at=created,
            updated_at=created,
            description=description,
            agent=agent,
        )
        self._tasks[task_id] = record
        order = next(self._counter)
        queue_payload = {
            "task_id": task_id,
            "kind": kind,
            "conversation_id": conversation_id,
            "payload": payload,
        }
        self.task_queue.put((priority, order, queue_payload))
        logger.debug(
            "Enqueued task %s (kind=%s conversation=%s priority=%s)",
            task_id,
            kind,
            conversation_id,
            priority,
        )
        return task_id

    def mark_summary_needed(self, conversation_id: str) -> None:
        self._needs_summary.add(conversation_id)

    def pending_summary_ids(self) -> Set[str]:
        return set(self._needs_summary)

    def drain_events(self) -> None:
        processed = 0
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            processed += 1
            task_id = event.get("task_id")
            if task_id not in self._tasks:
                continue
            record = self._tasks[task_id]
            status = event.get("status", record.status)
            timestamp = event.get("timestamp", utcnow())
            if status == "running" and record.started_at is None:
                record.started_at = timestamp
            record.status = status
            record.updated_at = timestamp
            record.detail = event.get("message")
            extra = event.get("data") or {}
            if extra.get("requires_summary") and record.conversation_id:
                self.mark_summary_needed(record.conversation_id)
        # Drop completed tasks after a while to keep the queue compact.
        if processed:
            self._trim_completed_tasks()
            self.prune(max_items=20)

    def prune(self, max_items: int) -> None:
        if len(self._tasks) <= max_items:
            return
        # Retain newest tasks by updated_at.
        ordered = sorted(
            self._tasks.values(),
            key=lambda record: record.updated_at,
            reverse=True,
        )
        keep = {record.id for record in ordered[:max_items]}
        self._tasks = {task_id: self._tasks[task_id] for task_id in keep}

    def snapshot(self) -> List[TaskRecord]:
        self._trim_completed_tasks()
        return sorted(
            self._tasks.values(),
            key=lambda record: (
                record.status == "completed",
                record.priority,
                record.updated_at,
            ),
        )

    def worker_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def _trim_completed_tasks(self) -> None:
        failed_ids = [
            task.id for task in self._tasks.values() if task.status == "failed"
        ]
        for task_id in failed_ids:
            self._tasks.pop(task_id, None)
        completed = [
            task for task in self._tasks.values() if task.status == "completed"
        ]
        completed.sort(key=lambda record: record.updated_at, reverse=True)
        for task in completed[2:]:
            self._tasks.pop(task.id, None)


class IdleMonitor:
    """
    Tracks local activity and invokes callbacks when the app enters or leaves the idle window.
    """

    def __init__(self, timeout_seconds: float = 30.0) -> None:
        self.timeout = timeout_seconds
        self._last_activity = time.monotonic()
        self._idle = False

    @property
    def idle(self) -> bool:
        return self._idle

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    async def loop(
        self,
        on_idle: Callable[[], None],
        on_active: Callable[[], None],
        interval: float = 5.0,
    ) -> None:
        while True:
            await asyncio.sleep(interval)
            if time.monotonic() - self._last_activity > self.timeout:
                if not self._idle:
                    self._idle = True
                    on_idle()
            else:
                if self._idle:
                    self._idle = False
                    on_active()


def _worker_main(
    task_queue: mp.Queue,
    event_queue: mp.Queue,
    data_dir: str,
    settings_path: str,
) -> None:
    data_root = Path(data_dir)
    settings_manager = SettingsManager(Path(settings_path))
    conversation_store = ConversationStore(data_root)
    index_store = IndexStore(data_root)
    registry = ToolRegistry()
    register_default_tools(registry)
    try:
        # Optional user extension hook.
        from tools import register_tools  # type: ignore
    except ImportError:
        register_tools = None

    if callable(register_tools):
        try:
            register_tools(registry)
        except Exception as err:  # pragma: no cover - user-defined
            _post_event(
                event_queue,
                "bootstrap",
                "failed",
                f"Custom tool registration failed: {err}",
            )
            logger.exception("Custom tool registration failed.")

    llama_client: Optional[LlamaCppClient] = None
    logger.info("Worker online. Registered tools: %d", len(registry.definitions()))

    while True:
        priority, _, payload = task_queue.get()
        kind = payload.get("kind")
        if kind == "shutdown":
            logger.info("Worker received shutdown signal.")
            break
        task_id = payload.get("task_id")
        conversation_id = payload.get("conversation_id")
        task_payload = payload.get("payload") or {}
        _post_event(event_queue, task_id, "running", "Task in progress.")
        try:
            settings = settings_manager.reload()
            if llama_client is None or _settings_changed(llama_client, settings):
                llama_client = LlamaCppClient(
                    base_url=settings["llama_cpp"]["base_url"],
                    api_key=settings["llama_cpp"].get("api_key", ""),
                )
                logger.debug(
                    "Initialised llama.cpp client at %s",
                    llama_client.base_url,
                )
            logger.info(
                "Processing task %s (kind=%s conversation=%s priority=%s)",
                task_id,
                kind,
                conversation_id,
                priority,
            )
            if kind == "completion":
                result = _handle_completion(
                    conversation_store=conversation_store,
                    conversation_id=conversation_id,
                    llama_client=llama_client,
                    registry=registry,
                    settings=settings,
                    agent_name=task_payload.get("agent"),
                    model_override=task_payload.get("model"),
                    temperature_override=task_payload.get("temperature"),
                    context_size_override=task_payload.get("context_size"),
                )
                result["requires_summary"] = True
            elif kind == "summarize":
                result = _handle_summarize(
                    conversation_store=conversation_store,
                    index_store=index_store,
                    conversation_id=conversation_id,
                )
            else:
                raise ValueError(f"Unknown task type: {kind}")
            _post_event(
                event_queue,
                task_id,
                "completed",
                "Task completed successfully.",
                data=result,
            )
            logger.info(
                "Task %s completed (kind=%s conversation=%s)",
                task_id,
                kind,
                conversation_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "Task %s failed (kind=%s conversation=%s)",
                task_id,
                kind,
                conversation_id,
            )
            _post_event(
                event_queue,
                task_id,
                "failed",
                f"{type(exc).__name__}: {exc}",
            )


def _settings_changed(client: LlamaCppClient, settings: Dict[str, Any]) -> bool:
    return (
        client.base_url != settings["llama_cpp"]["base_url"]
        or client.api_key != settings["llama_cpp"].get("api_key", "")
    )


def _build_message_history(
    conversation: List[Dict[str, Any]],
    default_system_prompt: str,
) -> Tuple[List[Dict[str, Any]], str]:
    system_prompt = default_system_prompt
    messages: List[Dict[str, Any]] = []
    for entry in conversation:
        etype = entry.get("type")
        if etype == "metadata":
            system_prompt = entry["content"].get("system_prompt") or system_prompt
            continue
        if etype == "label":
            continue
        if etype == "message":
            messages.append(
                {"role": entry["role"], "content": entry.get("content", "")}
            )
        elif etype == "completion":
            content = entry.get("content") or {}
            message = {
                "role": entry.get("role", "assistant"),
                "content": content.get("text") or "",
            }
            tool_calls = []
            for call in content.get("tool_calls") or []:
                tool_calls.append(
                    {
                        "id": call.get("id") or uuid4().hex,
                        "type": "function",
                        "function": {
                            "name": call.get("name"),
                            "arguments": json.dumps(call.get("arguments", {})),
                        },
                    }
                )
            if tool_calls:
                message["tool_calls"] = tool_calls
            messages.append(message)
        elif etype == "tool_result":
            content = entry.get("content") or {}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": content.get("tool_call_id"),
                    "name": content.get("tool"),
                    "content": json.dumps(content.get("result", {})),
                }
            )
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})
    return messages, system_prompt


def _normalise_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalised: List[Dict[str, Any]] = []
    for message in messages:
        content = message.get("content", "")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            try:
                content = json.dumps(content, ensure_ascii=False)
            except TypeError:
                content = str(content)
        message["content"] = content

        tool_calls = message.get("tool_calls") or []
        for call in tool_calls:
            function = call.get("function") or {}
            arguments = function.get("arguments")
            if arguments is None:
                function["arguments"] = "{}"
            elif not isinstance(arguments, str):
                try:
                    function["arguments"] = json.dumps(arguments, ensure_ascii=False)
                except TypeError:
                    function["arguments"] = str(arguments)
            call["function"] = function
        if tool_calls:
            message["tool_calls"] = tool_calls

        if message.get("role") == "tool":
            if not isinstance(message.get("name"), str):
                message["name"] = str(message.get("name"))
            if message.get("content") is None:
                message["content"] = ""
        normalised.append(message)
    return normalised


def _handle_completion(
    conversation_store: ConversationStore,
    conversation_id: str,
    llama_client: LlamaCppClient,
    registry: ToolRegistry,
    settings: Dict[str, Any],
    agent_name: Optional[str] = None,
    model_override: Optional[str] = None,
    temperature_override: Optional[float] = None,
    context_size_override: Optional[int] = None,
) -> Dict[str, Any]:
    conversation = conversation_store.load_conversation(conversation_id)
    if not conversation:
        raise LlamaCppError("Conversation is empty.")
    agent_settings = next(
        (
            agent
            for agent in settings.get("agents", [])
            if agent.get("name") == agent_name
        ),
        settings.get("agents", [{}])[0] if settings.get("agents") else {},
    )
    default_agent = settings.get("agents", [{}])[0] if settings.get("agents") else {}
    temperature = (
        temperature_override
        if temperature_override is not None
        else agent_settings.get(
            "temperature", default_agent.get("temperature", 0.2)
        )
    )
    context_size = (
        context_size_override
        if context_size_override is not None
        else agent_settings.get(
            "context_size", default_agent.get("context_size", 4096)
        )
    )
    tools = registry.definitions() or None
    iterations = 0
    max_iterations = 4
    last_completion_id = None
    model_name = model_override
    if not model_name and agent_name:
        for agent in settings.get("agents", []):
            if agent.get("name") == agent_name:
                model_name = agent.get("model")
                break
    if not model_name:
        model_name = settings["llama_cpp"]["model"]
    logger.debug(
        "Invoking llama.cpp",
        extra={
            "conversation": conversation_id,
            "agent": agent_name,
            "model": model_name,
        },
    )
    while iterations < max_iterations:
        messages, _ = _build_message_history(conversation, settings["system_prompt"])
        messages = _normalise_messages(messages)
        response = llama_client.chat(
            model=model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=context_size,
            tools=tools,
        )
        choice = (response.get("choices") or [{}])[0]
        assistant_message = choice.get("message") or {}
        text, reasoning, reasoning_content = unpack_assistant_message(assistant_message)
        tool_calls = assistant_message.get("tool_calls") or []
        formatted_calls = []
        for call in tool_calls:
            func = call.get("function") or {}
            try:
                arguments = json.loads(func.get("arguments") or "{}")
            except json.JSONDecodeError:
                arguments = {"_raw": func.get("arguments")}
            formatted_calls.append(
                {
                    "id": call.get("id") or uuid4().hex,
                    "name": func.get("name", ""),
                    "arguments": arguments,
                }
            )
        completion_entry = {
            "id": uuid4().hex,
            "timestamp": utcnow(),
            "role": "assistant",
            "type": "completion",
            "content": {
                "agent": agent_name,
                "model": model_name,
                "text": text,
                "reasoning": reasoning,
                "reasoning_content": reasoning_content,
                "tool_calls": formatted_calls,
            },
        }
        conversation_store.append_entry(conversation_id, completion_entry)
        conversation.append(completion_entry)
        last_completion_id = completion_entry["id"]

        if not formatted_calls:
            break

        for call in formatted_calls:
            name = call.get("name")
            arguments = call.get("arguments") or {}
            result = registry.execute(name, arguments)
            serialised = _ensure_jsonable(result)
            tool_entry = {
                "id": uuid4().hex,
                "timestamp": utcnow(),
                "role": "tool",
                "type": "tool_result",
                "content": {
                    "tool": name,
                    "tool_call_id": call.get("id"),
                    "arguments": arguments,
                    "result": serialised,
                },
            }
            conversation_store.append_entry(conversation_id, tool_entry)
            conversation.append(tool_entry)
        iterations += 1

    if iterations >= max_iterations:
        raise LlamaCppError("Tool call loop exceeded max iterations.")

    return {"message_id": last_completion_id}


def _handle_summarize(
    conversation_store: ConversationStore,
    index_store: IndexStore,
    conversation_id: str,
) -> Dict[str, Any]:
    conversation = conversation_store.load_conversation(conversation_id)
    if not conversation:
        raise ValueError("Conversation not found.")
    first_user = next(
        (entry for entry in conversation if entry.get("role") == "user"), None
    )
    last_assistant = next(
        (entry for entry in reversed(conversation) if entry.get("role") == "assistant"),
        None,
    )
    user_text = (first_user or {}).get("content", "")
    assistant_payload = (last_assistant or {}).get("content", {})
    assistant_text = ""
    if isinstance(assistant_payload, dict):
        assistant_text = assistant_payload.get("text", "")
    elif isinstance(assistant_payload, str):
        assistant_text = assistant_payload
    summary = assistant_text or user_text or "New conversation"
    if user_text and assistant_text:
        summary = f"{user_text[:80]} → {assistant_text[:120]}"
    title = build_title(summary, user_text or assistant_text or "Conversation")
    latest = index_store.latest_index().get(conversation_id, {})
    last_accessed = latest.get("last_accessed")
    index_store.record_summary(
        conversation_id=conversation_id,
        summary=summary,
        title=title,
        last_accessed=last_accessed,
    )
    return {"summary": summary, "title": title}


def _post_event(
    queue: mp.Queue,
    task_id: str,
    status: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    queue.put(
        {
            "task_id": task_id,
            "status": status,
            "message": message,
            "timestamp": utcnow(),
            "data": data or {},
        }
    )
