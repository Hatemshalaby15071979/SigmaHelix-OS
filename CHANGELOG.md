# Changelog

All notable changes to SigmaHelix are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Tasks and notes now live in the durable SQLite core. Migration v14 adds
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
