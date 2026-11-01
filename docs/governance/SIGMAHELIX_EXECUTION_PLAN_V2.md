# SigmaHelix — Autonomous Execution Plan v2

**Supersedes:** `SIGMAHELIX_MASTER_PLAN_2026-11-01.md` (v1)
**Reason for v2:** v1 used calendar estimates, treated testing and DevOps as a checklist rather than an engineering discipline, left the model/skill runtime undefined, and had no autonomous execution protocol. v2 removes all time frames, defines gate-based execution, and makes Tommy's runtime the centre of the build.
**Owner:** Hatem Shalaby
**Execution mode:** autonomous, gate-driven, evidence-bound
**Spend cap:** $40/month. v1 requires $0.
**Status:** approved-for-execution plan; gates P0–P2 are safe to start immediately.

---

## 0. What changed from v1, and why

| v1 weakness | v2 correction |
|---|---|
| Calendar estimates ("3–5 days", "~14 weeks") | **No time frames at all.** Progress is measured by gates passed and evidence produced, not elapsed time. |
| Testing was a per-phase bullet list | A full **test engineering programme** (§6) with layers, coverage gates, mutation testing, fault injection, and a rule that no gate closes without its tests. |
| DevOps was "add CI" | A complete **delivery pipeline** (§7): pre-commit, staged CI, reproducible builds, SBOM, signing, release/rollback, backup/restore drills, runbooks, observability. |
| Model choice unexamined (`llama3.2:1b`) | **Verified model ladder** with VRAM math, measured evidence that the 1B model cannot call tools reliably, and a hard GPU-residency guard (§4 of `TOMMY_RUNTIME_SPEC_V2.md`). |
| Skills mentioned as "skill packs" | A real **skill/plugin runtime**: discovery, hash verification, sandboxed probes, tiered injection, hot reload, trust boundary (§5 of the runtime spec). |
| No execution protocol | **Autonomous ledger loop** (§2) with ready-task selection, evidence artifacts, retry limits, and an explicit human-gate list. |
| "Done" was prose | Every gate has **machine-checkable exit criteria** and an evidence path. |
| No failure analysis | §11 risk register plus §9 of the self-evaluation: what would make this plan fail. |

Full self-critique: [`SELF_EVALUATION_AND_PLAN_CRITIQUE.md`](SELF_EVALUATION_AND_PLAN_CRITIQUE.md).

---

## 1. Product definition

**SigmaHelix is a local-first personal operating system and career command centre.** It unifies projects, tasks, alarms, evidence, resume, and external platforms behind one durable desktop surface, operated by a governed agent — **Tommy** — that performs research and complex execution but never makes a consequential decision alone.

### 1.1 Non-negotiable properties

1. **Durable.** Nothing is lost on restart, crash, or power loss.
2. **Truthful.** No claim without evidence; no metric without a source; no capability without a passing test.
3. **Governed.** Every side effect passes a policy engine; every external write needs human approval bound to the exact payload.
4. **Local.** Data and model stay on the machine. No telemetry. No cloud dependency.
5. **GPU-only.** If the model is not 100% on GPU, the agent refuses to run. No silent CPU fallback.
6. **Extensible.** Skills, tools, panels, and integrations are plugins behind stable contracts.
7. **ADHD-friendly.** One next action, visible state, no surprise audio, keyboard-first.

### 1.2 Explicit non-goals for v1

- Multi-tenant SaaS. (Tenant fields exist from day one, but no tenancy claims.)
- Autonomous job applications, posting, messaging, payment, or deployment.
- LinkedIn scraping. (Import + draft only.)
- Mobile app.
- Cloud sync.
- Being a therapist, lawyer, or financial adviser.

### 1.3 Naming

| Item | Value |
|---|---|
| Product | **SigmaHelix** |
| Repo | `sigmahelix` (private, local git first) |
| Agent | **Tommy** |
| Binary | `sigmahelix` (Linux), `SigmaHelix.exe` (Windows, later gate) |
| Legacy names | `company-os`, `company-os-app` — archive only |

---

## 2. Autonomous execution protocol

This is how the plan actually gets executed, with or without a human in the loop for build work.

### 2.1 The ledger is the source of truth

`docs/execution/LEDGER.yaml`:

```yaml
version: 1
project: sigmahelix
gates:
  - id: P0
    name: Truth and safety net
    status: in_progress
    tasks:
      - id: P0-001
        title: Backup workspace to second physical disk with checksum manifest
        status: ready          # ready | in_progress | blocked | done | failed
        depends_on: []
        acceptance:
          - "archive exists on /dev/sda2"
          - "sha256 manifest verifies"
          - "restore of 3 sampled files matches byte-for-byte"
        evidence: docs/execution/evidence/P0-001.md
        risk: R1
      - id: P0-002
        title: Initialize sigmahelix git repository and first commit
        status: blocked
        depends_on: [P0-001]
```

Rules:

- Exactly one task is `in_progress` at a time per workstream.
- A task may only move to `done` when its evidence file exists and contains the command, the output, and a hash.
- Dependencies are enforced by the runner, not by memory.
- Acceptance criteria are immutable during implementation. If they are wrong, that is a **scope change** and requires a human gate.

### 2.2 The loop

```
1. SELECT     first task with status=ready and all deps done
2. RESTATE    acceptance criteria verbatim
3. PLAN       smallest change that satisfies them
4. IMPLEMENT  code + tests together
5. TEST       targeted tests, then the gate's full suite
6. VERIFY     run the acceptance commands; capture output
7. COMMIT     conventional commit referencing the task id
8. RECORD     write evidence file; mark done; unblock dependents
9. NEXT       return to 1
```

### 2.3 Retry and escalation

| Condition | Action |
|---|---|
| Test fails, cause understood | Fix, re-run. |
| Same approach fails twice | Write a short decision note; try a materially different approach. |
| Third failure | Mark `failed`, write the blocker, move to the next ready task, escalate in the daily summary. |
| Flaky test | Quarantine with an issue id; never delete; never `skip` without a reason and an owner. |
| Acceptance criterion cannot be met | Stop. Do not rewrite the criterion. Escalate. |

### 2.4 Prohibited shortcuts

- Marking a task done without an evidence file.
- Weakening or deleting a failing test to make a gate pass.
- Editing acceptance criteria to match the implementation.
- Adding `# type: ignore`, `noqa`, or `skip` without a linked justification.
- Committing secrets, real tenant data, or model files.
- Running an external write during a build task.
- Claiming a capability in docs before its test passes.

### 2.5 Human gates (the only stop conditions)

| Gate | Decision | Why it cannot be automated |
|---|---|---|
| **HG-1** | Scope or product-name change | Owner authority. |
| **HG-2** | Provide credentials / complete OAuth consent | Secrets and legal consent. |
| **HG-3** | Approve an external write (runtime R2) | Consequential side effect. |
| **HG-4** | Approve destructive/irreversible action (R3) | Cannot be undone. |
| **HG-5** | Approve spend | Money. |
| **HG-6** | Approve a release or publish | Reputation and distribution. |
| **HG-7** | Approve career facts/evidence into durable memory | Identity and truth. |
| **HG-8** | Install a third-party skill/plugin | Supply-chain trust. |

Everything else — code, tests, refactors, migrations, docs, benchmarks, packaging, local commits — executes without asking.

### 2.6 Daily autonomous report

Written to `docs/execution/RUNLOG.md` at the end of each work session:

- Tasks completed with evidence links.
- Tasks failed with the blocker.
- Gate status changes.
- Test counts and coverage deltas.
- Decisions made and their assumptions.
- What needs a human, ranked by blocking impact.

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ apps/desktop (CustomTkinter)      apps/cli (REPL, headless) │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
        ┌───────▼─────────────────────────────▼───────┐
        │            application service               │
        │  commands · queries · event bus · sessions   │
        └───┬────────┬─────────┬─────────┬────────────┘
            │        │         │         │
   ┌────────▼──┐ ┌───▼────┐ ┌──▼─────┐ ┌─▼──────────────┐
   │ projects  │ │ career │ │ resume │ │ scheduler      │
   │ registry  │ │ engine │ │ engine │ │ alarms · cron  │
   └────────┬──┘ └───┬────┘ └──┬─────┘ └─┬──────────────┘
            │        │         │         │
        ┌───▼────────▼─────────▼─────────▼────┐
        │            core                     │
        │ models · sqlite · migrations ·      │
        │ config · logging · audit chain      │
        └───────────────────┬─────────────────┘
                            │
        ┌───────────────────▼─────────────────┐
        │        agent runtime (Tommy)        │
        │ observe→clarify→plan→approve→act→   │
        │ verify→report→record                │
        └───┬──────────┬──────────┬───────────┘
            │          │          │
     ┌──────▼───┐ ┌────▼─────┐ ┌──▼──────────────┐
     │ policy   │ │ tool     │ │ model gateway   │
     │ engine   │ │ registry │ │ GPU guard       │
     └──────┬───┘ └────┬─────┘ └──┬──────────────┘
            │          │          │
     ┌──────▼──────────▼───┐ ┌────▼──────────────┐
     │ approval queue      │ │ skill runtime     │
     │ audit log           │ │ probe·inject·swap │
     └─────────────────────┘ └───────────────────┘
```

### 3.1 Package boundaries

| Package | Owns | Must not |
|---|---|---|
| `core` | models, DB, migrations, config, logging, audit | import agent, integrations, or UI |
| `scheduler` | recurrence, alarms, notifications, missed runs | perform external writes |
| `projects` | scan, registry, health, launch profiles | execute arbitrary commands without a profile |
| `agent` | runtime, policy, tools, memory, prompts | talk to a database directly |
| `career` | profile, evidence graph, plans, reviews | write to the resume |
| `resume` | templates, tailoring, renderers | invent evidence |
| `integrations/*` | adapters, auth, retries, contract tests | bypass the policy engine |
| `apps/*` | presentation only | contain business logic |

Dependency rule: dependencies point inward. `core` depends on nothing. A violation fails a test (`import-linter`).

### 3.2 Storage

- SQLite, WAL mode, `synchronous=NORMAL`, foreign keys on.
- `~/.local/share/sigmahelix/sigmahelix.db`.
- Versioned migrations with forward and rollback scripts.
- FTS5 for notes, evidence, and skill retrieval.
- No ORM. Typed repositories over `sqlite3`.
- Every table carries `created_at`, `updated_at`, and where relevant `tenant_id` (default `local`).

### 3.3 Event bus

In-process, synchronous by default, persisted when the event is durable.

```
task.created · task.completed · task.missed
project.scanned · project.changed · project.launch_failed
alarm.due · alarm.acknowledged · alarm.missed
career.evidence.proposed · career.plan.approved
resume.generated · resume.approved
approval.requested · approval.granted · approval.rejected · approval.expired
agent.run.started · agent.run.finished · agent.run.failed
skill.loaded · skill.quarantined · skill.reloaded
```

Subscribers: UI refresh, scheduler, audit log, n8n emitter.

---

## 4. Work breakdown — gates, not weeks

Each gate has: **purpose**, **tasks**, **exit criteria**, **test evidence required**. No gate may close on prose.

---

### P0 — Truth and safety net

**Purpose:** make the work recoverable and the record honest before any refactor.

| ID | Task | Acceptance |
|---|---|---|
| P0-001 | Backup `Career/` to `/dev/sda2` (separate physical disk) | Archive + SHA-256 manifest; 3-file restore is byte-identical |
| P0-002 | `git init` `sigmahelix/`; `.gitignore`; first commit | `git log` has the baseline; no secrets, no models, no venvs |
| P0-003 | Import governance → `docs/governance/`; app → `apps/desktop/` | Tests pass in the new tree |
| P0-004 | Rename product to SigmaHelix everywhere user-visible | `sigmahelix --version`; window title; spec; README |
| P0-005 | Correction notice for `stage-2/FINAL_REPORT.md` | Notice file exists; original unedited; index links both |
| P0-006 | Remove or repair stray root `.github/` and `.env.example` | No CI references a missing path |
| P0-007 | Threat model v1 for SigmaHelix | STRIDE table + data-flow diagram + 10 abuse cases |
| P0-008 | CI skeleton: lint, type, unit | Green on the baseline commit |
| P0-009 | `docs/execution/LEDGER.yaml` + runner script | Runner selects the correct next task |
| P0-010 | Dependency pinning + hash lockfile | `pip install --require-hashes` succeeds in a clean venv |

**Exit:** recoverable workspace, honest record, green baseline CI, executable ledger.
**Evidence:** archive manifest, `git log`, CI run log, ledger runner test.

---

### P1 — Durable core

**Purpose:** replace in-memory state with a typed, migrated, auditable store.

| ID | Task | Acceptance |
|---|---|---|
| P1-001 | Domain models (task, note, project, event, approval, evidence) | Schema validation tests |
| P1-002 | SQLite connection, WAL, pragmas, repositories | CRUD round-trip; concurrent read test |
| P1-003 | Migration runner v0→v1 with rollback | Forward + rollback tests |
| P1-004 | Config layer (YAML + env + keyring) | No hardcoded paths; precedence tests |
| P1-005 | Structured logging + redaction | Secret-pattern test yields zero leaks |
| P1-006 | Hash-chained audit log | 1,000-event chain verifies; tamper detected |
| P1-007 | Event bus + persistence | Publish/subscribe; replay test |
| P1-008 | Backup/export/restore commands | Round-trip byte-identical |
| P1-009 | Crash-safety test (kill -9 during write) | WAL recovery; no corruption |
| P1-010 | Import legacy in-memory session (if any) | Idempotent importer test |

**Exit:** restart preserves 100% of state; audit chain verifies; restore works.
**Evidence:** migration test log, chain verification log, crash-recovery log.

---

### P2 — Time and projects

**Purpose:** alarms that actually fire, and a project library that stays current without a restart.

| ID | Task | Acceptance |
|---|---|---|
| P2-001 | Recurrence engine (daily/weekly/monthly, weekdays, every-N) | Property tests over 10k generated rules |
| P2-002 | Occurrence materialisation + completion semantics | Completing one occurrence does not kill the series |
| P2-003 | Scheduler with persisted jobs + fake clock | Fires ±2 s in test; no duplicates |
| P2-004 | Missed-run recovery on startup | Missed alarms surfaced, never silently dropped |
| P2-005 | Notifications (DBus/notify-send) + in-app fallback | Delivery test; no automatic TTS |
| P2-006 | Snooze / dismiss / reschedule | State machine tests |
| P2-007 | Project scanner: git state, manifests, entrypoints, health | 12 repos in < 2 s |
| P2-008 | Watch mode + debounce + rescan | New repo detected < 5 s |
| P2-009 | Launcher profiles + command preview + run history | Unknown command never auto-runs |
| P2-010 | Windows-only artifact labelling | `.exe` marked unsupported on Linux |
| P2-011 | Project health score + "new since last scan" | Deterministic score tests |

**Exit:** alarms fire and survive restart; a new repo appears without restart; every launcher either works or states precisely why not.
**Evidence:** scheduler trace, watch-mode log, launcher run records.

---

### P3 — Model gateway and skill runtime

**Purpose:** give Tommy a body that is fast, GPU-bound, and equipped with verified skills at every launch.

| ID | Task | Acceptance |
|---|---|---|
| P3-001 | Model gateway (Ollama client, retries, timeouts, streaming) | Contract tests against a fake server |
| P3-002 | GPU residency guard | Refuses to run at < 100% GPU; auto-shrinks context; hard fail if still split |
| P3-003 | Model ladder + routing policy | Router/standard/deep selection tests |
| P3-004 | Context assembler with token budget | Budget never exceeded; prefix stable across turns |
| P3-005 | Skill manifest schema + validator | 15 invalid manifests rejected with precise errors |
| P3-006 | Skill loader: discover, hash-verify, probe, register | Corrupt hash → quarantine; probe timeout → quarantine |
| P3-007 | Tiered injection (index → body → references) | Token accounting test; only selected skills injected |
| P3-008 | Sandboxed probe runner (subprocess, no network, timeout) | Escape attempt fails; network attempt fails |
| P3-009 | Hot reload with atomic swap at step boundary | No mid-run swap; reload test |
| P3-010 | Trust model: local-signed vs quarantined third-party | Unsigned skill cannot enter system prompt |
| P3-011 | Prompt-prefix cache optimisation | ≥ 60% cached prompt tokens on repeat turns |
| P3-012 | Benchmark harness (latency, tokens/s, VRAM) | Baselines recorded; > 20% regression fails |

**Exit:** app launch probes every skill, loads only healthy ones, pins the model at 100% GPU, and injects the right context within budget.
**Evidence:** GPU residency log, probe report, token-budget trace, benchmark table.

---

### P4 — Tommy's brain

**Purpose:** the governed agent — policy, approvals, tools, memory, career coaching.

| ID | Task | Acceptance |
|---|---|---|
| P4-000 | **Evaluation harness**: 30 fixed career scenarios + rubric (evidence use, specificity, actionability, honesty, zero fabrication) | Harness runs offline; baseline scores recorded for both 9B models; re-runnable on every prompt/skill change |
| P4-001 | Tool contract + registry (risk, schema, undo, timeout) | 100% of tools have all fields |
| P4-002 | Policy engine: deny-by-default, risk classes, allowlists | R2/R3 blocked without approval in 100% of tests |
| P4-003 | Approval queue: payload hash, TTL, single-use | Replay, expiry, tamper all rejected |
| P4-004 | Runtime loop with step budget + kill switch | Kill stops within one step |
| P4-005 | Memory layers (working/episodic/semantic/evidence) | Semantic write requires confirmation |
| P4-006 | Context retrieval (FTS5) + relevance ranking | Top-k relevance test on a labelled set |
| P4-007 | Career intake workflow | Profile persisted; gaps produced |
| P4-008 | Evidence graph + Evidence Inbox | No evidence auto-merged |
| P4-009 | Gap analysis with cited requirements | Every requirement has a source |
| P4-010 | 90-day plan generator + task linkage | Plan approval creates linked tasks |
| P4-011 | Daily brief / weekly review / monthly review jobs | Run on schedule; outputs stored; no duplicates |
| P4-012 | "Never guess" validator | Missing evidence → ask/unknown, never fabricate |
| P4-013 | Prompt-injection defence + untrusted tagging | 40-payload suite: zero unauthorised tool calls |
| P4-014 | Interview prep + STAR story bank from evidence | Every story links to evidence |
| P4-015 | Application tracker + follow-up tasks | Stage transitions tested |

**Exit:** Tommy coaches, plans, and executes R0/R1; every R2+ waits for a human; every claim is traceable.
**Evidence:** policy test report, approval bypass report, injection suite report, career workflow traces.

---

### P5 — Resume engine

**Purpose:** a resume that updates itself from evidence, and refuses to lie.

| ID | Task | Acceptance |
|---|---|---|
| P5-001 | Resume data model + versioning | Old versions immutable |
| P5-002 | Evidence-to-bullet pipeline | Bullet without evidence is rejected at render |
| P5-003 | `[quantify]` placeholder rule | Fabricated-metric suite: zero passes |
| P5-004 | ATS-safe template + modern template | Snapshot tests |
| P5-005 | Markdown → HTML → PDF (WeasyPrint) | PDF renders; text extractable |
| P5-006 | DOCX renderer (python-docx) | Opens in LibreOffice; styles correct |
| P5-007 | Job-description parser + keyword coverage | Coverage score reproducible |
| P5-008 | Tailoring diff + approval | Diff shown; unapproved diff cannot export |
| P5-009 | Evidence snapshot stored with each version | Version → evidence ids resolvable |
| P5-010 | Auto-update proposals on new project/commit | Proposal only; never silent |

**Exit:** a tailored, ATS-safe resume in minutes; 100% bullet traceability; zero fabricated metrics.
**Evidence:** rendered PDFs/DOCX, traceability report, anti-fabrication test log.

---

### P6 — Integrations

**Purpose:** connect the outside world without giving up control.

Order is deliberate: read before write, local before remote, simple before complex.

| ID | Task | Acceptance |
|---|---|---|
| P6-001 | Secret store (keyring) + rotation procedure | No secret in DB/log/prompt; rotation drill |
| P6-002 | HTTP client with retries, backoff, circuit breaker, timeouts | Fault-injection tests |
| P6-003 | GitHub read sync (repos, commits, languages, README, Actions) | 12 repos mapped or explicitly unmapped |
| P6-004 | GitHub mapping UI for unmapped repos | User resolves; no guessing |
| P6-005 | n8n outbound webhook (signed) | Signature verified by receiver fixture |
| P6-006 | n8n inbound receiver (loopback + shared secret) | Replay rejected |
| P6-007 | LinkedIn data-export importer | Parser tests; no scraping code |
| P6-008 | LinkedIn draft workflow (clipboard only) | No auto-post path exists |
| P6-009 | Salesforce OAuth + read sync | Recorded-fixture contract tests |
| P6-010 | Salesforce write behind approval | Approval + audit entry |
| P6-011 | Zendesk token + read sync | Contract tests |
| P6-012 | Zendesk comment/update behind approval | Approval + audit entry |
| P6-013 | Integration health dashboard | Status per connector |
| P6-014 | Egress log + domain allowlist | Unapproved host blocked |

**Exit:** real data flows in; every write is approved, diffed, and audited; no credential leaks.
**Evidence:** contract-test reports, approval traces, egress log, secret scan.

---

### P7 — Hardening and release

**Purpose:** make it installable, observable, recoverable, and extensible.

| ID | Task | Acceptance |
|---|---|---|
| P7-001 | Plugin API + permissions + loader | Third-party plugin loads without core edit |
| P7-002 | Skill packs shipped (`career-coach`, `project-steward`, `resume-smith`) | Install/enable/disable tested |
| P7-003 | Full security review (SAST, deps, secrets, injection, sandbox) | Zero P0/P1 findings |
| P7-004 | Performance budget + soak test (30 min) | Targets met; no leak |
| P7-005 | Accessibility audit (keyboard, contrast, screen reader) | WCAG 2.2 AA on core flows |
| P7-006 | Packaging: AppImage + deb | Clean install on a second Linux machine |
| P7-007 | Windows build path documented + CI matrix stub | Documented, not claimed working |
| P7-008 | Backup/restore/DR drill | RPO/RTO met; restored DB verifies |
| P7-009 | Runbooks (install, upgrade, rollback, key rotation, model update, incident) | Each runbook executed once |
| P7-010 | SBOM + checksums + signed release | `cosign verify` passes |
| P7-011 | Release notes + changelog | Generated from commits; reviewed |
| P7-012 | v1.0 gate review | All prior gates closed with evidence |

**Exit:** a signed, installable, documented, recoverable v1.0.
**Evidence:** SBOM, signature verification, install log, DR drill log, accessibility report.

---

## 5. Cross-cutting engineering standards

### 5.1 Code

- Python 3.12, `pyproject.toml`, `src/` layout per package.
- Type hints everywhere; `mypy --strict` on `core`, `agent`, `career`, `resume`; `--strict` optional elsewhere.
- `ruff` for lint + format; line length 100.
- No global mutable state. Dependencies injected.
- Pure functions where possible; side effects at the edges.
- Every public function has a docstring stating contract and failure modes.
- Errors are typed; no bare `except`.
- No `print` in library code; structured logging only.
- Time is injected (`Clock` protocol) so tests are deterministic.

### 5.2 Git

- Trunk-based; short-lived branches.
- Conventional commits: `feat(agent): ...`, `fix(scheduler): ...`, `test(policy): ...`.
- Every commit references a task id.
- No commit without passing pre-commit.
- Tags: `vMAJOR.MINOR.PATCH`.
- `CHANGELOG.md` generated, then edited for meaning.

### 5.3 Dependencies

- Pinned exact versions in a lockfile with hashes.
- `pip-audit` and `safety` on every CI run.
- No dependency without a stated reason in `docs/decisions/`.
- Prefer stdlib. Current deliberate additions: `customtkinter`, `APScheduler` (or in-house), `python-dateutil`, `keyring`, `watchdog`, `weasyprint`, `python-docx`, `httpx`, `pydantic` (optional), `hypothesis` (dev), `pytest`, `ruff`, `mypy`, `bandit`, `semgrep`, `pip-audit`, `gitleaks`.
- Vendoring is forbidden unless licensed and recorded.

### 5.4 Documentation

- ADR per irreversible decision in `docs/decisions/NNNN-title.md`.
- Every module has a README stating role, boundary, owner, and failure modes.
- Every gate writes evidence, not narrative.
- Docs are tested: links resolve, code blocks parse, claims reference evidence.

---

## 6. Test engineering programme

The rule: **a gate does not close because the code works on the happy path. It closes because the failure paths are tested too.**

### 6.1 Layers

| Layer | Scope | Tooling | Gate |
|---|---|---|---|
| **L1 Unit** | pure functions, policy, recurrence, validation, redaction | pytest | every commit |
| **L2 Property** | invariants over generated inputs | Hypothesis | every commit |
| **L3 Contract** | adapter ↔ external API schema | pytest + recorded fixtures + JSON Schema | every commit (offline) |
| **L4 Integration** | DB + repo + service + event bus | pytest + temp SQLite | every commit |
| **L5 End-to-end** | real user journeys through the app service | pytest + headless GUI (xvfb) | every PR / gate |
| **L6 Security** | injection, approval bypass, secrets, sandbox | pytest + custom corpus + bandit/semgrep/gitleaks | every PR / gate |
| **L7 Performance** | latency, throughput, memory, VRAM | pytest-benchmark + custom harness | every gate |
| **L8 Reliability** | crash, kill -9, disk full, clock jump, network partition | fault-injection harness | every gate |
| **L9 Migration** | schema forward + rollback | pytest + fixture DBs | every migration |
| **L10 Packaging** | install, launch, upgrade, uninstall | clean VM/container | every release |
| **L11 Accessibility** | keyboard, contrast, screen reader | axe-core (if web), manual checklist, contrast script | every release |
| **L12 Model/runtime** | GPU residency, context budget, tool-call validity | custom harness | every model/skill change |

### 6.2 Coverage and quality gates

| Target | Threshold |
|---|---|
| Line coverage, `core` + `agent` + `career` + `resume` | ≥ 85% |
| Branch coverage, same | ≥ 75% |
| Coverage, `policy.py`, `approvals.py`, `evidence.py` | **100%** |
| Mutation score (mutmut) on policy + evidence | ≥ 70% killed |
| Flaky tests | 0 tolerated; quarantine with issue id |
| Test runtime (L1–L4) | < 3 minutes |
| Test runtime (full, offline) | < 15 minutes |
| Determinism | same seed → same result; no network in L1–L4 |

### 6.3 Required test suites (explicit)

**Policy and approval**
- R0 auto-runs; R1 auto-runs with undo; R2 blocks; R3 blocks with typed confirmation.
- Approval bound to payload hash; changed payload invalidates.
- Expired approval rejected.
- Replayed approval rejected.
- Approval for tool A cannot execute tool B.
- Concurrent approval race → single execution.
- Kill switch checked between steps.
- Deny-by-default for unknown tools.

**Evidence and anti-fabrication**
- Bullet without evidence → render error.
- Metric not in evidence → rejected.
- `[quantify]` placeholder preserved, never replaced by a guess.
- "I worked at X" with no record → "no record" response.
- Contradictory evidence → surfaced, not silently resolved.
- Evidence deletion blocked if referenced by a resume version.

**Scheduler**
- Daily/weekly/monthly across DST boundaries.
- Leap day, month-end, 31st in a 30-day month.
- Missed run on startup.
- Snooze does not duplicate.
- Clock jump backwards/forwards.
- Concurrent scheduler instances → single owner (lock).

**Project scanner**
- Symlink loops do not hang.
- Permission-denied directory does not crash.
- Huge repo does not block UI (timeout).
- Non-git directory handled.
- Detached HEAD, no commits, corrupt `.git`.
- Path traversal via crafted manifest rejected.
- New repo detected within 5 s.
- Deleted repo removed from registry.

**Skill runtime**
- Invalid manifest rejected with field-level error.
- Hash mismatch → quarantine.
- Probe timeout → quarantine.
- Probe network attempt → blocked.
- Probe writes outside temp dir → blocked.
- Skill requesting a tool above its risk ceiling → rejected.
- Hot reload swaps atomically at step boundary.
- Unsigned third-party skill cannot inject into system prompt.
- Token budget exceeded → skill body truncated or dropped, never system prompt.
- Skill index always fits its budget.

**Model gateway / GPU**
- Ollama down → typed error, no partial write.
- Model missing → actionable message.
- GPU split detected → auto-shrink context; if still split → refuse.
- CPU fallback never silently used.
- Timeout → cancel, no orphan request.
- Streaming interrupted → consistent state.
- Malformed tool call → repair or reject, never execute garbage.
- Context overflow → summarise or reject, never truncate mid-instruction.

**Integrations**
- 401/403/429/500 handling.
- Retry with backoff; no retry on 4xx except 429.
- Circuit breaker opens and recovers.
- Webhook signature invalid → reject.
- Replay of inbound webhook → reject.
- Token refresh failure → degrade to read-only + notify.
- Domain allowlist blocks unapproved host.
- No secret in request logs.

**Data**
- Backup/restore round-trip.
- Migration forward + rollback.
- Kill -9 during write.
- Disk full during write.
- Corrupt DB detected on startup with recovery path.
- FTS index rebuild.
- Retention policy deletes only what it should.

**UI**
- Keyboard-only journey: open → create task → complete → quit.
- Focus order and visible focus ring.
- Contrast ≥ 4.5:1 for body text.
- No audio without explicit action.
- Long text does not break layout.
- Screen-reader labels on all controls.
- Reduced-motion setting respected.

### 6.4 Test data

- Synthetic only. `External tenant data/` fixtures are read-only.
- No real PII in fixtures.
- Factories for every model.
- Golden files reviewed like code.
- Faker seeded for reproducibility.

### 6.5 Fault injection harness

`tests/chaos/` with a controllable fake:

| Fault | Injection point |
|---|---|
| Ollama unavailable | gateway transport |
| Slow model | delay injection |
| GPU split | fake `/api/ps` |
| DB locked | SQLite busy handler |
| Disk full | fake filesystem |
| Clock jump | injected clock |
| Network partition | httpx transport |
| Webhook replay | fixture replay |
| Process kill | subprocess kill |
| Corrupt config | malformed YAML |

Every fault must produce: a typed error, no partial write, a user-visible explanation, and an audit entry.

---

## 7. DevOps and delivery

### 7.1 Local pre-commit (fast, < 10 s)

```
ruff format --check
ruff check
mypy (changed packages)
gitleaks protect --staged
check-yaml / check-json / check-toml
trailing-whitespace / end-of-file-fixer
no-commit-to-branch main (except merge)
pytest -m "not slow" (changed modules)
```

### 7.2 CI pipeline (staged, fail-fast)

| Stage | Jobs | Fails the build |
|---|---|---|
| 1 Static | ruff, mypy, import-linter, yamllint | yes |
| 2 Unit | pytest L1–L2, coverage gate | yes |
| 3 Integration | L3–L4 with temp DB | yes |
| 4 Security | bandit, semgrep, pip-audit, gitleaks, secret scan | yes |
| 5 E2E | headless GUI + CLI journeys | yes |
| 6 Chaos | L8 fault injection | yes |
| 7 Performance | benchmarks vs baseline | > 20% regression |
| 8 Package | wheel, AppImage/deb, SBOM | yes |
| 9 Smoke | install artifact in clean container, run `--version`, `--selftest` | yes |
| 10 Sign & publish | cosign sign, checksums, release notes | manual gate HG-6 |

Rules:
- No `|| true` on a test step.
- Live integration tests never run in CI; contract tests with fixtures do.
- Artifacts retained with the commit SHA.
- Builds are reproducible: pinned toolchain, `SOURCE_DATE_EPOCH`, no network at build after dependency fetch.

### 7.3 Versioning and release

- SemVer. Breaking schema change → major.
- Every release: tag, changelog, SBOM, checksums, signature, install test, rollback test.
- Rollback: previous AppImage + DB downgrade path or restore from pre-upgrade backup. A release without a tested rollback is not a release.

### 7.4 Observability (local only)

- Structured JSON logs, rotating, 7-day retention default.
- `agent_runs`, `tool_calls`, `approvals` tables are the operational record.
- `/health` for the app service: DB, scheduler, model gateway, skill registry, integrations.
- Self-diagnostic command: `sigmahelix doctor` prints versions, GPU status, DB integrity, skill health, integration health.
- No telemetry, ever.

### 7.5 Backup and disaster recovery

| Item | Policy |
|---|---|
| Frequency | Daily automatic local snapshot; weekly to second physical disk |
| Retention | 7 daily, 4 weekly, 3 monthly |
| Encryption | age/GPG for off-disk copies |
| Verification | SHA-256 manifest + monthly restore drill |
| RPO | ≤ 24 h |
| RTO | ≤ 1 h on the same machine |
| Drill | Restore into a temp dir, run `sigmahelix doctor`, compare row counts |

### 7.6 Runbooks (each executed at least once before v1.0)

- Install / first run
- Upgrade / rollback
- Model update / rollback
- Skill install / quarantine / removal
- Key rotation (GitHub, n8n, Salesforce, Zendesk)
- Database corruption recovery
- Disk full recovery
- GPU not detected
- Ollama down
- Incident response and kill switch

---

## 8. Security architecture

### 8.1 Threat model summary

| Threat | Control |
|---|---|
| Prompt injection via repo/README/ticket/JD | `<untrusted>` tagging, instruction hierarchy, no tool execution from content, 40-payload suite |
| Tool abuse by model | deny-by-default policy, risk classes, approval binding, allowlists |
| Secret leakage | OS keyring, redaction, log scrubbing, gitleaks in CI |
| Data exfiltration | domain allowlist, egress log, approval card shows target |
| Approval bypass | payload hash, TTL, single-use, audit |
| Supply chain (skills/deps) | hash-pinned, signed, sandboxed probes, pip-audit, SBOM |
| Local compromise | OS permissions, optional DB encryption, no world-readable files |
| Model error | schema validation, evidence policy, verification step, low-temperature extraction |
| Runaway cost | step budget, token budget, circuit breaker, kill switch |
| Destructive action | R3 typed confirmation + backup reminder |

### 8.2 Secrets

- Stored only in the OS keyring (`secretstorage`/libsecret).
- Never in SQLite, YAML, logs, prompts, crash dumps, or Git.
- Redaction runs on every log record and every prompt assembly.
- Rotation documented and drilled.
- A `sigmahelix doctor --secrets` check verifies no plaintext token exists in the data dir.

### 8.3 Sandboxing

- Skill probes run in a subprocess with: temp HOME, no network, CPU/time/memory limits, cwd inside the skill dir.
- Launch profiles are explicit; unknown commands are R2.
- No `shell=True` anywhere.
- Path arguments resolved and confined to allowed roots.

### 8.4 Audit

- Append-only, hash-chained.
- Every agent run, tool call, approval, and external request recorded.
- Chain verified on startup; failure is a visible incident, not a warning.
- Export redacted for review.

---

## 9. Data and privacy

| Class | Examples | Storage | Egress |
|---|---|---|---|
| **S0 Public** | repo names, public READMEs | local | allowed |
| **S1 Personal** | tasks, notes, career goals | local DB | never without approval |
| **S2 Sensitive** | resume, salary, applications, health-adjacent notes | local DB, optional encryption | explicit approval only |
| **S3 Secret** | tokens, keys, passwords | keyring only | never |

- Retention: configurable per class; default keep forever for evidence, 90 days for logs.
- Deletion: soft delete + purge job; evidence referenced by a resume cannot be hard-deleted without breaking the link explicitly.
- Export: user-owned, one command, machine-readable.
- No analytics, no crash reporting to a server.

---

## 10. Acceptance criteria (product level)

| Area | Criterion |
|---|---|
| Durability | Restart, kill -9, and power-loss simulation preserve committed state |
| Alarms | Fire within ±2 s in test; missed alarms surfaced; no duplicates |
| Project scan | 12 repos < 2 s; new repo < 5 s in watch mode; 100 repos < 8 s |
| Launchers | Every profile launches or states a precise unsupported reason |
| GPU | 100% GPU residency asserted before every agent run; zero CPU fallback |
| Context | Token budget never exceeded; prompt-prefix cache hit ≥ 60% on repeats |
| Skills | Every shipped skill passes its probes at startup; unhealthy skills quarantined and visible |
| Agent safety | 100% of R2/R3 test actions blocked without approval |
| Audit | 1,000-event chain verifies; tamper detected |
| Truth | 100% of resume bullets trace to evidence; 0 fabricated metrics in the adversarial suite |
| Injection | 0 unauthorised tool calls across 40 payloads |
| Career cadence | Daily/weekly/monthly jobs run on schedule for 7 simulated days without duplication |
| Integrations | Offline contract tests pass; live calls gated by credentials; every write approved |
| Privacy | 0 secrets in logs/prompts/Git; `sigmahelix doctor --secrets` clean |
| Packaging | Clean install on a second Linux machine; signed artifact; tested rollback |
| Accessibility | WCAG 2.2 AA on the core journey |

---

## 11. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope creep | High | High | Gate discipline; ledger; HG-1 for scope changes |
| No real backup until P0-001 | Certain today | Catastrophic | P0-001 is the first task, before any code |
| 12 GB VRAM too small for 9B + long context | Medium | High | Context ladder + KV quantisation + measured residency; fallback to shorter context, never CPU and never a silent quality drop |
| Local model unreliable at tool calling | High | High | Constrained JSON schema, repair pass, deterministic tools, small model only for routing |
| Prompt injection via project content | High | High | Untrusted tagging, no instruction execution, test corpus |
| LinkedIn API unavailable | Certain | Medium | Import + draft only; no scraping |
| Salesforce/Zendesk org access delayed | Medium | Medium | n8n path; adapters built against fixtures |
| Dirty Helix-Prime/CompliProof work lost | Medium | High | Back up before migration; commit/stash with reasons |
| Single-user design blocks selling | Medium | Medium | `tenant_id` from day one; no multi-tenant claims |
| Skill system becomes an injection vector | Medium | High | Hash-pinned, signed, sandboxed, risk-ceilinged, human-approved third-party installs |
| Test suite becomes slow and ignored | Medium | High | < 3 min fast suite; slow suite gated; flake quarantine |
| Over-engineering before value | Medium | High | P0–P2 deliver a usable app before Tommy's full brain |
| Windows packaging surprises | Medium | Medium | Linux first; Windows documented, not claimed |

---

## 12. What I need from you (the real blockers)

Only these, and only when the gate reaches them:

1. **HG-2 credentials** — GitHub PAT (read-only first), n8n URL/key, Salesforce connected app, Zendesk subdomain/token, LinkedIn data export. Not needed until P6.
2. **HG-7 career facts** — target roles, constraints, salary floor, timeline, and confirmation of evidence. Needed at P4-007.
3. **HG-6 release approval** — before any artifact is published.
4. **A decision on the primary model** once the benchmark lands (see `TOMMY_RUNTIME_SPEC_V2.md` §3). I will bring measured numbers, not opinions.

Everything else in P0–P3 executes autonomously.

---

## 13. Definition of done for the whole plan

SigmaHelix v1.0 is done when, on a clean Linux machine:

1. `sigmahelix` installs and launches.
2. `sigmahelix doctor` reports: DB OK, scheduler OK, model 100% GPU, all skills healthy, integrations configured or explicitly unconfigured.
3. A task created today survives restart, fires its alarm, and appears in the calendar.
4. A new repository is detected without restart and appears with real git status.
5. Tommy produces a morning brief, a weekly review, and a resume draft whose every bullet traces to evidence.
6. An R2 action is blocked, approved with a diff, executed, and audited.
7. The audit chain verifies after 1,000 events.
8. Backup restores byte-identically; rollback to the previous version works.
9. The 40-payload injection suite makes zero unauthorised tool calls.
10. No secret exists outside the keyring.

Until all ten are true, the product is described by what it does, not by what it is called.
