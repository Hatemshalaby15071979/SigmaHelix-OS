"""SQLite persistence for the SigmaHelix durable core."""

from .alarms import AlarmAction, AlarmError, AlarmService, AlarmState
from .audit import AuditLog, AuditLogEntry, AuditLogError, AuditVerification
from .backup import BackupError, BackupManifest, DatabaseBackup
from .database import Database
from .event_bus import EventBus, EventBusError, EventDispatchError, EventEnvelope
from .launchers import (
    CommandPreview,
    LauncherError,
    LauncherProfile,
    LauncherRun,
    LauncherService,
    LaunchHandle,
)
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
from .occurrences import OccurrenceError, OccurrenceService
from .project_scanner import (
    ProjectArtifact,
    ProjectScan,
    ProjectScanBatch,
    ProjectScanError,
    ProjectScanner,
)
from .project_watch import ProjectWatch, ProjectWatchError
from .repositories import (
    ApprovalRepository,
    EventRepository,
    EvidenceRepository,
    NoteRepository,
    ProjectRepository,
    RepositoryOperationError,
    TaskQuestionRepository,
    TaskRepository,
)
from .scheduler import JobRun, MissedJobRun, ScheduledJob, Scheduler, SchedulerError

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
    "CommandPreview",
    "LaunchHandle",
    "LauncherError",
    "LauncherProfile",
    "LauncherRun",
    "LauncherService",
    "JobRun",
    "EventRepository",
    "NoteRepository",
    "OccurrenceError",
    "OccurrenceService",
    "ProjectRepository",
    "ProjectArtifact",
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
    "TaskQuestionRepository",
    "TaskRepository",
]
