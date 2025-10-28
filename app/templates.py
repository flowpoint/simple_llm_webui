from __future__ import annotations

import json
from html import escape
from typing import Any, Dict, List, Optional

from .tasks import TaskRecord


def render_dashboard(
    *,
    conversations: List[Dict],
    active_conversation: Optional[str],
    conversation_entries: List[Dict],
    entry_ids: List[str],
    reward_map: Dict[str, int],
    tool_reward_map: Dict[str, int],
    conversation_title: str,
    agents: List[Dict],
    tasks: List[TaskRecord],
    status: Dict[str, str],
    task_signature: List[List[str]],
) -> str:
    agent_names = [agent.get("alias", "") for agent in agents if agent.get("alias")]
    agents_json = escape(json.dumps(agent_names))
    history_html = render_conversation_list(conversations, active_conversation)
    messages_html = render_conversation_messages(
        conversation_entries,
        reward_map,
        tool_reward_map,
        active_conversation,
    )
    completed = [task for task in tasks if task.status == "completed"]
    queued = [task for task in tasks if task.status != "completed"]
    completed.sort(key=lambda record: record.updated_at, reverse=True)
    completed = completed[:2]
    queued.sort(key=lambda record: (record.priority, record.updated_at))

    completed_html = render_task_strip(
        completed, css_class="completed", empty_html=""
    )
    queued_html = render_task_strip(
        queued, css_class="queued", empty_html=""
    )

    task_sections: List[str] = []
    if completed_html:
        task_sections.append(completed_html)
    if completed_html and queued_html:
        task_sections.append("<div class=\"task-divider\"></div>")
    if queued_html:
        task_sections.append(queued_html)
    tasks_html = "\n".join(task_sections) or "<div class='empty'>No queued work.</div>"
    scripts = _refresh_script()
    active_attr = escape(active_conversation or "")
    title_html = escape(conversation_title or "Conversation")
    entry_ids_json = escape(json.dumps(entry_ids))
    last_entry_id = escape(entry_ids[-1] if entry_ids else "")
    task_signature_json = escape(json.dumps(task_signature))

    prompt_html = render_prompt_form(active_conversation, agents)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Minimal LLM WebUI</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f5f5;
      --border: #ccc;
      --panel-bg: #fff;
      --accent: #3367d6;
      --muted: #666;
      --queue-bg: #f0f4fb;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    [hidden] {{
      display: none !important;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: #111;
      height: 100vh;
      display: flex;
      flex-direction: column;
      padding: 0.4rem;
      box-sizing: border-box;
    }}
    main {{
      flex: 1;
      min-height: 0;
      display: grid;
      grid-template-columns: 220px 1fr;
      grid-template-rows: 1fr 150px;
      grid-template-areas:
        "history chat"
        "queue queue";
      gap: 0.5rem;
      padding: 0.5rem;
      box-sizing: border-box;
      overflow: hidden;
    }}
    main > * {{
      min-height: 0;
    }}
    .status-badges {{
      display: flex;
      gap: 0.35rem;
      align-items: center;
      flex-wrap: wrap;
    }}
    .help-button {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.25rem 0.5rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #eef2ff;
      color: #123e90;
      text-decoration: none;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .settings-button {{
      display: inline-flex;
      align-items: center;
      padding: 0.25rem 0.5rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #fff;
      color: #123e90;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      text-decoration: none;
    }}
    .badge {{
      padding: 0.12rem 0.45rem;
      border-radius: 999px;
      background: var(--border);
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge[data-state="ok"] {{
      background: #d9f0ff;
      color: #004b91;
    }}
    .badge[data-state="warn"] {{
      background: #ffe8d6;
      color: #a55300;
    }}
    nav {{
      grid-area: history;
      background: var(--panel-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
    }}
    nav h2 {{
      font-size: 0.9rem;
      padding: 0.5rem 0.6rem 0.2rem;
      margin: 0;
    }}
    nav .conversations {{
      overflow-y: auto;
      padding: 0 0.35rem 0.35rem 0.55rem;
      flex: 1;
      margin-right: -0.3rem;
      padding-right: 0.5rem;
    }}
    nav a {{
      display: block;
      padding: 0.4rem 0.55rem;
      margin-bottom: 0.2rem;
      border-radius: 6px;
      text-decoration: none;
      color: inherit;
      background: transparent;
      border: 1px solid transparent;
    }}
    nav a strong {{
      display: block;
      font-size: 0.85rem;
    }}
    nav a span {{
      display: block;
      font-size: 0.7rem;
      color: var(--muted);
      margin-top: 0.15rem;
    }}
    nav a.active {{
      background: #e7f0ff;
      border-color: #c5d7ff;
      color: #123e90;
    }}
    nav form {{
      padding: 0.45rem 0.6rem 0.6rem;
      border-top: 1px solid var(--border);
      background: rgba(0,0,0,0.02);
    }}
    nav button {{
      width: 100%;
      padding: 0.35rem 0.45rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: #f2f4f8;
      cursor: pointer;
    }}
    section.chat {{
      grid-area: chat;
      display: flex;
      flex-direction: column;
      background: var(--panel-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
      min-height: 0;
      position: relative;
    }}
    .chat-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.55rem 0.75rem;
      background: rgba(0,0,0,0.02);
      border-bottom: 1px solid var(--border);
    }}
    .chat-header h2 {{
      margin: 0;
      font-size: 1rem;
      font-weight: 600;
    }}
    .history {{
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 0.65rem 0.75rem;
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
    }}
    .message {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.45rem 0.65rem;
      background: #fafafa;
    }}
    .message.user {{
      border-color: #c8d1ff;
      background: #f1f4ff;
    }}
    .message.assistant {{
      border-color: #c2e0ff;
      background: #eef7ff;
    }}
    .message.tool {{
      border-color: #e2d4ff;
      background: #f5efff;
    }}
    .message-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 0.6rem;
      margin-bottom: 0.35rem;
      font-size: 0.82rem;
      color: var(--muted);
    }}
    .message-meta {{
      flex: 1 1 auto;
      word-break: break-word;
    }}
    .message-actions {{
      flex: 0 0 auto;
      display: flex;
      gap: 0.25rem;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .message-actions form {{
      display: flex;
      gap: 0.25rem;
      flex-wrap: wrap;
    }}
    .message-actions .label-actions {{
      margin: 0;
    }}
    .label-actions {{
      display: flex;
      gap: 0.25rem;
    }}
    .label-actions button {{
      font-size: 0.72rem;
      padding: 0.2rem 0.45rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
    }}
    .label-actions button.selected {{
      background: #d6f5d6;
      border-color: #36a536;
      font-weight: 600;
    }}
    .message-body {{
      display: flex;
      flex-direction: column;
      gap: 0.45rem;
    }}
    .message-body pre {{
      margin: 0;
      white-space: pre-wrap;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      background: rgba(0, 0, 0, 0.03);
      padding: 0.5rem;
      border-radius: 4px;
    }}
    .message-body details {{
      border: 1px dashed var(--border);
      border-radius: 4px;
      padding: 0.35rem 0.5rem;
      background: rgba(0,0,0,0.02);
    }}
    .reasoning-toggle {{
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--accent);
      background: rgba(51, 103, 214, 0.12);
      color: #123e90;
      font-size: 0.7rem;
      cursor: pointer;
      transition: background 0.2s ease;
    }}
    .reasoning-toggle[aria-expanded="true"] {{
      background: var(--accent);
      color: #fff;
    }}
    .reasoning-details {{
      border: 1px solid rgba(51, 103, 214, 0.35);
      background: rgba(51, 103, 214, 0.05);
      padding: 0.35rem 0.45rem 0.45rem;
    }}
    .reasoning-details summary {{
      font-size: 0.72rem;
      font-weight: 600;
      color: #123e90;
      cursor: pointer;
    }}
    .reasoning-details summary::-webkit-details-marker {{
      display: none;
    }}
    .reasoning-content {{
      margin-top: 0.35rem;
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }}
    .reasoning-content pre {{
      margin: 0;
      padding: 0.35rem;
      background: rgba(10, 40, 120, 0.08);
    }}
    .sr-only {{
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }}
    .reasoning {{
      margin-top: 0.35rem;
      padding: 0.45rem 0.55rem;
      border-left: 3px solid rgba(51, 103, 214, 0.35);
      background: rgba(51, 103, 214, 0.06);
      border-radius: 6px;
      display: none;
    }}
    .reasoning.visible {{
      display: block;
    }}
    .prompt-container {{
      border-top: 1px solid var(--border);
      background: #f7f9ff;
      padding: 0.6rem 0.7rem 0.55rem;
      position: relative;
    }}
    form.prompt {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    form.prompt textarea {{
      resize: vertical;
      min-height: 72px;
      padding: 0.5rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      font-size: 0.95rem;
      font-family: inherit;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }}
    .prompt-container.mention-visible textarea {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px rgba(51, 103, 214, 0.2);
    }}
    .prompt-row {{
      display: flex;
      gap: 0.45rem;
      align-items: stretch;
    }}
    .prompt-row textarea {{
      flex: 1 1 auto;
    }}
    .prompt-row button {{
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      min-width: 72px;
    }}
    .agent-card h3 {{
      margin: 0 0 0.4rem;
      font-size: 0.9rem;
    }}
    aside button {{
      padding: 0.35rem 0.55rem;
      border-radius: 6px;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      cursor: pointer;
    }}
    section.queue {{
      grid-area: queue;
      background: var(--queue-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.55rem 0.65rem;
      overflow: hidden;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }}
    .queue-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.4rem;
    }}
    .queue-header h2 {{
      margin: 0;
      font-size: 0.9rem;
    }}
    .queue-header small {{
      color: var(--muted);
      font-size: 0.7rem;
    }}
    .queue-title {{
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 0.4rem;
    }}
    .queue-title h2 {{
      margin: 0;
      font-size: 0.9rem;
    }}
    .queue-actions {{
      display: flex;
      gap: 0.35rem;
      align-items: center;
    }}
    .task-area {{
      display: flex;
      flex-direction: row;
      gap: 0.4rem;
      align-items: stretch;
      overflow-x: auto;
      padding-bottom: 0.25rem;
    }}
    .task-lane {{
      display: flex;
      flex: 0 0 auto;
      align-items: stretch;
    }}
    .task-lane.completed {{
      opacity: 0.9;
    }}
    .task-lane.queued {{
      flex: 1 1 auto;
      min-width: 0;
    }}
    .task-strip {{
      display: flex;
      flex-direction: row;
      gap: 0.45rem;
      flex: 0 0 auto;
      align-items: stretch;
    }}
    .task-lane.completed .task-strip {{
      max-width: calc(200px * 2 + 0.9rem);
    }}
    .task-lane.completed.empty {{
      flex: 0 0 calc(200px * 2 + 0.9rem);
      max-width: calc(200px * 2 + 0.9rem);
    }}
    .task-lane.queued.empty {{
      flex: 1 1 auto;
      min-width: 0;
    }}
    .task-lane.empty .task-strip {{
      justify-content: center;
      max-width: 100%;
    }}
    .task-divider {{
      flex: 0 0 4px;
      background: linear-gradient(
        180deg,
        rgba(51, 103, 214, 0.15) 0%,
        rgba(51, 103, 214, 0.6) 50%,
        rgba(51, 103, 214, 0.15) 100%
      );
      border-radius: 6px;
      align-self: stretch;
    }}
    .task-card {{
      flex: 0 0 200px;
      max-width: 200px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-bg);
      padding: 0.55rem 0.55rem;
      font-size: 0.78rem;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
      display: flex;
      flex-direction: column;
      gap: 0.18rem;
      min-width: 0;
      min-height: 120px;
      margin: 0;
      overflow: hidden;
      box-sizing: border-box;
    }}
    .task-card.high {{
      border-color: #d64545;
    }}
    .task-card.low {{
      border-color: #8aa6d6;
    }}
    .task-card.running {{
      border-color: #36a536;
    }}
    .task-card h3 {{
      margin: 0 0 0.25rem;
      font-size: 0.82rem;
      line-height: 1.2;
      max-height: 2.4em;
      overflow: hidden;
      word-break: break-word;
    }}
    .task-card span {{
      color: var(--muted);
      font-size: 0.7rem;
      display: block;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .task-card p {{
      margin: 0;
      font-size: 0.72rem;
      line-height: 1.25;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
      word-break: break-word;
    }}
    .task-lane.empty .task-card.placeholder {{
      align-items: center;
      justify-content: center;
      text-align: center;
      border-style: dashed;
      background: rgba(51, 103, 214, 0.08);
      color: var(--muted);
    }}
    .task-card.placeholder {{
      flex: 0 0 200px;
      max-width: 200px;
      min-height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0;
    }}
    .task-card.placeholder p {{
      margin: 0;
      font-size: 0.74rem;
      width: 100%;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .task-action {{
      margin-top: auto;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 0.3rem 0.55rem;
      border-radius: 6px;
      border: 1px solid var(--accent);
      background: rgba(51, 103, 214, 0.12);
      font-size: 0.72rem;
      color: #123e90;
      text-decoration: none;
      transition: background 0.15s ease;
    }}
    .task-action:hover {{
      background: var(--accent);
      color: #fff;
    }}
    .prompt-hint {{
      margin: 0.35rem 0 0;
      font-size: 0.75rem;
      color: var(--muted);
    }}
    .task-details {{
      margin-top: 0.2rem;
    }}
    .task-details summary {{
      cursor: pointer;
      font-size: 0.7rem;
      color: var(--accent);
    }}
    .task-details pre {{
      background: rgba(15, 23, 42, 0.04);
      padding: 0.4rem;
      border-radius: 6px;
      overflow-x: auto;
      font-size: 0.7rem;
      max-height: 160px;
      margin: 0.3rem 0 0;
    }}
    }}
    .placeholder {{
      color: var(--muted);
      margin: auto;
      padding: 1rem;
      text-align: center;
    }}
    .empty {{
      color: var(--muted);
      padding: 0.5rem 0;
    }}
    .mention-helper {{
      position: absolute;
      z-index: 20;
      max-height: 140px;
      overflow-y: auto;
      min-width: 150px;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 6px;
      box-shadow: 0 2px 6px rgba(0,0,0,0.12);
      padding: 0.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
    }}
    .mention-helper button {{
      text-align: left;
      border: none;
      background: transparent;
      padding: 0.3rem 0.4rem;
      border-radius: 4px;
      cursor: pointer;
      font-size: 0.8rem;
    }}
    .mention-helper button:hover,
    .mention-helper button:focus {{
      background: #eef3ff;
    }}
    .mention-helper button.active {{
      background: rgba(51, 103, 214, 0.15);
      font-weight: 600;
    }}
    .task-card.completed {{
      background: #e9f7ec;
      border-color: #6fbe7c;
      opacity: 0.8;
    }}
    .task-card.failed {{
      background: #fdecea;
      border-color: #f28b82;
    }}
  </style>
</head>
<body>
  <main id="layout" data-active-conversation="{active_attr}" data-agents='{agents_json}'>
    <nav>
      <h2>Conversations</h2>
      <div class="conversations" id="conversation-list">
        {history_html}
      </div>
      <form method="post" action="/conversation/new">
        <button type="submit">Start new conversation</button>
      </form>
    </nav>
    <section class="chat" id="chat-panel">
      <header class="chat-header">
        <h2 id="conversation-title">{title_html}</h2>
      </header>
      <div class="history" id="conversation-history" data-entry-ids='{entry_ids_json}' data-last-entry-id="{last_entry_id}">
        {messages_html}
      </div>
      <div class="prompt-container">
        {prompt_html}
      </div>
    </section>
    <section class="queue">
      <div class="queue-header">
        <div class="queue-title">
          <h2>Priority Queue</h2>
          <div class="status-badges">
            <div class="badge" id="worker-badge" data-state="{escape(status.get('worker_state', 'warn'))}">Worker {escape(status.get('worker_label', 'offline'))}</div>
              <div class="badge" id="idle-badge" data-state="{escape(status.get('idle_state', 'ok'))}">{escape(status.get('idle_label', 'Active'))}</div>
              <div class="badge" id="llama-badge" data-state="{escape(status.get('llama_state', 'warn'))}">{escape(status.get('llama_label', 'LLM Unknown'))}</div>
            </div>
          </div>
        <div class="queue-actions">
          <a class="settings-button" href="/settings">Settings</a>
          <a class="help-button" href="/help" target="_blank" rel="noopener">Help</a>
        </div>
      </div>
      <div class="task-area" id="task-strip" data-task-signature='{task_signature_json}'>
        {tasks_html}
      </div>
    </section>
  </main>
  <noscript><div class="placeholder">JavaScript disabled – refresh the page to see new messages.</div></noscript>
  {scripts}
</body>
</html>"""


def render_conversation_list(
    conversations: List[Dict],
    active_conversation: Optional[str],
) -> str:
    if not conversations:
        return "<p class='placeholder'>No conversations yet.</p>"
    return "\n".join(
        _render_history_item(item, active_conversation) for item in conversations
    )


def render_conversation_messages(
    entries: List[Dict],
    reward_map: Dict[str, int],
    tool_reward_map: Dict[str, int],
    conversation_id: Optional[str],
) -> str:
    if not conversation_id:
        return "<p class='placeholder'>Select or start a conversation.</p>"
    rendered = [
        _render_entry(entry, reward_map, tool_reward_map, conversation_id)
        for entry in entries
        if entry.get("type") != "label"
    ]
    if not rendered:
        return "<p class='placeholder'>No messages yet.</p>"
    return "\n".join(rendered)


def render_task_strip(
    tasks: List[TaskRecord], *, css_class: str = "", empty_html: str = ""
) -> str:
    if not tasks:
        return empty_html
    cards = "\n".join(_render_task_card(task) for task in tasks)
    lane_classes = ["task-lane"]
    if css_class:
        lane_classes.append(css_class)
    lane_class_attr = " ".join(lane_classes)
    return f"<div class=\"{lane_class_attr}\"><div class=\"task-strip\">{cards}</div></div>"


def _format_entry_content(value: Any) -> str:
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, indent=2, ensure_ascii=False, default=str)
        except TypeError:
            return json.dumps(json.loads(json.dumps(value, default=str)), indent=2)
    return str(value)


def _normalise_reasoning(value: Any) -> List[str]:
    parts: List[str] = []

    def _append(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, str):
            text = item.strip()
            if text:
                parts.append(text)
            return
        if isinstance(item, dict):
            for key in ("text", "content", "message"):
                if key in item:
                    _append(item[key])
                    return
            parts.append(json.dumps(item, ensure_ascii=False))
            return
        if isinstance(item, list):
            for sub in item:
                _append(sub)
            return
        parts.append(str(item))

    _append(value)
    return parts


def _render_history_item(item: Dict, active_conversation: Optional[str]) -> str:
    conversation_id = item["conversation_id"]
    title = escape(item.get("title") or item.get("summary") or conversation_id[:8])
    url = f"/?conversation={conversation_id}"
    classes = "active" if conversation_id == active_conversation else ""
    timestamp = escape(item.get("last_accessed", ""))
    return (
        f'<a class="{classes}" href="{url}"><strong>{title}</strong>'
        f"<span>{timestamp}</span></a>"
    )


def _render_entry(
    entry: Dict,
    reward_map: Dict[str, int],
    tool_reward_map: Dict[str, int],
    conversation_id: Optional[str],
) -> str:
    etype = entry.get("type")
    role = entry.get("role")
    entry_id = entry.get("id")
    header_text = f"{role.title()} · {entry.get('timestamp')}"
    reward_html = ""
    if conversation_id and etype == "completion":
        current_reward = reward_map.get(entry_id)
        reward_html = _render_reward_controls(
            conversation_id,
            entry_id,
            current_reward,
            target_type="completion",
        )
    actions: List[str] = []
    if reward_html:
        actions.append(reward_html)
    body_parts: List[str] = []
    if etype == "message":
        body_text = _format_entry_content(entry.get("content", ""))
        body_parts.append(f"<pre>{escape(body_text)}</pre>")
    elif etype == "metadata":
        body_text = _format_entry_content(entry.get("content", {}))
        body_parts.append(f"<pre>{escape(body_text)}</pre>")
    elif etype == "completion":
        content = entry.get("content") or {}
        text = escape(str(content.get("text", "")))
        raw_reasoning = content.get("reasoning_content")
        if raw_reasoning is None:
            raw_reasoning = content.get("reasoning") or []
        reasoning_segments = _normalise_reasoning(raw_reasoning)
        tool_calls = content.get("tool_calls") or []
        reasoning_html = ""
        reasoning_button = ""
        if reasoning_segments:
            reasoning_body = "".join(
                f"<pre>{escape(str(seg))}</pre>" for seg in reasoning_segments
            )
            reasoning_id = f"reasoning-{entry_id}"
            reasoning_html = (
                f"<details id=\"{reasoning_id}\" class=\"reasoning-details\" "
                "data-reasoning data-show-label=\"Show reasoning\" data-hide-label=\"Hide reasoning\" open>"
                "<summary>Reasoning trace</summary>"
                f"<div class=\"reasoning-content\">{reasoning_body}</div>"
                "</details>"
            )
            reasoning_button = (
                f"<button type=\"button\" class=\"reasoning-toggle\" data-target=\"{reasoning_id}\" aria-expanded=\"false\">Show reasoning</button>"
            )
            actions.insert(0, reasoning_button)
        tool_html = "".join(
            _render_tool_call(conversation_id, call, tool_reward_map)
            for call in tool_calls
        )
        if reasoning_html:
            body_parts.append(reasoning_html)
        if text:
            body_parts.append(f"<pre>{text}</pre>")
        if tool_html:
            body_parts.append(tool_html)
    elif etype == "tool_result":
        content = entry.get("content") or {}
        result = escape(json.dumps(content.get("result"), indent=2, default=str))
        body_parts.append(
            f"<details><summary>Tool Result · {escape(content.get('tool', ''))}</summary>"
            f"<pre>{result}</pre></details>"
        )
    else:
        body_text = _format_entry_content(entry.get("content", ""))
        body_parts.append(f"<pre>{escape(body_text)}</pre>")
    classes = f"message {escape(role or 'system')}"
    entry_attr = f' data-entry-id="{escape(entry_id)}"' if entry_id else ""
    header_html = (
        f'<header class="message-header"><span class="message-meta">{escape(header_text)}</span>'
    )
    if actions:
        header_html += f"<div class=\"message-actions\">{''.join(actions)}</div>"
    header_html += "</header>"
    body_html = ""
    if body_parts:
        body_html = f"<div class=\"message-body\">{''.join(body_parts)}</div>"
    return f'<article class="{classes}"{entry_attr}>{header_html}{body_html}</article>'


def _render_tool_call(
    conversation_id: Optional[str],
    call: Dict,
    _tool_reward_map: Dict[str, int],
) -> str:
    call_id = call.get("id") or ""
    name = escape(call.get("name") or "")
    args = escape(json.dumps(call.get("arguments"), indent=2, default=str))
    return f"""
    <details>
      <summary>Tool Call · {name}</summary>
      <pre>{args}</pre>
    </details>
    """


def _render_reward_controls(
    conversation_id: str,
    target_id: Optional[str],
    current_value: Optional[int],
    target_type: str,
) -> str:
    if not target_id:
        return ""
    labels = {2: "Great", 1: "Good", 0: "Neutral", -1: "Poor", -2: "Bad"}
    buttons = []
    for value in [-2, -1, 0, 1, 2]:
        label = labels[value]
        classes = "selected" if current_value == value else ""
        buttons.append(
            f"<button type='submit' name='reward' value='{value}' class='{classes}'>{label}</button>"
        )
    buttons_html = "".join(buttons)
    return f"""
    <form method="post" action="/conversation/{conversation_id}/label" class="label-actions">
      <input type="hidden" name="target_id" value="{escape(target_id)}" />
      <input type="hidden" name="target_type" value="{escape(target_type)}" />
      {buttons_html}
    </form>
    """


def render_prompt_form(
    conversation_id: Optional[str],
    agents: List[Dict],
) -> str:
    if not conversation_id:
        return "<p class='placeholder'>Create a conversation to start chatting.</p>"
    agent_aliases = [agent.get("alias", "") for agent in agents if agent.get("alias")]
    suggestions = escape(json.dumps(agent_aliases))
    hint = ""
    if agent_aliases:
        alias = agent_aliases[0]
        agent_name = next((agent.get("name") for agent in agents if agent.get("alias") == alias), alias)
        hint = (
            f"<p class=\"prompt-hint\">Tip: address <strong>@{escape(alias)}</strong> for {escape(agent_name)} or type @ to choose another agent.</p>"
        )
    return f"""
    <form method="post" action="/conversation/{conversation_id}/send" class="prompt">
      <div class="mention-helper" id="mention-helper" hidden></div>
      <div class="prompt-row">
        <textarea name="prompt" placeholder="Type your message… (use @alias to target agents)" required data-agent-names='{suggestions}'></textarea>
        <button type="submit">Send</button>
      </div>
      {hint}
    </form>
    """


def render_settings_form(settings: Dict, agents: List[Dict]) -> str:
    llama = settings.get("llama_cpp", {})
    agents_html = "".join(
        _render_agent_fields(index, agent) for index, agent in enumerate(agents)
    )
    return f"""
    <form method="post" action="/settings">
      <label>OpenAI-Compatible URL
        <input type="url" name="llama_base_url" value="{escape(llama.get('base_url', ''))}" required />
      </label>
      <label>API Key
        <input type="password" name="llama_api_key" value="{escape(llama.get('api_key', ''))}" />
      </label>
      <label>Default Model
        <input type="text" name="llama_model" value="{escape(llama.get('model', ''))}" required />
      </label>
      <div class="agent-grid">
        {agents_html}
      </div>
      <button type="submit">Save settings</button>
    </form>
    """


def render_settings_page(settings: Dict, agents: List[Dict], status: Dict[str, str]) -> str:
    form_html = render_settings_form(settings, agents)
    alias_list = "\n".join(
        f"<li><code>@{escape(agent.get('alias') or f'agent-{idx + 1}')}</code> → {escape(agent.get('name', f'Agent {idx + 1}'))}</li>"
        for idx, agent in enumerate(agents)
    ) or "<li>No custom agents yet.</li>"
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>Session Settings</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --border: #c7cad6;
      --accent: #3367d6;
      --muted: #657185;
      --panel: #ffffff;
      background: #f5f7fb;
    }}
    body {{
      margin: 0;
      padding: 1.5rem;
      background: #f5f7fb;
      color: #0f172a;
    }}
    main {{
      max-width: 820px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
    }}
    h1 {{
      margin: 0;
      font-size: 1.6rem;
    }}
    .status-badges {{
      display: flex;
      gap: 0.4rem;
      flex-wrap: wrap;
    }}
    .badge {{
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      border: 1px solid var(--border);
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge[data-state="ok"] {{
      background: #d9f0ff;
      color: #004b91;
    }}
    .badge[data-state="warn"] {{
      background: #ffe8d6;
      color: #a55300;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      box-shadow: 0 1px 2px rgba(10, 20, 40, 0.05);
    }}
    .panel h2 {{
      margin-top: 0;
      font-size: 1.05rem;
    }}
    form {{
      display: flex;
      flex-direction: column;
      gap: 1rem;
    }}
    label {{
      font-size: 0.85rem;
      font-weight: 600;
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }}
    input, textarea, select {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 0.5rem 0.6rem;
      font-size: 0.9rem;
      font-family: inherit;
      background: #fff;
    }}
    textarea {{
      min-height: 72px;
      resize: vertical;
    }}
    .agent-grid {{
      display: grid;
      gap: 0.75rem;
    }}
    .agent-card {{
      border: 1px dashed var(--border);
      border-radius: 8px;
      padding: 0.85rem;
      background: rgba(51, 103, 214, 0.04);
    }}
    button {{
      align-self: flex-start;
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      font-size: 0.85rem;
      cursor: pointer;
    }}
    nav a {{
      text-decoration: none;
      color: var(--accent);
      font-size: 0.85rem;
    }}
    ul.aliases {{
      padding-left: 1.2rem;
      color: var(--muted);
    }}
    ul.aliases li {{
      margin-bottom: 0.35rem;
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Session Settings</h1>
        <nav><a href="/">← Back to Chat</a> · <a href="/help" target="_blank" rel="noopener">Help</a></nav>
      </div>
      <div class="status-badges">
        <div class="badge" data-state="{escape(status.get('worker_state', 'warn'))}">Worker {escape(status.get('worker_label', 'offline'))}</div>
        <div class="badge" data-state="{escape(status.get('idle_state', 'ok'))}">{escape(status.get('idle_label', 'Active'))}</div>
        <div class="badge" data-state="{escape(status.get('llama_state', 'warn'))}">{escape(status.get('llama_label', 'LLM Unknown'))}</div>
      </div>
    </header>
    <section class="panel">
      <h2>Agent Mentions</h2>
      <p>Use <code>@alias</code> at the start of a message to address a specific agent. Available aliases:</p>
      <ul class="aliases">{alias_list}</ul>
    </section>
    <section class="panel">
      <h2>Configuration</h2>
      {form_html}
    </section>
  </main>
</body>
</html>"""
def _render_agent_fields(index: int, agent: Dict) -> str:
    name = escape(agent.get("name", f"Agent {index + 1}"))
    description = escape(agent.get("description", ""))
    prompt = escape(agent.get("system_prompt", ""))
    model = escape(agent.get("model", ""))
    temperature = escape(str(agent.get("temperature", 0.2)))
    context = escape(str(agent.get("context_size", 4096)))
    return f"""
      <section class="agent-card">
        <h3>Agent {index + 1}</h3>
        <label>Name
          <input type="text" name="agents_{index}_name" value="{name}" required />
        </label>
        <label>Description
          <input type="text" name="agents_{index}_description" value="{description}" />
        </label>
        <label>Model
          <input type="text" name="agents_{index}_model" value="{model}" />
        </label>
        <label>Temperature
          <input type="number" step="0.05" min="0" max="2" name="agents_{index}_temperature" value="{temperature}" />
        </label>
        <label>Context Size
          <input type="number" min="128" step="1" name="agents_{index}_context" value="{context}" />
        </label>
        <label>System Prompt
          <textarea name="agents_{index}_prompt">{prompt}</textarea>
        </label>
      </section>
    """


def _render_task_card(task: TaskRecord) -> str:
    classes = ["task-card"]
    if task.priority <= 1:
        classes.append("high")
    elif task.priority >= 9:
        classes.append("low")
    if task.status == "running":
        classes.append("running")
    elif task.status == "completed":
        classes.append("completed")
    elif task.status == "failed":
        classes.append("failed")
    title = escape(task.description or task.kind)
    priority_label = _priority_label(task.priority)
    status = escape(task.status.title())
    conversation = escape((task.conversation_id or "—")[:16])
    updated = escape(task.updated_at)
    detail_text = "" if task.detail is None else str(task.detail)
    preview = escape(detail_text[:80] + ("…" if detail_text and len(detail_text) > 80 else "")) if detail_text else ""
    detail_link = f"/tasks/{escape(task.id)}"
    preview_html = f"<p>{preview}</p>" if preview else ""
    return f"""
    <article class="{' '.join(classes)}">
      <h3>{title}</h3>
      <span>Priority: {priority_label}</span>
      <span>Status: {status}</span>
      <span>Conversation: {conversation}</span>
      <span>Updated: {updated}</span>
      {preview_html}
      <a class="task-action" href="{detail_link}" target="_blank" rel="noopener">Open details</a>
    </article>
    """


def _priority_label(priority: int) -> str:
    if priority <= 1:
        return "High"
    if priority >= 9:
        return "Low"
    return "Normal"


def render_help_page(agents: List[Dict]) -> str:
    alias_items = []
    for idx, agent in enumerate(agents, start=1):
        alias = agent.get("alias") or f"agent-{idx}"
        name = agent.get("name") or f"Agent {idx}"
        alias_items.append(
            f"<li><strong>{escape(name)}</strong> — mention <code>@{escape(alias)}</code></li>"
        )
    alias_section = (
        "<ul class=\"alias-list\">" + "\n".join(alias_items) + "</ul>"
        if alias_items
        else "<p>No custom agents yet. Mentions will use defaults like <code>@agent-1</code>.</p>"
    )
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>WebUI Help</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      --border: #ccc;
      --accent: #3367d6;
      --muted: #666;
    }}
    body {{
      margin: 0;
      padding: 1.5rem;
      background: #f7f8fb;
      color: #111;
      line-height: 1.55;
    }}
    h1 {{
      margin-top: 0;
      font-size: 1.4rem;
    }}
    h2 {{
      margin-top: 1.6rem;
      font-size: 1.1rem;
    }}
    section {{
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.2rem;
      margin-bottom: 1rem;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
    }}
    ul {{
      padding-left: 1.1rem;
    }}
    code {{
      background: rgba(0, 0, 0, 0.06);
      padding: 0.15rem 0.35rem;
      border-radius: 4px;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      font-size: 0.85rem;
    }}
    a {{
      color: var(--accent);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <h1>WebUI Quick Reference</h1>
  <section>
    <h2>Directing Agents</h2>
    <p>Start any message with <code>@alias</code> to route it to a specific agent. The tag is removed before the model sees your text.</p>
    {alias_section}
    <p>Tip: a space is inserted automatically after autocomplete so you can keep typing.</p>
  </section>
  <section>
    <h2>Conversation Workflow</h2>
    <ul>
      <li>Messages send asynchronously; the worker finishes completions even if you close the page.</li>
      <li>Reasoning steps and tool calls stay collapsed — expand them when you need details.</li>
      <li>Label assistant replies using the buttons beside each completion to capture feedback.</li>
    </ul>
  </section>
  <section>
    <h2>Priority Queue</h2>
    <ul>
      <li>Only active tasks and the last two completed jobs are shown; failed tasks are hidden once acknowledged.</li>
      <li>Cards move left to right from highest to lowest priority.</li>
      <li>Idle mode triggers background summarisation when you stop typing for 30 seconds.</li>
    </ul>
  </section>
  <section>
    <h2>Settings</h2>
    <ul>
      <li>Each agent has its own system prompt, model, and mention alias.</li>
      <li>Changes save immediately and feed the next request; use <code>@alias</code> to pick the agent inline.</li>
    </ul>
  </section>
    <p><a href="/">Back to the WebUI</a></p>
</body>
</html>"""


def render_task_detail_page(task: TaskRecord) -> str:
    payload = {
        "id": task.id,
        "kind": task.kind,
        "priority": task.priority,
        "status": task.status,
        "conversation_id": task.conversation_id,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "description": task.description,
        "detail": task.detail,
    }
    pretty = escape(json.dumps(payload, indent=2, default=str))
    title = escape(task.description or task.kind or task.id)
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>Task {title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      --border: #ccd2e1;
      --accent: #3367d6;
      --muted: #5c647a;
    }}
    body {{
      margin: 0;
      padding: 2rem;
      background: #f6f8fd;
      color: #0f172a;
    }}
    main {{
      max-width: 720px;
      margin: 0 auto;
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
    }}
    h1 {{
      margin-top: 0;
      font-size: 1.4rem;
      line-height: 1.3;
    }}
    dl {{
      display: grid;
      grid-template-columns: 140px 1fr;
      row-gap: 0.35rem;
      column-gap: 1rem;
      margin: 1rem 0 1.5rem;
    }}
    dt {{
      font-weight: 600;
      color: var(--muted);
    }}
    dd {{
      margin: 0;
    }}
    pre {{
      background: rgba(51, 103, 214, 0.08);
      border: 1px solid rgba(51, 103, 214, 0.2);
      border-radius: 8px;
      padding: 1rem;
      overflow: auto;
      font-size: 0.82rem;
      line-height: 1.35;
    }}
    a.back {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.45rem 0.75rem;
      border-radius: 6px;
      border: 1px solid var(--border);
      color: var(--accent);
      text-decoration: none;
      font-size: 0.82rem;
      margin-top: 1.25rem;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Task: {title}</h1>
    <dl>
      <dt>Status</dt><dd>{escape(task.status.title())}</dd>
      <dt>Priority</dt><dd>{escape(_priority_label(task.priority))}</dd>
      <dt>Conversation</dt><dd>{escape(task.conversation_id or '—')}</dd>
      <dt>Created</dt><dd>{escape(task.created_at)}</dd>
      <dt>Updated</dt><dd>{escape(task.updated_at)}</dd>
    </dl>
    <h2>Payload</h2>
    <pre>{pretty}</pre>
    <a class="back" href="/">← Back to dashboard</a>
  </main>
</body>
</html>"""
def _refresh_script() -> str:
    return """
    <script>
      (function(){
        const layout = document.getElementById('layout');
        const workerBadge = document.getElementById('worker-badge');
        const idleBadge = document.getElementById('idle-badge');
        const llamaBadge = document.getElementById('llama-badge');
        const conversationList = document.getElementById('conversation-list');
        const conversationHistory = document.getElementById('conversation-history');
        const conversationTitle = document.getElementById('conversation-title');
        const taskStrip = document.getElementById('task-strip');
        if (taskStrip && taskStrip.dataset.taskSignature && !taskStrip.dataset.signature) {
          taskStrip.dataset.signature = taskStrip.dataset.taskSignature;
        }
        const promptForm = document.querySelector('form.prompt');
        const promptArea = promptForm ? promptForm.querySelector('textarea[name=\"prompt\"]') : null;
        const promptContainer = promptForm ? promptForm.closest('.prompt-container') : null;
        const mentionHelper = document.getElementById('mention-helper');
        let pendingScroll = false;
        let refreshTimeout = null;
        let sendingPrompt = false;
        let knownEntryIds = [];
        let mentionActiveIndex = -1;
        let agentNames = [];
        function setAgentNames(names) {
          if (Array.isArray(names)) {
            agentNames = names;
          } else {
            agentNames = [];
          }
          if (layout) {
            layout.dataset.agents = JSON.stringify(agentNames);
          }
          if (!agentNames.length) {
            hideMentionHelper();
          }
        }
        if (layout) {
          try {
            const initial = JSON.parse(layout.dataset.agents || '[]');
            setAgentNames(initial);
          } catch (err) {
            setAgentNames([]);
          }
        }

        if (conversationHistory) {
          try {
            const initialIds = JSON.parse(conversationHistory.dataset.entryIds || '[]');
            if (Array.isArray(initialIds)) {
              knownEntryIds = initialIds.slice();
            }
          } catch (err) {
            knownEntryIds = Array.from(conversationHistory.querySelectorAll('[data-entry-id]'))
              .map(function(node){ return node.dataset.entryId; })
              .filter(function(id){ return !!id; });
          }
        }

        if (promptForm && conversationHistory) {
          promptForm.addEventListener('submit', function(event){
            if (typeof window.fetch !== 'function') {
              pendingScroll = true;
              return;
            }
            event.preventDefault();
            submitPrompt();
          });
        }

        if (promptArea && mentionHelper) {
          promptArea.addEventListener('keydown', function(event){
            if (!mentionHelper.hidden && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
              event.preventDefault();
              moveMentionFocus(event.key === 'ArrowDown' ? 1 : -1);
              return;
            }
            if (event.key === 'Enter' && !event.shiftKey) {
              if (!mentionHelper.hidden) {
                const active = mentionHelper.querySelector('button.active') || mentionHelper.querySelector('button[data-agent-name]');
                if (active && active.dataset.agentName) {
                  event.preventDefault();
                  applyMention(active.dataset.agentName);
                  return;
                }
              }
              event.preventDefault();
              if (typeof window.fetch === 'function') {
                submitPrompt();
              } else if (event.target.form) {
                event.target.form.submit();
              }
            }
            if (event.key === 'Tab' && !mentionHelper.hidden) {
              const first = mentionHelper.querySelector('button[data-agent-name]');
              if (first) {
                event.preventDefault();
                applyMention(first.dataset.agentName);
              }
            }
            if (event.key === '@') {
              window.requestAnimationFrame(function(){
                updateMentionSuggestions();
              });
            }
            if (event.key === 'Escape') {
              hideMentionHelper();
            }
          });
          promptArea.addEventListener('input', updateMentionSuggestions);
          promptArea.addEventListener('click', updateMentionSuggestions);
          promptArea.addEventListener('keyup', function(){
            updateMentionSuggestions();
          });
          promptArea.addEventListener('blur', function(){
            window.setTimeout(hideMentionHelper, 150);
          });
          mentionHelper.hidden = true;
          mentionHelper.addEventListener('mousedown', function(event){
            event.preventDefault();
          });
          mentionHelper.addEventListener('click', function(event){
            const target = event.target;
            if (target && target.dataset && target.dataset.agentName) {
              const buttons = Array.from(mentionHelper.querySelectorAll('button[data-agent-name]'));
              const idx = buttons.indexOf(target);
              if (idx >= 0) {
                setActiveMention(idx);
              }
              applyMention(target.dataset.agentName);
            }
          });
        }

        function hideMentionHelper(){
          if (!mentionHelper) return;
          mentionHelper.hidden = true;
          mentionHelper.innerHTML = '';
          if (promptContainer) {
            promptContainer.classList.remove('mention-visible');
          }
          mentionActiveIndex = -1;
        }

        async function submitPrompt(){
          if (!promptForm || !promptArea || sendingPrompt) return;
          const value = promptArea.value;
          if (!value || !value.trim()) {
            return;
          }
          if (typeof window.fetch !== 'function') {
            promptForm.submit();
            return;
          }
          const formData = new FormData(promptForm);
          const payload = new URLSearchParams();
          formData.forEach(function(val, key){
            if (typeof val === 'string') {
              payload.append(key, val);
            }
          });
          sendingPrompt = true;
          pendingScroll = true;
          try {
            const response = await fetch(promptForm.action, {
              method: 'POST',
              headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
              },
              body: payload.toString(),
            });
            if (!response.ok) {
              pendingScroll = false;
              console.error('Prompt submission failed', response.status);
              return;
            }
            let result = null;
            try {
              result = await response.json();
            } catch (err) {
              result = null;
            }
            if (result && result.ok === false) {
              pendingScroll = false;
              console.warn('Prompt rejected', result.error || 'Unknown error');
              return;
            }
            promptArea.value = '';
            hideMentionHelper();
            updateMentionSuggestions();
            await refreshState(true);
          } catch (error) {
            pendingScroll = false;
            console.error('Prompt submission failed', error);
          } finally {
            sendingPrompt = false;
          }
        }

        function setActiveMention(index){
          if (!mentionHelper) return;
          const buttons = Array.from(mentionHelper.querySelectorAll('button[data-agent-name]'));
          if (!buttons.length) {
            mentionActiveIndex = -1;
            return;
          }
          if (index < 0) {
            index = buttons.length - 1;
          }
          if (index >= buttons.length) {
            index = 0;
          }
          mentionActiveIndex = index;
          buttons.forEach(function(btn, i){
            if (i === mentionActiveIndex) {
              btn.classList.add('active');
              btn.setAttribute('aria-selected', 'true');
            } else {
              btn.classList.remove('active');
              btn.removeAttribute('aria-selected');
            }
          });
        }

        function moveMentionFocus(delta){
          if (!mentionHelper || mentionHelper.hidden) return;
          const buttons = mentionHelper.querySelectorAll('button[data-agent-name]');
          if (!buttons.length) return;
          const nextIndex = mentionActiveIndex === -1 ? (delta > 0 ? 0 : buttons.length - 1) : mentionActiveIndex + delta;
          setActiveMention(nextIndex);
        }

        function findMentionContext(){
          if (!promptArea) return null;
          if (typeof promptArea.selectionStart !== 'number' || typeof promptArea.selectionEnd !== 'number') {
            return null;
          }
          if (promptArea.selectionStart !== promptArea.selectionEnd) {
            return null;
          }
          const caret = promptArea.selectionStart;
          const upto = promptArea.value.slice(0, caret);
          const match = upto.match(/(^|\\s)@([a-z0-9\\-]*)$/i);
          if (!match) {
            return null;
          }
          const fragment = match[2] || '';
          const start = caret - fragment.length - 1;
          if (start < 0) {
            return null;
          }
          return { start: start, caret: caret, fragment: fragment };
        }

        function applyMention(name){
          if (!promptArea) return;
          const context = findMentionContext();
          if (!context) {
            hideMentionHelper();
            return;
          }
          const before = promptArea.value.slice(0, context.start);
          const after = promptArea.value.slice(context.caret);
          const mention = '@' + name + ' ';
          promptArea.value = before + mention + after;
          const newCaret = before.length + mention.length;
          promptArea.setSelectionRange(newCaret, newCaret);
          hideMentionHelper();
        }

        function updateMentionSuggestions(){
          if (!promptArea || !mentionHelper) return;
          if (!agentNames.length) {
            hideMentionHelper();
            return;
          }
          const context = findMentionContext();
          if (!context) {
            hideMentionHelper();
            return;
          }
          const prefix = context.fragment.toLowerCase();
          const matches = agentNames.filter(function(name){
            return name.toLowerCase().startsWith(prefix);
          });
          if (!matches.length) {
            hideMentionHelper();
            return;
          }
          mentionHelper.hidden = false;
          mentionHelper.innerHTML = '';
          if (promptContainer) {
            promptContainer.classList.add('mention-visible');
          }
          const frag = document.createDocumentFragment();
          matches.forEach(function(name){
            const button = document.createElement('button');
            button.type = 'button';
            button.dataset.agentName = name;
            button.textContent = '@' + name;
            frag.appendChild(button);
          });
          mentionHelper.appendChild(frag);
          const buttons = mentionHelper.querySelectorAll('button');
          mentionActiveIndex = buttons.length ? 0 : -1;
          setActiveMention(mentionActiveIndex);
          const areaRect = promptArea.getBoundingClientRect();
          const containerRect = promptContainer ? promptContainer.getBoundingClientRect() : areaRect;
          const baseLeft = areaRect.left - containerRect.left;
          const gap = 6;
          const left = baseLeft + (promptContainer ? promptContainer.scrollLeft : 0) + 4;
          const width = Math.max(150, promptArea.offsetWidth - 8);
          const height = mentionHelper.offsetHeight || 0;
          const scrollOffset = promptContainer ? promptContainer.scrollTop : 0;
          let top = areaRect.top - containerRect.top - height - gap + scrollOffset;
          if (top < 0) {
            top = scrollOffset;
          }
          mentionHelper.style.bottom = 'auto';
          mentionHelper.style.top = top + 'px';
          mentionHelper.style.left = left + 'px';
          mentionHelper.style.maxWidth = width + 'px';
        }

        function prepareReasoning(scope){
          const root = scope || document;
          const detailsList = root.querySelectorAll('details[data-reasoning]');
          detailsList.forEach(function(detail){
            if (detail.dataset.prepared === '1') return;
            detail.dataset.prepared = '1';
            if (!detail.id) {
              detail.id = 'reasoning-' + Math.random().toString(36).slice(2);
            }
            const toggle = document.querySelector('button.reasoning-toggle[data-target="' + detail.id + '"]');
            const summary = detail.querySelector('summary');
            const showLabel = detail.dataset.showLabel || 'Show reasoning';
            const hideLabel = detail.dataset.hideLabel || 'Hide reasoning';

            function collapse(){
              detail.removeAttribute('open');
              detail.dataset.state = 'collapsed';
              if (toggle) {
                toggle.textContent = showLabel;
                toggle.setAttribute('aria-expanded', 'false');
              }
            }

            function expand(){
              detail.setAttribute('open', '');
              detail.dataset.state = 'expanded';
              if (toggle) {
                toggle.textContent = hideLabel;
                toggle.setAttribute('aria-expanded', 'true');
              }
            }

            if (summary && toggle) {
              summary.classList.add('sr-only');
              summary.setAttribute('aria-hidden', 'true');
            }

            detail.addEventListener('toggle', function(){
              const isOpen = detail.hasAttribute('open');
              if (toggle) {
                toggle.textContent = isOpen ? hideLabel : showLabel;
                toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
              }
            });

            collapse();

            if (toggle) {
              toggle.addEventListener('click', function(){
                if (detail.hasAttribute('open')) {
                  collapse();
                } else {
                  expand();
                }
              });
            } else if (summary) {
              summary.classList.remove('sr-only');
              summary.removeAttribute('aria-hidden');
              expand();
            }
          });
        }

        const interval = 5000;

        function scheduleRefresh(){
          if (refreshTimeout) {
            window.clearTimeout(refreshTimeout);
          }
          refreshTimeout = window.setTimeout(function(){
            refreshState(false);
          }, interval);
        }

        async function refreshStatus(){
          try {
            const response = await fetch('/status');
            if (!response.ok) throw new Error('Network response was not ok');
            const data = await response.json();
            if (workerBadge) {
              workerBadge.dataset.state = data.worker_state;
              workerBadge.textContent = 'Worker ' + data.worker_label;
            }
            if (idleBadge) {
              idleBadge.dataset.state = data.idle_state;
              idleBadge.textContent = data.idle_label;
            }
          } catch (error) {
            pendingScroll = false;
            if (workerBadge) {
              workerBadge.dataset.state = 'warn';
              workerBadge.textContent = 'Worker offline';
            }
            if (llamaBadge) {
              llamaBadge.dataset.state = 'warn';
              llamaBadge.textContent = 'LLM Offline';
            }
          } finally {
            window.setTimeout(refreshStatus, interval);
          }
        }
        refreshStatus();

        async function refreshLlama(){
          try {
            const response = await fetch('/health/llama');
            if (!response.ok) throw new Error('Health check failed');
            const data = await response.json();
            if (llamaBadge) {
              llamaBadge.dataset.state = data.status || 'warn';
              llamaBadge.textContent = data.label || 'LLM Status';
            }
          } catch (error) {
            if (llamaBadge) {
              llamaBadge.dataset.state = 'warn';
              llamaBadge.textContent = 'LLM Offline';
            }
          } finally {
            window.setTimeout(refreshLlama, interval);
          }
        }
        refreshLlama();

        prepareReasoning(document);

        async function refreshState(force){
          if (refreshTimeout) {
            window.clearTimeout(refreshTimeout);
            refreshTimeout = null;
          }
          if (!layout) {
            scheduleRefresh();
            return;
          }
          const conversationId = layout.dataset.activeConversation || '';
          const query = conversationId ? ('?conversation=' + encodeURIComponent(conversationId)) : '';
          try {
            const response = await fetch('/state' + query, { headers: { 'Accept': 'application/json' } });
            if (!response.ok) throw new Error('Network response was not ok');
            const data = await response.json();
            if (conversationList && data.history_html !== undefined) {
              conversationList.innerHTML = data.history_html;
            }
            const messageIds = Array.isArray(data.entry_ids) ? data.entry_ids : null;
            if (conversationHistory && data.messages_html !== undefined) {
              let appended = false;
              if (messageIds && knownEntryIds.length && knownEntryIds.length <= messageIds.length) {
                appended = knownEntryIds.every(function(id, idx){
                  return id === messageIds[idx];
                });
              }
              if (appended && messageIds && messageIds.length > knownEntryIds.length) {
                const temp = document.createElement('div');
                temp.innerHTML = data.messages_html;
                const nodes = temp.querySelectorAll('[data-entry-id]');
                nodes.forEach(function(node, idx){
                  if (idx >= knownEntryIds.length) {
                    conversationHistory.appendChild(node);
                    prepareReasoning(node);
                  }
                });
              } else if (!(appended && messageIds && messageIds.length === knownEntryIds.length)) {
                conversationHistory.innerHTML = data.messages_html;
                prepareReasoning(conversationHistory);
              }
              if (messageIds) {
                knownEntryIds = messageIds.slice();
              } else {
                knownEntryIds = Array.from(conversationHistory.querySelectorAll('[data-entry-id]'))
                  .map(function(node){ return node.dataset.entryId; })
                  .filter(function(id){ return !!id; });
              }
              conversationHistory.dataset.entryIds = JSON.stringify(knownEntryIds);
              conversationHistory.dataset.lastEntryId = knownEntryIds.length ? knownEntryIds[knownEntryIds.length - 1] : '';
              if (pendingScroll) {
                conversationHistory.scrollTop = conversationHistory.scrollHeight;
                pendingScroll = false;
              }
            } else if (pendingScroll) {
              pendingScroll = false;
            }
            if (conversationTitle && data.conversation_title) {
              conversationTitle.textContent = data.conversation_title;
            }
            if (layout && data.active_conversation !== undefined) {
              layout.dataset.activeConversation = data.active_conversation || '';
            }
            if (taskStrip && data.tasks_html !== undefined) {
              const newSignature = JSON.stringify(data.tasks_signature || []);
              const currentSignature = taskStrip.dataset.signature || taskStrip.dataset.taskSignature || '';
              if (newSignature !== currentSignature) {
                taskStrip.innerHTML = data.tasks_html;
                taskStrip.dataset.signature = newSignature;
                taskStrip.dataset.taskSignature = newSignature;
              }
            }
            if (data.status) {
              if (workerBadge) {
                workerBadge.dataset.state = data.status.worker_state;
                workerBadge.textContent = 'Worker ' + data.status.worker_label;
              }
              if (idleBadge) {
                idleBadge.dataset.state = data.status.idle_state;
                idleBadge.textContent = data.status.idle_label;
              }
              if (llamaBadge && data.status.llama_state) {
                llamaBadge.dataset.state = data.status.llama_state;
                llamaBadge.textContent = data.status.llama_label || 'LLM Status';
              }
            }
            if (data.agents) {
              setAgentNames(data.agents);
              updateMentionSuggestions();
            }
          } catch (error) {
            pendingScroll = false;
            if (workerBadge) {
              workerBadge.dataset.state = 'warn';
              workerBadge.textContent = 'Worker offline';
            }
            if (llamaBadge) {
              llamaBadge.dataset.state = 'warn';
              llamaBadge.textContent = 'LLM Offline';
            }
          } finally {
            scheduleRefresh();
          }
        }

        refreshState(false);
      })();
    </script>
    """
