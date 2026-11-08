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
- Model mode (Local/Cloud/Hybrid) and API keys are managed in the web UI
  **Settings** view (⚙️). The mode persists to `~/.config/sigmahelix/config.yaml`
  and is reloaded on startup; keys go to the OS keyring only, never to config.
- `projects_dir()` must keep discovering `cloned_repos` when there is no source
  checkout sibling (installed binaries); do not revert it to `~/projects`.
- Tommy's question-task actions and `create_project` are deterministic and must
  keep working without a model. A build request must scaffold real files — never
  answer it with a refusal.
- `app/tools.py` holds the agent's real tools (`fetch_url`, workspace file ops,
  project readiness, PDF). Keep them deterministic-routed in the agent: a URL
  read, a project scan, or a document request must never degrade to "I can't".
  `fetch_url` must keep refusing private/loopback hosts (SSRF guard), and file
  operations must stay confined to `cloned_repos`.
- **The `code` plugin makes Tommy a real coding agent — only in Cloud mode.**
  `app/coder.py` holds `run_command`/`run_tests`/`audit_repo`/`edit_file`
  (no shell, workspace-confined, destructive-command deny-list, exact
  search/replace edits). In Cloud mode the agent runs a bounded multi-step loop
  (`Agent._agent_loop`): audit the repo → run its tests → read the real failures
  → edit the code → run again → report what changed and what still fails. A list
  of file names is never the answer to "fix this". Keep Local/Hybrid modes on the
  single-shot path; never make the loop run outside Cloud mode, and never let a
  disabled `code` plugin act. The loop prompt block is injected only in Cloud
  mode (`Agent.loop_block()`), so `system_prompt()` must reproduce the local
  prompt exactly when the loop is off.
- **Everything is a plugin, and all of them are on.** `app/plugins.py` is the
  single catalogue of capabilities (`PLUGINS`) and presets (`PRESETS`). Tommy is
  one persona with every capability enabled by default — the switches are for
  trimming a task, not for choosing a role. A capability's actions are declared
  there, shown in Settings → Plugins, persisted as `plugins_enabled` in
  `config.yaml`, injected into the prompt via `PluginRegistry.prompt_block()`,
  and enforced by `PluginRegistry.gate()` in `Agent._execute`. When you add a
  capability, add the plugin manifest *and* the handler; when you add a
  handler, add the manifest — otherwise the action is unreachable or ungated.
  The base `SYSTEM_PROMPT` must not document individual actions; the plugin
  block is the only place they are listed, so disabling one really removes it.
- **No persona pickers.** Tommy's traits (honest/practical, human tone,
  evidence-aware, doer) are always on together. Do not reintroduce a switch that
  makes them exclusive — the old `persona_style` control did nothing.
- **No hardcoded app names.** `launch <anything>` must resolve the name against
  the real projects (`projects.match_projects`) and start what the project
  actually contains (`launchables.detect_launchables`). Never reintroduce a
  fixed list of launchable apps or a "which app?" reply — an unknown name gets
  the real project list, an ambiguous one gets a choice, and a project with no
  interface says exactly what was looked for.
- **Project pages are served, not linked as `file://`.** `/project/<name>/<path>`
  serves files from the project folder (token in `?t=`, path-confined) with a
  sandbox CSP so a project's JavaScript cannot reach the app API or read the
  session token. Keep that CSP when touching the route.
- Run the gate before declaring work done; if a test fails, fix the code or the
  test's stale assumption, but never delete or disable tests to make it pass.
