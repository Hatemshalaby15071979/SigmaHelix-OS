import random
from datetime import date, datetime, timedelta

import pytest

from sigmahelix.core.recurrence import (
    RecurrenceError,
    RecurrenceFrequency,
    RecurrenceRule,
    occurrences,
    occurs_on,
)


def test_daily_every_n_and_weekday_filter_are_both_applied():
    rule = RecurrenceRule(
        RecurrenceFrequency.DAILY,
        date(2026, 11, 2),
        interval=2,
        weekdays=(0, 1, 2, 3, 4),
    )

    assert occurrences(rule, date(2026, 11, 12)) == [
        date(2026, 11, 2),
        date(2026, 11, 4),
        date(2026, 11, 6),
        date(2026, 11, 10),
        date(2026, 11, 12),
    ]


def test_weekly_rules_select_multiple_weekdays_every_n_weeks():
    rule = RecurrenceRule(
        RecurrenceFrequency.WEEKLY,
        date(2026, 11, 2),
        interval=2,
        weekdays=(1, 3),
    )

    assert occurrences(rule, date(2026, 11, 23)) == [
        date(2026, 11, 3),
        date(2026, 11, 5),
        date(2026, 11, 17),
        date(2026, 11, 19),
    ]


def test_weekly_rule_defaults_to_anchor_weekday():
    rule = RecurrenceRule(RecurrenceFrequency.WEEKLY, date(2026, 11, 4), interval=2)

    assert occurrences(rule, date(2026, 11, 30)) == [
        date(2026, 11, 4),
        date(2026, 11, 18),
    ]


def test_monthly_day_31_clamps_to_month_end_and_handles_leap_year():
    rule = RecurrenceRule(
        RecurrenceFrequency.MONTHLY,
        date(2024, 1, 31),
        day_of_month=31,
    )

    assert occurrences(rule, date(2024, 5, 31)) == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
        date(2024, 4, 30),
        date(2024, 5, 31),
    ]


def test_monthly_every_n_count_end_date_and_exclusive_cursor():
    rule = RecurrenceRule(
        RecurrenceFrequency.MONTHLY,
        date(2026, 1, 30),
        interval=2,
        count=3,
        end_date=date(2026, 8, 31),
    )

    assert occurrences(rule, date(2026, 12, 31)) == [
        date(2026, 1, 30),
        date(2026, 3, 30),
        date(2026, 5, 30),
    ]
    assert occurrences(rule, date(2026, 12, 31), after=date(2026, 3, 30)) == [
        date(2026, 5, 30)
    ]
    assert occurs_on(rule, date(2026, 3, 30))
    assert not occurs_on(rule, date(2026, 4, 30))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"interval": 0},
        {"interval": True},
        {"weekdays": (0, 0)},
        {"weekdays": (7,)},
        {"day_of_month": 32},
        {"count": 0},
        {"end_date": date(2026, 1, 1)},
    ],
)
def test_invalid_recurrence_rules_are_rejected(kwargs):
    with pytest.raises(RecurrenceError):
        RecurrenceRule(
            RecurrenceFrequency.DAILY,
            date(2026, 2, 1),
            **kwargs,
        )


def test_rule_and_expansion_types_are_checked():
    with pytest.raises(RecurrenceError, match="frequency"):
        RecurrenceRule("daily", date(2026, 1, 1))
    with pytest.raises(RecurrenceError, match="not a datetime"):
        RecurrenceRule(RecurrenceFrequency.DAILY, datetime(2026, 1, 1))
    with pytest.raises(RecurrenceError, match="through"):
        occurrences(
            RecurrenceRule(RecurrenceFrequency.DAILY, date(2026, 1, 1)),
            datetime(2026, 1, 1),
        )


def test_ten_thousand_deterministically_generated_rules_obey_recurrence_invariants():
    generator = random.Random(42)
    base = date(2000, 1, 1)

    for _ in range(10_000):
        anchor = base + timedelta(days=generator.randrange(0, 10_000))
        frequency = generator.choice(tuple(RecurrenceFrequency))
        interval = generator.randrange(1, 13)
        weekdays = ()
        day_of_month = None
        if frequency == RecurrenceFrequency.WEEKLY:
            weekdays = tuple(day for day in range(7) if generator.random() < 0.35) or (
                anchor.weekday(),
            )
        elif frequency == RecurrenceFrequency.DAILY and generator.random() < 0.4:
            weekdays = tuple(day for day in range(5) if generator.random() < 0.65) or (
                anchor.weekday(),
            )
        elif frequency == RecurrenceFrequency.MONTHLY and generator.random() < 0.5:
            day_of_month = generator.randrange(1, 32)
        count = generator.choice((None, None, generator.randrange(1, 20)))
        duration = generator.randrange(0, 366)
        through = anchor + timedelta(days=duration)
        end_date = (
            anchor + timedelta(days=generator.randrange(0, 366))
            if generator.random() < 0.25
            else None
        )
        rule = RecurrenceRule(
            frequency,
            anchor,
            interval=interval,
            weekdays=weekdays,
            day_of_month=day_of_month,
            count=count,
            end_date=end_date,
        )

        result = occurrences(rule, through, limit=1000)
        assert result == sorted(set(result))
        assert all(anchor <= day <= through and occurs_on(rule, day) for day in result)
        if count is not None:
            assert len(result) <= count
        cursor = anchor + timedelta(days=generator.randrange(0, duration + 1))
        resumed = occurrences(rule, through, after=cursor, limit=1000)
        assert resumed == [day for day in result if day > cursor]
