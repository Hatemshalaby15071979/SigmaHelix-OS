"""A small persisted scheduler with transactional run claims and an injected clock."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ..logging import redact_text
from .audit import AuditLog
from .database import Database

_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|credential|private.?key|api.?key|access.?key|authorization",
    re.IGNORECASE,
)
Clock = Callable[[], datetime]
JobHandler = Callable[[Mapping[str, Any]], None]


class SchedulerError(RuntimeError):
    """Raised when a scheduled job cannot be safely registered or claimed."""


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    """A persisted one-shot or fixed-interval job definition."""

    id: UUID
    tenant_id: str
    job_type: str
    payload: Mapping[str, Any]
    next_run_at: datetime
    interval_seconds: int | None
    enabled: bool
    created_at: datetime
    last_run_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class JobRun:
    """One durable claim and final handler outcome for a scheduled slot."""

    id: UUID
    job_id: UUID
    tenant_id: str
    scheduled_for: datetime
    started_at: datetime
    finished_at: datetime
    status: str
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class MissedJobRun:
    """A durable overdue slot or interrupted callback requiring review."""

    id: UUID
    job_id: UUID
    tenant_id: str
    scheduled_for: datetime
    detected_at: datetime
    reason: str
    state: str


def _utc(value: datetime, label: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise SchedulerError(f"{label} must be a timezone-aware datetime")
    return value.astimezone(UTC)


def _payload_json(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping) or any(
        not isinstance(key, str) for key in payload
    ):
        raise SchedulerError("job payload must be a mapping with string keys")

    def check(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str) or _SENSITIVE_KEY.search(key):
                    raise SchedulerError("job payload must not contain secret fields")
                check(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                check(child)
        elif isinstance(value, str) and redact_text(value) != value:
            raise SchedulerError("job payload must not contain secret-like values")

    check(payload)
    try:
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise SchedulerError("job payload must contain finite JSON values") from exc


def _job_from_row(row) -> ScheduledJob:
    return ScheduledJob(
        id=UUID(row["id"]),
        tenant_id=row["tenant_id"],
        job_type=row["job_type"],
        payload=json.loads(row["payload_json"]),
        next_run_at=datetime.fromisoformat(row["next_run_at"]),
        interval_seconds=row["interval_seconds"],
        enabled=bool(row["enabled"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        last_run_at=datetime.fromisoformat(row["last_run_at"])
        if row["last_run_at"]
        else None,
    )


class Scheduler:
    """Claim due jobs once across concurrent instances, then invoke handlers."""

    def __init__(self, database: Database, clock: Clock | None = None) -> None:
        self.database = database
        self._clock = clock or (lambda: datetime.now(UTC))
        self._handlers: dict[str, JobHandler] = {}
        self._audit = AuditLog(database)

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register one process-local handler for a durable job type."""
        if not isinstance(job_type, str) or not job_type.strip():
            raise ValueError("job_type must be a non-empty string")
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._handlers[job_type] = handler

    def schedule(
        self,
        job_type: str,
        payload: Mapping[str, Any],
        run_at: datetime,
        tenant_id: str = "local",
        interval_seconds: int | None = None,
        job_id: UUID | None = None,
    ) -> ScheduledJob:
        """Persist one one-shot or fixed-interval job definition."""
        if not isinstance(job_type, str) or not job_type.strip():
            raise ValueError("job_type must be a non-empty string")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if job_id is not None and not isinstance(job_id, UUID):
            raise ValueError("job_id must be a UUID or None")
        if interval_seconds is not None and (
            isinstance(interval_seconds, bool)
            or not isinstance(interval_seconds, int)
            or interval_seconds < 1
            or interval_seconds > 3_153_600_000
        ):
            raise ValueError("interval_seconds must be between 1 and 3153600000")
        now = _utc(self._clock(), "clock")
        scheduled_at = _utc(run_at, "run_at")
        encoded_payload = _payload_json(payload)
        identifier = job_id or uuid4()
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO scheduled_jobs (id, tenant_id, job_type, payload_json, "
                "next_run_at, interval_seconds, enabled, created_at, last_run_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, NULL)",
                (
                    str(identifier),
                    tenant_id,
                    job_type,
                    encoded_payload,
                    scheduled_at.isoformat(),
                    interval_seconds,
                    now.isoformat(),
                ),
            )
        return ScheduledJob(
            identifier,
            tenant_id,
            job_type,
            json.loads(encoded_payload),
            scheduled_at,
            interval_seconds,
            True,
            now,
        )

    def get_job(self, job_id: UUID, tenant_id: str = "local") -> ScheduledJob | None:
        """Return a persisted job within the requested tenant."""
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM scheduled_jobs WHERE id = ? AND tenant_id = ?",
                (str(job_id), tenant_id),
            ).fetchone()
        return _job_from_row(row) if row is not None else None

    def cancel(self, job_id: UUID, tenant_id: str = "local") -> bool:
        """Disable future runs without deleting the job's run history."""
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE scheduled_jobs SET enabled = 0 WHERE id = ? AND tenant_id = ? AND enabled = 1",
                (str(job_id), tenant_id),
            )
        return cursor.rowcount == 1

    def run_due(self) -> list[JobRun]:
        """Claim due slots transactionally and run each callback once.

        A handler failure is recorded as a failed run and does not prevent other
        due handlers from running. Recovery of interrupted `running` records is
        left to P2-004.
        """
        now = _utc(self._clock(), "clock")
        pending: list[tuple[UUID, str, str, datetime, datetime, Mapping[str, Any]]] = []
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM scheduled_jobs WHERE enabled = 1 AND next_run_at <= ? "
                "AND NOT EXISTS (SELECT 1 FROM missed_job_runs m "
                "WHERE m.tenant_id = scheduled_jobs.tenant_id "
                "AND m.job_id = scheduled_jobs.id AND m.scheduled_for = scheduled_jobs.next_run_at "
                "AND m.state = 'pending') "
                "ORDER BY next_run_at, id",
                (now.isoformat(),),
            ).fetchall()
            for row in rows:
                job = _job_from_row(row)
                scheduled_for = job.next_run_at.astimezone(UTC)
                run_id = uuid5(
                    NAMESPACE_URL,
                    f"sigmahelix:job-run:{job.id}:{scheduled_for.isoformat()}",
                )
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO job_runs (id, tenant_id, job_id, scheduled_for, "
                    "started_at, finished_at, status, error_type) "
                    "VALUES (?, ?, ?, ?, ?, NULL, 'running', NULL)",
                    (
                        str(run_id),
                        job.tenant_id,
                        str(job.id),
                        scheduled_for.isoformat(),
                        now.isoformat(),
                    ),
                )
                if cursor.rowcount != 1:
                    continue
                if job.interval_seconds is None:
                    connection.execute(
                        "UPDATE scheduled_jobs SET enabled = 0, last_run_at = ? "
                        "WHERE id = ? AND tenant_id = ?",
                        (scheduled_for.isoformat(), str(job.id), job.tenant_id),
                    )
                else:
                    next_run = scheduled_for + timedelta(seconds=job.interval_seconds)
                    connection.execute(
                        "UPDATE scheduled_jobs SET next_run_at = ?, last_run_at = ? "
                        "WHERE id = ? AND tenant_id = ?",
                        (
                            next_run.isoformat(),
                            scheduled_for.isoformat(),
                            str(job.id),
                            job.tenant_id,
                        ),
                    )
                pending.append(
                    (
                        run_id,
                        str(job.id),
                        job.tenant_id,
                        scheduled_for,
                        now,
                        job.payload,
                    )
                )

        completed: list[JobRun] = []
        for (
            run_id,
            job_id_text,
            tenant_id,
            scheduled_for,
            started_at,
            payload,
        ) in pending:
            claimed_job = self.get_job(UUID(job_id_text), tenant_id)
            handler = (
                self._handlers.get(claimed_job.job_type)
                if claimed_job is not None
                else None
            )
            error_type: str | None = None
            status = "succeeded"
            if handler is None:
                status = "failed"
                error_type = "HandlerNotRegistered"
            else:
                try:
                    handler(payload)
                except Exception as exc:
                    status = "failed"
                    error_type = type(exc).__name__
            finished_at = _utc(self._clock(), "clock")
            event_type = f"scheduler.job.{status}"
            event_id = uuid5(NAMESPACE_URL, f"sigmahelix:{event_type}:{run_id}")
            audit_payload = {
                "job_id": job_id_text,
                "run_id": str(run_id),
                "scheduled_for": scheduled_for.isoformat(),
                "status": status,
                "error_type": error_type or "",
            }
            with self.database.transaction() as connection:
                connection.execute(
                    "UPDATE job_runs SET finished_at = ?, status = ?, error_type = ? "
                    "WHERE id = ? AND tenant_id = ? AND status = 'running'",
                    (
                        finished_at.isoformat(),
                        status,
                        error_type,
                        str(run_id),
                        tenant_id,
                    ),
                )
                connection.execute(
                    "INSERT INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(event_id),
                        tenant_id,
                        event_type,
                        json.dumps(
                            audit_payload, sort_keys=True, separators=(",", ":")
                        ),
                        finished_at.isoformat(),
                    ),
                )
                self._audit.append_in_transaction(
                    connection,
                    event_type,
                    "scheduled_job",
                    job_id_text,
                    audit_payload,
                    tenant_id=tenant_id,
                    occurred_at=finished_at,
                )
            completed.append(
                JobRun(
                    run_id,
                    UUID(job_id_text),
                    tenant_id,
                    scheduled_for,
                    started_at,
                    finished_at,
                    status,
                    error_type,
                )
            )
        return completed

    def recover_missed(self, tenant_id: str = "local") -> list[MissedJobRun]:
        """Persist and return overdue and interrupted slots for explicit review.

        Call once during process startup before polling due work. Overdue slots
        remain blocked from dispatch until acknowledged. Interrupted slots are
        reported but are not automatically retried because their side effects
        may already have happened before the process stopped.
        """
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        now = _utc(self._clock(), "clock")
        discovered: list[tuple[UUID, str, str, datetime, str]] = []
        with self.database.transaction() as connection:
            overdue_rows = connection.execute(
                "SELECT j.id, j.tenant_id, j.next_run_at FROM scheduled_jobs j "
                "WHERE j.enabled = 1 AND j.next_run_at <= ? "
                "AND NOT EXISTS (SELECT 1 FROM job_runs r WHERE r.tenant_id = j.tenant_id "
                "AND r.job_id = j.id AND r.scheduled_for = j.next_run_at) "
                "AND NOT EXISTS (SELECT 1 FROM missed_job_runs m WHERE m.tenant_id = j.tenant_id "
                "AND m.job_id = j.id AND m.scheduled_for = j.next_run_at) "
                "AND j.tenant_id = ?",
                (now.isoformat(), tenant_id),
            ).fetchall()
            interrupted_rows = connection.execute(
                "SELECT r.id, r.job_id, r.tenant_id, r.scheduled_for "
                "FROM job_runs r WHERE r.status = 'running' "
                "AND NOT EXISTS (SELECT 1 FROM missed_job_runs m WHERE m.tenant_id = r.tenant_id "
                "AND m.job_id = r.job_id AND m.scheduled_for = r.scheduled_for) "
                "AND r.tenant_id = ?",
                (tenant_id,),
            ).fetchall()
            discovered.extend(
                (
                    uuid5(
                        NAMESPACE_URL,
                        f"sigmahelix:job-run:{row['id']}:{row['next_run_at']}",
                    ),
                    row["id"],
                    row["tenant_id"],
                    datetime.fromisoformat(row["next_run_at"]),
                    "overdue",
                )
                for row in overdue_rows
            )
            discovered.extend(
                (
                    UUID(row["id"]),
                    row["job_id"],
                    row["tenant_id"],
                    datetime.fromisoformat(row["scheduled_for"]),
                    "interrupted",
                )
                for row in interrupted_rows
            )
            for run_id, job_id, record_tenant_id, scheduled_for, reason in discovered:
                missed_cursor = connection.execute(
                    "INSERT OR IGNORE INTO missed_job_runs "
                    "(id, tenant_id, job_id, scheduled_for, detected_at, reason, state, acknowledged_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL)",
                    (
                        str(run_id),
                        record_tenant_id,
                        job_id,
                        scheduled_for.isoformat(),
                        now.isoformat(),
                        reason,
                    ),
                )
                if missed_cursor.rowcount != 1:
                    continue
                event_type = "scheduler.job.missed"
                event_id = uuid5(NAMESPACE_URL, f"sigmahelix:{event_type}:{run_id}")
                audit_payload = {
                    "job_id": job_id,
                    "run_id": str(run_id),
                    "scheduled_for": scheduled_for.isoformat(),
                    "reason": reason,
                }
                connection.execute(
                    "INSERT OR IGNORE INTO events (id, tenant_id, event_type, payload_json, occurred_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        str(event_id),
                        record_tenant_id,
                        event_type,
                        json.dumps(
                            audit_payload, sort_keys=True, separators=(",", ":")
                        ),
                        now.isoformat(),
                    ),
                )
                self._audit.append_in_transaction(
                    connection,
                    event_type,
                    "scheduled_job",
                    job_id,
                    audit_payload,
                    tenant_id=record_tenant_id,
                    occurred_at=now,
                )
        return self.list_missed_runs(tenant_id)

    def list_missed_runs(
        self, tenant_id: str = "local", include_acknowledged: bool = False
    ) -> list[MissedJobRun]:
        """List missed slots for a tenant, pending first by scheduled time."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        with self.database.connection() as connection:
            query = "SELECT * FROM missed_job_runs WHERE tenant_id = ?"
            parameters: tuple[str, ...] = (tenant_id,)
            if not include_acknowledged:
                query += " AND state = 'pending'"
            query += " ORDER BY scheduled_for, id"
            rows = connection.execute(query, parameters).fetchall()
        return [
            MissedJobRun(
                UUID(row["id"]),
                UUID(row["job_id"]),
                row["tenant_id"],
                datetime.fromisoformat(row["scheduled_for"]),
                datetime.fromisoformat(row["detected_at"]),
                row["reason"],
                row["state"],
            )
            for row in rows
        ]

    def acknowledge_missed(self, run_id: UUID, tenant_id: str = "local") -> bool:
        """Acknowledge a missed slot; an unclaimed overdue slot may then run."""
        if not isinstance(run_id, UUID):
            raise ValueError("run_id must be a UUID")
        now = _utc(self._clock(), "clock")
        with self.database.transaction() as connection:
            cursor = connection.execute(
                "UPDATE missed_job_runs SET state = 'acknowledged', acknowledged_at = ? "
                "WHERE id = ? AND tenant_id = ? AND state = 'pending'",
                (now.isoformat(), str(run_id), tenant_id),
            )
        return cursor.rowcount == 1

    def list_runs(self, job_id: UUID, tenant_id: str = "local") -> list[JobRun]:
        """Return a job's durable runs in scheduled order."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM job_runs WHERE job_id = ? AND tenant_id = ? "
                "ORDER BY scheduled_for",
                (str(job_id), tenant_id),
            ).fetchall()
        return [
            JobRun(
                UUID(row["id"]),
                UUID(row["job_id"]),
                row["tenant_id"],
                datetime.fromisoformat(row["scheduled_for"]),
                datetime.fromisoformat(row["started_at"]),
                datetime.fromisoformat(row["finished_at"])
                if row["finished_at"]
                else datetime.fromisoformat(row["started_at"]),
                row["status"],
                row["error_type"],
            )
            for row in rows
        ]
