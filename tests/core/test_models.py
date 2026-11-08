from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from sigmahelix.core.models import (
    Approval,
    ApprovalStatus,
    DomainValidationError,
    Event,
    Evidence,
    Note,
    Project,
    RiskLevel,
    Task,
    TaskStatus,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
HASH = "a" * 64


def test_all_domain_records_accept_valid_values_and_generate_ids():
    project_id = UUID("089a9876-4f8b-44a0-b83f-c57bb8113919")
    records = [
        Task("Review deployment", project_id=project_id),
        Note("Record the deployment result", project_id=project_id),
        Project("SigmaHelix", Path("/home/user/SigmaHelix")),
        Event("task.created", {"task_id": str(project_id), "labels": ["work"]}),
        Approval(
            "calendar.create",
            RiskLevel.R2,
            HASH,
            NOW + timedelta(minutes=5),
            created_at=NOW,
        ),
        Evidence(
            "test", "tests/test_core.py", "Schema checks pass", project_id=project_id
        ),
    ]

    assert len({record.id for record in records}) == len(records)
    assert all(isinstance(record.id, UUID) for record in records)
    assert all(record.tenant_id == "local" for record in records)


def test_task_defaults_and_normalizes_timestamp_to_utc():
    local_created = NOW.astimezone(timezone(timedelta(hours=-4)))
    task = Task(
        "Write notes",
        status=TaskStatus.IN_PROGRESS,
        created_at=local_created,
        updated_at=local_created + timedelta(seconds=1),
    )

    assert task.status is TaskStatus.IN_PROGRESS
    assert task.created_at == NOW
    assert task.updated_at >= task.created_at
    assert task.created_at.utcoffset() == timedelta(0)


def test_task_rejects_empty_title_naive_time_and_reversed_timestamps():
    with pytest.raises(DomainValidationError, match="title"):
        Task("  ")
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        Task("Write notes", created_at=datetime(2026, 11, 2))
    with pytest.raises(DomainValidationError, match="updated_at"):
        Task("Write notes", created_at=NOW, updated_at=NOW - timedelta(seconds=1))


def test_note_requires_nonblank_content_and_aware_timestamps():
    with pytest.raises(DomainValidationError, match="content"):
        Note(" \n ")
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        Note("Content", created_at=datetime(2026, 11, 2))


def test_project_path_must_be_absolute_and_scan_time_aware():
    with pytest.raises(DomainValidationError, match="absolute Path"):
        Project("Project", Path("relative/project"))
    with pytest.raises(DomainValidationError, match="timezone-aware"):
        Project("Project", Path("/tmp/project"), last_scanned_at=datetime(2026, 11, 2))


def test_event_payload_is_defensively_copied_and_json_safe():
    original = {"items": ["first"]}
    event = Event("project.scanned", original, occurred_at=NOW)
    original["items"].append("mutated")

    assert event.payload == {"items": ["first"]}
    with pytest.raises(DomainValidationError, match="finite JSON"):
        Event("bad.event", {"value": float("nan")})
    with pytest.raises(DomainValidationError, match="finite JSON"):
        Event("bad.event", {"value": object()})
    with pytest.raises(DomainValidationError, match="string keys"):
        Event("bad.event", {1: "not a string key"})


def test_approval_requires_hash_expiry_and_consistent_decision_fields():
    with pytest.raises(DomainValidationError, match="payload_sha256"):
        Approval(
            "send", RiskLevel.R3, "bad", NOW + timedelta(minutes=1), created_at=NOW
        )
    with pytest.raises(DomainValidationError, match="later than"):
        Approval("send", RiskLevel.R3, HASH, NOW, created_at=NOW)
    with pytest.raises(DomainValidationError, match="decided_at and decided_by"):
        Approval(
            "send",
            RiskLevel.R3,
            HASH,
            NOW + timedelta(minutes=1),
            status=ApprovalStatus.APPROVED,
            created_at=NOW,
        )


def test_approval_approved_record_binds_decision_to_expiry_window():
    approval = Approval(
        "send",
        RiskLevel.R2,
        HASH,
        NOW + timedelta(minutes=5),
        status=ApprovalStatus.APPROVED,
        created_at=NOW,
        decided_at=NOW + timedelta(seconds=1),
        decided_by="owner",
    )

    assert approval.status is ApprovalStatus.APPROVED
    assert approval.decided_by == "owner"

    with pytest.raises(DomainValidationError, match="before expires_at"):
        Approval(
            "send",
            RiskLevel.R2,
            HASH,
            NOW + timedelta(minutes=5),
            status=ApprovalStatus.APPROVED,
            created_at=NOW,
            decided_at=NOW + timedelta(minutes=6),
            decided_by="owner",
        )


def test_evidence_validates_source_hash_confidence_tags_and_provenance_dates():
    evidence = Evidence(
        "test",
        "tests/test_core.py",
        "Schema checks pass",
        artifact_sha256=HASH,
        confidence=0.9,
        tags=("verification", "core"),
        captured_at=NOW,
        last_seen=NOW + timedelta(days=1),
    )
    assert evidence.tags == ("verification", "core")

    with pytest.raises(DomainValidationError, match="source_ref"):
        Evidence("test", " ", "A claim")
    with pytest.raises(DomainValidationError, match="artifact_sha256"):
        Evidence("test", "artifact", "A claim", artifact_sha256="ABC")
    with pytest.raises(DomainValidationError, match="confidence"):
        Evidence("test", "artifact", "A claim", confidence=float("inf"))
    with pytest.raises(DomainValidationError, match="duplicates"):
        Evidence("test", "artifact", "A claim", tags=("same", "same"))
    with pytest.raises(DomainValidationError, match="last_seen"):
        Evidence(
            "test",
            "artifact",
            "A claim",
            captured_at=NOW,
            last_seen=NOW - timedelta(seconds=1),
        )
