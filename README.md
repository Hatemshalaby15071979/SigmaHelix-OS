# SigmaHelix

A local-first personal operating system: tasks, notes, projects, calendar,
launchers, and an assistant that runs on your own machine.

Everything lives in one SQLite file under your home directory. There is no
account, no sync service, and no telemetry. Cloud models are available but
**off by default**; when you enable one, the key is stored in your operating
system's keyring, never in a file this project writes.

```
sigmahelix            # desktop app
sigmahelix chat       # terminal assistant
sigmahelix doctor     # check that everything works
```

## What it does

| Area | Capability |
| --- | --- |
| Tasks | Create, complete, pin, delete; recurring series with materialised occurrences |
| Notes | Create, edit, pin, delete, full-text search |
| Projects | Discover repositories, read git branch/commit/dirty state, score health, list build artifacts |
| Calendar | Month view built from task occurrences and due dates |
| Launchers | Named argv profiles per project with a whitelisted environment and no shell |
| Assistant | Local Ollama first, deterministic keyword fallback, optional cloud providers |
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
| `~/.config/sigmahelix/config.yaml` | Optional settings: `database_path`, `log_level` |
| `~/.local/state/sigmahelix/logs/` | Rotating JSON logs with secret redaction |

Override the data directory with `SIGMAHELIX_DATA_DIR` (this also moves the
database) or point at a specific database file with `SIGMAHELIX_DB_PATH`. Both
must be absolute paths. Set `SIGMAHELIX_NO_AUDIO=1` to run without touching
microphone or speech hardware.

## Commands

```
sigmahelix                     start the desktop app
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
