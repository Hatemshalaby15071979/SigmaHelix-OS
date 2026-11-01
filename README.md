# SigmaHelix

SigmaHelix is a local-first personal operating system and career command centre. This repository is being built gate by gate under the approved execution plan.

## Current status

P0 (truth and safety net), P1-001 (domain models), and P1-002 (SQLite persistence) are complete; P1-003 (migrations) is in progress. No release or production-readiness claim is made. See `docs/execution/LEDGER.yaml` for task state and `docs/execution/RUNLOG.md` for session evidence.

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
