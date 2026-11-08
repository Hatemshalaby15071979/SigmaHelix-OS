"""Local web interface for SigmaHelix.

The desktop window fought the layout engine on every new panel, so the primary
surface is now a single page served on loopback and opened in the user's own
browser. Nothing leaves the machine:

* the socket binds ``127.0.0.1`` only;
* every API call needs a per-session token that is generated at start-up and
  embedded in the served page, so another local process cannot drive the app;
* ``Origin`` must be loopback or absent (no cross-site form posts).

The desktop Tk window remains available as ``sigmahelix --desktop``.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ...core.storage.repositories import RepositoryOperationError
from ..service import AppService

STATIC_DIR = Path(__file__).resolve().parent / "static"
TOKEN_HEADER = "X-SigmaHelix-Token"
MAX_BODY = 256 * 1024


def _parse_due(raw: Any) -> Any:
    """Accept ``2026-11-09`` or a full ISO timestamp, else None."""
    from datetime import UTC, date, datetime, time

    text = str(raw or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min, UTC)
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class AppState:
    """The one object the HTTP layer talks to."""

    def __init__(self, service: AppService | None = None) -> None:
        from ..agent import Agent

        self.service = service or AppService()
        self.agent = Agent()
        self.token = secrets.token_urlsafe(24)

    # ---- read ------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "tasks": self.service.list_tasks(),
            "notes": self.service.list_notes(),
            "projects": self._projects(),
            "agenda": self.agenda("today"),
            "model": {
                "name": self.agent.model_name,
                "kind": self.agent.model_kind,
                "available": self.agent.llm_available,
            },
            "skills": self._skills(),
        }

    def agenda(self, scope: str) -> str:
        from ..managers import CalendarManager

        return CalendarManager(self.service).get_tasks_for_date(scope)

    def _skills(self) -> list[dict[str, Any]]:
        try:
            return [
                {
                    "name": skill.name,
                    "source": skill.source,
                    "token": skill.token,
                    "size": skill.size,
                }
                for skill in self.agent.skills.skills()
            ]
        except Exception:  # noqa: BLE001 - the UI still works without skills
            return []

    def _projects(self) -> list[dict[str, Any]]:
        from ..launchables import detect_launchables

        rows = self.service.scan_projects()
        for row in rows:
            items = detect_launchables(Path(row["path"]))
            row["launchables"] = [item.as_dict() for item in items]
        return rows

    # ---- write -----------------------------------------------------------
    def chat(self, text: str) -> dict[str, Any]:
        reply = self.agent.process_command(text)
        return {
            "reply": reply,
            "trace": dict(self.agent.last_trace),
            "model": self.agent.model_name,
        }

    def launch(self, project: str, index: int) -> dict[str, Any]:
        from ..launchables import detect_launchables, launch
        from ..paths import projects_dir
        from ..security import confine_to_root

        try:
            root = confine_to_root(projects_dir(), project)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}
        items = detect_launchables(root)
        if index < 0 or index >= len(items):
            return {"ok": False, "message": "that link is stale — refresh"}
        ok, message = launch(items[index])
        return {"ok": ok, "message": message}

    def settings(self) -> dict[str, Any]:
        """Current model-mode + cloud key state for the Settings view."""
        from ..models import (
            PROVIDERS,
            check_cloud_auth,
            load_api_keys,
        )

        keys = load_api_keys()
        verified = keys.get("_verified") or {}
        providers = []
        for name in PROVIDERS:
            providers.append(
                {
                    "name": name,
                    "has_key": bool(str(keys.get(name) or "").strip()),
                    "verified": bool(verified.get(name)),
                }
            )
        local = []
        try:
            from ..models import get_local_models

            local = get_local_models()
        except Exception:  # noqa: BLE001 - local listing is best-effort
            local = []
        return {
            "mode": self.agent.model_kind,
            "cloud_provider": self.agent.cloud_provider,
            "cloud_model": self.agent.cloud_model,
            "providers": providers,
            "cloud_auth": check_cloud_auth(),
            "local_available": bool(local),
            "local_models": [m["value"] for m in local],
            "model_name": self.agent.model_name,
        }

    def save_settings(
        self, mode: str, cloud_provider: str | None, cloud_model: str | None
    ) -> dict[str, Any]:
        """Persist and apply the model-mode selection to the live agent."""
        self.agent.apply_settings(mode, cloud_provider, cloud_model)
        return self.settings()

    def set_key(self, provider: str, key: str) -> dict[str, Any]:
        """Store a provider key in the keyring and live-verify it."""
        from ..models import verify_cloud_key

        ok, message = verify_cloud_key(provider, key)
        return {"ok": ok, "message": message, **self.settings()}

    def delete_key(self, provider: str) -> dict[str, Any]:
        from ..models import forget_api_key

        forget_api_key(provider)
        return self.settings()

    def plugins_state(self) -> dict[str, Any]:
        """Every plugin with its live enabled state, plus presets."""
        registry = self.agent.plugins
        enabled = registry.enabled_ids()
        return {
            "plugins": [
                plugin.as_dict(plugin.id in enabled) for plugin in registry.plugins()
            ],
            "presets": [
                {
                    "id": preset.id,
                    "name": preset.name,
                    "description": preset.description,
                    "plugins": list(preset.plugins),
                }
                for preset in registry.presets()
            ],
            "enabled": sorted(enabled),
        }

    def set_plugin(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        self.agent.plugins.set_enabled(plugin_id, enabled)
        return self.plugins_state()

    def apply_plugin_preset(self, preset_id: str) -> dict[str, Any]:
        self.agent.plugins.apply_preset(preset_id)
        return self.plugins_state()


class Handler(BaseHTTPRequestHandler):
    state: AppState
    server_version = "SigmaHelix"

    # ---- plumbing --------------------------------------------------------
    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        return  # the console stays quiet; the UI shows its own errors

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; script-src 'self'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status)

    def _authorised(self) -> bool:
        origin = self.headers.get("Origin")
        if origin:
            host = urlparse(origin).hostname or ""
            if host not in ("127.0.0.1", "localhost", "::1"):
                return False
        supplied = self.headers.get(TOKEN_HEADER, "")
        return secrets.compare_digest(supplied, self.state.token)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return {}
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    # ---- routes ----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._serve_index()
        if path.startswith("/static/"):
            return self._serve_static(path.removeprefix("/static/"))
        if path == "/api/state":
            if not self._authorised():
                return self._error(HTTPStatus.FORBIDDEN, "bad token")
            return self._json(self.state.snapshot())
        if path == "/api/agenda":
            if not self._authorised():
                return self._error(HTTPStatus.FORBIDDEN, "bad token")
            scope = (parse_qs(parsed.query).get("scope") or ["today"])[0]
            return self._json({"scope": scope, "text": self.state.agenda(scope)})
        if path == "/api/settings":
            if not self._authorised():
                return self._error(HTTPStatus.FORBIDDEN, "bad token")
            return self._json(self.state.settings())
        if path == "/api/plugins":
            if not self._authorised():
                return self._error(HTTPStatus.FORBIDDEN, "bad token")
            return self._json(self.state.plugins_state())
        return self._error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorised():
            return self._error(HTTPStatus.FORBIDDEN, "bad token")
        path = urlparse(self.path).path
        data = self._body()
        try:
            return self._dispatch_post(path, data)
        except ValueError as exc:
            return self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except RepositoryOperationError as exc:
            # A checkpoint refused the change; the client must handle it.
            return self._error(HTTPStatus.CONFLICT, str(exc))
        except Exception as exc:  # noqa: BLE001 - report, never kill the server
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _dispatch_post(self, path: str, data: dict[str, Any]) -> None:
        service = self.state.service

        if path == "/api/chat":
            text = str(data.get("text") or "").strip()
            if not text:
                return self._error(HTTPStatus.BAD_REQUEST, "empty message")
            return self._json(self.state.chat(text))

        if path == "/api/tasks" and data.get("title"):
            questions = [str(q) for q in (data.get("questions") or [])]
            if questions:
                task = service.create_task_with_questions(
                    str(data["title"]),
                    questions,
                    recurrence=str(data.get("recurrence") or "none"),
                    due_at=_parse_due(data.get("due")),
                )
            else:
                task = service.create_task(
                    str(data["title"]),
                    recurrence=str(data.get("recurrence") or "none"),
                    due_at=_parse_due(data.get("due")),
                )
            return self._json({"task": task})

        if path == "/api/plan":
            from ..planner import propose_questions

            title = str(data.get("title") or "").strip()
            if not title:
                return self._error(HTTPStatus.BAD_REQUEST, "a task name is required")
            return self._json(
                {
                    "title": title,
                    "questions": propose_questions(self.state.agent, title),
                }
            )

        match = re.fullmatch(r"/api/tasks/(\d+)/questions", path)
        if match and data.get("question"):
            question = service.add_question(int(match.group(1)), str(data["question"]))
            return self._json({"question": question})

        match = re.fullmatch(r"/api/tasks/(\d+)/questions/(\d+)/(answer|reopen)", path)
        if match:
            task_id, question_id, action = (
                int(match.group(1)),
                int(match.group(2)),
                match.group(3),
            )
            if action == "answer":
                question = service.answer_question(
                    task_id,
                    question_id,
                    str(data.get("answer") or ""),
                    str(data.get("evidence") or ""),
                )
            else:
                question = service.reopen_question(task_id, question_id)
            return self._json({"question": question, "task": service.get_task(task_id)})

        match = re.fullmatch(r"/api/tasks/(\d+)/(done|pin|delete)", path)
        if match:
            task_id, action = int(match.group(1)), match.group(2)
            if action == "done":
                result = service.set_task_done(
                    task_id, bool(data.get("done", True)), bool(data.get("force"))
                )
            elif action == "pin":
                result = service.set_task_pinned(
                    task_id, bool(data.get("pinned", True))
                )
            else:
                ok = service.delete_task(task_id, force=bool(data.get("force")))
                return self._json({"deleted": ok})
            return self._json({"task": result})

        if path == "/api/notes" and data.get("title"):
            note = service.create_note(str(data["title"]))
            return self._json({"note": note})

        match = re.fullmatch(r"/api/notes/(\d+)/(pin|delete)", path)
        if match:
            note_id, action = int(match.group(1)), match.group(2)
            if action == "pin":
                return self._json(
                    {
                        "note": service.set_note_pinned(
                            note_id, bool(data.get("pinned", True))
                        )
                    }
                )
            return self._json({"deleted": service.delete_note(note_id)})

        if path == "/api/launch":
            project = str(data.get("project") or "")
            index = int(data.get("index") or 0)
            return self._json(self.state.launch(project, index))

        if path == "/api/skills/reload":
            count = self.state.agent.reload_skills()
            return self._json({"skills": count})

        if path == "/api/settings" and data:
            mode = str(data.get("mode") or "local").strip()
            provider = data.get("cloud_provider") or None
            model = data.get("cloud_model") or None
            if provider is not None:
                provider = str(provider).strip() or None
            if model is not None:
                model = str(model).strip() or None
            return self._json(self.state.save_settings(mode, provider, model))

        if path == "/api/settings/key" and data.get("provider") and "key" in data:
            return self._json(
                self.state.set_key(str(data["provider"]), str(data["key"]))
            )

        if path == "/api/settings/key/delete" and data.get("provider"):
            return self._json(self.state.delete_key(str(data["provider"])))

        if path == "/api/plugins/toggle" and data.get("id"):
            return self._json(
                self.state.set_plugin(str(data["id"]), bool(data.get("enabled")))
            )

        if path == "/api/plugins/preset" and data.get("preset"):
            return self._json(self.state.apply_plugin_preset(str(data["preset"])))

        return self._error(HTTPStatus.NOT_FOUND, "not found")

    # ---- files -----------------------------------------------------------
    def _serve_index(self) -> None:
        try:
            html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        except OSError:
            return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "missing index.html")
        html = html.replace("__SIGMAHELIX_TOKEN__", self.state.token)
        self._send(HTTPStatus.OK, html.encode(), "text/html; charset=utf-8")

    def _serve_static(self, name: str) -> None:
        if "/" in name or "\\" in name or name.startswith("."):
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        target = STATIC_DIR / name
        if not target.is_file():
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        kind = {
            ".js": "text/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }.get(target.suffix, "application/octet-stream")
        self._send(HTTPStatus.OK, target.read_bytes(), kind)


def serve(port: int = 0, open_browser: bool = True) -> int:
    """Start the local UI and block until interrupted."""
    state = AppState()
    handler = type("BoundHandler", (Handler,), {"state": state})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    actual = httpd.server_address[1]
    url = f"http://127.0.0.1:{actual}/"
    print(f"SigmaHelix UI  {url}")
    print("  loopback only · token required · Ctrl+C to stop")

    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0
