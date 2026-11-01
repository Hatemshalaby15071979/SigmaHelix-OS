"""SQLite schema v1 for the durable core."""

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    root_path TEXT NOT NULL CHECK(length(trim(root_path)) > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_scanned_at TEXT,
    deleted_at TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, root_path)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    title TEXT NOT NULL CHECK(length(trim(title)) > 0),
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK(status IN ('todo', 'in_progress', 'done', 'cancelled')),
    project_id TEXT,
    due_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    content TEXT NOT NULL CHECK(length(trim(content)) > 0),
    project_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    event_type TEXT NOT NULL CHECK(length(trim(event_type)) > 0),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    action TEXT NOT NULL CHECK(length(trim(action)) > 0),
    risk TEXT NOT NULL CHECK(risk IN ('R0', 'R1', 'R2', 'R3')),
    payload_sha256 TEXT NOT NULL CHECK(length(payload_sha256) = 64 AND payload_sha256 NOT GLOB '*[^0-9a-f]*'),
    status TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected', 'expired', 'consumed')),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    decided_at TEXT,
    decided_by TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    CHECK (
        (status IN ('approved', 'rejected', 'consumed')
         AND decided_at IS NOT NULL AND decided_by IS NOT NULL
         AND length(trim(decided_by)) > 0)
        OR
        (status IN ('pending', 'expired')
         AND decided_at IS NULL AND decided_by IS NULL)
    ),
    CHECK (status NOT IN ('approved', 'consumed') OR decided_at <= expires_at)
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    source_type TEXT NOT NULL CHECK(length(trim(source_type)) > 0),
    source_ref TEXT NOT NULL CHECK(length(trim(source_ref)) > 0),
    claim TEXT NOT NULL CHECK(length(trim(claim)) > 0),
    project_id TEXT,
    metric TEXT,
    artifact_sha256 TEXT CHECK(artifact_sha256 IS NULL OR (length(artifact_sha256) = 64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*')),
    verified_by TEXT,
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    captured_at TEXT NOT NULL,
    last_seen TEXT,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_projects_tenant_name
    ON projects(tenant_id, name);
CREATE INDEX IF NOT EXISTS idx_tasks_tenant_created
    ON tasks(tenant_id, created_at, id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_tenant_status_due
    ON tasks(tenant_id, status, due_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_tenant_project
    ON tasks(tenant_id, project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notes_tenant_updated
    ON notes(tenant_id, updated_at) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_notes_tenant_project
    ON notes(tenant_id, project_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_events_tenant_occurred
    ON events(tenant_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_events_tenant_type_time
    ON events(tenant_id, event_type, occurred_at);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant_created
    ON approvals(tenant_id, created_at, id);
CREATE INDEX IF NOT EXISTS idx_approvals_tenant_status_expiry
    ON approvals(tenant_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_evidence_tenant_captured
    ON evidence(tenant_id, captured_at, id);
CREATE INDEX IF NOT EXISTS idx_evidence_tenant_project
    ON evidence(tenant_id, project_id, captured_at);
CREATE TABLE IF NOT EXISTS evidence_tags (
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    evidence_id TEXT NOT NULL,
    tag TEXT NOT NULL CHECK(length(trim(tag)) > 0),
    PRIMARY KEY (tenant_id, evidence_id, tag),
    FOREIGN KEY (tenant_id, evidence_id) REFERENCES evidence(tenant_id, id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_evidence_tags_tenant_tag
    ON evidence_tags(tenant_id, tag, evidence_id);

CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events BEGIN
    SELECT RAISE(ABORT, 'events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS evidence_no_update
BEFORE UPDATE ON evidence BEGIN
    SELECT RAISE(ABORT, 'evidence is append-only');
END;
CREATE TRIGGER IF NOT EXISTS evidence_no_delete
BEFORE DELETE ON evidence BEGIN
    SELECT RAISE(ABORT, 'evidence is append-only');
END;
CREATE TRIGGER IF NOT EXISTS evidence_tags_no_update
BEFORE UPDATE ON evidence_tags BEGIN
    SELECT RAISE(ABORT, 'evidence tags are append-only');
END;
CREATE TRIGGER IF NOT EXISTS evidence_tags_no_delete
BEFORE DELETE ON evidence_tags BEGIN
    SELECT RAISE(ABORT, 'evidence tags are append-only');
END;

CREATE VIEW IF NOT EXISTS evidence_records AS
SELECT evidence.*,
       COALESCE((
           SELECT json_group_array(tag)
           FROM (SELECT tag FROM evidence_tags
                 WHERE tenant_id = evidence.tenant_id AND evidence_id = evidence.id
                 ORDER BY tag)
       ), '[]') AS tags_json
FROM evidence;
"""
