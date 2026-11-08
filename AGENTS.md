# AGENTS.md — how to work in this repository

This file is for AI agents and contributors. Read it before editing SigmaHelix.

## What this is

A local-first personal OS: tasks, notes, projects, calendar, launchers, audit, and
backup, plus an assistant named **Tommy** that runs on the user's machine. The
primary UI is a **loopback-only web app** (`sigmahelix`, opens in the browser);
`sigmahelix --desktop` is the legacy Tk window, `sigmahelix chat` is the console.

## Start here

- **Product/what it does**: `README.md`
- **Structure**: `REPOMAP.md` (authoritative directory map)
- **Invariants**: `CONSTITUTION.md` (must not violate)
- **Why decisions were made**: `docs/adr/` (0001–0010) and `docs/architecture/`
- **History of the merge**: `docs/CONSOLIDATION.md`

## Command map

```
sigmahelix                 # web UI (default) — loopback, token-protected
sigmahelix --desktop      # legacy Tk window
sigmahelix chat           # console REPL
sigmahelix doctor         # verify the environment (skills, DB, keyring, …)
sigmahelix skills verify  # prove every skill reaches the model payload
sigmahelix scan           # scan cloned_repos for projects + runnable artefacts
sigmahelix db upgrade     # apply pending migrations
```

## Development loop

```sh
# 1. create/activate the venv (already present as .venv in this checkout)
. .venv/bin/activate

# 2. run the full gate (the definition of done)
./scripts/ci.sh

# 3. targeted tests
python -m pytest tests/app -q
python -m pytest tests/core -q

# 4. verify environment + skills
SIGMAHELIX_NO_AUDIO=1 python -m sigmahelix doctor
SIGMAHELIX_NO_AUDIO=1 python -m sigmahelix skills verify
```

The gate runs, in order: ruff format → ruff lint → mypy (source) → compileall →
pytest → CLI smoke. **Do not skip it.** If you touch the schema, also run the
migration tests (`tests/core/test_migrations.py`) and extend
`backup.py`'s required-tables map for the new version.

## Architecture boundaries (respect them)

- **`core/`** is provider-agnostic: domain models, config, and SQLite storage.
  It must not import UI, network clients, or the agent. Keep it pure.
- **`app/`** orchestrates `core` for the surfaces. UI code talks to the core only
  through **`AppService`** — never directly to repositories — so every mutation
  is audited.
- **`skills/`** holds bundled skill prompts. Personal skills (`i-have-adhd`,
  `Hatem_specific`) are auto-installed to `~/.local/share/sigmahelix/skills`.
- **`webui/`** is a static `index.html` + `app.js` served by a stdlib HTTP server.
  No framework, no build step, no network beyond loopback.

## Common tasks

- **Add a skill**: drop `skills/builtin/<name>.md`, register it in
  `app/skills.py`, and confirm `skills verify` lists it.
- **Change the schema**: append a migration in `core/storage/migrations.py`,
  update `schema.py` baseline + `backup.py` required-tables, and add a test.
- **Add a UI feature**: edit `webui/static/*` and the `Handler` in
  `webui/server.py`; keep all writes behind `AppService`.
- **New task behavior**: task questions live in `TaskQuestion` (migration v15);
  Tommy drafts them in `app/planner.py` by scanning the real project in
  `cloned_repos`.

## Hard rules (from CONSTITUTION.md)

- Tommy is the only assistant; the six skills are injected into **every** model
  call (local and cloud) and Tommy always shows thinking + tokens.
- Migrations are append-only; never edit an existing one.
- No telemetry, no cloud by default, secrets only in the OS keyring.
- Web surface is loopback-only + token-protected.
- One codebase, no duplicates; `build/`, `dist/`, `.coverage`, caches are
  git-ignored and disposable.
- Update `README.md`/`CHANGELOG.md` for every user-visible change; keep the root
  `REPOMAP.md`, `AGENTS.md`, `CONSTITUTION.md` in sync.

## Notes for agents

- Prefer editing existing files over creating new ones. Don't add documentation
  files unless asked.
- When the user runs `sigmahelix` with no subcommand, it serves the web UI — do
  not "fix" the default to the Tk window.
- Run the gate before declaring work done; if a test fails, fix the code or the
  test's stale assumption, but never delete or disable tests to make it pass.
