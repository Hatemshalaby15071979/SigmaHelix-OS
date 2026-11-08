# Changelog

All notable changes to SigmaHelix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Documentation: SigmaHelix as the Hub.** `README.md` and `AGENTS.md` now state
  plainly that this repository is the founder's control centre — the one surface
  Hatem Shalaby uses to monitor and modify his other projects (`cloned_repos/`)
  and to plan his daily tasks — and why those projects live here.

- **`cloud_replay_history` setting** (default `false`). Past turns are replayed
  into the prompt by the local model only; sending them to a cloud provider
  needs the founder's explicit opt-in.
- **Metacognition ledger (migration v16).** Every turn is written to

### Changed

- **The turn proof now covers the reasoning trail.** The canonical digest of a
  turn's ordered steps is part of its proof, so editing, deleting or inserting a
  step is detected by `sigmahelix ledger verify` — the reasoning trail is
  provable like the reply is.
- **Verification is driven by the audit chain.** Every `agent.turn.completed`
  anchor must have a live closed turn, every closed turn must have exactly one
  anchor, and a turn that was deleted from the table is reported as an orphan.
  `verify` now reports `complete`, `orphans` and `duplicates` next to `valid`.
- **A turn is written in one transaction.** The steps, the turn row, its proof
  and the audit anchor are committed together, and the anchor can no longer be
  left behind a failed write. A closed turn cannot be closed a second time.
- **Recommendations remember a rejection.** One row per (kind, title): a
  recommendation the founder rejected is not re-proposed by the next analysis.
  Decisions follow an explicit transition table — `proposed → approved |
  rejected`, `approved → rejected`, `rejected → approved | proposed` (reopen) —
  and every decision is audited with the state it came from. The Mind tab shows
  a **Reopen** button for rejected recommendations; `sigmahelix ledger decide`
  accepts `approve`, `reject` and `reopen`.
- **SQLite runs with `synchronous = NORMAL`** (WAL). The old `FULL` setting cost
  an fsync per commit — ~88 ms on this machine's disk, and eight commits per
  agent turn.
- **The Mind report no longer issues one query per turn.** Step metrics come from
  a single aggregate `GROUP BY` over the steps table joined to the period's turns,
  so `report` stays fast as the ledger grows and `analyze` builds the report once
  and hands it to `recommend` instead of recomputing it. `turn_ids` are no longer
  sent over the wire (the Mind tab never read them) — only the recommendations
  that cite them keep the id list.
- **`applied` is now a real, reachable state.** `Ledger.apply()` runs only on
  `approved` recommendations and only for whitelisted, reversible kinds
  (`config` writes the setting, `skill` writes a reversible user skill file,
  plugin toggles update the enabled set); `prompt`/`tool`/`new_plugin` are refused
  with "not auto-applied" so the founder routes them to the coding agent. Every
  application is audited with what it did, and an applied recommendation can no
  longer be decided. `sigmahelix ledger apply <rec-id>` exposes it. The config
  recommendation now carries the exact `setting`/`value` it will write.
- **Config secret detection no longer false-positives on `cloud_max_tokens`.** The
  secret-key guard matches a token/key/password only as a whole segment, so
  `cloud_max_tokens` is a valid setting while `api_token`/`auth_token`/`api_key`
  still raise.
- **Outcomes are decided at the route, not sniffed from the reply.** `process_command`
  now assigns an explicit outcome (`answered` / `acted` / `blocked` / `refused` /
  `failed`) at each return point from the route's own status contract; the old
  emoji-prefix sniffing over the reply string is gone. Deterministic action routes
  (`tool`, `task`) that succeed are marked `acted`.
- **Deterministic routes now record a step.** `tool` and `task` routes never ran the
  model loop, so they left the steps table empty and quietly distorted the tool-call
  metrics and the "pushback without a tool" rule. Each now records one honest
  `tool_call` step, so those metrics reflect reality; a blocked/disabled route is
  recorded as `blocked` and gets no fabricated success step.
- **`pushback_rate` can no longer exceed 1.** It was feedback rows (filtered by
  `created_at`) divided by turns (filtered by `started_at`) — a late verdict on an
  old turn, or two verdicts on one turn, pushed it past 1. It is now the count of
  distinct period turns (joined on `started_at`) carrying a pushback verdict, so it
  stays within [0, 1].
- **The report no longer silently truncates busy periods.** `report` fetched period
  turns with a 100 000-row `LIMIT` ordered ascending, which dropped the newest turns
  past the cap. `turns(since=…, limit=None)` returns every period turn and `report`
  uses it.
- **Metacognition ledger (migration v17).** Adds the two covering indexes the
  report/recommend queries were missing — `idx_agent_feedback_tenant_created` on
  `agent_feedback(tenant_id, created_at)` and
  `idx_agent_recommendations_tenant_status_created` on
  `agent_recommendations(tenant_id, status, created_at)` — so pushback and
  recommendation lookups scan by index instead of the whole table.
- **`evidence_json` is always a JSON array.** An unclosed turn now stores `[]`
  instead of `{}`, so callers never special-case an unclosed turn's evidence
  shape; the report and the `verify` proof both cover it.
- **Ledger tests hardened (regressions stop hiding).** The four tautological
  metacognition assertions were rewritten to check real behaviour — a decision's
  `from`/`to` state in the audit chain, the exact repeated-intent key the report
  groups under, that a ledger failure leaves no half-written turn behind, and that
  assistant replies (not just user prompts) survive a restart — and ten regression
  tests were added: double-decide refusal, unknown-turn 404, invalid-period 400,
  mid-turn ledger failure, evidence shape, persisted steps, feedback-on-unknown 400,
  concurrent same-session turns, recovered-intent vs skill rule, and
  `sigmahelix ledger verify` / `report --json` through the CLI.

### Fixed

- **Credentials are no longer written to the ledger in plaintext.** The user's
  text, the reply and every step argument and summary pass through the
  existing `redact_text` before they are stored, and provider keys without a
  label (`sk-…`, `gsk_…`) are now redacted too.
- **A bad request could kill the web connection.** Every GET route now has the
  same exception boundary the POST routes have: an unknown turn id is a 404, a
  bad period is a 400, and an internal error is a plain 500 that does not echo
  the exception. Periods are bounded (3650 days / 8760 hours / 520 weeks).
- **`sigmahelix ledger` no longer prints a traceback** for a bad turn id or a
  bad period; it explains the problem and exits with the usage code.
- **Metacognition ledger (migration v16).** Every turn is written to
  `agent_turns` with its steps in `agent_steps`, and each closed turn's content
  hash is anchored in the existing hash-chained `audit_log` — so a turn is
  provable by id, timestamp and chain position. `sigmahelix ledger verify`
  checks the chain and recomputes every proof.
- **A deterministic self-report and recommendations.** `sigmahelix ledger
  report` (and the **Mind** tab in the web UI) computes outcomes, success and
  truncation rates, tool failure rates, pushback and repeated intents from SQL —
  never from a model — and proposes typed recommendations (config, tool, prompt,
  skill, plugin). Each recommendation cites the turn ids behind it; the founder
  approves or rejects it, and nothing applies itself.
- **A visible reasoning trail.** Every loop step is recorded with its action,
  arguments, the model's own one-line `plan`, duration and result, and rendered
  in the web UI, console and desktop window. `finish_reason` and a truncation
  flag are part of the trace.
- **`cloud_max_tokens` setting** (1024–16384, default 4096) with a per-request
  budget and an 8192 retry for heavy tool payloads.
- **Conversation persistence.** `_build_messages` reloads the last turns from
  the ledger after a restart, so Tommy no longer claims it cannot see the
  conversation.

### Fixed

- **The 500-token cap that cut tool calls in half.** A truncated reply is now
  detected via `finish_reason == "length"`, retried once with a larger budget,
  and reported — never echoed as raw `{"action": ...}` JSON. Malformed
  action-shaped output is treated as a tool-call error, not an answer.
- **Readiness score and verdict could disagree.** `assess_project` now computes
  one weighted score from the same checks that produce `missing`, so
  `score == 100` ⟺ `missing == []` ⟺ production-ready. Git state no longer
  moves the score, and the `env_config` label is now the honest
  "env template (.env.example)".
- **Claims were not bound to evidence.** A final answer that says it created,
  edited, fixed or committed something without a successful tool result in the
  same turn gets one correction round, then a visible
  `⚠️ unverified claim` prefix.

- **Persona renamed to Tommy.** The assistant now introduces itself as Tommy in
  the web UI, desktop window and console. All skill injection is wired to Tommy.
- **Dynamic web interface is the default.** `sigmahelix` now serves a
  loopback-only web app (token-protected) and opens it in your browser;
  `sigmahelix --desktop` keeps the legacy Tk window. The web UI talks to the
  same durable core, so nothing is lost switching surfaces.
- **Skill engine (`SkillLibrary`) wired into every model call.** Tommy composes
  a fixed skill set into the system prompt for *both* local Ollama and cloud
  providers: frontend/webapp engineering, UI & interactive design, DevOps,
  prompt engineering, `i-have-adhd`, and the personal `Hatem_specific` skill.
  The composed prompt is sent on every request; a `skills verify` command
  proves each skill reaches the payload. Personal skills install automatically
  to `~/.local/share/sigmahelix/skills`.
- **Model thinking and token trace.** Ollama `thinking` + `eval_count` and
  cloud `usage`/`reasoning` are captured, printed in the console, and shown in
  the web UI as a collapsible thinking block plus an in/out token chip.
- **Project launch links.** The Projects section scans `cloned_repos` for any
  deployed app, executable, web/dashboard or desktop build and renders a
  clickable **Run** link that persists across launches and spawns the process
  safely (no shell, confined to the project root).
- **Question-driven Tasks (migration v15).** A task is now a question seeking an
  answer. Each task carries sub-questions, each with an answer and evidence; the
  task is only completable once every question is answered (readiness gate).
  Tommy proposes the questions for any project in `cloned_repos` by scanning the
  real project on disk; you approve before the task is created. Tasks carry a
  due date and appear in the calendar.
- **Web Settings view (⚙️).** Choose the model mode — **Local**, **Cloud**, or
  **Hybrid** — and manage provider API keys from the web UI. Selecting a mode
  persists `model_mode`/`cloud_provider`/`cloud_model` to `config.yaml` and is
  applied to the live agent; a restart reloads the same selection automatically.
  Keys are added, live-verified against the provider, and removed entirely from
  the OS keyring (never written to config). Unverified or bad keys are reported
  and never stored.
- **Tommy manages and executes question-driven tasks.** New agent actions let
  Tommy create a task with its questions, add/answer/reopen/show questions, and
  **execute** a task — answering its open questions with the model and marking it
  done once every answer is in. These are deterministic, so "add question to
  task 3: …", "answer question 1 on task 3: …" and "execute task 3" work even
  without a model connection.
- **Tommy has a coding workspace.** Ask him to create a webapp, app, site, tool
  or script and he scaffolds a runnable project under `cloned_repos` (with a
  **Run** link) and can edit its files via file operations — instead of
  apologising that he cannot do it here. If a model reply refuses a build
  request, the refusal is replaced by an actual scaffold.
- **Everything is a plugin — one Tommy persona, all capabilities on.** Every
  capability — tasks, question-driven tasks, notes, projects/readiness,
  workspace files, web access, documents, calendar, launchers, YouTube, skill
  upload — is a plugin in a registry (`app/plugins.py`), and **all of them are
  on by default**: Tommy is a single persona with the features of every role,
  not a menu you must choose from. Settings → **Plugins** lists them with their
  permissions and a live switch so you can trim one for a specific task, plus
  a **Reset to full Tommy** button. The enabled set is persisted to
  `config.yaml` (`plugins_enabled`) and applied to the running agent
  immediately: the model prompt lists only enabled actions and the dispatcher
  refuses a disabled one with a pointer to Settings. The base persona no longer
  hardcodes action docs, so the plugin block is the single source of truth.
- **The three persona switches are gone.** "Honest & practical", "human tone"
  and "evidence-aware" were mutually exclusive buttons that never changed the
  prompt. They are now one always-on identity in both the web UI and the Tk
  window.
- **Every project has a Run link and a page link.** The Projects view now shows,
  per project, a **▶ Run** action that starts whatever the project actually
  contains (packaged app, desktop script, npm dev server, Streamlit, FastAPI,
  Flask, compose) in a terminal so its log is visible, plus a link to its
  `index.html`/`home.html` served from the project folder so its CSS and JS
  still load. Clicking the project name opens the page too. Project pages are
  served with a sandbox CSP, so their own JavaScript can never reach the app's
  API or read the session token.
- **Launch is no longer hardcoded.** "launch Helix codex app" resolves any real
  project by fuzzy name, inspects what it contains, starts the best entry point,
  and says what it matched and why. Unknown names get the real project list;
  ambiguous names get a choice; projects with no interface say exactly what was
  looked for instead of guessing.
- **Interface detection covers real layouts.** HTML pages are found in
  subfolders (`dashboard/`, `dist/`, `apps/web/`), vendored copies of other
  projects and Jinja `templates/` are excluded, and Streamlit, FastAPI, Flask,
  Django and tkinter/PyQt/pywebview entry points are detected at a bounded
  depth. A missing runtime (e.g. `streamlit` not installed) is reported before
  a window is opened.
- **Real agent tools (`app/tools.py`).** Tommy can now `fetch_url` any public
  page and read its text (SSRF-guarded: localhost/private ranges are refused),
  `list`/`read`/`search`/`create`/`modify` any file inside `cloned_repos`
  (path-confined), assess every project's production readiness from on-disk
  evidence (README, tests, CI, container, healthcheck, env template, build
  commands, git state), and write valid multi-page PDFs with the standard
  library. These routes are deterministic, so "scan my projects", "which project
  is production ready?", "read <url>" and "create a resume PDF" work even when
  the model would otherwise answer "I can't".
- **Tommy is a real coding agent in Cloud mode.** A new `code` plugin exposes
  `audit_repo`, `run_tests`, `run_command` and `edit_file`, backed by
  `app/coder.py` (no shell, workspace-confined, destructive-command deny-list,
  test-runner detection, exact search/replace edits). In Cloud mode Tommy runs a
  bounded multi-step loop: he audits the repo, reads real test output, edits the
  code, runs the tests again, and reports what changed and what still fails —
  a list of file names is never the answer to "fix this". Local and Hybrid modes
  keep the prior single-shot behaviour.
- **Cloud-mode launches self-heal a missing runtime.** When a launch fails
  because a Python module/runtime is not installed, Tommy (Cloud mode only)
  installs the project's requirements into a project-local `.venv` and retries
  the launch — instead of stopping at "install the project requirements first".
  This only runs in Cloud mode and stays off for Local/Hybrid.
- **"Install <project> requirements" is a real command.** A deterministic route
  and a `code` plugin action (`install_requirements`) resolve the project, create
  its `.venv`, install `requirements.txt`/`pyproject`, and — if the request also
  says "and run it" — start the app. It never dumps a directory tree.
- Tasks and notes live in the durable SQLite core. Migration v14 adds
  `pinned`, `display_id` and `recurrence` to tasks and `pinned`/`display_id` to
  notes; existing rows are numbered during the upgrade.
- `AppService` is the single doorway from the UI to the core. Every mutation
  writes one audit record.
- One-time import of the pre-merge `tasks.json` / `notes.json`, including
  pinned flags and frequencies. It runs automatically on first start and is
  idempotent.
- Project panel now uses the core scanner: health score, git branch, dirty
  marker, and a refresh button.
- `📅 Agenda` button and a real calendar: scheduling writes a task with a due
  date, and the agenda reads them back for a day, week or month.
- `SIGMAHELIX_NO_AUDIO=1` disables microphone and speech hardware entirely.
- Single `sigmahelix` command with `gui`, `chat`, `status`, `doctor`, `scan`,
  `backup`, `restore`, `audit` and `db` subcommands.
- `packaging/install.sh` and `packaging/uninstall.sh` for per-user installs,
  with a desktop entry and icon.
- PyInstaller spec for a self-contained desktop binary.
- `packaging/sigmahelix.desktop` and `packaging/sigmahelix.svg`.

### Changed

- API keys are stored in the operating system keyring instead of
  `api_keys.json`. A legacy plaintext file is migrated into the keyring and
  then deleted. With no keyring available, cloud providers stay disabled.
- Cloud providers remain off until a key is added and passes a live probe.
- `SIGMAHELIX_DATA_DIR` now also relocates the database, so one variable moves
  all user state.
- Merged the three previously separate trees (`sigmahelix`, `company-os`,
  `company-os-app`) into one `src`-layout package with a single entry point.
- The desktop app now lives in `src/sigmahelix/app` and imports the package
  relatively instead of relying on a `sys.path` shim.
- Every filesystem location is resolved by `sigmahelix.app.paths`; no absolute
  developer paths remain in the source.
- The assistant persona is `Helix`; the product is `SigmaHelix`.
- Cloud model calls use `urllib` instead of the undeclared `requests`
  dependency.
- Local chat timeout raised to 60 s so the first reply after a restart can wait
  for the model to load.
- CI now tests Python 3.11, 3.12 and 3.13 and builds distributions.

### Fixed

- **Tommy knows its real workspace root.** The system prompt now states the
  absolute path of the projects directory and that absolute paths inside it are
  valid, so it no longer claims it "can't reach" a folder that is inside its own
  workspace. It is also told to resolve project names itself (never ask for a
  path inside the workspace), to treat a localhost/`127.0.0.1` URL as a link and
  never fetch it, to read the code before declaring a task blocked, and never to
  invent policy or capability limits (no "Zone R").
- The Projects view showed 0 and Tommy said "Projects directory not found" when
  run from an installed binary: the projects dir fell back to `~/projects`
  because there was no source checkout sibling. `projects_dir()` now discovers a
  `cloned_repos` folder (under home and mounted volumes) and caches it, so the
  real projects are scanned on every run from either the source checkout or an
  installed binary.
- The web Settings button did nothing because `settings` was missing from the
  UI's `VIEWS` list; clicking it silently fell back to Chat. It now opens the
  Settings view.
- `console.py` read `agent.model`, an attribute that does not exist; it now
  reads `agent.model_name`.
- The model picker read `T.colors["text"]`, a missing theme key that raised
  `KeyError` on open; it now reads `text_main`.
- `agent.py` imported the removed `model_selector` module, so the "best local
  model" selection silently never ran.
- Three unused `_save_*_key` methods referenced attributes that were never
  assigned; removed.
- The calendar was backed by a dictionary nothing ever wrote to; it now reads
  real due dates.
- Test runs no longer hang at exit waiting on a speech-synthesis thread.
- Dead `current_indicator` variable and unused widget handle in the UI.

### Removed

- `apps/desktop/` (the reduced fork, superseded by the merged app).
- `scripts/db_admin.py` (replaced by `sigmahelix backup` / `sigmahelix restore`).
- `requirements.in` and `requirements.lock` (dependencies now live in
  `pyproject.toml`).
- The `VERSION` file (the version is declared once, in `pyproject.toml`).
