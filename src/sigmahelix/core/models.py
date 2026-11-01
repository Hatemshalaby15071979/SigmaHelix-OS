"""Validated domain records used by the SigmaHelix durable core."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_TENANT = "local"


class DomainValidationError(ValueError):
    """Raised when a domain record violates its invariants."""


class TaskStatus(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"
    R3 = "R3"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


def _non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DomainValidationError(f"{field_name} must be a non-empty string")


def _aware_utc(value: datetime, field_name: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DomainValidationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _ordered_times(
    start: datetime, end: datetime, start_name: str, end_name: str
) -> None:
    if end < start:
        raise DomainValidationError(f"{end_name} must not be earlier than {start_name}")


def _sha256(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise DomainValidationError(
            f"{field_name} must be 64 lowercase hexadecimal characters"
        )


def _json_object(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise DomainValidationError(f"{field_name} must be a mapping with string keys")
    try:
        encoded = json.dumps(value, allow_nan=False, sort_keys=True)
        normalized = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(
            f"{field_name} must contain finite JSON values"
        ) from exc
    if not isinstance(normalized, dict):
        raise DomainValidationError(f"{field_name} must be a JSON object")
    return normalized


def _tags(value: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(tag, str) or not tag.strip() for tag in value
    ):
        raise DomainValidationError("tags must be a tuple of non-empty strings")
    normalized = tuple(tag.strip() for tag in value)
    if len(set(normalized)) != len(normalized):
        raise DomainValidationError("tags must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class Task:
    """A durable unit of work; recurring occurrence completion is separate."""

    title: str
    id: UUID = field(default_factory=uuid4)
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    project_id: UUID | None = None
    due_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str = _LOCAL_TENANT

    def __post_init__(self) -> None:
        _non_empty(self.title, "title")
        if not isinstance(self.id, UUID):
            raise DomainValidationError("id must be a UUID")
        if not isinstance(self.status, TaskStatus):
            raise DomainValidationError("status must be a TaskStatus")
        if self.project_id is not None and not isinstance(self.project_id, UUID):
            raise DomainValidationError("project_id must be a UUID or None")
        if not isinstance(self.description, str):
            raise DomainValidationError("description must be a string")
        _non_empty(self.tenant_id, "tenant_id")
        created = _aware_utc(self.created_at, "created_at")
        updated = _aware_utc(self.updated_at, "updated_at")
        _ordered_times(created, updated, "created_at", "updated_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        if self.due_at is not None:
            object.__setattr__(self, "due_at", _aware_utc(self.due_at, "due_at"))


@dataclass(frozen=True, slots=True)
class Note:
    """A user-authored durable note, optionally associated with a project."""

    content: str
    id: UUID = field(default_factory=uuid4)
    project_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str = _LOCAL_TENANT

    def __post_init__(self) -> None:
        _non_empty(self.content, "content")
        if not isinstance(self.id, UUID):
            raise DomainValidationError("id must be a UUID")
        if self.project_id is not None and not isinstance(self.project_id, UUID):
            raise DomainValidationError("project_id must be a UUID or None")
        _non_empty(self.tenant_id, "tenant_id")
        created = _aware_utc(self.created_at, "created_at")
        updated = _aware_utc(self.updated_at, "updated_at")
        _ordered_times(created, updated, "created_at", "updated_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)


@dataclass(frozen=True, slots=True)
class Project:
    """A registered local project directory."""

    name: str
    root_path: Path
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_scanned_at: datetime | None = None
    tenant_id: str = _LOCAL_TENANT

    def __post_init__(self) -> None:
        _non_empty(self.name, "name")
        if not isinstance(self.id, UUID):
            raise DomainValidationError("id must be a UUID")
        if not isinstance(self.root_path, Path) or not self.root_path.is_absolute():
            raise DomainValidationError("root_path must be an absolute Path")
        _non_empty(self.tenant_id, "tenant_id")
        created = _aware_utc(self.created_at, "created_at")
        updated = _aware_utc(self.updated_at, "updated_at")
        _ordered_times(created, updated, "created_at", "updated_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "updated_at", updated)
        if self.last_scanned_at is not None:
            object.__setattr__(
                self,
                "last_scanned_at",
                _aware_utc(self.last_scanned_at, "last_scanned_at"),
            )


@dataclass(frozen=True, slots=True)
class Event:
    """A timestamped domain event with an immutable JSON-compatible payload."""

    event_type: str
    payload: Mapping[str, Any]
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str = _LOCAL_TENANT

    def __post_init__(self) -> None:
        _non_empty(self.event_type, "event_type")
        if not isinstance(self.id, UUID):
            raise DomainValidationError("id must be a UUID")
        _non_empty(self.tenant_id, "tenant_id")
        object.__setattr__(
            self, "occurred_at", _aware_utc(self.occurred_at, "occurred_at")
        )
        object.__setattr__(self, "payload", _json_object(self.payload, "payload"))


@dataclass(frozen=True, slots=True)
class Approval:
    """A time-bounded human decision bound to an action payload hash."""

    action: str
    risk: RiskLevel
    payload_sha256: str
    expires_at: datetime
    id: UUID = field(default_factory=uuid4)
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    decided_by: str | None = None
    tenant_id: str = _LOCAL_TENANT

    def __post_init__(self) -> None:
        _non_empty(self.action, "action")
        if not isinstance(self.risk, RiskLevel):
            raise DomainValidationError("risk must be a RiskLevel")
        if not isinstance(self.status, ApprovalStatus):
            raise DomainValidationError("status must be an ApprovalStatus")
        if not isinstance(self.id, UUID):
            raise DomainValidationError("id must be a UUID")
        _sha256(self.payload_sha256, "payload_sha256")
        _non_empty(self.tenant_id, "tenant_id")
        created = _aware_utc(self.created_at, "created_at")
        expires = _aware_utc(self.expires_at, "expires_at")
        if expires <= created:
            raise DomainValidationError("expires_at must be later than created_at")
        object.__setattr__(self, "created_at", created)
        object.__setattr__(self, "expires_at", expires)
        if self.decided_at is not None:
            decided = _aware_utc(self.decided_at, "decided_at")
            _ordered_times(created, decided, "created_at", "decided_at")
            object.__setattr__(self, "decided_at", decided)
            if (
                self.status in {ApprovalStatus.APPROVED, ApprovalStatus.CONSUMED}
                and decided > expires
            ):
                raise DomainValidationError(
                    "approval decision must occur before expires_at"
                )
        if self.status in {
            ApprovalStatus.APPROVED,
            ApprovalStatus.REJECTED,
            ApprovalStatus.CONSUMED,
        }:
            if self.decided_at is None or self.decided_by is None:
                raise DomainValidationError(
                    "decided approvals require decided_at and decided_by"
                )
            _non_empty(self.decided_by, "decided_by")
        elif self.decided_at is not None or self.decided_by is not None:
            raise DomainValidationError(
                "pending or expired approvals cannot carry decision fields"
            )


@dataclass(frozen=True, slots=True)
class Evidence:
    """A source-backed claim with provenance and an optional integrity hash."""

    source_type: str
    source_ref: str
    claim: str
    id: UUID = field(default_factory=uuid4)
    project_id: UUID | None = None
    metric: str | None = None
    artifact_sha256: str | None = None
    verified_by: str | None = None
    confidence: float = 1.0
    tags: tuple[str, ...] = ()
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime | None = None
    tenant_id: str = _LOCAL_TENANT

    def __post_init__(self) -> None:
        for value, name in (
            (self.source_type, "source_type"),
            (self.source_ref, "source_ref"),
            (self.claim, "claim"),
        ):
            _non_empty(value, name)
        if not isinstance(self.id, UUID):
            raise DomainValidationError("id must be a UUID")
        if self.project_id is not None and not isinstance(self.project_id, UUID):
            raise DomainValidationError("project_id must be a UUID or None")
        if self.metric is not None and not isinstance(self.metric, str):
            raise DomainValidationError("metric must be a string or None")
        if self.artifact_sha256 is not None:
            _sha256(self.artifact_sha256, "artifact_sha256")
        if self.verified_by is not None:
            _non_empty(self.verified_by, "verified_by")
        if isinstance(self.confidence, bool) or not isinstance(
            self.confidence, (int, float)
        ):
            raise DomainValidationError("confidence must be a number between 0 and 1")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise DomainValidationError(
                "confidence must be a finite number between 0 and 1"
            )
        _non_empty(self.tenant_id, "tenant_id")
        captured = _aware_utc(self.captured_at, "captured_at")
        object.__setattr__(self, "captured_at", captured)
        object.__setattr__(self, "tags", _tags(self.tags))
        if self.last_seen is not None:
            last_seen = _aware_utc(self.last_seen, "last_seen")
            _ordered_times(captured, last_seen, "captured_at", "last_seen")
            object.__setattr__(self, "last_seen", last_seen)
