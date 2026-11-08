# ADR 0010 — Consolidate the three trees into one repository

- **Status:** accepted
- **Date:** 2026-11-08

## Context

Three directories in the workspace implemented the same product:

- `sigmahelix/` — the durable core (storage, migrations, audit, scheduler,
  scanner, launchers, backup) plus a reduced desktop fork.
- `company-os-app/` — the most complete application layer: desktop shell,
  agent, model catalogue, managers, settings, 58 tests.
- `company-os/` — governance documents only. 44 of its 45 files were
  byte-identical to `sigmahelix/docs/governance/`.

Maintaining three copies had already produced defects: two hard crashes that
existed only in one copy, a broken import that silently disabled model
selection, and a security regression (Google speech recognition) present in one
tree and fixed in the other.

## Decision

One repository, one package, one entry point.

- Core stays at `src/sigmahelix/core` unchanged in behaviour.
- The application moves to `src/sigmahelix/app`, taken from `company-os-app`
  and merged with the security fixes from the `sigmahelix` fork.
- A single `AppService` facade sits between the UI and the core. The UI never
  touches SQLite, and the core never imports the UI.
- `apps/desktop`, `scripts/db_admin.py`, `requirements.{in,lock}` and `VERSION`
  are removed. Their replacements are the package entry point, the CLI
  subcommands, `pyproject.toml`, and the package version.

## Alternatives considered

1. **Keep `sigmahelix` as the base and port the app into it.** Rejected: the
   `sigmahelix` desktop fork is deliberately reduced (no persistence, no
   settings, no pinning), so porting would have meant re-implementing the
   richer application.
2. **Keep `company-os-app` as the base and copy the core in.** Rejected: the
   core is already packaged as `src/sigmahelix` with its own tests, migrations
   and CI expectations; moving it would churn 6,400 lines for no benefit.
3. **Leave the three trees and share code via a path dependency.** Rejected:
   that keeps three sources of truth for the same product, which is the problem
   being solved.

## Consequences

- The pre-merge state is preserved as git tag `pre-merge-2026-11-08` and as an
  archive outside the repository, with a 262-file SHA-256 manifest.
- Existing users keep their data: `tasks.json` and `notes.json` are imported
  once into SQLite, and the legacy data directory is still recognised.
- `docs/execution/evidence/` refers to paths that no longer exist
  (`apps/desktop/...`). The files are kept verbatim as historical records;
  `docs/CONSOLIDATION.md` maps the old commands to the new ones.
- Any future feature is added once, in one place.
