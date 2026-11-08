# Repository consolidation — 2026-11-08

Three directories in the workspace implemented the same product:

| Directory | Role before consolidation |
| --- | --- |
| `sigmahelix/` | Durable core (6,405 LOC, 122 tests, migrations, audit, scheduler) plus a deliberately reduced desktop fork |
| `company-os-app/` | The most complete application layer (3,722 LOC, 58 tests, persistence, pinning, settings) |
| `company-os/` | Governance documents only; 44 of 45 files were byte-identical to `sigmahelix/docs/governance/` |

They are now one repository, `SigmaHelix`.

## What was kept

- **Core** — `sigmahelix/src/sigmahelix/core` was already the strongest layer
  and moved without behavioural change.
- **Application** — `company-os-app` supplied the desktop shell, agent, model
  catalogue and managers. These were copied into `src/sigmahelix/app` and their
  imports rewritten to be package-relative.
- **Security fork** — `sigmahelix/apps/desktop` contributed two things worth
  keeping: the loopback-only endpoint policy (now `app/security.py`) and the
  lazy, local-only voice engine (now `app/voice.py`, with the Google recogniser
  removed).
- **Governance** — `company-os/` was redundant; the copy in
  `docs/governance/` is authoritative.

## Where the old commands went

| Before | After |
| --- | --- |
| `bin/sigmahelix` | `sigmahelix` (installed) or `bin/sigmahelix` (checkout) |
| `bin/sigmahelix --cli` | `sigmahelix chat` |
| `scripts/db_admin.py backup --destination X` | `sigmahelix backup --destination X` |
| `scripts/db_admin.py restore --source X --destination Y` | `sigmahelix restore --source X --destination Y` |
| `python apps/desktop/main.py` | `sigmahelix` |
| `python apps/desktop/console_os.py` | `sigmahelix chat` |

## Data continuity

The application previously stored tasks and notes as JSON under
`~/.company-os/`. The new data directory is `~/.local/share/sigmahelix/`
(override with `SIGMAHELIX_DATA_DIR`). `sigmahelix.app.paths` still recognises
`COMPANY_OS_DATA_DIR` and the legacy `~/.company-os` location so existing
installs can be migrated rather than abandoned.

## Safety net

Before any file was removed:

- the pre-merge tree was tagged `pre-merge-2026-11-08`;
- a copy was archived outside the repository in
  `Career/_archive_pre_merge/`;
- a 262-file SHA-256 manifest was written to
  `docs/audit/MERGE_BASELINE_2026-11-08.sha256` and verified.

## Evidence note

Files under `docs/execution/evidence/` are historical records of commands run
against the pre-merge tree. They are preserved verbatim. Where they reference
`scripts/db_admin.py`, read that as the equivalent `sigmahelix backup` or
`sigmahelix restore` command.
