"""Task, note, project, calendar and launcher views over the durable core.

Everything user-owned is persisted in SQLite through :class:`AppService`.
These managers keep the dictionary-shaped API the desktop UI and the console
already speak, so presentation code never depends on storage details.
"""

import datetime
import os
import re
from pathlib import Path
from typing import Any

from ..core.storage.repositories import RepositoryOperationError
from .paths import data_dir as paths_data_dir
from .paths import projects_dir as _projects_dir
from .projects import PROJECTS_DIR, list_project_dirs
from .service import AppService


def pinned_first(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pinned records first, then by id — the order users expect to see."""
    return sorted(records, key=lambda r: (not r.get("pinned"), r.get("id") or 0))


def _id_from(text: str) -> int | None:
    """First number in the text ('pin note 3' -> 3), else None."""
    match = re.search(r"\d+", text or "")
    return int(match.group()) if match else None


class TasksManager:
    """Task commands and the programmatic API used by the GUI."""

    def __init__(self, service: AppService | None = None) -> None:
        self.service = service or AppService()

    # ---- programmatic API (used by the GUI) ------------------------------
    @property
    def tasks(self) -> list[dict[str, Any]]:
        """Every task, pinned first — a read-only snapshot."""
        return self.service.list_tasks()

    def find(self, task_id: int) -> dict[str, Any] | None:
        return self.service.get_task(task_id)

    def set_pinned(self, task_id: int, pinned: bool = True) -> dict[str, Any] | None:
        """Pin/unpin a task. Returns the task dict, or None if it is missing."""
        return self.service.set_task_pinned(task_id, pinned)

    def delete(self, task_id: int, force: bool = False) -> bool:
        """Delete a task. Pinned tasks are protected unless force=True."""
        return self.service.delete_task(task_id, force)

    # ---- text-command wrappers (agent / console) -------------------------
    def create_task(self, text: str) -> str:
        """Create a new task."""
        task_name = clean_content(text)
        if not task_name:
            return "Please specify what task you want to create."

        frequency = "daily"
        if "weekly" in text:
            frequency = "weekly"
        elif "monthly" in text:
            frequency = "monthly"

        task = self.service.create_task(task_name, recurrence=frequency)
        return "Task '{}' created with {} frequency (ID: {}).".format(
            task_name, frequency, task["id"]
        )

    def list_tasks(self, text: str = "") -> str:
        """List tasks, pinned first."""
        tasks = self.tasks
        if not tasks:
            return "You have no tasks yet."

        result = "Your tasks:\n"
        for task in tasks:
            status = "[✓]" if task.get("completed") else "[ ]"
            pin = "📌 " if task.get("pinned") else ""
            result += "{} {}ID {}: {} ({}, created: {})\n".format(
                status,
                pin,
                task["id"],
                task["name"],
                task["frequency"],
                task["created"],
            )
        return result.rstrip()

    def complete_task(self, text: str) -> str:
        """Complete a task."""
        task_id = _id_from(text)
        if task_id is None:
            return "Please specify a task ID to complete."

        task = self.find(task_id)
        if task is None:
            return f"Task ID {task_id} not found."
        try:
            self.service.set_task_done(task_id, True)
        except RepositoryOperationError as exc:
            return f"🔒 {exc}"
        return "Task '{}' marked as completed.".format(task["name"])

    def delete_task(self, text: str) -> str:
        """Delete a task — refused while it is pinned."""
        task_id = _id_from(text)
        if task_id is None:
            return "Please specify a task ID to delete."

        task = self.find(task_id)
        if task is None:
            return f"Task ID {task_id} not found."
        if task.get("pinned"):
            return (
                f"📌 Task ID {task_id} is pinned — say 'unpin task {task_id}' first, "
                "then delete it."
            )

        self.delete(task_id)
        return "Task '{}' deleted.".format(task["name"])

    def pin_task(self, text: str) -> str:
        """Pin a task by ID; with no ID, pin the newest task."""
        task_id = _id_from(text)
        tasks = self.tasks
        if task_id is None:
            if not tasks:
                return "You have no tasks to pin."
            task_id = max(t["id"] for t in tasks)
        task = self.find(task_id)
        if task is None:
            return f"Task ID {task_id} not found."
        if task.get("pinned"):
            return f"Task ID {task_id} is already pinned."
        self.set_pinned(task_id, True)
        return "📌 Task ID {} pinned: {} — it stays until you unpin it.".format(
            task_id, task["name"]
        )

    def unpin_task(self, text: str) -> str:
        """Unpin a task by ID; with no ID, unpin the newest pinned task."""
        task_id = _id_from(text)
        tasks = self.tasks
        if task_id is None:
            pinned = [t for t in tasks if t.get("pinned")]
            if not pinned:
                return "No pinned tasks."
            task_id = max(t["id"] for t in pinned)
        task = self.find(task_id)
        if task is None:
            return f"Task ID {task_id} not found."
        if not task.get("pinned"):
            return f"Task ID {task_id} is not pinned."
        self.set_pinned(task_id, False)
        return "Task ID {} unpinned: {}.".format(task_id, task["name"])


_PREFIX_TOKENS = {
    "please",
    "create",
    "add",
    "make",
    "save",
    "new",
    "a",
    "an",
    "note",
    "memo",
    "task",
    "todo",
    "to-do",
    "reminder",
    "remind",
    "remember",
    "me",
    "to",
    "that",
    "down",
    "write",
    "jot",
}
_MARKERS = {"note", "memo", "task", "todo", "to-do", "reminder", "remind", "remember"}


def clean_content(text):
    """Strip a leading command phrase, never words from the middle of the text.

    "write down that the supplier is closed" -> "the supplier is closed"
    "create note call the accountant at 3pm" -> "call the accountant at 3pm"
    "create task write report"               -> "write report"
    "write report"                           -> "write report"  (no command prefix)
    """
    tokens = (text or "").strip().split()
    if not tokens:
        return ""

    def norm(tok):
        return tok.strip(":,.-").lower()

    head = [norm(t) for t in tokens[:4]]
    has_marker = any(t in _MARKERS for t in head)
    if (
        not has_marker
        and len(tokens) > 1
        and head[0] in ("write", "jot")
        and head[1] == "down"
    ):
        has_marker = True
    if not has_marker:
        return " ".join(tokens).strip(" :,-")

    seen_marker = False
    i = 0
    while i < len(tokens):
        tok = norm(tokens[i])
        if tok in _MARKERS or tok == "down":
            seen_marker = True
        if tok in _PREFIX_TOKENS and not (seen_marker and tok in ("write", "jot")):
            i += 1
            continue
        break
    return " ".join(tokens[i:]).strip(" :,-")


def data_dir():
    """Where user data lives, resolved by :mod:`sigmahelix.app.paths`."""
    return str(paths_data_dir())


class NotesManager:
    """Note commands and the programmatic API used by the GUI."""

    def __init__(self, service: AppService | None = None) -> None:
        self.service = service or AppService()

    # ---- programmatic API (used by the GUI) ------------------------------
    def add(self, content: str) -> dict[str, Any] | None:
        """Add a note. Returns the note dict, or None when content is empty."""
        return self.service.create_note(content)

    def all(self) -> list[dict[str, Any]]:
        """All notes, pinned first."""
        return self.service.list_notes()

    def get(self, note_id: int) -> dict[str, Any] | None:
        return self.service.get_note(note_id)

    def update(self, note_id: int, content: str) -> bool:
        """Edit a note's text. Returns True when the note existed."""
        return self.service.update_note(note_id, content) is not None

    def delete(self, note_id: int, force: bool = False) -> bool:
        """Delete a note. Pinned notes are protected unless force=True."""
        return self.service.delete_note(note_id, force)

    def set_pinned(self, note_id: int, pinned: bool = True) -> dict[str, Any] | None:
        """Pin/unpin a note. Returns the note dict, or None if it is missing."""
        return self.service.set_note_pinned(note_id, pinned)

    def is_pinned(self, note_id: int) -> bool:
        note = self.get(note_id)
        return bool(note and note.get("pinned"))

    # ---- text-command wrappers (agent / console) -------------------------
    def create_note(self, text: str) -> str:
        """Create a note from a typed command."""
        content = clean_content(text)
        note = self.add(content)
        if note is None:
            return "Please specify what you want to write in your note."
        return "Note created (ID: {}): {}".format(note["id"], note["content"])

    def list_notes(self, text: str = "") -> str:
        """List notes, pinned first."""
        notes = self.all()
        if not notes:
            return "You have no notes yet."
        result = "Your notes:\n"
        for note in notes:
            pin = "📌 " if note.get("pinned") else ""
            result += "• {}ID {}: {} (created: {})\n".format(
                pin, note.get("id"), note.get("content"), note.get("created")
            )
        return result.rstrip()

    def edit_note(self, text: str) -> str:
        """Edit a note: 'edit note 2 <new text>'."""
        match = re.search(r"\d+", text or "")
        if not match:
            return "Please specify a note ID to edit."
        note_id = int(match.group())
        if self.get(note_id) is None:
            return f"Note ID {note_id} not found."
        new_content = clean_content((text or "")[match.end() :])
        if not new_content:
            return f"Please specify the new text for note ID {note_id}."
        self.update(note_id, new_content)
        return f"Note ID {note_id} updated: {new_content}"

    def delete_note(self, text: str) -> str:
        """Delete a note: 'delete note 2'. Refused while pinned."""
        note_id = _id_from(text)
        if note_id is None:
            return "Please specify a note ID to delete."
        note = self.get(note_id)
        if note is None:
            return f"Note ID {note_id} not found."
        if note.get("pinned"):
            return (
                f"📌 Note ID {note_id} is pinned — say 'unpin note {note_id}' first, "
                "then delete it."
            )
        self.delete(note_id)
        return f"Note ID {note_id} deleted."

    def pin_note(self, text: str) -> str:
        """Pin a note by ID; with no ID, pin the newest note."""
        note_id = _id_from(text)
        notes = self.all()
        if note_id is None:
            if not notes:
                return "You have no notes to pin."
            note_id = max(n["id"] for n in notes)
        note = self.get(note_id)
        if note is None:
            return f"Note ID {note_id} not found."
        if note.get("pinned"):
            return f"Note ID {note_id} is already pinned."
        self.set_pinned(note_id, True)
        return f"📌 Note ID {note_id} pinned — it stays until you unpin it."

    def unpin_note(self, text: str) -> str:
        """Unpin a note by ID; with no ID, unpin the newest pinned note."""
        note_id = _id_from(text)
        notes = self.all()
        if note_id is None:
            pinned = [n for n in notes if n.get("pinned")]
            if not pinned:
                return "No pinned notes."
            note_id = max(n["id"] for n in pinned)
        note = self.get(note_id)
        if note is None:
            return f"Note ID {note_id} not found."
        if not note.get("pinned"):
            return f"Note ID {note_id} is not pinned."
        self.set_pinned(note_id, False)
        return f"Note ID {note_id} unpinned."


class ProjectsManager:
    """Project listing, health scanning and released-app discovery."""

    def __init__(self, service: AppService | None = None) -> None:
        self.service = service or AppService()
        self.projects_dir = PROJECTS_DIR

    def scan(self) -> list[dict[str, Any]]:
        """Scan every proven project and report git state, health and runners."""
        from .launchables import detect_launchables

        rows = self.service.scan_projects()
        for row in rows:
            items = detect_launchables(Path(row["path"]))
            row["launchables"] = [item.as_dict() for item in items]
        return rows

    def list_projects(self, text):
        """List only directories that prove they are projects."""
        if not os.path.exists(self.projects_dir):
            return "Projects directory not found."

        projects = list_project_dirs(self.projects_dir)

        if not projects:
            return "No projects found in cloned_repos."

        result = f"Available projects ({len(projects)}):\n"
        for project in projects:
            result += f"• {project}\n"
        return result

    def explore_apps(self, text):
        """Explore released .exe apps from real projects only."""
        import glob as _glob

        result = "Released .exe apps from all projects:\n"

        if not os.path.exists(self.projects_dir):
            return "Projects directory not found."

        for project in list_project_dirs(self.projects_dir):
            project_path = os.path.join(self.projects_dir, project)
            # Look for .exe files in dist/, build/, bin/, or root
            exe_files = _glob.glob(
                os.path.join(project_path, "**", "*.exe"), recursive=True
            )
            if exe_files:
                result += f"\n{project}:\n"
                for exe_file in exe_files:
                    rel_path = os.path.relpath(exe_file, self.projects_dir)
                    result += f"  • {rel_path}\n"

        if (
            "explorer" not in text.lower()
            and "apps" not in text.lower()
            and ".exe" not in text.lower()
        ):
            result += (
                "\nTo explore all released apps, say 'open explorer' or 'show apps'."
            )

        return result


class CalendarManager:
    """Agenda view over task due dates, backed by the durable store."""

    def __init__(self, service: AppService | None = None) -> None:
        self.service = service or AppService()

    def _range(self, text: str) -> tuple[datetime.date, datetime.date] | None:
        today = datetime.date.today()
        lowered = (text or "").lower()
        if "today" in lowered:
            return today, today + datetime.timedelta(days=1)
        if "tomorrow" in lowered:
            start = today + datetime.timedelta(days=1)
            return start, start + datetime.timedelta(days=1)
        if "week" in lowered:
            return today, today + datetime.timedelta(days=7)
        if "month" in lowered:
            return today, today + datetime.timedelta(days=30)
        match = re.search(r"\d{4}-\d{2}-\d{2}", text or "")
        if match:
            try:
                day = datetime.date.fromisoformat(match.group())
            except ValueError:
                return None
            return day, day + datetime.timedelta(days=1)
        return None

    @staticmethod
    def _line(task: dict[str, Any]) -> str:
        mark = "[✓]" if task.get("completed") else "[ ]"
        pin = "📌 " if task.get("pinned") else ""
        return f"  {mark} {pin}ID {task['id']}: {task['name']}"

    def get_tasks_for_date(self, text: str = "") -> str:
        """Render the agenda for today, tomorrow, this week, this month, or a date."""
        span = self._range(text)
        if span is None:
            return (
                "I can show you tasks for today, tomorrow, this week, this month, "
                "or a specific date like 2026-11-10."
            )
        start, end = span
        tasks = self.service.tasks_due_between(start, end)
        if not tasks:
            return (
                f"Nothing scheduled between {start.isoformat()} and {end.isoformat()}."
            )

        label = (
            start.isoformat()
            if end - start == datetime.timedelta(days=1)
            else (
                f"{start.isoformat()} → {(end - datetime.timedelta(days=1)).isoformat()}"
            )
        )
        lines = [f"Agenda {label}:"]
        current_day = None
        for task in tasks:
            if task["due"] != current_day:
                current_day = task["due"]
                weekday = datetime.date.fromisoformat(current_day).strftime("%A")
                lines.append(f"{weekday} {current_day}")
            lines.append(self._line(task))
        return "\n".join(lines)

    def schedule_task(
        self, task_name: str, date_str: str, time_str: str | None = None
    ) -> str:
        """Schedule a task at a date (and optional ``HH:MM``)."""
        try:
            day = datetime.date.fromisoformat(date_str)
        except ValueError:
            return f"'{date_str}' is not a date I understand (use YYYY-MM-DD)."
        clock = datetime.time()
        if time_str:
            try:
                clock = datetime.time.fromisoformat(time_str)
            except ValueError:
                return f"'{time_str}' is not a time I understand (use HH:MM)."
        due = datetime.datetime.combine(day, clock, datetime.UTC)
        task = self.service.create_task(task_name, due_at=due)
        return (
            f"Task '{task_name}' scheduled for {day.isoformat()} "
            f"{clock.strftime('%H:%M')} (ID: {task['id']})."
        )


class LauncherManager:
    def __init__(self):
        root = _projects_dir()
        self.study_studio_path = str(root / "Study-Studio")
        self.ld_command_center_path = str(root / "L-D-Command-Center")

    def launch_study_studio(self, text):
        """Launch Study Studio application."""
        import os
        import subprocess

        if not os.path.exists(self.study_studio_path):
            return f"Study Studio not found at {self.study_studio_path}."

        try:
            # Try to launch using python
            subprocess.Popen(
                ["python", "-m", "streamlit", "run", "app.py"],
                cwd=self.study_studio_path,
            )
            return "Launching Study Studio..."
        except Exception as e:
            return f"Failed to launch Study Studio: {str(e)}"

    def launch_ld_command_center(self, text):
        """Launch L-D Command Center application."""
        import os
        import subprocess

        if not os.path.exists(self.ld_command_center_path):
            return f"L-D Command Center not found at {self.ld_command_center_path}."

        try:
            # Try to launch using streamlit
            subprocess.Popen(
                ["python", "-m", "streamlit", "run", "main.py"],
                cwd=self.ld_command_center_path,
            )
            return "Launching L-D Command Center..."
        except Exception as e:
            return f"Failed to launch L-D Command Center: {str(e)}"
