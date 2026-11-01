"""SQLite persistence for the SigmaHelix durable core."""

from .audit import AuditLog, AuditLogEntry, AuditLogError, AuditVerification
from .alarms import AlarmAction, AlarmError, AlarmService, AlarmState
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
from .notifications import Notification, NotificationError, NotificationService
from .project_scanner import (
    ProjectScan,
    ProjectScanBatch,
    ProjectScanError,
    ProjectScanner,
)
from .project_watch import ProjectWatch, ProjectWatchError
from .occurrences import OccurrenceError, OccurrenceService
from .scheduler import JobRun, MissedJobRun, ScheduledJob, Scheduler, SchedulerError
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
    "AlarmAction",
    "AlarmError",
    "AlarmService",
    "AlarmState",
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
    "MissedJobRun",
    "Notification",
    "NotificationError",
    "NotificationService",
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
    "ProjectScan",
    "ProjectScanBatch",
    "ProjectScanError",
    "ProjectScanner",
    "ProjectWatch",
    "ProjectWatchError",
    "RepositoryOperationError",
    "ScheduledJob",
    "Scheduler",
    "SchedulerError",
    "TaskRepository",
]
