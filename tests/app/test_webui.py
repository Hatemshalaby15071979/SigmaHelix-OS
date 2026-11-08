"""The local web interface: token gate, JSON API, no path escapes."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest
import yaml

from sigmahelix.app import agent as agent_module
from sigmahelix.app import models as app_models
from sigmahelix.app.webui.server import AppState, Handler
from sigmahelix.core.secrets import KeyringSecretStore


class _MemoryKeyring:
    """Keyring backend that keeps secrets in a dict (for isolated tests)."""

    def __init__(self):
        self.values = {}

    def get_password(self, service_name, username):
        return self.values.get((service_name, username))

    def set_password(self, service_name, username, password):
        self.values[(service_name, username)] = password

    def delete_password(self, service_name, username):
        self.values.pop((service_name, username), None)


@pytest.fixture
def settings_server(tmp_path, monkeypatch):
    """A web server with an isolated config file and an in-memory keyring."""
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("SIGMAHELIX_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("SIGMAHELIX_NO_NETWORK", "1")
    store = KeyringSecretStore(backend=_MemoryKeyring())
    monkeypatch.setattr(app_models, "_secret_store", store)
    monkeypatch.setattr(
        agent_module.Agent, "_check_llm", lambda self, timeout=2.0: False
    )
    state = AppState()
    handler = type("TestHandler", (Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, state.token, config_path
    httpd.shutdown()
    httpd.server_close()


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


def test_get_settings_reports_mode_and_providers(settings_server):
    base, token, _ = settings_server
    status, body = call(base, "/api/settings", token)
    assert status == 200
    data = json.loads(body)
    assert data["mode"] == "local"
    assert data["cloud_provider"] is None
    assert isinstance(data["providers"], list)
    assert {p["name"] for p in data["providers"]} == {
        "openai",
        "openrouter",
        "deepseek",
    }
    for provider in data["providers"]:
        assert set(provider) >= {"name", "has_key", "verified"}
        assert provider["has_key"] is False
        assert provider["verified"] is False
    assert isinstance(data["cloud_auth"], dict)
    assert data["cloud_auth"]["any"] is False
    assert isinstance(data["local_models"], list)
    assert data["model_name"]


def test_post_settings_changes_mode_and_persists_to_config(settings_server):
    base, token, config_path = settings_server
    status, body = call(
        base,
        "/api/settings",
        token,
        {"mode": "cloud", "cloud_provider": "openrouter"},
    )
    assert status == 200
    data = json.loads(body)
    assert data["mode"] == "cloud"
    assert data["cloud_provider"] == "openrouter"

    # A restart would read the same selection back from disk.
    on_disk = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert on_disk["model_mode"] == "cloud"
    assert on_disk["cloud_provider"] == "openrouter"

    # The change is reflected by a later read too.
    _, body = call(base, "/api/settings", token)
    assert json.loads(body)["mode"] == "cloud"


def test_post_settings_rejects_unknown_mode(settings_server):
    base, token, _ = settings_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/settings", token, {"mode": "telepathic"})
    assert exc.value.code == 400


def test_settings_update_requires_the_token(settings_server):
    base, _, _ = settings_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/settings", None, {"mode": "hybrid"})
    assert exc.value.code == 403


def test_set_key_rejects_a_failing_probe(settings_server, monkeypatch):
    base, token, _ = settings_server
    monkeypatch.setattr(
        app_models,
        "verify_cloud_key",
        lambda provider, key, timeout=25: (False, "probe failed"),
    )
    status, body = call(
        base,
        "/api/settings/key",
        token,
        {"provider": "openrouter", "key": "sk-bogus"},
    )
    data = json.loads(body)
    assert status == 200
    assert data["ok"] is False
    assert data["message"] == "probe failed"
    # A rejected key must not linger as configured.
    assert all(p["has_key"] is False for p in data["providers"])


def test_delete_key_clears_a_configured_provider(settings_server):
    base, token, _ = settings_server
    app_models.set_api_key("openrouter", "sk-or-v1-test")
    app_models.mark_verified("openrouter", True)

    before_status, before = call(base, "/api/settings", token)
    assert before_status == 200
    assert json.loads(before)["providers"][1]["has_key"] is True

    status, body = call(
        base, "/api/settings/key/delete", token, {"provider": "openrouter"}
    )
    assert status == 200
    after = json.loads(body)
    openrouter = next(p for p in after["providers"] if p["name"] == "openrouter")
    assert openrouter["has_key"] is False
    assert openrouter["verified"] is False


def test_plugins_endpoint_lists_every_plugin(settings_server):
    base, token, _ = settings_server
    status, body = call(base, "/api/plugins", token)
    data = json.loads(body)
    assert status == 200
    ids = {p["id"] for p in data["plugins"]}
    assert {"core", "tasks", "projects", "files", "web"} <= ids
    assert data["enabled"] == sorted(ids)  # one persona: everything on
    assert "core" in data["enabled"]
    core = next(p for p in data["plugins"] if p["id"] == "core")
    assert core["always_on"] is True
    assert {p["id"] for p in data["presets"]} >= {"tommy", "coding", "minimal"}


def test_plugins_toggle_changes_state_and_persists(settings_server):
    base, token, config_path = settings_server
    status, body = call(
        base, "/api/plugins/toggle", token, {"id": "web", "enabled": False}
    )
    data = json.loads(body)
    assert status == 200
    assert "web" not in data["enabled"]
    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "web" not in saved["plugins_enabled"]

    # The running agent is gated immediately — no restart.
    status, body = call(base, "/api/chat", token, {"text": "read https://example.com"})
    assert "turned off" in json.loads(body)["reply"].lower()


def test_plugins_preset_endpoint(settings_server):
    base, token, _ = settings_server
    status, body = call(base, "/api/plugins/preset", token, {"preset": "minimal"})
    data = json.loads(body)
    assert status == 200
    assert data["enabled"] == ["core"]


def test_plugins_rejects_unknown_and_always_on(settings_server):
    base, token, _ = settings_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/plugins/toggle", token, {"id": "teleport", "enabled": True})
    assert exc.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/api/plugins/toggle", token, {"id": "core", "enabled": False})
    assert exc.value.code == 400


def test_project_page_is_served_with_its_assets(settings_server, tmp_path, monkeypatch):
    base, token, _ = settings_server
    root = tmp_path / "cloned_repos"
    demo = root / "Demo"
    demo.mkdir(parents=True)
    (demo / "index.html").write_text(
        "<html><link rel=stylesheet href=style.css></html>"
    )
    (demo / "style.css").write_text("body { color: red; }")
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(root))

    status, body = call(base, f"/project/Demo/index.html?t={token}")
    assert status == 200
    assert "<html>" in body

    status, body = call(base, f"/project/Demo/style.css?t={token}")
    assert status == 200
    assert "color: red" in body


def test_project_page_needs_the_token(settings_server, tmp_path, monkeypatch):
    base, _, _ = settings_server
    root = tmp_path / "cloned_repos"
    (root / "Demo").mkdir(parents=True)
    (root / "Demo" / "index.html").write_text("<html>demo</html>")
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(root))

    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, "/project/Demo/index.html")
    assert exc.value.code == 403


def test_project_page_cannot_escape_its_folder(settings_server, tmp_path, monkeypatch):
    base, token, _ = settings_server
    root = tmp_path / "cloned_repos"
    (root / "Demo").mkdir(parents=True)
    (root / "Demo" / "index.html").write_text("<html>demo</html>")
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(root))

    with pytest.raises(urllib.error.HTTPError) as exc:
        call(base, f"/project/Demo/%2e%2e%2f%2e%2e%2fetc%2fpasswd?t={token}")
    assert exc.value.code == 404


def test_state_reports_index_and_runnable_for_each_project(
    settings_server, tmp_path, monkeypatch
):
    base, token, _ = settings_server
    root = tmp_path / "cloned_repos"
    demo = root / "Demo"
    demo.mkdir(parents=True)
    (demo / "pyproject.toml").write_text("[project]\nname = 'demo'\n")
    (demo / "index.html").write_text("<html>demo</html>")
    monkeypatch.setenv("SIGMAHELIX_PROJECTS_DIR", str(root))

    status, body = call(base, "/api/state", token)
    assert status == 200
    project = next(p for p in json.loads(body)["projects"] if p["name"] == "Demo")
    assert project["index"] == "index.html"
    assert project["launchables"][0]["kind"] == "dashboard"
