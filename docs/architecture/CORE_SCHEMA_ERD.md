# Durable core schema v10

```mermaid
erDiagram
    PROJECTS ||--o{ TASKS : "tenant-scoped project link"
    PROJECTS ||--o{ NOTES : "tenant-scoped project link"
    PROJECTS ||--o{ EVIDENCE : "tenant-scoped project link"
    EVIDENCE ||--o{ EVIDENCE_TAGS : "has tags"

    PROJECTS {
        text id PK
        text tenant_id
        text name
        text root_path
        text created_at
        text updated_at
        text last_scanned_at
        text deleted_at
    }
    TASKS {
        text id PK
        text tenant_id
        text title
        text description
        text status
        text project_id FK
        text due_at
        text created_at
        text updated_at
        text deleted_at
    }
    NOTES {
        text id PK
        text tenant_id
        text content
        text project_id FK
        text created_at
        text updated_at
        text deleted_at
    }
    EVENTS {
        text id PK
        text tenant_id
        text event_type
        text payload_json
        text occurred_at
    }
    APPROVALS {
        text id PK
        text tenant_id
        text action
        text risk
        text payload_sha256
        text status
        text created_at
        text expires_at
        text decided_at
        text decided_by
    }
    EVIDENCE {
        text id PK
        text tenant_id
        text source_type
        text source_ref
        text claim
        text project_id FK
        text metric
        text artifact_sha256
        text verified_by
        real confidence
        text captured_at
        text last_seen
    }
    EVIDENCE_TAGS {
        text tenant_id PK
        text evidence_id PK_FK
        text tag PK
    }
    AUDIT_LOG {
        integer sequence PK
        text id UK
        text tenant_id
        text action
        text entity_type
        text entity_id
        text occurred_at
        text payload_json
        text previous_hash
        text record_hash
    }
    EVENT_STREAM {
        integer sequence PK
        text event_id FK
        text tenant_id
    }
    LEGACY_IMPORTS {
        text source_id PK
        text snapshot_sha256
        text imported_at
        integer task_count
        integer note_count
    }
    TASK_SERIES ||--o{ TASK_OCCURRENCES : "materializes"
    TASKS ||--o| TASK_OCCURRENCES : "occurrence task"
    TASK_SERIES {
        text id PK
        text tenant_id
        text title
        text description
        text project_id FK
        text rule_json
        text created_at
        integer active
        text last_materialized_through
    }
    TASK_OCCURRENCES {
        text id PK
        text tenant_id
        text series_id FK
        text task_id FK
        text scheduled_for
        text created_at
    }
    SCHEDULED_JOBS ||--o{ JOB_RUNS : "claims slots"
    SCHEDULED_JOBS ||--o{ MISSED_JOB_RUNS : "surfaces recovery"
    SCHEDULED_JOBS {
        text id PK
        text tenant_id
        text job_type
        text payload_json
        text next_run_at
        integer interval_seconds
        integer enabled
        text created_at
        text last_run_at
    }
    JOB_RUNS {
        text id PK
        text tenant_id
        text job_id FK
        text scheduled_for
        text started_at
        text finished_at
        text status
        text error_type
    }
    MISSED_JOB_RUNS {
        text id PK
        text tenant_id
        text job_id FK
        text scheduled_for
        text detected_at
        text reason
        text state
        text acknowledged_at
    }
    NOTIFICATIONS {
        text id PK
        text tenant_id
        text dedupe_key
        text title
        text body
        text created_at
        text read_at
        text native_status
    }
    NOTIFICATIONS ||--|| NOTIFICATION_ALARM_STATES : "action state"
    NOTIFICATIONS ||--o{ NOTIFICATION_ACTIONS : "action history"
    NOTIFICATION_ALARM_STATES {
        text notification_id PK_FK
        text tenant_id
        text state
        text due_at
        text scheduled_job_id FK
        text updated_at
    }
    NOTIFICATION_ACTIONS {
        text id PK
        text tenant_id
        text notification_id FK
        text action
        text from_state
        text to_state
        text due_at
        text created_at
    }
    PROJECTS ||--o{ PROJECT_SCAN_SNAPSHOTS : "records scans"
    PROJECT_SCAN_SNAPSHOTS {
        text id PK
        text tenant_id
        text project_id FK
        text scanned_at
        text git_branch
        text git_commit
        integer git_dirty
        integer git_change_count
        text manifests_json
        text entrypoints_json
        text findings_json
        text health
    }
```

`id` is a UUID primary key. Project relationships use composite foreign keys on `(tenant_id, project_id)` to reject cross-tenant links. Tasks, notes, and projects are soft-deleted; event, evidence, and evidence-tag rows are append-only at both repository and SQLite-trigger boundaries. Approval rows retain their state transitions in place, with decision metadata and expiry constraints.

Evidence tags are normalized into `evidence_tags`; the `evidence_records` view assembles them for typed reads. Schema v2 adds the globally sequenced, tenant-labelled audit chain; its entity reference is intentionally polymorphic and is not a foreign key. Schema v3 adds `event_stream`, whose sequence cursor references each immutable event. Schema v4 adds the append-only import ledger that makes legacy in-memory snapshot import idempotent. Schema v5 stores recurrence definitions separately from immutable series/date occurrence links to materialized tasks; task completion mutates the task and does not mutate the series or occurrence link. Schema v6 adds durable scheduled jobs and run claims. Schema v7 adds the append-only missed-run recovery history with a one-way pending-to-acknowledged transition. Schema v8 adds a deduplicated in-app notification inbox and delivery status. Schema v9 adds alarm state and immutable snooze/dismiss/reschedule action history. Schema v10 stores append-only project scan snapshots and advances the project's last-scan timestamp. All links are tenant scoped. The generated diagram is based on schema analyzer output, with the tenant-scoped composite foreign-key labels retained from the actual DDL.
