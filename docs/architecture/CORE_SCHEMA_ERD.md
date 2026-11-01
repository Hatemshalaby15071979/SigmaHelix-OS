# Durable core schema v2

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
```

`id` is a UUID primary key. Project relationships use composite foreign keys on `(tenant_id, project_id)` to reject cross-tenant links. Tasks, notes, and projects are soft-deleted; event, evidence, and evidence-tag rows are append-only at both repository and SQLite-trigger boundaries. Approval rows retain their state transitions in place, with decision metadata and expiry constraints.

Evidence tags are normalized into `evidence_tags`; the `evidence_records` view assembles them for typed reads. Schema v2 adds the globally sequenced, tenant-labelled audit chain; its entity reference is intentionally polymorphic and is not a foreign key. The generated diagram is based on schema analyzer output, with the tenant-scoped composite foreign-key labels retained from the actual DDL.
