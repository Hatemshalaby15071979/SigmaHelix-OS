"""The agenda is built from real task due dates."""

import datetime

from sigmahelix.app.managers import CalendarManager, TasksManager


def test_scheduling_creates_a_task_with_a_due_date():
    calendar = CalendarManager()
    today = datetime.date.today().isoformat()

    message = calendar.schedule_task("Prepare the QBR deck", today, "14:30")

    assert "scheduled" in message
    due = TasksManager().tasks[0]
    assert due["name"] == "Prepare the QBR deck"
    assert due["due"] == today


def test_agenda_lists_today_and_tomorrow_only():
    calendar = CalendarManager()
    tasks = TasksManager()
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)

    calendar.schedule_task("Today item", today.isoformat())
    calendar.schedule_task("Tomorrow item", tomorrow.isoformat())
    calendar.schedule_task(
        "Next month item", (today + datetime.timedelta(days=40)).isoformat()
    )

    today_view = calendar.get_tasks_for_date("today")
    assert "Today item" in today_view
    assert "Tomorrow item" not in today_view

    week_view = calendar.get_tasks_for_date("week")
    assert "Today item" in week_view
    assert "Tomorrow item" in week_view
    assert "Next month item" not in week_view

    assert len(tasks.tasks) == 3


def test_agenda_rejects_unparseable_dates():
    calendar = CalendarManager()
    assert "not a date" in calendar.schedule_task("x", "next tuesday")
    assert "not a time" in calendar.schedule_task("x", "2026-11-10", "noon")


def test_agenda_with_nothing_scheduled_says_so():
    assert "Nothing scheduled" in CalendarManager().get_tasks_for_date("today")
