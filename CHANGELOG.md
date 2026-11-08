# Changelog

All notable changes to SigmaHelix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
