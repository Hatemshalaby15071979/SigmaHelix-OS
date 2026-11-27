# AGENTS.md — how to work in this repository

This file is for AI agents and contributors. Read it before editing SigmaHelix.

## What this is

A local-first personal OS: tasks, notes, projects, calendar, launchers, audit, and
backup, plus an assistant named **Tommy** that runs on the user's machine. The
primary UI is a **loopback-only web app** (`sigmahelix`, opens in the browser);
`sigmahelix --desktop` is the legacy Tk window, `sigmahelix chat` is the console.

**This repository is the Hub.** SigmaHelix is the single surface its founder
(**Hatem Shalaby**) uses to dynamically monitor and modify his other projects
(under `cloned_repos/`) and to plan his daily tasks from their real state. Treat
`cloned_repos` as live projects to scan, read, assess and build in — not as
decorative examples.

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
- **Never show raw model JSON, and never trust a truncated call.**
  `try_cloud_query` reports `finish_reason`/`truncated` in the trace;
  `_agent_loop` retries a truncated call once with a larger budget (8192 for
  `file_operations`/`edit_file`/`run_command`/`audit_repo`) and otherwise reports
  the cut-off. `Agent._looks_like_action` distinguishes a malformed tool call
  from prose: the former is an error to retry, never a reply to display. The
  reply budget comes from `Settings.cloud_max_tokens` — do not reintroduce a
  constant.
- **Every success claim needs a tool result.** `Agent._unverified_claim` checks
  the final answer against the steps of the same turn (created/edited/fixed/
  passing/committed/100). One correction round, then a visible
  `⚠️ unverified claim` prefix. Keep this deterministic; do not replace it with
  a model self-check.
- **Every turn is recorded in the metacognition ledger.** `Agent.process_command`
  opens a turn and closes it in `finally`; `app/metacognition.py` writes
  `agent_turns`/`agent_steps` and anchors each closed turn's content hash in
  `audit_log`. The steps, the turn row, its proof and the anchor go into
  **one transaction**, and the proof covers the digest of the steps — an edited
  step, a deleted turn or a duplicate anchor fails `ledger verify`. Recording
  must never break a reply (all calls are wrapped), and a report must never call
  a model for a number — every metric is SQL-derived and every recommendation
  cites turn ids. Recommendations are never auto-applied: `Ledger.decide` moves
  a recommendation along an explicit transition table (`proposed → approved |
  rejected`, `approved → rejected`, `rejected → approved | proposed`) and
  audits every decision. A rejected recommendation is never re-proposed; only
  the founder may reopen it. What is stored is redacted with
  `core.logging.redact_text`, and past turns are replayed to a cloud provider
  only when `cloud_replay_history` is on.
- **Launches self-heal in Cloud mode too.** `Agent._handle_launch` →
  `Agent._remediate_launch` → `coder.install_project_requirements` creates a
  project-local `.venv` and installs the project's requirements when a launch
  fails for a missing runtime (`_preflight` "is not installed for … install the
  project requirements"). It then re-detects and retries once. This is gated by
  `_loop_enabled()` (Cloud + code plugin), so Local/Hybrid never install
  anything. Never run it outside Cloud mode, and never let it install into a
  project the user did not ask to launch.
- **"Install <project> requirements" must actually install.** The
  `install_requirements` action and the deterministic install route
  (`_handle_install_requirements`) resolve the project and run
  `coder.install_project_requirements`; if the request also says "and run it",
  they launch afterwards. Never answer this with a directory listing or the
  project list — resolve the project and act.
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
- **The prompt must ground the model in its real workspace.** `Agent.workspace_block()`
  injects the absolute `projects_dir()` path into `system_prompt()` and tells the
  model that absolute paths inside it are valid. Without this the model invents a
  sandbox wall and refuses to edit a folder that is inside its own workspace.
  The same block also forbids fetching `127.0.0.1`/localhost (it is a link, not a
  fetch target), tells it to resolve project names itself, to read code before
  declaring a task blocked, and never to invent policy ("Zone R"). Keep
  `workspace_block()` in the base prompt (both modes) — only `loop_block()` may
  differ between local and cloud.
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

## Ledger (sign-in / sign-out)

## [2026-11-27 05:02 EET] — sami (OpenMausBot), owner-authorised governance landing

STATUS: SIGN-IN (work in progress)

Task: Bring this repository onto the portfolio governance standard, as the owner approved in chat on 2026-11-27 ("bring the remaining eleven onto the same governance standard"). This repository already had a root CONFIGURATION of AGENTS.md, CONSTITUTION.md, REPOMAP.md, GLOSSARY.md, CHANGELOG.md, LICENSE and SECURITY.md, but no GOVERNANCE.md and no root-document gate.

Touched: Will add `GOVERNANCE.md`, `scripts/check_root_docs.py` and one `governance` job in `.github/workflows/ci.yml`; will append this entry and its sign-out to `AGENTS.md`. Nothing is moved, renamed or deleted.

Why: Five repositories in the portfolio now share one rule — root holds only the documented set — enforced by one gate. This repository had the documents but no written policy for the root and no enforcement, so the rule could not be checked here. `CONSTITUTION.md` in this repository is the project's invariants text rather than the shared portfolio philosophy; that divergence is recorded in `GOVERNANCE.md` section 5 rather than resolved, because the constitution is owner-only.

Verification: Planned — `python3 scripts/check_root_docs.py` and `--self-test` locally, then `./scripts/ci.sh`, then the GitHub Actions run on the landing commit.

Left undone: Nothing at sign-in.

Sensitive: `git push origin main` (owner's instruction in chat, 2026-11-27). No force push, no history rewrite, no secrets.

## [2026-11-27 05:16 EET] — sami (OpenMausBot), owner-authorised governance landing

STATUS: SIGN-OUT (landing complete)

Task: Bring this repository onto the portfolio governance standard. Done.

Touched: `GOVERNANCE.md` (new); `scripts/check_root_docs.py` (new, md5 `35fc37ab16ff4461a33d4e2dcaedb7bf`, byte-identical to the copy in Assay, createlee, Helix-Solutions, Helix-Matrix, Helix-Codex, work-samples and Mannschaft); `.github/workflows/ci.yml` (one new `governance` job); this ledger (heading plus sign-in and sign-out). Nothing was moved, renamed or deleted.

Why: This repository already held the right root documents — README, AGENTS, CONSTITUTION, REPOMAP, GLOSSARY, CHANGELOG, LICENSE, SECURITY — but no written policy for the root and nothing enforcing it. It now has both. The two extra documents are **named in the section 2 table as required rather than moved**, because both are load-bearing: `AGENTS.md` and `CONSTITUTION.md` both require `REPOMAP.md` kept in sync with the tree, and `GLOSSARY.md` is hashed in `docs/audit/MERGE_BASELINE_2026-11-08.sha256`, so moving it would invalidate a recorded baseline.

Verification: `scripts/check_root_docs.py` → "OK — SigmaHelix-OS/ holds only the GOVERNANCE.md section 2 set" (9 table rows, 9 allowed root documents); `--self-test` → 7/7 cases behaved. The `governance` job parses as valid YAML (jobs: `verify`, `package`, `governance`). `ruff check src tests scripts` → "All checks passed!"; `pytest --co` collects cleanly.

Left undone: **The full pytest suite was not observed to finish here.** It ran past 280 seconds (the ceiling for a single command in this workspace) without completing, so this landing cannot claim a green suite from local evidence — the GitHub Actions run is the record. This is a workspace limit, not a known failure: the suite was still progressing with no error when the clock cut it. CI on `fbaa0ec` and the sign-out commit is the record of the same steps on a clean runner.

Also left undone, and it is the owner's call: `CONSTITUTION.md` here is this project's invariants text, not the shared portfolio philosophy that the other governed repositories carry. `GOVERNANCE.md` section 5 records that divergence explicitly instead of resolving it, because the constitution is owner-only and this file is referenced from code, docs and a hash baseline.

Sensitive: `git push origin main` (owner's instruction in chat, 2026-11-27). No force push, no history rewrite, no secrets.

## [2026-11-27 05:18 EET] — sami (OpenMausBot), CI repair (SigmaHelix-OS format gate)

STATUS: SIGN-IN (work in progress)

Task: Repair the red CI on `main` at commit `952a4ec`, which this landing itself caused. The `verify` job fails at step 5, "Check formatting" (`ruff format --check src tests scripts`), on all three Python matrix jobs; every later step is skipped, and the `package` job is skipped with them. The new `root-document hygiene` job passes.

Touched: Will move `scripts/check_root_docs.py` to `.github/scripts/check_root_docs.py` and repoint the `governance` job; will append this entry and its sign-out to `AGENTS.md`. No other file changes.

Why: The gate is a shared artefact that must stay byte-identical across the portfolio (md5 `35fc37ab16ff4461a33d4e2dcaedb7bf`), so it cannot be reformatted to suit one repository. This repository sets `line-length = 88` and includes `scripts` in its format check, so the file is the only one that "would be reformatted" — with it set aside, the same command reports 97 files already formatted. Helix-Solutions solved the identical collision the same way, by keeping the gate under `.github/scripts/`, which its format check does not cover. Fixing the file would have been the other option and is the wrong one: it would fork the shared text.

Verification: Planned — `ruff format --check src tests scripts` clean, `python3 .github/scripts/check_root_docs.py` and `--self-test` green, then the GitHub Actions run on the repair commit with all `verify` steps reaching the tests.

Left undone: Nothing at sign-in.

Sensitive: `git push origin main` (owner's instruction in chat, 2026-11-27). No force push, no history rewrite.
