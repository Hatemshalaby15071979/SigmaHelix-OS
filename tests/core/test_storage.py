from concurrent.futures import ThreadPoolExecutor
import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from sigmahelix.core.models import (
    Approval,
    ApprovalStatus,
    Evidence,
    Event,
    Note,
    Project,
    RiskLevel,
    Task,
    TaskStatus,
)
from sigmahelix.core.storage import (
    ApprovalRepository,
    Database,
    EvidenceRepository,
    EventRepository,
    NoteRepository,
    ProjectRepository,
    RepositoryOperationError,
    TaskRepository,
)

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
HASH = "b" * 64


@pytest.fixture
def database(tmp_path: Path) -> Database:
    db = Database(tmp_path / "data" / "sigmahelix.db")
    db.initialize()
    return db


def test_database_configures_wal_integrity_pragmas_and_private_file(database):
    with database.connection() as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 13
    assert database.path.stat().st_mode & 0o777 == 0o600


def test_database_requires_an_absolute_file_path(tmp_path):
    with pytest.raises(ValueError, match="absolute Path"):
        Database(Path("relative.db"))


def test_all_six_repositories_round_trip_typed_records(database, tmp_path):
    project = Project(
        "SigmaHelix", tmp_path / "project", created_at=NOW, updated_at=NOW
    )
    task = Task(
        "Review schema",
        project_id=project.id,
        status=TaskStatus.IN_PROGRESS,
        due_at=NOW + timedelta(hours=1),
        created_at=NOW,
        updated_at=NOW,
    )
    note = Note(
        "Persistence is enabled", project_id=project.id, created_at=NOW, updated_at=NOW
    )
    event = Event(
        "task.created", {"task_id": str(task.id), "labels": ["core"]}, occurred_at=NOW
    )
    approval = Approval(
        "calendar.create",
        RiskLevel.R2,
        HASH,
        NOW + timedelta(minutes=5),
        created_at=NOW,
    )
    evidence = Evidence(
        "test",
        "tests/core/test_storage.py",
        "Repository round-trip passed",
        project_id=project.id,
        artifact_sha256=HASH,
        tags=("storage", "test"),
        captured_at=NOW,
        last_seen=NOW,
    )
    repos = [
        (ProjectRepository(database), project),
        (TaskRepository(database), task),
        (NoteRepository(database), note),
        (EventRepository(database), event),
        (ApprovalRepository(database), approval),
        (EvidenceRepository(database), evidence),
    ]

    for repository, record in repos:
        repository.create(record)
        assert repository.get(record.id, record.tenant_id) == record
        assert repository.list_all(record.tenant_id) == [record]


def test_task_repository_crud_uses_tenant_scoped_soft_delete(database, tmp_path):
    projects = ProjectRepository(database)
    tasks = TaskRepository(database)
    project = Project("Repo", tmp_path / "repo", created_at=NOW, updated_at=NOW)
    projects.create(project)
    task = Task("Initial", project_id=project.id, created_at=NOW, updated_at=NOW)
    tasks.create(task)

    assert tasks.get(task.id, "other-tenant") is None
    updated = replace(
        task,
        title="Updated",
        status=TaskStatus.DONE,
        updated_at=NOW + timedelta(minutes=1),
    )
    tasks.update(updated)
    assert tasks.get(task.id) == updated
    assert tasks.delete(task.id) is True
    assert tasks.delete(task.id) is False
    assert tasks.get(task.id) is None

    with database.connection() as connection:
        assert connection.execute(
            "SELECT deleted_at FROM tasks WHERE id = ?", (str(task.id),)
        ).fetchone()[0]


def test_project_foreign_keys_are_scoped_to_the_same_tenant(database, tmp_path):
    projects = ProjectRepository(database)
    tasks = TaskRepository(database)
    project = Project(
        "Tenant A project",
        tmp_path / "tenant-a",
        tenant_id="tenant-a",
        created_at=NOW,
        updated_at=NOW,
    )
    projects.create(project)
    task = Task(
        "Cross-tenant link",
        project_id=project.id,
        tenant_id="tenant-b",
        created_at=NOW,
        updated_at=NOW,
    )

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        tasks.create(task)


def test_event_and_evidence_repositories_are_append_only(database):
    event = Event("audit.entry", {"ok": True}, occurred_at=NOW)
    evidence = Evidence(
        "test", "ref", "A claim", tags=("verification",), captured_at=NOW
    )
    events = EventRepository(database)
    evidence_records = EvidenceRepository(database)
    events.create(event)
    evidence_records.create(evidence)

    with pytest.raises(RepositoryOperationError, match="append-only"):
        events.update(event)
    with pytest.raises(RepositoryOperationError, match="cannot be deleted"):
        events.delete(event.id)
    with pytest.raises(RepositoryOperationError, match="append-only"):
        evidence_records.update(evidence)
    with pytest.raises(RepositoryOperationError, match="cannot be deleted"):
        evidence_records.delete(evidence.id)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("UPDATE events SET event_type = 'rewritten'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        with database.transaction() as connection:
            connection.execute("DELETE FROM evidence_tags")


def test_approval_repository_allows_recorded_status_transition(database):
    repository = ApprovalRepository(database)
    pending = Approval(
        "calendar.create",
        RiskLevel.R2,
        HASH,
        NOW + timedelta(minutes=5),
        created_at=NOW,
    )
    repository.create(pending)
    approved = replace(
        pending,
        status=ApprovalStatus.APPROVED,
        decided_at=NOW + timedelta(seconds=1),
        decided_by="owner",
    )

    repository.update(approved)
    assert repository.get(approved.id) == approved


def test_concurrent_readers_use_independent_wal_connections(database):
    repository = TaskRepository(database)
    task = Task("Concurrent read", created_at=NOW, updated_at=NOW)
    repository.create(task)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repository.get(task.id), range(32)))

    assert results == [task] * 32


def test_repository_indexes_match_tenant_scoped_read_paths(database):
    plans = {
        "task_list": (
            "SELECT * FROM tasks WHERE tenant_id = 'local' AND deleted_at IS NULL "
            "ORDER BY created_at, id",
            "idx_tasks_tenant_created",
        ),
        "task_due": (
            "SELECT * FROM tasks WHERE tenant_id = 'local' AND status = 'todo' "
            "AND due_at IS NOT NULL AND deleted_at IS NULL ORDER BY due_at",
            "idx_tasks_tenant_status_due",
        ),
        "task_project": (
            "SELECT * FROM tasks WHERE tenant_id = 'local' AND project_id = 'p' "
            "AND deleted_at IS NULL",
            "idx_tasks_tenant_project",
        ),
        "evidence_tag": (
            "SELECT evidence_id FROM evidence_tags "
            "WHERE tenant_id = 'local' AND tag = 'core'",
            "idx_evidence_tags_tenant_tag",
        ),
    }

    with database.connection() as connection:
        for name, (query, expected_index) in plans.items():
            details = " ".join(
                row["detail"]
                for row in connection.execute("EXPLAIN QUERY PLAN " + query)
            )
            assert expected_index in details, (
                f"{name} did not use {expected_index}: {details}"
            )
