"""Plugin registry: every capability is a toggleable plugin.

The model only ever sees the actions of *enabled* plugins, and the agent gates
execution by the same set. That is what makes "activate live from Settings"
real instead of cosmetic.

Built-in plugins describe existing behaviour (tasks, files, web, …). Adding a
capability means adding a :class:`Plugin` here and a handler in the agent; the
legacy dispatcher stays as a fallback so migration is incremental.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from ..core.config import load_settings, save_plugin_settings


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """One action a plugin exposes to the model."""

    name: str
    description: str


@dataclass(frozen=True, slots=True)
class Plugin:
    """A capability bundle the user can turn on or off."""

    id: str
    name: str
    description: str
    category: str
    actions: tuple[ActionSpec, ...]
    always_on: bool = False
    permissions: tuple[str, ...] = ()

    def as_dict(self, enabled: bool) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "enabled": enabled,
            "always_on": self.always_on,
            "permissions": list(self.permissions),
            "actions": [action.name for action in self.actions],
        }


@dataclass(frozen=True, slots=True)
class Preset:
    """A named set of plugins for a kind of task."""

    id: str
    name: str
    description: str
    plugins: tuple[str, ...]


PLUGINS: tuple[Plugin, ...] = (
    Plugin(
        "core",
        "Core persona",
        "Tommy's identity, small talk and help. Always on.",
        "core",
        (
            ActionSpec("chat", "Greetings, small talk, direct answers."),
            ActionSpec("help", "Explain what Tommy can do right now."),
        ),
        always_on=True,
        permissions=("none",),
    ),
    Plugin(
        "tasks",
        "Tasks",
        "Create, list, complete, delete and pin tasks.",
        "productivity",
        (
            ActionSpec(
                "create_task",
                "Create a task from the user's text, clean of command words "
                "(weekly/monthly in the text sets frequency).",
            ),
            ActionSpec("list_tasks", "List tasks."),
            ActionSpec(
                "complete_task", "Mark a task done. content = numeric id, or empty."
            ),
            ActionSpec("delete_task", "Delete a task. content = numeric id, or empty."),
            ActionSpec(
                "pin_task",
                "Pin a task so it stays on top and cannot be deleted. "
                "content = id, or empty to pin the newest.",
            ),
            ActionSpec("unpin_task", "Unpin a task. content = id, or empty."),
        ),
        permissions=("local database",),
    ),
    Plugin(
        "task_questions",
        "Question-driven tasks",
        "Sub-questions with answers/evidence; execute a task to answer them.",
        "productivity",
        (
            ActionSpec(
                "create_task_with_questions",
                'content = "TITLE" on the first line, then one question per '
                'following line (separate lines or "||").',
            ),
            ActionSpec("add_question", 'content = "to task <id>: <question text>".'),
            ActionSpec(
                "answer_question",
                'content = "question <qid> on task <id>: <answer>".',
            ),
            ActionSpec("reopen_question", 'content = "question <qid> on task <id>".'),
            ActionSpec("show_questions", 'content = "task <id>".'),
            ActionSpec(
                "execute_task",
                'content = "task <id>" — answer its open questions yourself, '
                "then complete it.",
            ),
        ),
        permissions=("local database",),
    ),
    Plugin(
        "notes",
        "Notes",
        "Create, edit, pin and delete notes.",
        "productivity",
        (
            ActionSpec(
                "create_note",
                "Create a note: information to KEEP with nothing to do "
                '(memo, fact, reference). If the user says "remember to '
                '<do something>", use create_task instead.',
            ),
            ActionSpec("list_notes", "List notes."),
            ActionSpec("edit_note", "Edit a note. content = id and new text."),
            ActionSpec("delete_note", "Delete a note. content = numeric id."),
            ActionSpec(
                "pin_note",
                "Pin a note so it stays on top and cannot be deleted. "
                "content = id, or empty to pin the newest.",
            ),
            ActionSpec("unpin_note", "Unpin a note. content = id, or empty."),
        ),
        permissions=("local database",),
    ),
    Plugin(
        "projects",
        "Projects & readiness",
        "List/scan projects, assess production readiness, scaffold new ones.",
        "engineering",
        (
            ActionSpec("list_projects", "List projects in the workspace."),
            ActionSpec("explore", "Find released apps in the projects."),
            ActionSpec(
                "assess_projects",
                'content = "" or a project name. Scans every project and reports '
                "real readiness evidence (readme, tests, CI, container, env "
                "template, build commands, git state). Use it to answer "
                '"which project is production ready?" — never guess or just '
                "list names.",
            ),
            ActionSpec(
                "create_project",
                "content = the project name/description. Scaffolds a runnable "
                "app there; follow up with file_operations to add files.",
            ),
        ),
        permissions=("read cloned_repos", "write new projects"),
    ),
    Plugin(
        "files",
        "Workspace files",
        "List, read, search, create and modify any file in the projects directory.",
        "engineering",
        (
            ActionSpec(
                "file_operations",
                'content = JSON {"operation":"list|read|search|create|modify",'
                '"path":"<relative path in the workspace>","content":"<text for '
                'create/modify>","pattern":"<regex for search>","glob":"<optional '
                'file glob>"}. The workspace is the projects directory; you may '
                'read, create and modify ANY file in it. Use "list" to explore, '
                '"read" to inspect, "search" to grep.',
            ),
        ),
        permissions=("read/write inside cloned_repos",),
    ),
    Plugin(
        "web",
        "Web access",
        "Visit public pages and read their text; search the web.",
        "research",
        (
            ActionSpec(
                "fetch_url",
                "content = a public http(s) URL. You CAN visit pages and read "
                "their text: documentation, GitHub pages, raw README files, "
                'articles. Never say "I\'m not a browser" — call this. Pages '
                "behind a login wall (a private profile) may return only a "
                "login page; say so honestly.",
            ),
            ActionSpec("web_search", "content = the query. Search the web."),
        ),
        permissions=("public HTTP(S) only",),
    ),
    Plugin(
        "documents",
        "Documents",
        "Write real PDFs into the workspace.",
        "research",
        (
            ActionSpec(
                "create_document",
                'content = JSON {"title":"...","sections":[{"heading":"...",'
                '"body":"..."}],"filename":"resume.pdf"}. Writes a real PDF into '
                "the workspace. Use local READMEs and fetched pages for facts; "
                "never invent details.",
            ),
        ),
        permissions=("write PDFs in cloned_repos",),
    ),
    Plugin(
        "calendar",
        "Calendar",
        "Today / week / month agenda from task due dates.",
        "productivity",
        (ActionSpec("calendar", "content = today|tomorrow|week|month."),),
        permissions=("local database",),
    ),
    Plugin(
        "launch",
        "Launchers",
        "Launch the configured apps.",
        "system",
        (ActionSpec("launch", "Launch a named app."),),
        permissions=("start local apps",),
    ),
    Plugin(
        "youtube",
        "YouTube",
        "Summarise a YouTube video (basic metadata).",
        "research",
        (ActionSpec("youtube_summary", "Summarise a YouTube URL."),),
        permissions=("public HTTP(S) only",),
    ),
    Plugin(
        "skills",
        "Skill upload",
        "Load user-provided skill files.",
        "system",
        (ActionSpec("upload_skills", "Load skills from a JSON file."),),
        permissions=("read skill files",),
    ),
)

PRESETS: tuple[Preset, ...] = (
    Preset(
        "tommy",
        "Tommy",
        "One persona with every capability — the default.",
        tuple(p.id for p in PLUGINS),
    ),
    Preset(
        "coding",
        "Coding",
        "Build, edit and assess projects.",
        (
            "core",
            "tasks",
            "task_questions",
            "notes",
            "projects",
            "files",
            "web",
            "documents",
        ),
    ),
    Preset(
        "research",
        "Research",
        "Read the web, files and produce documents.",
        ("core", "projects", "files", "web", "documents"),
    ),
    Preset(
        "ops",
        "Ops",
        "Tasks, questions, calendar and project health.",
        ("core", "tasks", "task_questions", "calendar", "projects", "files", "web"),
    ),
    Preset(
        "resume",
        "Resume",
        "Gather from the web and local projects, then write a PDF.",
        ("core", "projects", "files", "web", "documents"),
    ),
    Preset("minimal", "Minimal", "Core only.", ("core",)),
)


def _action_map() -> dict[str, Plugin]:
    mapping: dict[str, Plugin] = {}
    for plugin in PLUGINS:
        for action in plugin.actions:
            mapping[action.name] = plugin
    return mapping


class PluginRegistry:
    """The live set of enabled plugins plus their prompt and gate logic."""

    def __init__(self, enabled: list[str] | None = None, persist: bool = True) -> None:
        self._plugins = {plugin.id: plugin for plugin in PLUGINS}
        self._persist = persist
        if enabled is None:
            saved = None
            try:
                saved = load_settings().plugins_enabled
            except Exception:  # noqa: BLE001 - config must never break the agent
                saved = None
            # Tommy is one persona with every capability. The switches exist so
            # the user can trim a plugin for a specific task, not to pick a role.
            enabled = (
                list(saved) if saved is not None else [plugin.id for plugin in PLUGINS]
            )
        self._enabled = {pid for pid in enabled if pid in self._plugins}
        for plugin in PLUGINS:
            if plugin.always_on:
                self._enabled.add(plugin.id)

    # ---- reads -----------------------------------------------------------
    def plugins(self) -> list[Plugin]:
        return list(PLUGINS)

    def presets(self) -> list[Preset]:
        return list(PRESETS)

    def enabled_ids(self) -> set[str]:
        return set(self._enabled)

    def is_enabled(self, plugin_id: str) -> bool:
        return plugin_id in self._enabled

    def plugin_for_action(self, action: str) -> Plugin | None:
        return _action_map().get(action)

    def actions(self) -> list[ActionSpec]:
        specs: list[ActionSpec] = []
        for plugin in PLUGINS:
            if plugin.id in self._enabled:
                specs.extend(plugin.actions)
        return specs

    def prompt_block(self) -> str:
        lines = ["\n\n## ENABLED TOOLS (authoritative — only these exist)"]
        for plugin in PLUGINS:
            if plugin.id not in self._enabled:
                continue
            lines.append(f"\n### {plugin.name} ({plugin.id})")
            for action in plugin.actions:
                lines.append(f"- {action.name}: {action.description}")
        disabled = [
            plugin.name
            for plugin in PLUGINS
            if plugin.id not in self._enabled and not plugin.always_on
        ]
        if disabled:
            lines.append("\nTurned off (never claim these): " + ", ".join(disabled))
        return "\n".join(lines) + "\n"

    # ---- writes ----------------------------------------------------------
    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise ValueError(f"unknown plugin: {plugin_id!r}")
        if plugin.always_on and not enabled:
            raise ValueError(f"{plugin.name} is always on")
        if enabled:
            self._enabled.add(plugin_id)
        else:
            self._enabled.discard(plugin_id)
        self._save()

    def apply_preset(self, preset_id: str) -> set[str]:
        preset = next((item for item in PRESETS if item.id == preset_id), None)
        if preset is None:
            raise ValueError(f"unknown preset: {preset_id!r}")
        self._enabled = {pid for pid in preset.plugins if pid in self._plugins}
        for plugin in PLUGINS:
            if plugin.always_on:
                self._enabled.add(plugin.id)
        self._save()
        return set(self._enabled)

    def gate(self, action: str) -> str | None:
        """Return an 'off' message when a known action's plugin is disabled."""
        plugin = self.plugin_for_action(action)
        if plugin is None or plugin.id in self._enabled:
            return None
        return self.off_message(plugin.id)

    def off_message(self, plugin_id: str) -> str:
        plugin = self._plugins.get(plugin_id)
        name = plugin.name if plugin else plugin_id
        return (
            f"⚙️ '{name}' is turned off. Enable it in Settings → Plugins and ask again."
        )

    def _save(self) -> None:
        if not self._persist:
            return
        # A read-only or unwritable config must never break the agent.
        with contextlib.suppress(Exception):
            save_plugin_settings(sorted(self._enabled))
