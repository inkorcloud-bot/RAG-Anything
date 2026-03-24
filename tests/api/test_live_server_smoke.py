"""Black-box HTTP smoke tests.

Start the API server in a real OS thread (real TCP socket) and exercise it via
urllib — no TestClient, no ASGI transport shortcut.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from raganything.api.app import create_app


# ---------------------------------------------------------------------------
# Minimal fakes — only the interface surfaces touched by the smoke routes
# ---------------------------------------------------------------------------

class _DocStatus:
    async def get_all_status_counts(self) -> dict:
        return {}


class _LightRAG:
    def __init__(self) -> None:
        self.doc_status = _DocStatus()


class _FakeRAG:
    def __init__(self) -> None:
        self.lightrag = _LightRAG()
        self.pipeline_status = {
            "busy": False,
            "job_name": None,
            "job_start": None,
            "docs": 0,
            "batchs": 0,
            "cur_batch": 0,
            "request_pending": 0,
            "latest_message": "",
            "history_messages": [],
            "scan_disabled": False,
            "update_status": {},
        }


# ---------------------------------------------------------------------------
# Fixture: one real server for the whole module
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_base_url():
    """Yield the base URL of a real uvicorn server running in a daemon thread."""
    port = _free_port()
    app = create_app()
    app.state.rag = _FakeRAG()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(f"{base}/openapi.json", timeout=1)
            break
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        pytest.fail("Live server did not start within 10 s")

    yield base

    server.should_exit = True
    thread.join(timeout=5)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_openapi_json_reachable_over_real_http(live_base_url):
    status, body = _get(f"{live_base_url}/openapi.json")
    assert status == 200
    payload = json.loads(body)
    assert "openapi" in payload


def test_swagger_docs_ui_reachable_over_real_http(live_base_url):
    status, body = _get(f"{live_base_url}/docs")
    assert status == 200
    assert b"swagger" in body.lower()


def test_documents_status_counts_reachable_over_real_http(live_base_url):
    status, body = _get(f"{live_base_url}/documents/status_counts")
    assert status == 200
    payload = json.loads(body)
    assert "status_counts" in payload


def test_documents_pipeline_status_reachable_over_real_http(live_base_url):
    status, body = _get(f"{live_base_url}/documents/pipeline_status")
    assert status == 200
    payload = json.loads(body)
    assert "busy" in payload
