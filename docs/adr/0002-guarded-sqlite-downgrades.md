# ADR 0002: Guarded SQLite downgrades

- Status: Accepted
- Date: 2026-11-02

## Context

The v1 schema needs forward and rollback paths. Dropping v1 tables is only safe while the database is empty. Silently allowing a rollback after data has been written would remove tasks, notes, projects, approvals, events, evidence, and evidence tags.

## Decision

Apply migrations one version at a time inside SQLite transactions and track the current version with `PRAGMA user_version`. A downgrade checks every v1 data table while holding the write lock and refuses if any row exists. Failed migrations roll back all DDL and leave the version unchanged. A version-0 database with untracked objects and a database newer than the registered migration set are rejected.

## Consequences

- Empty v1 databases can be rolled back and upgraded again in tests.
- Populated databases require restore from a pre-upgrade backup or a forward repair; the migration runner will not discard their data.
- Release rollback must pair an application downgrade with the verified database backup/restore path from P1-008.
