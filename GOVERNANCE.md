# GOVERNANCE.md — Operating Policy & Repo Map for SigmaHelix-OS

> Companion to `CONSTITUTION.md` (this repository's non-negotiable invariants, which
> this file does not restate) and `AGENTS.md` (the agent charter and command map).
> Read all three before acting. This file may be updated by any agent **as a logged
> governance change** to keep the policy truthful; `CONSTITUTION.md` is owner-only.

## 1. Repository map

The authoritative directory map for this repository is **`REPOMAP.md`**. This section
deliberately does not repeat it: two maps would drift, and the owner's clean-code policy
forbids a second copy of anything. Only the parts a policy reader needs are listed here.

| Path | Purpose (one line) |
|---|---|
| `REPOMAP.md` | The authoritative directory map. Read it instead of this table. |
| `src/sigmahelix/` | The application: `core/` (domain, config, SQLite storage), `app/` (services and the agent), `skills/`, `webui/` (static, loopback-only). |
| `bin/`, `packaging/`, `scripts/` | Entry points, packaging metadata and the CI gate script. |
| `tests/` | The test suite (`./scripts/ci.sh`). |
| `docs/` | Standing documentation: `adr/` (decision records), `architecture/`, `governance/`, `audit/`, `security/`, `execution/`. |
| `.github/` | CI workflow. |

## 2. Documentation policy (what belongs where)

**Root holds only the requested set** — nothing else:

| File | State | Purpose |
|---|---|---|
| `README.md` | required | The single source of truth: what this is, why it's here, how to use it — in simple English for a professional reader. Carries the Helix Solutions logo. |
| `AGENTS.md` | required | Agent charter, command map and the sign-in/out ledger. |
| `CONSTITUTION.md` | required | This repository's non-negotiable invariants (see section 5). |
| `GOVERNANCE.md` | required | This file: documentation policy, sync policy, archiving rules. |
| `REPOMAP.md` | required | The authoritative directory map. It stays at the root because `AGENTS.md` and `CONSTITUTION.md` both require it to be kept in sync with the tree, and living docs link to it. |
| `GLOSSARY.md` | required | The shared vocabulary. It stays at the root because `REPOMAP.md` links to it and `docs/audit/MERGE_BASELINE_2026-11-08.sha256` records its hash, so moving it would invalidate a recorded baseline. |
| `CHANGELOG.md` | standard | Dated user-visible changes. |
| `LICENSE` / `LICENSE.md` | standard | MIT, unless the repo states otherwise. |
| `SECURITY.md` | standard | Threat model, vulnerability reporting, secret handling. |

**Everything else lives in `docs/`** — reports, audit logs, execution plans, research
notes, ADRs, runbooks, anything dated or one-off. No stray `.md`/`.txt` at the root.
If a document at the root is not in the table above, move it to `docs/` (or
`docs/archive/` if it is historical) and record the move in the `AGENTS.md` ledger.

## 3. Synchronization & harmony policy

The owner's rule: **the repository's actual status must match its README at all times,
locally and remotely.**

1. `README.md` is the canonical account. `index.html` and the web UI mirror it; they
   never fork it.
2. When reality changes, update `README.md` **first**, then mirror it to the pages.
3. Every sanctioned change is committed **and pushed** to the default branch, so the
   GitHub copy, the local working copy, and any local platform that reads the repo
   all show the same truth.
4. A number published anywhere (README, page, badge) must be reproducible from this
   repository. A stale figure is removed, not left to rot.

## 4. Archiving rule

- Archive (move to `docs/archive/`), never delete: historical reports, superseded plans,
  dated audits, and one-off execution logs.
- Delete outright only regenerable artifacts: caches, build output, coverage files.
- Record every move in the `AGENTS.md` ledger with date and time.

## 5. Note on CONSTITUTION.md — an unresolved divergence, recorded not hidden

In five repositories in this portfolio (Assay, createlee, Helix-Solutions, Helix-Matrix
and Helix-Codex) `CONSTITUTION.md` is the owner's shared engineering philosophy and
clean-code policy, byte-identical everywhere, and amended only by the owner in every
repo at once.

**In this repository it is not that text.** `CONSTITUTION.md` here is *"SigmaHelix
non-negotiable invariants"* — the load-bearing walls that keep the project local-first,
auditable and safe. It is referenced from `AGENTS.md`, from inside itself, from
`src/sigmahelix/skills/personal/hatem-specific.md`, from `docs/governance/` and from a
recorded SHA-256 baseline, so it is load-bearing and must not be moved or rewritten.

This landing therefore **did not touch it**. Reconciling the two — keeping the invariants
under a name that says so and adopting the shared constitution text, or deliberately
carrying a repo-specific constitution — is the owner's decision. Recorded here so the
next agent does not silently "fix" either half.

## 6. Engineering philosophy & clean-code policy (operational summary)

The owner's operational reminders, enforced here:

- **Fail closed.** Missing input or missing authority is a refusal, never a default.
- **Evidence before claims.** Published numbers carry a command, a date, and an artifact.
- **No duplicates, no temp files, one file one job, every file explains itself.**
- **Secrets never enter the tree.**
- **Simple English** in code, docs, and UI, so a non-technical professional reader
  (recruiter, partner) can follow.
- **One brand mark:** the Helix Solutions logo, everywhere.

## 7. Definition of done

It works; it has a test or a documented manual check; the `AGENTS.md` ledger has an
entry; the docs reflect the new reality; no temporary file was left behind; and every
published number can be re-run to reproduce itself.
