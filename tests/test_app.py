import multiprocessing
import random
import socket
import string
import time
from pathlib import Path
from typing import Tuple
import sys
from urllib.parse import parse_qs, urlparse

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import uvicorn  # type: ignore
except ImportError:  # pragma: no cover - environment-dependent
    uvicorn = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _run_server(port: int, project_root: Path) -> None:
    import os
    import sys

    sys.path.insert(0, str(project_root))
    os.chdir(project_root)

    from app.main import app  # local import to honour modified sys.path

    if uvicorn is None:
        raise RuntimeError("uvicorn is required to run this server process.")

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
    )


@pytest.fixture(scope="module")
def http_session() -> Tuple[requests.Session, str]:
    if uvicorn is None:
        import asyncio
        from urllib.parse import urlparse

        from app.main import app

        class InlineClient(requests.Session):
            def __init__(self) -> None:
                super().__init__()
                self.base_url = "http://testserver"

            def request(self, method, url, **kwargs):  # type: ignore[override]
                parsed = urlparse(url)
                path = parsed.path or "/"
                query = parsed.query.encode("utf-8")
                headers = [
                    (b"accept", b"*/*"),
                ]
                scope = {
                    "type": "http",
                    "http_version": "1.1",
                    "method": method.upper(),
                    "scheme": parsed.scheme or "http",
                    "path": path,
                    "raw_path": path.encode("utf-8"),
                    "query_string": query,
                    "headers": headers,
                    "server": (parsed.hostname or "testserver", parsed.port or 80),
                    "client": ("testclient", 50000),
                }
                body = kwargs.get("data") or kwargs.get("content") or b""
                if isinstance(body, str):
                    body = body.encode("utf-8")
                request_messages = [
                    {
                        "type": "http.request",
                        "body": body,
                        "more_body": False,
                    }
                ]

                async def receive() -> dict:
                    return request_messages.pop(0) if request_messages else {"type": "http.disconnect"}

                collected: list[dict] = []

                async def send(message: dict) -> None:
                    collected.append(message)

                asyncio.run(app(scope, receive, send))

                status = 500
                response_headers = requests.structures.CaseInsensitiveDict()
                chunks: list[bytes] = []
                for message in collected:
                    if message["type"] == "http.response.start":
                        status = message["status"]
                        for header_key, header_value in message.get("headers", []):
                            response_headers[header_key.decode("latin-1")] = header_value.decode("latin-1")
                    elif message["type"] == "http.response.body":
                        chunks.append(message.get("body", b""))
                response = requests.Response()
                response.status_code = status
                response._content = b"".join(chunks)
                response.url = url
                response.headers = response_headers
                if "content-type" in response_headers:
                    response.encoding = requests.utils.get_encoding_from_headers(response_headers)
                return response

        client = InlineClient()
        try:
            yield client, client.base_url  # type: ignore[return-value]
        finally:
            client.close()
        return

    project_root = Path(__file__).resolve().parents[1]
    port = _find_free_port()
    process = multiprocessing.Process(
        target=_run_server,
        args=(port, project_root),
        daemon=False,
    )
    process.start()

    session = requests.Session()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            response = session.get(base_url, timeout=1)
        except requests.RequestException:
            time.sleep(0.1)
            continue
        if response.status_code == 200:
            break
    else:
        process.terminate()
        process.join(timeout=2)
        pytest.fail("Server did not start within timeout.")

    yield session, base_url

    session.close()
    process.terminate()
    process.join(timeout=2)


def test_dashboard_served(http_session: Tuple[requests.Session, str]) -> None:
    session, base_url = http_session
    response = session.get(base_url, timeout=2)
    assert response.status_code == 200
    assert "Minimal LLM WebUI" in response.text


def _random_prompt(aliases: list[str]) -> str:
    body = "".join(random.choice(string.ascii_letters + string.digits + " .,?!") for _ in range(random.randint(5, 80)))
    if aliases and random.random() < 0.5:
        return f"@{random.choice(aliases)} {body}"
    return body


def _random_settings_payload(base_url: str, aliases: list[str]) -> dict[str, str]:
    data: dict[str, str] = {
        "llama_base_url": f"http://localhost:{random.randint(1000, 65000)}/api",
        "llama_api_key": _random_text(24),
        "llama_model": _random_text(12),
    }
    # ensure four agents worth of data
    for idx in range(4):
        data[f"agents_{idx}_name"] = _random_text(10)
        data[f"agents_{idx}_description"] = _random_text(20)
        data[f"agents_{idx}_model"] = _random_text(8)
        data[f"agents_{idx}_prompt"] = _random_text(60)
        data[f"agents_{idx}_temperature"] = f"{random.uniform(0.0, 1.5):.2f}"
        data[f"agents_{idx}_context"] = str(random.randint(1024, 8192))
    return data


def _random_text(length: int) -> str:
    alphabet = string.ascii_letters + string.digits + " -_.,?"
    return "".join(random.choice(alphabet) for _ in range(random.randint(0, length)))


def test_ui_fuzz(http_session: Tuple[requests.Session, str]) -> None:
    random.seed(1)
    session, base_url = http_session
    base = base_url.rstrip("/")

    # start a conversation
    resp = session.post(f"{base}/conversation/new", timeout=3)
    assert resp.status_code < 500
    conversation_id = None
    if resp.history:
        final_url = resp.url
    else:
        final_url = resp.request.url
    query = parse_qs(urlparse(final_url).query)
    conversation_id = (query.get("conversation") or [None])[0]
    if not conversation_id:
        state = session.get(f"{base}/state", timeout=3).json()
        conversation_id = state.get("active_conversation")
    assert conversation_id, "Failed to initialise conversation for fuzz tests"

    def refresh_aliases() -> list[str]:
        resp_state = session.get(
            f"{base}/state", params={"conversation": conversation_id}, timeout=3
        )
        assert resp_state.status_code < 500
        data = resp_state.json()
        return data.get("agents", []) or []

    aliases = refresh_aliases()

    actions = [
        "get_root",
        "get_conversation",
        "get_status",
        "get_state",
        "get_help",
        "get_llama_health",
        "post_message",
        "post_settings",
    ]

    for _ in range(25):
        action = random.choice(actions)
        if action == "get_root":
            resp = session.get(base, timeout=3)
            assert resp.status_code < 500
            assert "<!DOCTYPE html>" in resp.text
        elif action == "get_conversation":
            resp = session.get(f"{base}/", params={"conversation": conversation_id}, timeout=3)
            assert resp.status_code < 500
        elif action == "get_status":
            resp = session.get(f"{base}/status", timeout=3)
            assert resp.status_code < 500
            data = resp.json()
            assert "worker_state" in data
        elif action == "get_state":
            resp = session.get(
                f"{base}/state", params={"conversation": conversation_id}, timeout=3
            )
            assert resp.status_code < 500
            data = resp.json()
            assert data.get("active_conversation") == conversation_id
        elif action == "get_help":
            resp = session.get(f"{base}/help", timeout=3)
            assert resp.status_code < 500
            assert "WebUI Quick Reference" in resp.text
        elif action == "get_llama_health":
            resp = session.get(f"{base}/health/llama", timeout=3)
            assert resp.status_code < 500
            data = resp.json()
            assert "status" in data
        elif action == "post_message":
            prompt = _random_prompt(aliases)
            resp = session.post(
                f"{base}/conversation/{conversation_id}/send",
                data={"prompt": prompt},
                timeout=5,
            )
            assert resp.status_code < 500
            aliases = refresh_aliases()
        elif action == "post_settings":
            payload = _random_settings_payload(base, aliases)
            resp = session.post(f"{base}/settings", data=payload, timeout=5)
            assert resp.status_code < 500
            aliases = refresh_aliases()
        else:
            raise AssertionError(f"Unknown action {action}")
