"""Pure date-based recurrence rules for daily, weekly, and monthly work."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum


class RecurrenceError(ValueError):
    """Raised when a recurrence rule or expansion range is invalid."""


class RecurrenceFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class RecurrenceRule:
    """An anchored all-day recurrence with an optional count or end date.

    Weekday numbers use Python's convention: Monday is 0 and Sunday is 6.
    Weekly rules default to the anchor weekday. Monthly day numbers beyond a
    month's length clamp to that month's last day.
    """

    frequency: RecurrenceFrequency
    anchor: date
    interval: int = 1
    weekdays: tuple[int, ...] = ()
    day_of_month: int | None = None
    count: int | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.frequency, RecurrenceFrequency):
            raise RecurrenceError("frequency must be a RecurrenceFrequency")
        if not isinstance(self.anchor, date) or isinstance(self.anchor, datetime):
            raise RecurrenceError("anchor must be a date, not a datetime")
        if (
            isinstance(self.interval, bool)
            or not isinstance(self.interval, int)
            or self.interval < 1
        ):
            raise RecurrenceError("interval must be a positive integer")
        if not isinstance(self.weekdays, tuple) or any(
            isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6
            for day in self.weekdays
        ):
            raise RecurrenceError("weekdays must be a tuple of values from 0 to 6")
        if len(set(self.weekdays)) != len(self.weekdays):
            raise RecurrenceError("weekdays must not contain duplicates")
        if self.weekdays and self.frequency == RecurrenceFrequency.MONTHLY:
            raise RecurrenceError("monthly rules cannot also select weekdays")
        if self.day_of_month is not None:
            if (
                isinstance(self.day_of_month, bool)
                or not isinstance(self.day_of_month, int)
                or not 1 <= self.day_of_month <= 31
            ):
                raise RecurrenceError("day_of_month must be between 1 and 31")
            if self.frequency != RecurrenceFrequency.MONTHLY:
                raise RecurrenceError("day_of_month is only valid for monthly rules")
        if self.count is not None and (
            isinstance(self.count, bool)
            or not isinstance(self.count, int)
            or self.count < 1
        ):
            raise RecurrenceError("count must be a positive integer or None")
        if self.end_date is not None:
            if not isinstance(self.end_date, date) or isinstance(
                self.end_date, datetime
            ):
                raise RecurrenceError("end_date must be a date or None")
            if self.end_date < self.anchor:
                raise RecurrenceError("end_date must not be before anchor")


def _matches(rule: RecurrenceRule, candidate: date) -> bool:
    if candidate < rule.anchor:
        return False
    if rule.end_date is not None and candidate > rule.end_date:
        return False
    if rule.frequency == RecurrenceFrequency.DAILY:
        day_delta = (candidate - rule.anchor).days
        return day_delta % rule.interval == 0 and (
            not rule.weekdays or candidate.weekday() in rule.weekdays
        )
    if rule.frequency == RecurrenceFrequency.WEEKLY:
        anchor_monday = rule.anchor - timedelta(days=rule.anchor.weekday())
        candidate_monday = candidate - timedelta(days=candidate.weekday())
        week_delta = (candidate_monday - anchor_monday).days // 7
        weekdays = rule.weekdays or (rule.anchor.weekday(),)
        return week_delta % rule.interval == 0 and candidate.weekday() in weekdays
    month_delta = (
        (candidate.year - rule.anchor.year) * 12 + candidate.month - rule.anchor.month
    )
    if month_delta % rule.interval != 0:
        return False
    requested_day = rule.day_of_month or rule.anchor.day
    expected_day = min(
        requested_day, calendar.monthrange(candidate.year, candidate.month)[1]
    )
    return candidate.day == expected_day


def occurs_on(rule: RecurrenceRule, candidate: date) -> bool:
    """Return whether a calendar date is part of the recurrence series."""
    if not isinstance(rule, RecurrenceRule):
        raise RecurrenceError("rule must be a RecurrenceRule")
    if not isinstance(candidate, date) or isinstance(candidate, datetime):
        raise RecurrenceError("candidate must be a date")
    return _matches(rule, candidate)


def occurrences(
    rule: RecurrenceRule,
    through: date,
    after: date | None = None,
    limit: int = 1000,
) -> list[date]:
    """Expand a bounded recurrence through an inclusive date, after an exclusive cursor."""
    if not isinstance(rule, RecurrenceRule):
        raise RecurrenceError("rule must be a RecurrenceRule")
    if not isinstance(through, date) or isinstance(through, datetime):
        raise RecurrenceError("through must be a date")
    if after is not None and (
        not isinstance(after, date) or isinstance(after, datetime)
    ):
        raise RecurrenceError("after must be a date or None")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise RecurrenceError("limit must be a positive integer")
    if through < rule.anchor:
        return []

    result: list[date] = []
    occurrence_count = 0
    cursor = rule.anchor
    while cursor <= through:
        if _matches(rule, cursor):
            occurrence_count += 1
            if rule.count is not None and occurrence_count > rule.count:
                break
            if after is None or cursor > after:
                result.append(cursor)
                if len(result) == limit:
                    break
        if cursor == through:
            break
        cursor += timedelta(days=1)
    return result
