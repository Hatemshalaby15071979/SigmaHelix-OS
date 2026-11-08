# CONSTITUTION — SigmaHelix non-negotiable invariants

These rules are the project's load-bearing walls. They are not style preferences;
they are what keeps SigmaHelix local-first, auditable, and safe. Any change that
violates one must be rejected or amended here first.

## 1. Local-first, always

- All user data lives in **one SQLite file** under the user's home directory.
  There is no account, no sync service, and **no telemetry** of any kind.
- Cloud models are **off by default**. When a user enables one, the API key is
  stored in the **OS keyring**, never in a file this project writes.

## 2. Tommy is the only assistant, and skills are non-negotiable

- The assistant is named **Tommy** in every surface (web, desktop, console).
- The six skills — frontend/webapp engineering, UI & interaction design, DevOps,
  prompt engineering, `i-have-adhd`, and the personal `Hatem_specific` — are
  **composed into the system prompt of every model call**, local Ollama *and*
  cloud. The skill text is not merely stored; it is sent. This is proven by
  `sigmahelix skills verify`, which must pass.
- Tommy always shows its **thinking and token usage**; hiding it is not allowed.

## 3. Migrations are append-only and guarded

- Schema changes are ordered migrations `1..N`, contiguous, each with `up` and
  `down` SQL. **Never edit an existing migration** — add a new one.
- A downgrade that would drop a table still holding records is **refused**
  (atomic pre-flight: a failed downgrade leaves the schema intact).
- Every migration that expands the schema must also extend the backup
  validator's required-tables map.

## 4. Every mutation is auditable

- All writes go through `AppService`, which appends one entry to the
  **append-only, SHA-256 hash-chained audit log**. Bypassing `AppService` to
  touch `repositories` directly is forbidden.
- Backups are online SQLite snapshots with a checksum sidecar manifest; restores
  verify the checksum and refuse tampering.

## 5. The web surface is locked to the machine

- The web UI binds **127.0.0.1 only** and requires a **per-session token**
  embedded in the served page. No cross-origin form posts; no exposure to the
  network. The Tk window remains available via `sigmahelix --desktop` but is not
  the default.

## 6. Launches are confined and shell-free

- Project "Run" links and launcher profiles execute with `shell=False`, an
  allow-listed environment, and a working directory confined to the project root.
  No arbitrary command construction from untrusted input.

## 7. One codebase, no duplicates

- There is exactly one importable package (`src/sigmahelix`) and one test tree
  (`tests/`). Retired trees (`company-os`, `company-os-app`) were archived
  outside this repository and must not reappear here. Build/test outputs
  (`build/`, `dist/`, `.coverage`, caches) are git-ignored and disposable.

## 8. Quality gate is the definition of done

- A change is complete only when `./scripts/ci.sh` is green: ruff format + lint,
  mypy on the source, `compileall`, the full pytest suite, and a CLI smoke test.
- `sigmahelix doctor` must report all checks passed, including the skill count.

## 9. Documentation stays current

- `README.md` and `CHANGELOG.md` are updated with every user-visible change.
- `REPOMAP.md`, `AGENTS.md`, and `CONSTITUTION.md` at the repo root are kept in
  sync with the actual structure and rules. Architecture decisions get an ADR.
