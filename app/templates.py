from __future__ import annotations

import json
from html import escape
from typing import Dict, List, Optional

from .tasks import TaskRecord


def render_dashboard(
    *,
    conversations: List[Dict],
    active_conversation: Optional[str],
    conversation_entries: List[Dict],
    reward_map: Dict[str, int],
    tool_reward_map: Dict[str, int],
    conversation_title: str,
    settings: Dict,
    agents: List[Dict],
    tasks: List[TaskRecord],
    status: Dict[str, str],
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
    tasks_html = render_task_strip(tasks)
    scripts = _refresh_script()
    active_attr = escape(active_conversation or "")
    title_html = escape(conversation_title or "Conversation")

    prompt_html = render_prompt_form(active_conversation, agents)
    settings_html = render_settings_form(settings, agents)

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
      grid-template-columns: 220px 1fr 280px;
      grid-template-rows: 1fr 150px;
      grid-template-areas:
        "history chat settings"
        "queue queue queue";
      gap: 0.5rem;
      padding: 0.5rem;
      box-sizing: border-box;
      overflow: hidden;
    }}
    main > * {{
      min-height: 0;
    }}
    .settings-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.4rem;
      margin-bottom: 0.4rem;
      flex-wrap: wrap;
    }}
    .status-badges {{
      display: flex;
      gap: 0.35rem;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-start;
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
    .message h3 {{
      margin: 0 0 0.35rem;
      font-size: 0.85rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .message pre {{
      margin: 0;
      white-space: pre-wrap;
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
      background: rgba(0, 0, 0, 0.03);
      padding: 0.5rem;
      border-radius: 4px;
    }}
    .message details {{
      margin-top: 0.5rem;
      border: 1px dashed var(--border);
      border-radius: 4px;
      padding: 0.35rem 0.5rem;
      background: rgba(0,0,0,0.02);
    }}
    .label-actions {{
      display: flex;
      gap: 0.25rem;
      margin-top: 0.5rem;
    }}
    .label-actions button {{
      flex: 1;
      font-size: 0.75rem;
      padding: 0.25rem;
      border-radius: 4px;
      border: 1px solid var(--border);
      background: #fff;
      cursor: pointer;
    }}
    .label-actions button.selected {{
      background: #d6f5d6;
      border-color: #36a536;
      font-weight: 600;
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
    }}
    form.prompt button {{
      align-self: flex-end;
      padding: 0.35rem 0.9rem;
      border-radius: 6px;
      border: 1px solid var(--accent);
      background: var(--accent);
      color: #fff;
      cursor: pointer;
    }}
    aside {{
      grid-area: settings;
      background: var(--panel-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 0.6rem 0.7rem;
      overflow-y: auto;
      min-height: 0;
    }}
    aside h2 {{
      font-size: 0.95rem;
      margin-top: 0;
    }}
    aside form {{
      display: flex;
      flex-direction: column;
      gap: 0.65rem;
    }}
    aside label {{
      font-size: 0.8rem;
      font-weight: 600;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
    }}
    aside input, aside textarea, aside select {{
      border: 1px solid var(--border);
      padding: 0.3rem 0.45rem;
      border-radius: 4px;
      font-family: inherit;
      font-size: 0.85rem;
    }}
    aside textarea {{
      min-height: 60px;
      resize: vertical;
    }}
    .agent-grid {{
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }}
    .agent-card {{
      border: 1px dashed var(--border);
      border-radius: 6px;
      padding: 0.6rem 0.75rem;
      background: rgba(0,0,0,0.02);
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
    .task-strip {{
      display: flex;
      gap: 0.45rem;
      overflow-x: auto;
      padding-bottom: 0.2rem;
      margin-bottom: 0.2rem;
    }}
    .task-card {{
      flex: 0 0 190px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--panel-bg);
      padding: 0.5rem 0.6rem;
      font-size: 0.78rem;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
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
      margin: 0 0 0.35rem;
      font-size: 0.85rem;
    }}
    .task-card span {{
      color: var(--muted);
      font-size: 0.72rem;
    }}
    .task-card p {{
      margin: 0.25rem 0 0;
      font-size: 0.75rem;
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
      <div class="history" id="conversation-history">
        {messages_html}
      </div>
      <div class="prompt-container">
        {prompt_html}
      </div>
    </section>
    <aside>
      <div class="settings-header">
        <a class="help-button" href="/help" target="_blank" rel="noopener">Help</a>
        <div class="status-badges">
          <div class="badge" id="worker-badge" data-state="{escape(status.get('worker_state', 'warn'))}">Worker {escape(status.get('worker_label', 'offline'))}</div>
          <div class="badge" id="idle-badge" data-state="{escape(status.get('idle_state', 'ok'))}">{escape(status.get('idle_label', 'Active'))}</div>
        </div>
      </div>
      <h2>Session Settings</h2>
      {settings_html}
    </aside>
    <section class="queue">
      <div class="queue-header">
        <h2>Priority Queue</h2>
        <small>Updates automatically</small>
      </div>
      <div class="task-strip" id="task-strip">
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


def render_task_strip(tasks: List[TaskRecord]) -> str:
    if not tasks:
        return "<div class='empty'>No queued work.</div>"
    return "\n".join(_render_task_card(task) for task in tasks)


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
    header = f"{role.title()} · {entry.get('timestamp')}"
    reward_html = ""
    if conversation_id and etype == "completion":
        current_reward = reward_map.get(entry_id)
        reward_html = _render_reward_controls(
            conversation_id,
            entry_id,
            current_reward,
            target_type="completion",
        )
    body = ""
    if etype == "message":
        body = f"<pre>{escape(str(entry.get('content', '')))}</pre>"
    elif etype == "completion":
        content = entry.get("content") or {}
        text = escape(str(content.get("text", "")))
        reasoning_segments = content.get("reasoning") or []
        tool_calls = content.get("tool_calls") or []
        reasoning_html = "".join(
            f"<details><summary>Reasoning</summary><pre>{escape(seg)}</pre></details>"
            for seg in reasoning_segments
        )
        tool_html = "".join(
            _render_tool_call(conversation_id, call, tool_reward_map)
            for call in tool_calls
        )
        body = f"<pre>{text}</pre>{reasoning_html}{tool_html}"
    elif etype == "tool_result":
        content = entry.get("content") or {}
        result = escape(json.dumps(content.get("result"), indent=2, default=str))
        body = (
            f"<details><summary>Tool Result · {escape(content.get('tool', ''))}</summary>"
            f"<pre>{result}</pre></details>"
        )
    else:
        body = f"<pre>{escape(str(entry.get('content', '')))}</pre>"
    classes = f"message {escape(role or 'system')}"
    return f'<article class="{classes}"><h3>{escape(header)}{reward_html}</h3>{body}</article>'


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
    return f"""
    <form method="post" action="/conversation/{conversation_id}/send" class="prompt">
      <textarea name="prompt" placeholder="Type your message..." required data-agent-names='{suggestions}'></textarea>
      <div class="mention-helper" id="mention-helper" hidden></div>
      <button type="submit">Send</button>
    </form>
    """


def render_settings_form(settings: Dict, agents: List[Dict]) -> str:
    llama = settings.get("llama_cpp", {})
    agents_html = "".join(
        _render_agent_fields(index, agent) for index, agent in enumerate(agents)
    )
    return f"""
    <form method="post" action="/settings">
      <label>System Prompt
        <textarea name="system_prompt">{escape(settings.get("system_prompt", ""))}</textarea>
      </label>
      <label>OpenAI-Compatible URL
        <input type="url" name="llama_base_url" value="{escape(llama.get('base_url', ''))}" required />
      </label>
      <label>API Key
        <input type="password" name="llama_api_key" value="{escape(llama.get('api_key', ''))}" />
      </label>
      <label>Default Model
        <input type="text" name="llama_model" value="{escape(llama.get('model', ''))}" required />
      </label>
      <label>Temperature
        <input type="number" step="0.05" min="0" max="2" name="llama_temperature" value="{escape(str(llama.get('temperature', 0.2)))}" />
      </label>
      <div class="agent-grid">
        {agents_html}
      </div>
      <button type="submit">Save settings</button>
    </form>
    """


def _render_agent_fields(index: int, agent: Dict) -> str:
    name = escape(agent.get("name", f"Agent {index + 1}"))
    description = escape(agent.get("description", ""))
    prompt = escape(agent.get("system_prompt", ""))
    model = escape(agent.get("model", ""))
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
    detail_html = f"<p>{escape(task.detail)}</p>" if task.detail else ""
    return f"""
    <article class="{' '.join(classes)}">
      <h3>{title}</h3>
      <span>Priority: {priority_label}</span>
      <span>Status: {status}</span>
      <span>Conversation: {conversation}</span>
      <span>Updated: {updated}</span>
      {detail_html}
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
def _refresh_script() -> str:
    return """
    <script>
      (function(){
        const layout = document.getElementById('layout');
        const workerBadge = document.getElementById('worker-badge');
        const idleBadge = document.getElementById('idle-badge');
        const conversationList = document.getElementById('conversation-list');
        const conversationHistory = document.getElementById('conversation-history');
        const conversationTitle = document.getElementById('conversation-title');
        const taskStrip = document.getElementById('task-strip');
        const promptForm = document.querySelector('form.prompt');
        const promptArea = promptForm ? promptForm.querySelector('textarea[name=\"prompt\"]') : null;
        const mentionHelper = document.getElementById('mention-helper');

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

        if (promptForm && conversationHistory) {
          promptForm.addEventListener('submit', function(){
            conversationHistory.scrollTop = conversationHistory.scrollHeight;
          });
        }

        if (promptArea && mentionHelper) {
          promptArea.addEventListener('keydown', function(event){
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              event.target.form.submit();
            }
            if (event.key === 'Tab' && !mentionHelper.hidden) {
              const first = mentionHelper.querySelector('button[data-agent-name]');
              if (first) {
                event.preventDefault();
                applyMention(first.dataset.agentName);
              }
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
              applyMention(target.dataset.agentName);
            }
          });
        }

        function hideMentionHelper(){
          if (!mentionHelper) return;
          mentionHelper.hidden = true;
          mentionHelper.innerHTML = '';
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
          const value = promptArea.value;
          const upto = value.slice(0, caret);
          let start = -1;
          for (let i = upto.length - 1; i >= 0; i--) {
            const ch = upto[i];
            if (ch === '@') {
              start = i;
              break;
            }
            if (ch === '\\n') {
              break;
            }
          }
          if (start === -1) {
            return null;
          }
          if (start > 0 && /\\S/.test(upto[start - 1])) {
            return null;
          }
          const fragment = upto.slice(start + 1);
          if (/\\s/.test(fragment)) {
            return null;
          }
          if (!/^[a-z0-9\\-]*$/i.test(fragment)) {
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
          matches.forEach(function(name){
            const button = document.createElement('button');
            button.type = 'button';
            button.dataset.agentName = name;
            button.textContent = '@' + name;
            mentionHelper.appendChild(button);
          });
          const top = promptArea.offsetTop + promptArea.offsetHeight + 6;
          const left = promptArea.offsetLeft + 4;
          const width = Math.max(150, promptArea.offsetWidth - 8);
          mentionHelper.style.top = top + 'px';
          mentionHelper.style.left = left + 'px';
          mentionHelper.style.maxWidth = width + 'px';
        }

        const interval = 5000;

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
            if (workerBadge) {
              workerBadge.dataset.state = 'warn';
              workerBadge.textContent = 'Worker offline';
            }
          } finally {
            window.setTimeout(refreshStatus, interval);
          }
        }
        refreshStatus();

        async function refreshState(){
          if (!layout) {
            window.setTimeout(refreshState, interval);
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
            if (conversationHistory && data.messages_html !== undefined) {
              conversationHistory.innerHTML = data.messages_html;
            }
            if (conversationTitle && data.conversation_title) {
              conversationTitle.textContent = data.conversation_title;
            }
            if (layout && data.active_conversation !== undefined) {
              layout.dataset.activeConversation = data.active_conversation || '';
            }
            if (taskStrip && data.tasks_html !== undefined) {
              taskStrip.innerHTML = data.tasks_html;
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
            }
            if (data.agents) {
              setAgentNames(data.agents);
              updateMentionSuggestions();
            }
          } catch (error) {
            if (workerBadge) {
              workerBadge.dataset.state = 'warn';
              workerBadge.textContent = 'Worker offline';
            }
          } finally {
            window.setTimeout(refreshState, interval);
          }
        }

        refreshState();
      })();
    </script>
    """
