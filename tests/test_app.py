import multiprocessing
import socket
import time
from pathlib import Path
from typing import Tuple
import sys

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
