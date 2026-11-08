# SigmaHelix

A local-first personal operating system: tasks, notes, projects, calendar,
launchers, and an assistant that runs on your own machine.

Everything lives in one SQLite file under your home directory. There is no
account, no sync service, and no telemetry. Cloud models are available but
**off by default**; when you enable one, the key is stored in your operating
system's keyring, never in a file this project writes.

```
sigmahelix            # local web app (opens http://127.0.0.1:<port> in your browser)
sigmahelix --desktop # the legacy Tk desktop window
sigmahelix chat      # terminal assistant
sigmahelix doctor    # check that everything works
```

The web interface is the primary surface. It is served on loopback only and
every API call needs a per-session token embedded in the page, so no other
process on the machine can drive it. The Tk window is kept for environments
without a browser.

## What it does

| Area | Capability |
| --- | --- |
| Tasks | Question-driven: a task is a question seeking an answer. Each task carries sub-questions with answers + evidence; it is only "done" once every question is answered. Tommy drafts the questions, you approve — and Tommy can also add, answer, reopen, show and **execute** a task's questions himself when you ask. |
| Notes | Create, edit, pin, delete, full-text search |
| Projects | Auto-discovers the `cloned_repos` folder (works from the source checkout *and* an installed binary) and scans it on every run, reading git state, scoring health, and surfacing a **Run** link for any deployed app, executable, web/dashboard or desktop build |
| Calendar | Month view built from task occurrences and due dates |
| Launchers | Named argv profiles per project with a whitelisted environment and no shell |
| Assistant | **Tommy** — local Ollama first, deterministic keyword fallback, optional cloud providers. Always shows its thinking and token usage. Tommy has a **coding workspace**: ask him to build a webapp/app/site and he scaffolds a runnable project under `cloned_repos` (with a Run link) and edits files, instead of refusing. |
| Skills | Tommy auto-loads a fixed set of skills into every model call (frontend/webapp, UI design, DevOps, prompt engineering, `i-have-adhd` and your personal `Hatem_specific`), so they apply to any model, local or cloud |
| Reminders | Persisted scheduler, notification inbox, alarm state machine (snooze, dismiss, reschedule) |
| Audit | Append-only SHA-256 hash chain over every mutation, with verification |
| Backup | Online SQLite snapshots with a checksum sidecar manifest |

## Install

Requires Python 3.11 or newer and, for the desktop interface, a graphical
session. No root access is needed.

```sh
git clone <this repository> SigmaHelix
cd SigmaHelix
./packaging/install.sh
```

The installer creates a private virtualenv in `~/.local/share/sigmahelix`,
links `~/.local/bin/sigmahelix`, and registers a desktop entry. Add
`~/.local/bin` to `PATH` if it is not already there.

For development, install into the checkout instead:

```sh
./packaging/install.sh --dev
./scripts/ci.sh
```

## Where things live

| Path | Contents |
| --- | --- |
| `~/.local/share/sigmahelix/sigmahelix.db` | The database (mode 0600, WAL, `synchronous=FULL`) |
| OS keyring (`sigmahelix` service) | Cloud provider API keys, never a file |
| `~/.config/sigmahelix/config.yaml` | Optional settings: `database_path`, `log_level`, `model_mode` (`local`/`cloud`/`hybrid`), `cloud_provider`, `cloud_model` |
| `~/.local/state/sigmahelix/logs/` | Rotating JSON logs with secret redaction |

Override the data directory with `SIGMAHELIX_DATA_DIR` (this also moves the
database) or point at a specific database file with `SIGMAHELIX_DB_PATH`. Both
must be absolute paths. Set `SIGMAHELIX_NO_AUDIO=1` to run without touching
microphone or speech hardware.

## Commands

```
sigmahelix                     start the web app (localhost, browser)
sigmahelix chat                interactive console assistant
sigmahelix status              database path, schema version, counts, audit state
sigmahelix doctor              environment report: dependencies, database, model server
sigmahelix scan PATH...        scan project directories and score their health
sigmahelix backup --destination FILE
sigmahelix restore --source FILE --destination FILE
sigmahelix audit verify        verify the whole hash chain
sigmahelix audit list          recent audit entries
sigmahelix db upgrade          apply pending migrations
sigmahelix db info             show the schema version
```

## Architecture

```
src/sigmahelix/
├── core/          durable layer — no GUI imports, fully typed
│   ├── models.py        domain records and validation
│   ├── recurrence.py    recurrence rules and occurrence expansion
│   ├── config.py        settings resolution and secret rejection
│   ├── logging.py       JSON logs with redaction
│   ├── secrets.py       OS keyring access
│   └── storage/
│       ├── database.py       connection policy and transactions
│       ├── migrations.py     versioned, guarded schema migrations
│       ├── repositories.py   tenant-scoped CRUD with soft delete
│       ├── audit.py          append-only hash chain
│       ├── scheduler.py      persisted jobs with transactional claims
│       ├── notifications.py  inbox with dedupe keys
│       ├── alarms.py         snooze / dismiss / reschedule
│       ├── occurrences.py    recurring task materialisation
│       ├── project_scanner.py
│       ├── launchers.py
│       └── backup.py
└── app/           presentation layer
    ├── ui.py            CustomTkinter desktop shell
    ├── console.py       terminal REPL
    ├── agent.py         local-first assistant and intent routing
    ├── models.py        model catalogue and cloud providers
    ├── managers.py      view models over the core
    ├── voice.py         speech input and text to speech, on demand
    ├── security.py      loopback-only endpoint policy
    └── paths.py         every filesystem decision in one place
```

The core never imports from `app`, and `app` reaches the database only through
the core services. That direction is what makes the CLI, the desktop app, and
the tests agree on the same state.

## Security posture

- Secrets are rejected from YAML configuration, from `SIGMAHELIX_*` environment
  variables, from log output, and from audit payloads.
- API keys live in the OS keyring. If the keyring is unavailable, the operation
  fails closed instead of falling back to a plaintext file, and a legacy
  plaintext key file is migrated and deleted.
- Cloud providers are disabled until a key is explicitly added and verified.
- Only credential-free loopback HTTP endpoints can receive prompts.
- Launcher profiles execute an argv list with `shell=False` and a whitelisted
  environment.
- The database file and its directory are created with owner-only permissions.

## Tests

```sh
.venv/bin/python -m pytest        # unit and integration
./scripts/ci.sh                   # format, lint, types, compile, tests, CLI smoke
```

## Status

This is a pre-1.0 build. The durable core, the desktop app, and the CLI are
complete and tested; see `docs/execution/LEDGER.yaml` for the gate history.
