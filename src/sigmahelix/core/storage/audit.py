"""Append-only, hash-chained audit records stored in the durable SQLite core."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from ..logging import redact_text
from .database import Database

_GENESIS_HASH = "0" * 64
_SENSITIVE_KEY = re.compile(
    r"password|passwd|token|secret|credential|private.?key|api.?key|access.?key|authorization",
    re.IGNORECASE,
)


class AuditLogError(RuntimeError):
    """Raised when an audit record cannot be safely written or verified."""


@dataclass(frozen=True, slots=True)
class AuditLogEntry:
    """One immutable audit record and its digest-chain position."""

    sequence: int
    id: UUID
    tenant_id: str
    action: str
    entity_type: str
    entity_id: str
    occurred_at: datetime
    payload: Mapping[str, Any]
    previous_hash: str
    record_hash: str


@dataclass(frozen=True, slots=True)
class AuditVerification:
    """Result of validating the entire global audit chain."""

    valid: bool
    entries_checked: int
    error_sequence: int | None = None
    reason: str | None = None


def _canonical_payload(payload: Mapping[str, Any]) -> str:
    if not isinstance(payload, Mapping) or any(
        not isinstance(key, str) for key in payload
    ):
        raise ValueError("audit payload must be a mapping with string keys")

    def reject_secrets(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if not isinstance(key, str):
                    raise ValueError("audit payload must have string keys")
                if _SENSITIVE_KEY.search(key):
                    raise ValueError("audit payload must not contain secret fields")
                reject_secrets(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                reject_secrets(child)
        elif isinstance(value, str) and redact_text(value) != value:
            raise ValueError("audit payload must not contain secret-like values")

    reject_secrets(payload)
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        normalized = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("audit payload must contain finite JSON values") from exc
    if not isinstance(normalized, dict):
        raise ValueError("audit payload must be a JSON object")
    return json.dumps(
        normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _hash_record(
    sequence: int,
    entry_id: str,
    tenant_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    occurred_at: str,
    payload_json: str,
    previous_hash: str,
) -> str:
    canonical = json.dumps(
        [
            "sigmahelix.audit.v1",
            sequence,
            entry_id,
            tenant_id,
            action,
            entity_type,
            entity_id,
            occurred_at,
            payload_json,
            previous_hash,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class AuditLog:
    """Append and verify a single global SHA-256 chain with tenant labels."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def append(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        payload: Mapping[str, Any],
        tenant_id: str = "local",
        occurred_at: datetime | None = None,
    ) -> AuditLogEntry:
        """Append one record in an immediate transaction and return its digest."""
        with self.database.transaction() as connection:
            return self.append_in_transaction(
                connection,
                action,
                entity_type,
                entity_id,
                payload,
                tenant_id,
                occurred_at,
            )

    def append_in_transaction(
        self,
        connection: sqlite3.Connection,
        action: str,
        entity_type: str,
        entity_id: str,
        payload: Mapping[str, Any],
        tenant_id: str = "local",
        occurred_at: datetime | None = None,
    ) -> AuditLogEntry:
        """Append using a caller-owned transaction so domain changes can be atomic."""
        if not connection.in_transaction:
            raise AuditLogError("append_in_transaction requires an active transaction")
        for value, label in (
            (action, "action"),
            (entity_type, "entity_type"),
            (entity_id, "entity_id"),
            (tenant_id, "tenant_id"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} must be a non-empty string")
        timestamp = occurred_at or datetime.now(UTC)
        if (
            not isinstance(timestamp, datetime)
            or timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise ValueError("occurred_at must be timezone-aware")
        timestamp = timestamp.astimezone(UTC)
        timestamp_text = timestamp.isoformat()
        payload_json = _canonical_payload(payload)
        previous = connection.execute(
            "SELECT sequence, record_hash FROM audit_log ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        sequence = 1 if previous is None else int(previous["sequence"]) + 1
        previous_hash = _GENESIS_HASH if previous is None else previous["record_hash"]
        entry_id = str(uuid4())
        record_hash = _hash_record(
            sequence,
            entry_id,
            tenant_id,
            action,
            entity_type,
            entity_id,
            timestamp_text,
            payload_json,
            previous_hash,
        )
        connection.execute(
            "INSERT INTO audit_log (sequence, id, tenant_id, action, entity_type, "
            "entity_id, occurred_at, payload_json, previous_hash, record_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sequence,
                entry_id,
                tenant_id,
                action,
                entity_type,
                entity_id,
                timestamp_text,
                payload_json,
                previous_hash,
                record_hash,
            ),
        )
        return AuditLogEntry(
            sequence,
            UUID(entry_id),
            tenant_id,
            action,
            entity_type,
            entity_id,
            timestamp,
            json.loads(payload_json),
            previous_hash,
            record_hash,
        )

    def verify(self) -> AuditVerification:
        """Recompute every digest and predecessor link from the genesis record."""
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT sequence, id, tenant_id, action, entity_type, entity_id, "
                "occurred_at, payload_json, previous_hash, record_hash "
                "FROM audit_log ORDER BY sequence"
            ).fetchall()
        previous_hash = _GENESIS_HASH
        for expected_sequence, row in enumerate(rows, start=1):
            sequence = int(row["sequence"])
            if sequence != expected_sequence:
                return AuditVerification(
                    False, expected_sequence - 1, sequence, "sequence gap or reorder"
                )
            if row["previous_hash"] != previous_hash:
                return AuditVerification(
                    False, expected_sequence, sequence, "previous hash mismatch"
                )
            try:
                payload_json = _canonical_payload(json.loads(row["payload_json"]))
            except (json.JSONDecodeError, ValueError, TypeError):
                return AuditVerification(
                    False, expected_sequence - 1, sequence, "invalid payload encoding"
                )
            if payload_json != row["payload_json"]:
                return AuditVerification(
                    False, expected_sequence - 1, sequence, "non-canonical payload"
                )
            expected_hash = _hash_record(
                sequence,
                row["id"],
                row["tenant_id"],
                row["action"],
                row["entity_type"],
                row["entity_id"],
                row["occurred_at"],
                payload_json,
                previous_hash,
            )
            if row["record_hash"] != expected_hash:
                return AuditVerification(
                    False, expected_sequence - 1, sequence, "record hash mismatch"
                )
            previous_hash = expected_hash
        return AuditVerification(True, len(rows))

    def list_entries(
        self, tenant_id: str = "local", limit: int = 100
    ) -> list[AuditLogEntry]:
        """Read the newest tenant entries in ascending sequence order."""
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise ValueError("tenant_id must be a non-empty string")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT sequence, id, tenant_id, action, entity_type, entity_id, "
                "occurred_at, payload_json, previous_hash, record_hash "
                "FROM audit_log WHERE tenant_id = ? ORDER BY sequence DESC LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [
            AuditLogEntry(
                int(row["sequence"]),
                UUID(row["id"]),
                row["tenant_id"],
                row["action"],
                row["entity_type"],
                row["entity_id"],
                datetime.fromisoformat(row["occurred_at"]),
                json.loads(row["payload_json"]),
                row["previous_hash"],
                row["record_hash"],
            )
            for row in reversed(rows)
        ]
