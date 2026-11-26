<div align="center">

<img src="https://raw.githubusercontent.com/Hatemshalaby15071979/Helix-Solutions/main/assets/helix-solutions-logo.png" alt="Helix Solutions" width="72" height="72" style="margin-bottom:0.5rem">

# SigmaHelix-OS

A local-first personal operating system that runs on your own machine.

![Status](https://img.shields.io/badge/status-1.0.0%20released-brightgreen)

*by Helix Solutions*

</div>

## One-line identity

SigmaHelix is a local-first personal operating system: tasks, notes, projects,
calendar, launchers, and an assistant that runs on your own machine — and it is
**the Hub**, the one place its founder directs his working life from.

> **Operating principle.** One surface, not many. SigmaHelix is not a single app
> among many: it dynamically monitors and modifies the other projects on the
> founder's machine and plans his daily tasks from their real state, so he steers
> everything from one place instead of juggling repositories by hand. Everything
> lives in one SQLite file under your home directory. There is no account, no sync
> service, and no telemetry. Cloud models are available but off by default; when
> you enable one, the key is stored in your operating system's keyring, never in a
> file this project writes.

## The Hub

This repository is the control centre, not one project among many.

- **Who** — the founder is **Hatem Shalaby**. Tommy is the assistant that lives
  inside SigmaHelix; the founder is the human who owns every decision.
- **Why this is here** — to be the single surface that watches the founder's other
  projects, understands what each one is for, and acts on them (reads code, runs
  tests, proposes changes) on his behalf, while keeping an append-only,
  hash-proven record of everything that happened so nothing is invisible.
- **Why the other projects are here** — `cloned_repos/` holds the founder's other
  projects. SigmaHelix scans them on every run, scores their health, and Tommy
  reads, assesses and builds inside them — with everything he did recorded so the
  founder can always see and verify it.

## What it does

| Area | Capability |
|---|---|
| Tasks | A task is a question seeking an answer: it carries sub-questions with evidence and is only "done" once every question is answered. Tommy drafts the questions, you approve. |
| Notes | Create, edit, pin, delete, full-text search |
| Projects | Auto-discovers the `cloned_repos` folder, scans it on every run, scores each project's health, and gives every project a **▶ Run** link (starts its app or server in a terminal) |
| Calendar | Month view built from task occurrences and due dates |
| Launchers | Named command profiles per project with a whitelisted environment and no shell |
| Assistant | **Tommy** — local-first (Ollama), optional cloud providers, always shows its thinking and token usage. He is a real agent with tools: he visits URLs, reads and edits files in `cloned_repos`, assesses projects for production readiness, builds runnable projects, and writes real PDFs. In Cloud mode he is a coding agent: audits a repo, runs its tests, reads the real failures, edits the code, runs the tests again, and reports what changed and what still fails. Every turn is recorded in a hash-proven ledger; the **Mind** tab shows what he did and what he recommends changing about himself — nothing is applied without your approval. |
| Skills & plugins | Tommy auto-loads a fixed skill set into every model call (frontend, UI design, DevOps, prompt engineering, and your personal notes), so they apply to any model, local or cloud. He is one persona with every capability on — Settings → Plugins lets you trim one off for a specific task, with **Reset to full Tommy**. |
| Reminders | Persisted scheduler, notification inbox, alarms (snooze, dismiss, reschedule) |
| Audit | Append-only SHA-256 hash chain over every mutation, with verification |
| Backup | Online SQLite snapshots with a checksum manifest |

## Install

Requires Python 3.11 or newer and, for the desktop interface, a graphical
session. No root access is needed.

```sh
git clone <this repository> SigmaHelix
cd SigmaHelix
./packaging/install.sh
```

The installer creates a private virtualenv, links `sigmahelix` into `~/.local/bin`,
and registers a desktop entry.

For development, install into the checkout instead:

```sh
./packaging/install.sh --dev
./scripts/ci.sh
```

## Where things live

- The database: `~/.local/share/sigmahelix/sigmahelix.db` (owner-only permissions).
  Override with `SIGMAHELIX_DATA_DIR` or `SIGMAHELIX_DB_PATH`.
- Cloud API keys: the OS keyring — never a file. If the keyring is unavailable, the
  operation fails closed instead of falling back to plaintext.
- Settings: `~/.config/sigmahelix/config.yaml` (database path, log level, model
  mode, plugins). Secrets are rejected from this file and from environment
  variables.
- Logs: `~/.local/state/sigmahelix/logs/` (rotating JSON, secrets redacted).

## Commands

```
sigmahelix                     start the web app (localhost, browser)
sigmahelix chat                interactive console assistant
sigmahelix status              database path, schema version, counts, audit state
sigmahelix doctor              environment report: dependencies, database, model server
sigmahelix scan PATH...        scan project directories and score their health
sigmahelix backup / restore    snapshot and restore the database
sigmahelix audit verify        verify the whole hash chain
sigmahelix ledger report       what Tommy did, what it cost, what to change
sigmahelix db upgrade          apply pending migrations
```

(`sigmahelix ledger --help` shows the remaining ledger commands — show one turn,
give feedback, decide approve/reject.)

## Design in one paragraph

The code is split into a durable core (no GUI imports, fully typed) and a
presentation layer (desktop shell, terminal, assistant). The core never imports
from the app layer, and the app reaches the database only through core services —
that direction is what makes the CLI, the desktop app, and the tests agree on the
same state. Launcher profiles execute a command list with `shell=False`, only
loopback endpoints can receive prompts, and the database file is created with
owner-only permissions.

## Tests

```sh
.venv/bin/python -m pytest        # unit and integration
./scripts/ci.sh                   # format, lint, types, compile, tests, CLI smoke
```

## Status

> **Released: 1.0.0.** The durable core, the desktop app, the web UI and the CLI
> are complete and tested — 385 automated tests pass and the code is 72% covered.
> Each `v*` tag publishes a built wheel and sdist automatically via the Release
> workflow (see the GitHub Releases page). The full gate — format, lint, types,
> compile, tests and CLI smoke — runs in CI on every push.

## Related work

- Portfolio and wider work: https://github.com/Hatemshalaby15071979

## Author

Built by Hatem Ismail Shalaby, Contact Centre Operations & AI Implementation Lead |
WFM & CX Transformation.

Background: https://github.com/Hatemshalaby15071979

## Licence

MIT
