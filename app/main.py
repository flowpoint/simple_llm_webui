from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse, urlunparse

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
import requests

from .settings import DEFAULT_SETTINGS, SettingsManager
from .storage import ConversationStore, IndexStore, build_title
from .tasks import IdleMonitor, TaskService
from .templates import (
    render_conversation_list,
    render_conversation_messages,
    render_dashboard,
    render_task_strip,
    render_settings_page,
    render_help_page,
)

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = DATA_DIR / "server.log"
SETTINGS_PATH = DATA_DIR / "settings.json"


def _configure_logging() -> logging.Logger:
    logger = logging.getLogger("webui")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False
    logger.debug("Logging initialised, writing to %s", LOG_FILE)
    return logger


logger = _configure_logging()

app = FastAPI()

settings_manager = SettingsManager(SETTINGS_PATH)
conversation_store = ConversationStore(DATA_DIR)
index_store = IndexStore(DATA_DIR)
task_service = TaskService(DATA_DIR, SETTINGS_PATH)
idle_monitor = IdleMonitor(timeout_seconds=30)
idle_task: Optional[asyncio.Task] = None

app_state: Dict[str, bool] = {"idle": False}
llama_status: Dict[str, str] = {"state": "warn", "label": "LLM Unknown"}


def _ensure_agents() -> List[Dict]:
    configured = list(settings_manager.settings.get("agents", []))
    if len(configured) >= 4:
        agents = configured[:4]
    else:
        fallback = list(DEFAULT_SETTINGS["agents"])
        combined = configured + fallback[len(configured) : 4]
        while len(combined) < 4:
            combined.append(
                {
                    "name": f"Agent {len(combined) + 1}",
                    "description": "",
                    "system_prompt": settings_manager.settings.get(
                        "system_prompt", DEFAULT_SETTINGS["system_prompt"]
                    ),
                    "model": settings_manager.settings.get("llama_cpp", {}).get(
                        "model", DEFAULT_SETTINGS["llama_cpp"]["model"]
                    ),
                    "temperature": DEFAULT_SETTINGS["agents"][0]["temperature"],
                    "context_size": DEFAULT_SETTINGS["agents"][0]["context_size"],
                }
            )
        agents = combined[:4]
    alias_counts: Dict[str, int] = {}
    default_prompt = settings_manager.settings.get(
        "system_prompt", DEFAULT_SETTINGS["system_prompt"]
    )
    default_model = settings_manager.settings.get("llama_cpp", {}).get(
        "model", DEFAULT_SETTINGS["llama_cpp"]["model"]
    )
    default_temperature = DEFAULT_SETTINGS["agents"][0]["temperature"]
    default_context = DEFAULT_SETTINGS["agents"][0]["context_size"]
    for index, agent in enumerate(agents):
        agent.setdefault("description", "")
        agent.setdefault("system_prompt", default_prompt)
        agent.setdefault("model", default_model)
        agent.setdefault("temperature", default_temperature)
        agent.setdefault("context_size", default_context)
        alias = agent.get("alias")
        if not alias:
            alias = re.sub(r"[^a-z0-9]+", "-", agent["name"].lower()).strip("-")
        if not alias:
            alias = f"agent-{index + 1}"
        base_alias = alias
        counter = 1
        while alias in alias_counts:
            counter += 1
            alias = f"{base_alias}-{counter}"
        alias_counts[alias] = 1
        agent["alias"] = alias
    return agents[:4]


def _status_context() -> Dict[str, str]:
    worker_alive = task_service.worker_alive()
    idle = app_state.get("idle", False)
    llama_state = llama_status.get("state", "warn")
    llama_label = llama_status.get("label", "LLM Unknown")
    return {
        "worker_state": "ok" if worker_alive else "warn",
        "worker_label": "online" if worker_alive else "offline",
        "idle_state": "warn" if idle else "ok",
        "idle_label": "Idle" if idle else "Active",
        "llama_state": llama_state,
        "llama_label": llama_label,
    }


def _schedule_missing_summaries() -> None:
    latest_index = index_store.latest_index()
    for meta in conversation_store.list_conversations():
        record = latest_index.get(meta.conversation_id, {})
        if not record.get("summary"):
            task_service.mark_summary_needed(meta.conversation_id)
    for conversation_id in task_service.pending_summary_ids():
        task_service.enqueue_summary(conversation_id)


def _llama_health_url() -> Optional[str]:
    base_url = settings_manager.settings.get("llama_cpp", {}).get("base_url")
    if not base_url:
        return None
    parsed = urlparse(base_url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, "/health", "", "", ""))


def _collect_view_state(
    requested_conversation: Optional[str],
) -> Dict[str, Any]:
    task_service.drain_events()
    latest_index = index_store.latest_index()
    conversation_metadata = conversation_store.list_conversations()
    conversation_ids = [meta.conversation_id for meta in conversation_metadata]
    active_conversation = (
        requested_conversation if requested_conversation in conversation_ids else None
    )

    if not active_conversation and conversation_ids:
        def sort_key(cid: str) -> str:
            record = latest_index.get(cid, {})
            return record.get("last_accessed") or record.get("timestamp") or ""

        active_conversation = max(conversation_ids, key=sort_key)

    if active_conversation:
        index_store.record_access(active_conversation)
        latest_index = index_store.latest_index()

    history: List[Dict[str, str]] = []
    active_title = ""
    for meta in conversation_metadata:
        cid = meta.conversation_id
        record = latest_index.get(cid, {})
        title = record.get("title") or record.get("summary")
        if not title:
            title = build_title(record.get("summary"), f"Conversation {cid[:8]}")
        last_accessed = (
            record.get("last_accessed")
            or record.get("timestamp")
            or meta.last_modified.strftime("%Y-%m-%dT%H:%M:%S")
        )
        history.append(
            {
                "conversation_id": cid,
                "title": title,
                "summary": record.get("summary"),
                "last_accessed": last_accessed,
            }
        )
        if cid == active_conversation:
            active_title = title

    history.sort(key=lambda item: item.get("last_accessed", ""), reverse=True)

    if active_conversation and not active_title:
        active_title = f"Conversation {active_conversation[:8]}"

    entries = (
        conversation_store.load_conversation(active_conversation)
        if active_conversation
        else []
    )
    reward_map: Dict[str, int] = {}
    tool_reward_map: Dict[str, int] = {}
    for entry in entries:
        if entry.get("type") == "label":
            content = entry.get("content") or {}
            target = content.get("target")
            reward = content.get("reward")
            if content.get("target_type") == "tool_call":
                tool_reward_map[target] = reward
            else:
                reward_map[target] = reward

    visible_entries = [entry for entry in entries if entry.get("type") != "label"]
    entry_ids = [entry.get("id") for entry in visible_entries if entry.get("id")]
    last_entry_id = entry_ids[-1] if entry_ids else None

    status = _status_context()
    agents = _ensure_agents()
    tasks = task_service.snapshot()

    logger.debug(
        "Collected view state for %s (history=%d entries=%d tasks=%d)",
        active_conversation,
        len(history),
        len(entries),
        len(tasks),
    )

    return {
        "active_conversation": active_conversation,
        "conversation_title": active_title or "Conversation",
        "history": history,
        "entries": entries,
        "entry_ids": entry_ids,
        "last_entry_id": last_entry_id,
        "reward_map": reward_map,
        "tool_reward_map": tool_reward_map,
        "status": status,
        "agents": agents,
        "tasks": tasks,
    }


def _render_tasks_html(tasks: List[Any]) -> str:
    completed = [task for task in tasks if task.status == "completed"]
    queued = [task for task in tasks if task.status != "completed"]
    completed.sort(key=lambda rec: rec.updated_at, reverse=True)
    recent_completed = completed[:2]
    recent_completed.sort(key=lambda rec: getattr(rec, "created_at", rec.updated_at))
    queued.sort(key=lambda rec: (rec.priority, rec.updated_at))
    completed_placeholder = (
        "<div class=\"task-lane completed empty\">"
        "<div class=\"task-strip\">"
        "<div class=\"task-card placeholder\"><p>No finished tasks.</p></div>"
        "</div>"
        "</div>"
    )
    queued_placeholder = (
        "<div class=\"task-lane queued empty\">"
        "<div class=\"task-strip\">"
        "<div class=\"task-card placeholder\"><p>No queued tasks.</p></div>"
        "</div>"
        "</div>"
    )

    completed_html = render_task_strip(
        recent_completed,
        css_class="completed",
        empty_html=completed_placeholder,
    )
    queued_html = render_task_strip(
        queued,
        css_class="queued",
        empty_html=queued_placeholder,
    )

    parts = [completed_html, "<div class=\"task-divider\"></div>", queued_html]
    return "\n".join(parts)


@app.on_event("startup")
async def on_startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    task_service.start()
    logger.info("Application startup complete.")

    def enter_idle() -> None:
        app_state["idle"] = True
        task_service.drain_events()
        _schedule_missing_summaries()

    def exit_idle() -> None:
        app_state["idle"] = False

    global idle_task
    idle_task = asyncio.create_task(
        idle_monitor.loop(on_idle=enter_idle, on_active=exit_idle), name="idle-monitor"
    )


@app.on_event("shutdown")
async def on_shutdown() -> None:
    if idle_task:
        idle_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await idle_task
    task_service.stop()
    logger.info("Application shutdown complete.")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, conversation: Optional[str] = None) -> HTMLResponse:
    state = _collect_view_state(conversation)
    html = render_dashboard(
        conversations=state["history"],
        active_conversation=state["active_conversation"],
        conversation_entries=state["entries"],
        entry_ids=state["entry_ids"],
        reward_map=state["reward_map"],
        tool_reward_map=state["tool_reward_map"],
        conversation_title=state["conversation_title"],
        agents=state["agents"],
        tasks=state["tasks"],
        status=state["status"],
    )
    return HTMLResponse(html)


@app.post("/conversation/new")
async def new_conversation() -> RedirectResponse:
    idle_monitor.touch()
    agents = _ensure_agents()
    default_agent = agents[0]
    conversation_id = conversation_store.create_conversation(
        agent=default_agent.get("name", "General"),
        system_prompt=default_agent.get(
            "system_prompt", settings_manager.settings.get("system_prompt", DEFAULT_SETTINGS["system_prompt"])
        ),
        model=default_agent.get(
            "model", settings_manager.settings.get("llama_cpp", {}).get("model", DEFAULT_SETTINGS["llama_cpp"]["model"])
        ),
        temperature=default_agent.get("temperature", 0.2),
        context_size=default_agent.get("context_size", 4096),
    )
    index_store.record_access(conversation_id)
    logger.info(
        "Started new conversation %s (agent=%s model=%s)",
        conversation_id,
        default_agent.get("name"),
        default_agent.get("model"),
    )
    return RedirectResponse(
        url=f"/?conversation={conversation_id}", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/conversation/{conversation_id}/send")
async def send_message(
    conversation_id: str,
    request: Request,
) -> Response:
    idle_monitor.touch()
    accepts_json = "application/json" in (request.headers.get("accept", "").lower())

    body_bytes = await request.body()
    form_data = parse_qs(body_bytes.decode("utf-8"))
    raw_prompt = (form_data.get("prompt") or [""])[-1]
    if not raw_prompt or not raw_prompt.strip():
        if accepts_json:
            return JSONResponse(
                {"ok": False, "error": "Prompt must not be empty."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return RedirectResponse(
            url=f"/?conversation={conversation_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    entries = conversation_store.load_conversation(conversation_id)
    if not entries:
        if accepts_json:
            return JSONResponse(
                {"ok": False, "error": "Conversation not found."},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return RedirectResponse(
            url=f"/?conversation={conversation_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    agents = _ensure_agents()
    agent_lookup = {item["name"]: item for item in agents}
    alias_lookup = {item["alias"].lower(): item for item in agents}
    last_metadata = next(
        (
            entry
            for entry in reversed(entries)
            if entry.get("type") == "metadata"
        ),
        {},
    )
    last_content = last_metadata.get("content") or {}
    default_agent = agent_lookup.get(last_content.get("agent")) or agents[0]
    selected = default_agent
    system_prompt = (
        last_content.get("system_prompt")
        or selected.get("system_prompt")
        or settings_manager.settings["system_prompt"]
    )
    model_name = (
        last_content.get("model")
        or selected.get("model")
        or settings_manager.settings["llama_cpp"]["model"]
    )
    mention_pattern = re.compile(r"(^|\s)@([a-z0-9][a-z0-9\-]*)", re.IGNORECASE)
    mention_match = mention_pattern.search(raw_prompt)
    prompt_text = raw_prompt.strip()
    if mention_match:
        mention_name = mention_match.group(2).strip().lower()
        mentioned_agent = alias_lookup.get(mention_name)
        if mentioned_agent:
            selected = mentioned_agent
            system_prompt = (
                selected.get("system_prompt") or settings_manager.settings["system_prompt"]
            )
            model_name = selected.get("model") or settings_manager.settings["llama_cpp"]["model"]
            before = raw_prompt[: mention_match.start()]
            after = raw_prompt[mention_match.end() :]
            replacement = mention_match.group(1) if mention_match.group(1) else ""
            prompt_text = (before + replacement + after)
            prompt_text = re.sub(r"\s{2,}", " ", prompt_text).strip()
        else:
            prompt_text = raw_prompt.strip()
    if not prompt_text:
        if accepts_json:
            return JSONResponse(
                {"ok": False, "error": "Prompt must not be empty."},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return RedirectResponse(
            url=f"/?conversation={conversation_id}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    selected_temp = selected.get("temperature", 0.2)
    selected_ctx = selected.get("context_size", 4096)
    if (
        last_content.get("system_prompt") != system_prompt
        or last_content.get("agent") != selected.get("name")
        or last_content.get("model") != model_name
        or last_content.get("temperature") != selected_temp
        or last_content.get("context_size") != selected_ctx
    ):
        conversation_store.append_entry(
            conversation_id,
            {
                "role": "system",
                "type": "metadata",
                "content": {
                    "system_prompt": system_prompt,
                    "agent": selected.get("name"),
                    "model": model_name,
                    "temperature": selected_temp,
                    "context_size": selected_ctx,
                },
            },
        )
    conversation_store.append_user_message(conversation_id, prompt_text)
    logger.info(
        "Queued user message for %s (agent=%s model=%s)",
        conversation_id,
        selected.get("name"),
        model_name,
    )
    task_service.mark_summary_needed(conversation_id)
    task_service.enqueue_completion(
        conversation_id,
        selected.get("name"),
        model_name,
        temperature=selected_temp,
        context_size=selected_ctx,
    )
    if accepts_json:
        return JSONResponse({"ok": True, "conversation_id": conversation_id})
    return RedirectResponse(
        url=f"/?conversation={conversation_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/conversation/{conversation_id}/label")
async def label_message(
    conversation_id: str,
    request: Request,
) -> RedirectResponse:
    idle_monitor.touch()
    body_bytes = await request.body()
    form_data = parse_qs(body_bytes.decode("utf-8"))
    target_id = (form_data.get("target_id") or [""])[-1]
    target_type = (form_data.get("target_type") or [""])[-1]
    reward_value = int((form_data.get("reward") or ["0"])[-1])
    if reward_value not in {-2, -1, 0, 1, 2} or not target_id:
        return RedirectResponse(
            url=f"/?conversation={conversation_id}",
            status_code=status.HTTP_303_SEE_OTHER,
    )
    conversation_store.append_label(conversation_id, target_id, reward_value, target_type)
    logger.info(
        "Recorded reward for %s target=%s type=%s reward=%d",
        conversation_id,
        target_id,
        target_type,
        reward_value,
    )
    task_service.mark_summary_needed(conversation_id)
    return RedirectResponse(
        url=f"/?conversation={conversation_id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page() -> HTMLResponse:
    html = render_settings_page(
        settings_manager.settings,
        _ensure_agents(),
        _status_context(),
    )
    return HTMLResponse(html)


@app.post("/settings")
async def update_settings(request: Request) -> RedirectResponse:
    idle_monitor.touch()
    body_bytes = await request.body()
    form_pairs = parse_qs(body_bytes.decode("utf-8"))

    def get_field(name: str, default: str = "") -> str:
        values = form_pairs.get(name)
        if not values:
            return default
        return values[-1]

    llama = {
        "base_url": get_field("llama_base_url", settings_manager.settings["llama_cpp"]["base_url"]),
        "api_key": get_field("llama_api_key"),
        "model": get_field("llama_model", settings_manager.settings["llama_cpp"]["model"]),
        "temperature": float(get_field("llama_temperature", str(settings_manager.settings["llama_cpp"].get("temperature", 0.2)))),
    }
    agents: List[Dict] = []
    for idx, default_agent in enumerate(_ensure_agents()):
        default_temp = default_agent.get("temperature", 0.2)
        default_ctx = default_agent.get("context_size", 4096)
        agents.append(
            {
                "name": get_field(f"agents_{idx}_name", default_agent["name"]),
                "description": get_field(f"agents_{idx}_description", ""),
                "system_prompt": get_field(f"agents_{idx}_prompt", ""),
                "model": get_field(
                    f"agents_{idx}_model", default_agent.get("model", llama["model"])
                ),
                "temperature": float(
                    get_field(
                        f"agents_{idx}_temperature", str(default_temp)
                    )
                    or default_temp
                ),
                "context_size": int(
                    get_field(
                        f"agents_{idx}_context", str(default_ctx)
                    )
                    or default_ctx
                ),
            }
        )
    payload = {
        "llama_cpp": llama,
        "agents": agents,
    }
    if agents:
        payload["system_prompt"] = agents[0]["system_prompt"]
        llama["temperature"] = agents[0].get("temperature", 0.2)
    settings_manager.save(payload)
    logger.info(
        "Settings updated base_url=%s default_model=%s agents=%s",
        llama["base_url"],
        llama["model"],
        ", ".join(agent["name"] for agent in agents),
    )
    return RedirectResponse(url="/settings", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/help", response_class=HTMLResponse)
async def help_page() -> HTMLResponse:
    agents = _ensure_agents()
    html = render_help_page(agents)
    return HTMLResponse(html)


@app.get("/health/llama", response_class=JSONResponse)
async def llama_health() -> JSONResponse:
    health_url = _llama_health_url()
    if not health_url:
        llama_status["state"] = "warn"
        llama_status["label"] = "LLM Unknown"
        return JSONResponse({"status": "warn", "label": "LLM Unknown"})
    try:
        response = requests.get(health_url, timeout=3)
        ok = response.status_code < 400
    except requests.RequestException:
        ok = False
    status = "ok" if ok else "warn"
    label = "LLM Connected" if ok else "LLM Offline"
    llama_status["state"] = status
    llama_status["label"] = label
    return JSONResponse({"status": status, "label": label})


@app.get("/state", response_class=JSONResponse)
async def state_endpoint(conversation: Optional[str] = None) -> JSONResponse:
    state = _collect_view_state(conversation)
    payload = {
        "history_html": render_conversation_list(
            state["history"],
            state["active_conversation"],
        ),
        "messages_html": render_conversation_messages(
            state["entries"],
            state["reward_map"],
            state["tool_reward_map"],
            state["active_conversation"],
        ),
        "tasks_html": _render_tasks_html(state["tasks"]),
        "conversation_title": state["conversation_title"],
        "active_conversation": state["active_conversation"],
        "status": state["status"],
        "agents": [
            agent.get("alias") for agent in state["agents"] if agent.get("alias")
        ],
        "entry_ids": state["entry_ids"],
        "last_entry_id": state["last_entry_id"],
    }
    return JSONResponse(payload)


@app.get("/status", response_class=JSONResponse)
async def status_endpoint() -> JSONResponse:
    task_service.drain_events()
    snapshot = task_service.snapshot()
    data = _status_context()
    data["pending_tasks"] = len([task for task in snapshot if task.status != "completed"])
    return JSONResponse(data)


# Convenience include for uvicorn.
__all__ = ["app"]
