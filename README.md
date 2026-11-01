# SigmaHelix

SigmaHelix is a local-first personal operating system and career command centre. This repository is being built gate by gate under the approved execution plan.

## Current status

P0 (truth and safety net) and P1 (durable core) are complete; P2-001 through P2-009 (time features, project scanning/watch mode, and launcher profiles) are complete. P2-010 (Windows-only artifact labelling) is in progress. No legacy in-memory task/note data was available to import. No release or production-readiness claim is made. See `docs/execution/LEDGER.yaml` for task state and `docs/execution/RUNLOG.md` for session evidence.

## Source documents

The approved plan and Tommy runtime specification are maintained in `docs/governance/`.

## Install dependencies

The current lock targets Linux x86_64 with Python 3.12:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
```

## Local commands

- `PATH="$PWD/bin:$PATH" sigmahelix --version` reports the repository version.
- `bin/sigmahelix` opens the desktop app; `bin/sigmahelix --cli` starts the console interface.
- `bin/sigmahelix backup --destination /absolute/path/sigmahelix-backup.db` writes a consistent SQLite snapshot and checksum manifest; `bin/sigmahelix restore --source /absolute/path/sigmahelix-backup.db --destination /absolute/path/restored.db` validates and restores to a new file.
