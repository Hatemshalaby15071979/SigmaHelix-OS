"""The local web interface: token gate, JSON API, no path escapes."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from sigmahelix.app import agent as agent_module
from sigmahelix.app.webui.server import AppState, Handler


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    state = AppState()
    handler = type("TestHandler", (Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, state.token
    httpd.shutdown()
    httpd.server_close()


def call(base, path, token=None, payload=None, origin=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if payload is not None else "GET",
    )
    if token:
        request.add_header("X-SigmaHelix-Token", token)
    if origin:
        request.add_header("Origin", origin)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode()


def test_index_carries_the_session_token(server):
    base, token = server
    status, body = call(base, "/")
    assert status == 200
    assert token in body
    assert "__SIGMAHELIX_TOKEN__" not in body


def test_state_needs_the_token(server):
    base, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/state")
    assert exc.value.code == 403


def test_state_returns_the_workspace(server):
    base, token = server
    status, body = call(base, "/api/state", token)
    assert status == 200
    data = json.loads(body)
    assert set(data) >= {"tasks", "notes", "projects", "skills", "agenda"}
    assert any(skill["name"] == "hatem-specific" for skill in data["skills"])


def test_create_and_complete_a_task(server):
    base, token = server
    status, body = call(
        base, "/api/tasks", token, {"title": "web task", "due": "2026-12-01"}
    )
    task = json.loads(body)["task"]
    assert task["name"] == "web task" and task["due"] == "2026-12-01"

    status, body = call(base, f"/api/tasks/{task['id']}/done", token, {"done": True})
    assert json.loads(body)["task"]["completed"] is True


def test_chat_returns_reply_and_trace(server):
    base, token = server
    status, body = call(
        base, "/api/chat", token, {"text": "hey there, how are you today?"}
    )
    data = json.loads(body)
    assert status == 200
    assert "Tommy" in data["reply"]
    assert "trace" in data


def test_foreign_origin_is_rejected(server):
    base, token = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/state", token, origin="https://evil.example")
    assert exc.value.code == 403


def test_static_path_traversal_is_refused(server):
    base, token = server
    for path in ("/static/../server.py", "/static/..%2fserver.py", "/static/."):
        with pytest.raises(urllib.error.HTTPError) as exc:
            call(base, path, token)
        assert exc.value.code == 404


def test_unknown_route_is_404(server):
    base, token = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/nope", token)
    assert exc.value.code == 404
