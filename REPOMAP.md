# REPOMAP — SigmaHelix repository layout

A local-first personal operating system (tasks, notes, projects, calendar,
launchers, audit, backup) with an assistant named **Tommy** that runs on the
user's own machine. Everything persists in one SQLite file; the web UI is the
primary surface and is served on loopback only.

```
SigmaHelix/
├── README.md              What the product does + install + command map
├── CHANGELOG.md           Keep-a-Changelog entries (Unreleased at top)
├── GLOSSARY.md            Domain terms used across code and docs
├── pyproject.toml         Package metadata, entry points, tool config
├── .gitignore             Python/cache/build/secret/data exclusions
├── bin/
│   └── sigmahelix         Thin launcher shim (delegates to the installed CLI)
├── scripts/
│   ├── ci.sh              Full gate: format → lint → mypy → compile → test → cli
│   └── ledger.py          Gate ledger helper
├── packaging/
│   ├── install.sh         Per-user install (venv, bin link, desktop entry, skills)
│   ├── uninstall.sh
│   ├── sigmahelix.spec    PyInstaller spec for a self-contained binary
│   ├── sigmahelix.desktop
│   └── sigmahelix.svg
├── src/sigmahelix/
│   ├── __init__.py        Version + public exports
│   ├── __main__.py        `python -m sigmahelix`
│   ├── cli.py             Argument parsing + subcommand dispatch
│   ├── core/              Provider-agnostic domain + storage (NO UI, NO network)
│   │   ├── models.py      Frozen dataclasses: Task, Note, Project, TaskQuestion, …
│   │   ├── config.py      Settings load/save (keyring for secrets)
│   │   └── storage/       SQLite database, repositories, migrations, backup
│   │       ├── database.py        Connection + WAL + initialize()
│   │       ├── migrations.py     Ordered, contiguous, downgrade-guarded migrations
│   │       ├── repositories.py    Per-entity CRUD, tenant-scoped
│   │       ├── backup.py          Snapshot + checksum-sidecar restore
│   │       └── schema.py          Baseline CREATE TABLE statements
│   ├── app/               Application layer (orchestrates core for the surfaces)
│   │   ├── agent.py        Tommy: local Ollama first, keyword fallback, cloud
│   │   ├── skills.py       SkillLibrary — composes skills into every model prompt
│   │   ├── planner.py      Turns a task name into project-aware questions
│   │   ├── service.py      AppService — single doorway UI→core, writes audit
│   │   ├── managers.py     Task/Notes/Calendar/Projects managers
│   │   ├── projects.py     Cloned-repo discovery + manifest detection
│   │   ├── launchables.py  Detect runnable artefacts + safe spawn
│   │   ├── paths.py        Per-user data/project directories
│   │   ├── security.py     Loopback check, path confinement, secret checks
│   │   ├── models.py       UI-side serialisation helpers
│   │   ├── ui.py           Legacy Tk desktop window (sigmahelix --desktop)
│   │   └── webui/          Default surface: loopback HTTP server + static assets
│   │       ├── server.py   Token-protected request handler
│   │       └── static/     index.html, app.js, style.css (no build step)
│   └── skills/            Bundled skill prompts
│       ├── builtin/       frontend-webapp, ui-interaction-design, devops, prompt-engineering
│       └── personal/      i-have-adhd.md, hatem-specific.md (auto-installed to user config)
├── tests/                 Mirrors src layout; app/ + core/ suites
└── docs/                  Long-form documentation (see docs/README.md)
    ├── CONSOLIDATION.md   How the three pre-merge trees were combined
    ├── adr/               Architecture decision records (0001–0010)
    ├── architecture/      Per-service deep dives
    ├── security/          Threat notes + secret-handling policy
    ├── execution/         Gate ledger, run log, per-task evidence
    ├── audit/             Pre-merge baseline checksums (safety net)
    └── governance/        Inherited source documents + stage reviews
```

## Conventions

- **One layout**: `src/` is the only importable package (`sigmahelix`), `tests/`
  mirrors it. No second copy of the code lives in the repo.
- **Migrations are append-only**: numbered 1..N, contiguous, and a downgrade
  refuses to drop a schema that still holds records. Do not edit an existing
  migration; add a new one.
- **All writes go through `AppService`** so every mutation records one audit
  entry. UI code never touches `repositories` directly.
- **Secrets live in the OS keyring**, never in a file this repo writes.
- **The web surface binds 127.0.0.1 only** and requires a per-session token.

## Hygiene invariants (this map is the source of truth)

- No duplicate or retired code trees (the former `company-os` and
  `company-os-app` trees were archived outside this repository during the
  consolidation and are intentionally absent here).
- `build/`, `dist/`, `.coverage`, and the `__pycache__`/`*.cache` directories
  are git-ignored build/test outputs and are safe to delete at any time; the
  binary in `dist/` is regenerated with `pyinstaller packaging/sigmahelix.spec`.
- No `*.tmp`, `*.bak`, `tasks.json`/`notes.json` (legacy import), or stray
  duplicate config files exist at the repo root or under `src/`.
