"""SQLite persistence for the SigmaHelix durable core."""

from .audit import AuditLog, AuditLogEntry, AuditLogError, AuditVerification
from .database import Database
from .event_bus import EventBus, EventBusError, EventDispatchError, EventEnvelope
from .migrations import (
    Migration,
    MigrationDataLossError,
    MigrationError,
    MigrationRunner,
)
from .repositories import (
    ApprovalRepository,
    EvidenceRepository,
    EventRepository,
    NoteRepository,
    ProjectRepository,
    RepositoryOperationError,
    TaskRepository,
)

__all__ = [
    "ApprovalRepository",
    "AuditLog",
    "AuditLogEntry",
    "AuditLogError",
    "AuditVerification",
    "Database",
    "EventBus",
    "EventBusError",
    "EventDispatchError",
    "EventEnvelope",
    "EvidenceRepository",
    "Migration",
    "MigrationDataLossError",
    "MigrationError",
    "MigrationRunner",
    "EventRepository",
    "NoteRepository",
    "ProjectRepository",
    "RepositoryOperationError",
    "TaskRepository",
]
