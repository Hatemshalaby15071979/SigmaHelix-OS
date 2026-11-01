"""SQLite persistence for the SigmaHelix durable core."""

from .audit import AuditLog, AuditLogEntry, AuditLogError, AuditVerification
from .backup import BackupError, BackupManifest, DatabaseBackup
from .database import Database
from .event_bus import EventBus, EventBusError, EventDispatchError, EventEnvelope
from .legacy_import import (
    LegacyImportConflict,
    LegacyImportError,
    LegacyImportResult,
    LegacySessionImporter,
)
from .migrations import (
    Migration,
    MigrationDataLossError,
    MigrationError,
    MigrationRunner,
)
from .occurrences import OccurrenceError, OccurrenceService
from .scheduler import JobRun, ScheduledJob, Scheduler, SchedulerError
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
    "BackupError",
    "BackupManifest",
    "Database",
    "DatabaseBackup",
    "EventBus",
    "EventBusError",
    "EventDispatchError",
    "EventEnvelope",
    "EvidenceRepository",
    "Migration",
    "MigrationDataLossError",
    "MigrationError",
    "MigrationRunner",
    "LegacyImportConflict",
    "LegacyImportError",
    "LegacyImportResult",
    "LegacySessionImporter",
    "JobRun",
    "EventRepository",
    "NoteRepository",
    "OccurrenceError",
    "OccurrenceService",
    "ProjectRepository",
    "RepositoryOperationError",
    "ScheduledJob",
    "Scheduler",
    "SchedulerError",
    "TaskRepository",
]
