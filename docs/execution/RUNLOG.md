# Execution run log

## 2026-11-02

- Completed P0-001 through P0-010; see individual evidence files and git history.
- Completed P1-001: added validated task, note, project, event, approval, and evidence records; documented canonical vocabulary and the model boundary decision.
- Verification: formatting, lint, mypy, compileall, 16 core/ledger tests, and 27 offline desktop tests passed in the clean Python 3.12 environment. Two upstream SpeechRecognition deprecation warnings (`aifc`, `audioop`) remain.
- P1-002 (SQLite connection, WAL pragmas, repositories) is the next eligible task.
- Completed P1-002: added file-backed SQLite with WAL, foreign-key enforcement, full synchronous writes, busy timeout, private file permissions, tenant-scoped repositories, normalized evidence tags, append-only triggers, and schema/query-plan tests. Full local CI passed (25 core/ledger tests; 27 offline app tests).
- Schema review: 7 tables, 55 columns, 4 relationships, no high/medium normalization findings. The analyzer did not load JSON index metadata; actual tenant-scoped indexes were confirmed with `EXPLAIN QUERY PLAN`. See `docs/architecture/CORE_SCHEMA_ERD.md` and `docs/execution/evidence/P1-002.md`.
- P1-003 (migration runner v0→v1 with rollback) is now in progress.
- Completed P1-003: installed a transactional v0→v1 migration runner, idempotent initialization, schema-state checks, and an empty-database-only rollback guard. Failed DDL leaves no partial objects or version change. Full local CI passed (31 core/ledger tests; 27 offline app tests).
- The bundled migration generator was run but produced invalid SQLite syntax and `information_schema` validation SQL; no generated output was adopted. See P1-003 evidence and ADR 0002.
- P1-004 (YAML, environment, and keyring configuration) is now in progress.

- Completed P1-004: added XDG-derived defaults, YAML and environment precedence, secret-setting rejection, a fail-closed OS-keyring facade, and a hash-pinned `keyring` dependency. Clean-environment CI passed (39 core/ledger tests; 27 offline desktop tests). No real system keyring or credentials were accessed.
- Durability decision: kept SQLite `synchronous=FULL` to meet the committed-data power-loss requirement; see ADR 0003.
- P1-005 (structured logging and redaction) is now the next eligible task.
- Completed P1-005: added local JSON-lines logging, seven-day UTC rotation, owner-only log permissions, and message/field/exception redaction. Clean CI passed (49 core/ledger tests; 27 offline desktop tests).
- P1-006 (hash-chained audit log) is now in progress.
