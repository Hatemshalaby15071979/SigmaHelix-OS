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
- Completed P1-006: migration v2 adds a globally sequenced, tenant-labelled SHA-256 chain with atomic append support, append-only triggers, secret-like payload rejection, and full-chain verification. Clean CI passed (56 core/ledger tests; 27 offline desktop tests), including a 1,000-record chain and tamper detection.
- P1-007 (persistent event bus) is now in progress; P1-008 (backup/export/restore) is unblocked and ready.
- Completed P1-007: migration v3 adds a stable sequence index for immutable events, and `EventBus` provides persist-before-dispatch publish, tenant/type-scoped subscriptions, and cursor-based replay. Clean CI passed (64 core/ledger tests; 27 offline desktop tests).
- P1-008 (backup, export, and restore) is now in progress.
- Completed P1-008: added `backup`/`export`/`restore` commands with SQLite online snapshots, SHA-256 sidecars, schema and integrity checks, private files, and overwrite refusal. Full CI passed (70 core/ledger tests; 27 offline desktop tests); isolated CLI export/restore returned identical file hashes.
- P1-009 (crash safety during writes) is now in progress.
- Completed P1-009: an isolated writer spilled 4,000 uncommitted events into WAL, was killed with `SIGKILL`, and reopened with committed state intact, no partial rows, and `integrity_check=ok`. Full CI passed (71 core/ledger tests; 27 offline desktop tests).
- P1-010 (legacy in-memory session import) is now in progress. The legacy app stores tasks and notes only in live manager objects; no persisted snapshot file was found, so implementation will support importing an explicitly supplied live-session snapshot and report that no historical session was available to migrate.
- Completed P1-010: added an atomic, idempotent live-manager importer with migration v4 receipt, event and audit records, validation, and conflict detection. No legacy app process or persistent snapshot was available, so no historical task/note records were imported. Full CI passed (75 core/ledger tests; 27 offline desktop tests).
- P1 (Durable core) is complete. P2-001 (recurrence engine) is now in progress; the P2 task set has been added to the execution ledger.
- Completed P2-001: added deterministic date-based daily/weekly/monthly recurrence with weekday filters, every-N intervals, month-end clamping, count/end limits, and cursor expansion. The 10,000-rule generated property suite and full CI passed (89 core/ledger; 27 offline desktop tests).
- P2-002 (occurrence materialization and completion semantics) is now in progress.
- Completed P2-002: schema v5 separates recurring task definitions from immutable date/task occurrence links. Materialization is deterministic, resumable, concurrent-safe, and atomic with its event/audit entry; completing one task leaves the series active. Full CI passed (95 core/ledger; 27 offline desktop tests).
- P2-003 (persisted scheduler with fake clock) is now in progress.
