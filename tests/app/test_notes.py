#!/usr/bin/env python3
"""Notes: real create / edit / delete + persistence, and note-vs-task routing.

Run:  ./venv/bin/python -m pytest tests/test_notes.py -q
  or: ./venv/bin/python tests/test_notes.py      (no pytest needed)
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sigmahelix.app.agent import Agent, classify_intent
from sigmahelix.app.managers import NotesManager, clean_content
from sigmahelix.app.service import AppService

RESULTS = []


def fresh_store():
    """Each test gets its own data dir so runs never contaminate each other."""
    os.environ["SIGMAHELIX_DATA_DIR"] = tempfile.mkdtemp(prefix="sigmahelix-notes-")


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(
        ("  PASS  " if cond else "  FAIL  ")
        + name
        + (f"  [{detail}]" if detail else "")
    )
    return bool(cond)


# ---------------------------------------------------------------------------
# storage
# ---------------------------------------------------------------------------
def test_add_edit_delete():
    fresh_store()
    print("\n== notes: add / edit / delete ==")
    mgr = NotesManager()
    n1 = mgr.add("call the accountant")
    n2 = mgr.add("client prefers email")
    check("add returns note with id", n1["id"] == 1 and n2["id"] == 2)
    check("all() lists both", len(mgr.all()) == 2)

    check("update works", mgr.update(2, "client prefers phone"))
    check("update persisted in memory", mgr.get(2)["content"] == "client prefers phone")
    check("update unknown id is False", mgr.update(99, "x") is False)
    check("empty update rejected", mgr.update(2, "   ") is False)

    check("delete works", mgr.delete(1))
    check("delete unknown id is False", mgr.delete(99) is False)
    check("remaining ids are stable", [n["id"] for n in mgr.all()] == [2])


def test_persistence_survives_restart():
    fresh_store()
    print("\n== notes: survive an app restart ==")
    mgr = NotesManager()
    mgr.add("supplier closed on Fridays")
    mgr.add("invoice number 4471")

    reopened = NotesManager()  # simulates restarting the app
    contents = [n["content"] for n in reopened.all()]
    check(
        "notes reloaded from disk",
        contents == ["supplier closed on Fridays", "invoice number 4471"],
        str(contents),
    )

    reopened.update(1, "supplier closed all week")
    check(
        "edit survives restart",
        NotesManager().get(1)["content"] == "supplier closed all week",
    )

    reopened.delete(2)
    check("delete survives restart", len(NotesManager().all()) == 1)


def test_corrupt_legacy_file_does_not_crash():
    fresh_store()
    print("\n== notes: a corrupt legacy file is ignored ==")
    NotesManager().add("kept in the database")
    with open(os.path.join(os.environ["SIGMAHELIX_DATA_DIR"], "notes.json"), "w") as f:
        f.write("{not json")
    service = AppService()
    imported = service.import_legacy_json()
    check("corrupt legacy json imports nothing", imported == {"tasks": 0, "notes": 0})
    check("database notes survive", len(NotesManager().all()) == 1)


def test_clean_content():
    print("\n== notes: content cleaning keeps the middle of the text ==")
    cases = {
        "create note call the accountant at 3pm": "call the accountant at 3pm",
        "write down that the supplier is closed": "the supplier is closed",
        "note that the meeting moved": "the meeting moved",
        "remember to call supplier": "call supplier",
        "write report": "write report",
        "create task write report": "write report",
    }
    for raw, want in cases.items():
        got = clean_content(raw)
        check(f"{raw!r} -> {want!r}", got == want, got)


def test_text_commands():
    fresh_store()
    print("\n== notes: text commands (agent / console) ==")
    mgr = NotesManager()
    out = mgr.create_note("create note call the accountant at 3pm")
    check("create_note reports the id", "ID: 1" in out, out)
    check(
        "create_note stores clean text",
        mgr.get(1)["content"] == "call the accountant at 3pm",
    )
    check(
        "edit_note changes text",
        "updated" in mgr.edit_note("edit note 1 call the auditor"),
    )
    check("edit_note applied", mgr.get(1)["content"] == "call the auditor")
    check("edit_note needs an id", "specify" in mgr.edit_note("edit note").lower())
    check("delete_note removes", "deleted" in mgr.delete_note("delete note 1"))
    check("delete_note unknown", "not found" in mgr.delete_note("delete note 9"))


# ---------------------------------------------------------------------------
# intent routing: a task must never become a note
# ---------------------------------------------------------------------------
def test_classify_intent():
    print("\n== routing: note vs task intent ==")
    task_cases = [
        "remind me to call the supplier at 4pm",
        "remember to review the report on Friday",
        "add a task to write meeting notes",
        "create task audit expense receipts",
        "schedule the dentist appointment",
        "what are my tasks today",
        "call the supplier at 4pm",
        "review the report Friday",
        "buy milk",
        "open the task list",
    ]
    note_cases = [
        "note that the supplier is closed on Fridays",
        "write down that the client prefers email",
        "make a note: invoice 4471",
        "memo: the wifi password is on the router",
    ]
    for t in task_cases:
        got = classify_intent(t)
        check(f"task: {t!r}", got == "task", str(got))
    for t in note_cases:
        got = classify_intent(t)
        check(f"note: {t!r}", got == "note", str(got))
    check("plain chat has no intent", classify_intent("hello there") is None)


def test_agent_routes_reminders_to_tasks():
    fresh_store()
    print("\n== routing: agent does not write notes for tasks ==")
    orig = Agent._check_llm
    Agent._check_llm = lambda self, timeout=2.0: False
    try:
        a = Agent()
        a.process_command("remind me to call the supplier at 4pm")
        a.process_command("remember to review the report on Friday")
        check("two tasks created", len(a.tasks.tasks) == 2, str(a.tasks.tasks))
        check("no notes created", a.notes.all() == [], str(a.notes.all()))

        a.process_command("note that the supplier is closed on Fridays")
        check("information becomes a note", len(a.notes.all()) == 1, str(a.notes.all()))
        check("still two tasks", len(a.tasks.tasks) == 2)

        # the LLM may still pick the wrong action — the guard must win
        a._execute("create_note", "", "remind me to pay the invoice")
        check(
            "create_note coerced to task for a duty",
            len(a.tasks.tasks) == 3 and len(a.notes.all()) == 1,
        )
        a._execute("create_task", "", "note that the office closes at 6pm")
        check(
            "create_task coerced to note for information",
            len(a.notes.all()) == 2 and len(a.tasks.tasks) == 3,
        )
    finally:
        Agent._check_llm = orig


# ---------------------------------------------------------------------------
# GUI: the panel must actually let you write, edit, delete
# ---------------------------------------------------------------------------
def test_gui_notes_crud():
    fresh_store()
    print("\n== GUI: notes panel write / edit / delete ==")
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        check("GUI notes test", True, "skipped (no display)")
        return
    try:
        from main import CompanyOSApp
    except Exception as e:  # pragma: no cover
        check("GUI notes test", False, f"import failed: {e}")
        return

    app = CompanyOSApp()
    a = app.app
    a.update()

    check("notes list widget exists", hasattr(app, "note_list"))
    check("note entry is editable", str(app.note_entry.cget("state")) == "normal")

    app.note_entry.insert(0, "buy printer paper")
    app._save_note()
    a.update()
    check("note added from the GUI", len(app.agent.notes.all()) == 1)
    check(
        "note rendered in the list",
        any(
            "buy printer paper" in str(w.cget("text"))
            for card in app.note_list.winfo_children()
            for w in card.winfo_children()
            if hasattr(w, "cget")
        ),
    )

    note_id = app.agent.notes.all()[0]["id"]
    app._edit_note(note_id)
    a.update()
    check(
        "edit loads the note into the entry",
        app.note_entry.get() == "buy printer paper",
    )
    check("button switches to Save", "Save" in app.note_btn.cget("text"))
    app.note_entry.delete(0, "end")
    app.note_entry.insert(0, "buy A4 printer paper")
    app._save_note()
    a.update()
    check(
        "edit saved", app.agent.notes.get(note_id)["content"] == "buy A4 printer paper"
    )
    check("edit mode cleared", app.note_edit_id is None)
    check("button back to Add", "Add" in app.note_btn.cget("text"))

    app._delete_note(note_id)
    a.update()
    check("note deleted from the GUI", app.agent.notes.all() == [])

    # layout must still fit: notes controls may not blow the row budget
    w, h = app.app.winfo_reqwidth(), app.app.winfo_reqheight()
    check("window still fits without scrolling", w <= 1260 and h <= 800, f"{w}x{h}")
    canvas_h = app.note_list._parent_canvas.winfo_height()
    check("notes list has a usable viewport", canvas_h >= 100, f"{canvas_h}px")

    a.destroy()


if __name__ == "__main__":
    test_add_edit_delete()
    test_persistence_survives_restart()
    test_corrupt_legacy_file_does_not_crash()
    test_clean_content()
    test_text_commands()
    test_classify_intent()
    test_agent_routes_reminders_to_tasks()
    test_gui_notes_crud()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    if failed:
        print("FAILED:")
        for name, _, detail in failed:
            print("  -", name, detail)
        sys.exit(1)
