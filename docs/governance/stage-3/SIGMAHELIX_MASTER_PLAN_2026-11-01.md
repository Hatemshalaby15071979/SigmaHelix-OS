# SigmaHelix — Master Expansion Plan — 2026-11-01

**Owner:** Hatem Shalaby
**Working name:** **SigmaHelix** (replaces "Company OS")
**Current base:** `company-os-app/` prototype + `company-os/` governance
**Planning horizon:** 12–14 part-time weeks; ~45–60 focused build days
**Spend cap:** $40/month (unchanged); local-first, no paid SaaS required for v1
**Status:** proposed plan, not an approved commitment

---

## 1. Product definition

**SigmaHelix is a local-first personal operating system and career command center.** It connects the user's projects, tasks, calendar, evidence, and external platforms into one durable desktop surface, with a governed AI agent ("Tommy") that does the searching and complex execution work but **never makes consequential decisions alone**.

### What it is

- A **durable desktop app** (Linux first, Windows later) with a dashboard, task/calendar system, project registry, launcher, resume studio, and career cockpit.
- A **project nervous system**: scans repositories, reads Git state, detects runnable apps, tracks health, and updates the library without a restart.
- A **career engine**: evidence graph → 90-day plan → daily/weekly tasks → tailored resume → application tracker.
- A **governed agent runtime**: typed tools, risk classes, approval queue, audit log, prompt-injection defenses.
- An **integration hub**: GitHub, n8n, LinkedIn (import/draft), Salesforce, Zendesk, calendar.
- **Extensible by design**: skills, tools, panels, and integration adapters are plugins, not core edits.

### What it is not

- Not a multi-tenant SaaS (v1 is single-user).
- Not an autonomous decision-maker; it does not apply to jobs, send messages, post, pay, delete, or deploy without explicit approval.
- Not a cloud service; it runs locally and stores data locally.
- Not a replacement for Helix-Prime/CompliProof/LSA; it is the cockpit above them.

### Naming

| Item | Decision |
|---|---|
| Product name | **SigmaHelix** |
| Repo | `sigmahelix` (private monorepo) |
| App binary | `sigmahelix` (Linux), `SigmaHelix.exe` (Windows later) |
| Agent persona | **Tommy** |
| Old names | "Company OS", `company-os`, `company-os-app` — retained only in archive/history |

---

## 2. Design principles (derived from the workspace constitution)

1. **Truth before polish.** Every capability has a test and an evidence path. A document claim without a command/artifact is not a claim.
2. **Identity before implementation.** Every module has a role, boundary, owner, and authority.
3. **Human authority over decisions.** The agent may search, analyze, draft, and prepare; the human approves consequential actions.
4. **Fail closed.** Unknown integration, missing credential, ambiguous target, or low confidence → stop and ask.
5. **Never guess.** Missing evidence is labeled unknown; the agent asks rather than fabricates.
6. **Local-first and private.** Data stays on the machine; secrets in the OS keyring; no telemetry.
7. **Reversible by default.** Every write has an undo path or a versioned record.
8. **One source of truth.** SQLite is canonical; exports are projections.
9. **Composable, not monolithic.** Tools, skills, panels, and adapters plug into stable interfaces.
10. **ADHD-friendly.** One clear next action, visible state, low clutter, no surprise sounds.

---

## 3. Target architecture

```
sigmahelix/
├── apps/
│   ├── desktop/                 # CustomTkinter shell (kept from prototype)
│   │   ├── app.py               # window, navigation, theme
│   │   ├── views/               # dashboard, tasks, projects, career, resume, settings
│   │   └── widgets/             # approval card, project card, task row, chat
│   └── cli/                     # headless REPL + automation entrypoints
├── packages/
│   ├── core/                    # domain models, events, config, storage, migrations
│   │   ├── models.py            # typed dataclasses / pydantic
│   │   ├── db.py                # SQLite (WAL), repositories
│   │   ├── events.py            # local event bus
│   │   ├── config.py            # YAML + env + keyring
│   │   └── logging.py           # structured logs + hash-chained audit
│   ├── scheduler/               # recurrence, alarms, notifications, missed-run recovery
│   ├── projects/                # scanner, registry, health, launcher profiles
│   ├── agent/                   # Tommy runtime
│   │   ├── runtime.py           # observe → plan → act → verify → report
│   │   ├── policy.py            # risk classes, allowlists, approvals, rate limits
│   │   ├── tools.py             # typed tool registry
│   │   ├── memory.py            # episodic, semantic, evidence
│   │   └── prompts/             # system prompts, schemas, injection guards
│   ├── career/                  # coaching, evidence graph, plans, reviews
│   ├── resume/                  # templates, tailoring, renderers (MD/HTML/PDF/DOCX)
│   └── integrations/
│       ├── github/
│       ├── linkedin/            # import + draft only
│       ├── n8n/
│       ├── salesforce/
│       ├── zendesk/
│       └── calendar/
├── skills/                      # user-facing skill packs (manifest + prompts + tools)
├── docs/
│   ├── governance/              # migrated company-os stage-0..3
│   ├── architecture/
│   └── decisions/               # ADRs
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── security/                # prompt injection, approval bypass, secret leakage
├── pyproject.toml
├── .github/workflows/ci.yml
└── README.md
```

### Runtime shape

```
Desktop / CLI
     │
     ▼
Application service ──► Event bus ──► Scheduler / Notifications
     │                     │
     ├──► Project registry │
     ├──► Career engine    │
     ├──► Resume engine    │
     └──► Tommy runtime ───┴──► Policy engine ──► Approval queue
                                   │
                                   ├──► Tool registry ──► Integrations
                                   └──► Audit log (hash-chained)
```

### Storage

- **SQLite** (WAL mode) at `~/.local/share/sigmahelix/sigmahelix.db`.
- Migrations via a small versioned migration runner (no ORM requirement; `sqlite3` + typed repositories is enough).
- Tables: `tasks`, `task_occurrences`, `notes`, `projects`, `project_events`, `launch_profiles`, `career_profiles`, `evidence`, `plans`, `plan_items`, `applications`, `resumes`, `resume_bullets`, `integrations`, `agent_runs`, `tool_calls`, `approvals`, `audit_events`, `settings`.
- Exports: JSON/Markdown for backup; encrypted backup optional (age/GPG).
- **No data leaves the machine** unless an approved integration call is made.

### Event bus

- In-process publish/subscribe (`task.created`, `task.completed`, `project.scanned`, `project.changed`, `alarm.due`, `career.weekly_review`, `resume.generated`, `approval.requested`, `approval.granted`).
- Persist events that matter; ephemeral UI events can be memory-only.
- n8n adapter subscribes to selected events and posts signed webhooks.

### Scheduler

- `APScheduler` (or a small in-process scheduler with a persisted job table) for cron/interval jobs.
- Recurrence via `dateutil.rrule` (daily/weekly/monthly, weekdays, every-N).
- Alarm lifecycle: scheduled → due → notified → acknowledged/snoozed/missed.
- Missed alarms are surfaced on startup, never silently dropped.
- Notifications: Linux `notify-send`/DBus; fallback to in-app banner. Optional sound only if the user enables it; **no automatic TTS**.

---

## 4. Project registry and launcher

### 4.1 Scanner

For each configured root (default: `~/Career/cloned_repos`):

- Detect `.git`; read branch, HEAD, last commit date, dirty count, remote URL.
- Detect manifests: `pyproject.toml`, `requirements.txt`, `package.json`, `deno.json`, `Cargo.toml`, `go.mod`, `pom.xml`.
- Detect test frameworks and test counts where cheap; never run tests automatically.
- Detect runnable profiles:
  - Python: `pyproject` scripts, `streamlit run`, `uvicorn`, `python -m`, `main.py`.
  - Node: `package.json` scripts (`dev`, `start`, `tauri:dev`, `test`).
  - Deno: `deno.json` tasks.
  - Native: `dist/*.AppImage`, ELF, `.desktop`, `.exe` (mark Windows-only).
- Read README status heading and last-modified time.
- Compute a **health score** from: clean worktree, tests present, CI present, README status, last commit age, remote presence.
- Store in `projects` + `project_events`.
- Watch mode via `watchdog`; debounce 2 s; rescan on demand.

### 4.2 Launcher profiles

A profile is explicit, reviewable, and platform-aware:

```yaml
id: study-studio
name: Study Studio
path: ~/Career/cloned_repos/Study-Studio
platform: linux
command: ["npm", "run", "tauri:dev"]
cwd: ~/Career/cloned_repos/Study-Studio
env: {}
health_check: {type: process, pattern: "study-studio"}
timeout_seconds: 120
requires_confirmation: false
```

Rules:

- Never infer a command and run it silently. Show the command preview; user clicks Launch.
- If the profile is missing, show detected candidates and let the user pick.
- Record launch result (exit code, duration, stderr tail).
- Windows `.exe` entries are labeled "Windows only" on Linux; optional Wine profile is explicit.

### 4.3 Dashboard

- Project cards: name, branch, dirty badge, last commit, test/CI status, health score, quick actions (open folder, launch, view evidence).
- "New since last scan" section.
- Filters: active, needs attention, archived.
- No fake status: unknown is shown as unknown.

---

## 5. Integration matrix

| Integration | Auth | Read | Write (approval required) | v1? | Notes |
|---|---|---|---|---|---|
| **GitHub** | Fine-grained PAT in keyring | repos, commits, languages, README, Actions runs | issues/comments (optional) | **Yes** | Start read-only; map local repos by remote/name |
| **n8n** | API key / webhook URL | workflow list (optional) | trigger webhook | **Yes** | Best glue for Salesforce/Zendesk; signed payloads |
| **LinkedIn** | OAuth (OpenID basic profile) or data export | basic profile, manual export import | **draft only** (copy to clipboard) | **Yes (import/draft)** | Official API is restrictive; no scraping; no auto-post |
| **Salesforce** | Connected App OAuth 2.0 | accounts, contacts, opportunities, tasks | create/update tasks/notes (approval) | Phase 4 | Or via n8n connector |
| **Zendesk** | API token (email/token) | tickets, users, orgs | comment/update (approval) | Phase 4 | Or via n8n connector |
| **Calendar** | Local first; CalDAV/Google later | events | create/update (approval) | Phase 2 local; Phase 3 sync | Alarms are local |
| **Resume targets** | none | job descriptions (paste/URL) | generate files | **Yes** | Evidence-traceable |

### Integration rules

- Credentials only in OS keyring (`secretstorage`/libsecret); never in SQLite, logs, prompts, or Git.
- Every adapter has a **contract test** with recorded fixtures; no live calls in CI.
- Read sync is idempotent and cached; writes require an approval card with a diff.
- Rate limits, retries with backoff, and a circuit breaker are mandatory.
- All external content is tagged `<untrusted>` and never treated as instructions.

---

## 6. Career engine and dynamic resume

### 6.1 Evidence graph

The core primitive is **evidence**, not prose:

```
evidence(
  id, project_id, source_type, source_ref, claim, metric, date,
  verified_by, confidence, tags, last_seen
)
```

- Sources: project README, Git commit, test result, CI artifact, user-entered achievement, feedback, certification.
- A resume bullet must reference one or more evidence IDs. The renderer **refuses** bullets without evidence.
- New project detected → propose evidence candidates → user approves → resume update queue.

### 6.2 Coaching loop

```
Intake → Target roles → Gap analysis → 90-day plan → Weekly goals
   → Daily tasks (approved) → Weekly review → Monthly recalibration
   → Resume/LinkedIn update proposals → Application tracker
```

- Plans are proposals until approved.
- Tasks generated from the plan are linked to `plan_item_id`; completing them updates progress.
- Weekly review compares planned vs actual and proposes adjustments.
- Monthly review recalculates gaps against the market/target role.

### 6.3 Resume studio

- Templates: ATS-safe single column, modern, academic.
- Renderers: Markdown → HTML → PDF (WeasyPrint) and DOCX (python-docx).
- Tailoring: paste a job description; extract requirements/keywords; rank evidence; produce a diff; user approves.
- Versioning: every resume version stored with evidence snapshot and job target.
- **No fabrication:** missing metric → `[quantify]` placeholder, not invented numbers.
- Export: PDF/DOCX/Markdown; copy section to clipboard.

---

## 7. Tommy (summary)

Full design: [`TOMMY_CAREER_COACH_SPEC_2026-11-01.md`](TOMMY_CAREER_COACH_SPEC_2026-11-01.md).

Short version:

- Tommy is a **career coach + chief of staff** with a governed tool runtime.
- Risk classes: R0 read-only, R1 reversible local write, R2 external side effect, R3 destructive/irreversible.
- R0/R1 can run automatically within limits; R2/R3 require an approval card with evidence, diff, cost, and reversibility.
- "Never guess" policy: missing slot → ask; missing evidence → say unknown; confidence below threshold → verify or ask.
- Daily/weekly/monthly cadence drives tasks, reviews, and resume updates.
- Prompt injection defenses and a hash-chained audit log are non-negotiable.

---

## 8. Roadmap

Estimates are **focused build days** for one owner working with an AI coding agent. Calendar time assumes part-time work and includes review/testing.

### Phase 0 — Stabilize and consolidate (3–5 days)

| # | Task | Acceptance |
|---|---|---|
| 0.1 | Back up `Career/`; verify archive checksum | Restore test passes |
| 0.2 | Create `sigmahelix/` monorepo; `git init`; `.gitignore`; first commit; private remote | `git log` exists; remote push succeeds |
| 0.3 | Move `company-os/` → `docs/governance/`; move app → `apps/desktop/`; keep archive copies | Imports/tests still pass |
| 0.4 | Rename product to SigmaHelix in code, spec, window title, binary | `sigmahelix --version` prints name |
| 0.5 | Archive false `FINAL_REPORT.md` with correction header; publish audit docs | No unqualified false claim remains |
| 0.6 | Remove/fix stray root `.github` and `.env.example` | CI references only existing paths |
| 0.7 | Add SQLite persistence for tasks/notes/settings | Restart preserves data |
| 0.8 | Add scheduler + alarms + notifications | Alarm fires within ±10 s; missed alarm surfaces |
| 0.9 | Replace static project list with scanner + rescan | New repo appears within 5 s (watch) |
| 0.10 | Replace broken launchers with profiles + command preview | Study Studio/L-D launch or show explicit unsupported reason |

**Exit:** a durable, truthfully documented v0.2 that survives restart and scans projects dynamically.

### Phase 1 — Core OS (7–10 days)

| # | Task | Acceptance |
|---|---|---|
| 1.1 | Domain models + repositories + migrations | Schema v1; migration test |
| 1.2 | Config (YAML + env + keyring) | No hardcoded paths; secrets absent from logs |
| 1.3 | Event bus + structured logging + audit log | Events persisted; hash chain verifies |
| 1.4 | Task recurrence, snooze, complete, reschedule | Daily/weekly/monthly tests pass |
| 1.5 | Dashboard + project cards + filters | 12 repos render with real status |
| 1.6 | Launcher profiles + run history | Launch result recorded |
| 1.7 | Settings UI (roots, model, notifications, theme) | Changes persist |
| 1.8 | Backup/export/restore | Round-trip test |

**Exit:** daily-usable OS for tasks, projects, launchers, and alarms.

### Phase 2 — Tommy v1 (10–14 days)

| # | Task | Acceptance |
|---|---|---|
| 2.1 | Agent runtime loop + typed tool registry | Tool schemas validated |
| 2.2 | Policy engine + risk classes + allowlists | R2 blocked without approval in tests |
| 2.3 | Approval queue UI with diff/evidence | Approve/reject/edit recorded |
| 2.4 | Career intake + evidence graph | Profile and 10 evidence items stored |
| 2.5 | 90-day plan generator + task linking | Plan approval creates tasks |
| 2.6 | Daily brief, weekly review, monthly review jobs | Jobs run on schedule; outputs stored |
| 2.7 | "Never guess" validator | Missing evidence triggers ask/unknown, not fabrication |
| 2.8 | Prompt-injection test suite | 20 adversarial cases pass |

**Exit:** Tommy can coach, plan, and execute R0/R1 actions; every R2+ action waits for a human.

### Phase 3 — Integrations and resume (10–14 days)

| # | Task | Acceptance |
|---|---|---|
| 3.1 | GitHub read sync + repo mapping | 12 local repos mapped or explicitly unmapped |
| 3.2 | Project enrichment from GitHub (languages, last commit, README) | Dashboard shows synced data |
| 3.3 | Resume evidence model + ATS template | PDF/DOCX generated |
| 3.4 | Job-description tailoring + diff approval | Bullet traceability 100% |
| 3.5 | n8n webhook adapter + signed events | Test webhook received |
| 3.6 | LinkedIn data import + draft workflow | Import works; no auto-post |
| 3.7 | Calendar sync (optional) | Local alarms unaffected |

**Exit:** projects and career data flow into a resume the user can trust; n8n can automate around SigmaHelix.

### Phase 4 — Enterprise connectors (8–12 days)

| # | Task | Acceptance |
|---|---|---|
| 4.1 | Salesforce OAuth + read sync | Accounts/contacts/tasks read |
| 4.2 | Salesforce write behind approval | Approval card + audit entry |
| 4.3 | Zendesk token + read sync | Tickets read |
| 4.4 | Zendesk comment/update behind approval | Approval card + audit entry |
| 4.5 | Conflict handling + rate limits + retries | Contract tests pass |
| 4.6 | Integration health dashboard | Status visible per connector |

**Exit:** business workflows can touch CRM/support data without violating the approval model.

### Phase 5 — Hardening and extensibility (5–8 days, then ongoing)

| # | Task | Acceptance |
|---|---|---|
| 5.1 | Plugin manifest + loader + permissions | Third-party tool loads without core edit |
| 5.2 | Skill packs (`career-coach`, `project-steward`, `resume-smith`) | Install/enable/disable works |
| 5.3 | Security review: secrets, injection, approval bypass | No P0 findings |
| 5.4 | Performance: 100 projects, 5k tasks | Dashboard < 1 s |
| 5.5 | Packaging: AppImage/deb; Windows build plan | Clean install on a second machine |
| 5.6 | Backup/restore drill | Data restored byte-identical |

**Exit:** SigmaHelix is extensible, testable, and installable.

### Total

| Phase | Days | Calendar (part-time) |
|---|---:|---|
| 0 Stabilize | 3–5 | week 1 |
| 1 Core OS | 7–10 | weeks 2–3 |
| 2 Tommy v1 | 10–14 | weeks 4–6 |
| 3 Integrations + resume | 10–14 | weeks 7–9 |
| 4 Enterprise connectors | 8–12 | weeks 10–12 |
| 5 Hardening | 5–8 | weeks 13–14 |
| **Total** | **43–63** | **~14 weeks** |

---

## 9. Backlog (priority order)

### P0 — must ship before calling it usable

1. Monorepo + Git + private remote + backup.
2. Truth correction of stage-2 reports.
3. SQLite persistence.
4. Scheduler + alarms + notifications.
5. Dynamic project scanner + rescan/watch.
6. Correct launcher profiles.
7. Rename to SigmaHelix.
8. Policy engine skeleton + approval queue (before any write integration).

### P1 — the career core

9. Tommy runtime + tool registry.
10. Career intake + evidence graph.
11. 90-day plan + task linkage.
12. Daily/weekly/monthly cadence.
13. Resume generator + evidence traceability.
14. GitHub read sync.
15. n8n webhooks.

### P2 — external surface

16. LinkedIn import + draft workflow.
17. Salesforce read/write.
18. Zendesk read/write.
19. Calendar sync.
20. Application tracker + interview prep.

### P3 — scale and polish

21. Plugin API + skill packs.
22. Windows packaging.
23. Mobile/remote companion (optional).
24. Multi-user/tenant mode (only if selling).
25. Analytics and career metrics dashboard.

---

## 10. Acceptance criteria (product-level)

| Area | Criterion |
|---|---|
| Durability | Restart preserves 100% of tasks, notes, settings, projects, evidence |
| Alarms | Fire within ±10 s; missed alarms surfaced; no duplicate notifications |
| Project scan | 12 repos scanned in < 2 s; new repo detected < 5 s in watch mode |
| Launchers | Every profile either launches or reports a precise unsupported reason; no silent failure |
| Agent safety | 100% of R2/R3 test actions blocked without approval |
| Audit | Every tool call and approval is recorded; hash chain verifies |
| Truth | No resume bullet without evidence; no fabricated metric in tests |
| Career cadence | Daily brief and weekly review run on schedule; outputs stored |
| Integrations | Contract tests pass offline; live calls gated by credentials |
| Privacy | No secret in logs/prompts/Git; `gitleaks` clean |
| Packaging | Clean install on a second Linux machine; Windows plan documented |

---

## 11. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope creep | High | High | Phase gates; P0 first; no integration before policy engine |
| No Git/backup | Certain today | Catastrophic | Phase 0.1–0.2 before any refactor |
| Dirty Helix-Prime/CompliProof work lost | Medium | High | Commit/stash + backup before migration |
| LinkedIn API limits | High | Medium | Import/draft only; no scraping; human posts |
| Salesforce/Zendesk OAuth complexity | Medium | Medium | Build after n8n; offer n8n connector path |
| Local LLM unreliability | Medium | Medium | Deterministic tools; schema validation; fallback |
| Prompt injection via project/README/email | High | High | Untrusted tagging, allowlists, no instruction execution from content |
| Agent overreach | Medium | High | Risk classes, approvals, audit, kill switch |
| Single-user architecture blocks selling | Medium | Medium | Keep tenant_id fields from day one; don't claim multi-tenant |
| Windows packaging | Medium | Medium | Linux first; document Windows build path; CI matrix later |
| Time estimates slip | High | Medium | Treat estimates as ranges; ship Phase 0–2 before integrations |

---

## 12. Migration steps (concrete, in order)

1. **Backup:** `rsync -a Career/ /external/backup/Career-2026-11-01/` + `sha256sum` manifest.
2. **Create repo:** `mkdir sigmahelix && cd sigmahelix && git init`.
3. **Copy, don't move yet:** copy `company-os/` → `docs/governance/`, `company-os-app/` → `apps/desktop/`; run tests in the new tree.
4. **Add** `pyproject.toml`, `.gitignore`, `README.md`, `docs/architecture/`.
5. **Commit** "baseline: import governance and prototype".
6. **Push** to a private GitHub repo; verify clone on a second directory.
7. **Only then** refactor modules and delete the old folders (keep an archive tag).
8. **Add CI:** lint, unit tests, GUI smoke (xvfb), package; no live integrations.
9. **Tag** `v0.2.0` after Phase 0 acceptance.
10. **Record** every phase exit in `docs/governance/` with commands and artifacts.

---

## 13. What "done" looks like for the user

A normal day:

- Open SigmaHelix → dashboard shows today's tasks, alarms, project health, and one career next action.
- Tommy's morning brief: "2 interviews this week, Helix-Prime has 3 new commits, resume needs one updated bullet, Zendesk ticket awaiting approval."
- User clicks **Approve** on a resume diff; Tommy generates the PDF.
- User clicks **Launch** on Study Studio; the correct command runs and the result is recorded.
- A new repo appears in the library without a restart; Tommy proposes evidence bullets for review.
- Nothing is sent, posted, deleted, or paid without a visible approval card.
- Every action is traceable in the audit log.

That is the standard the plan is built to meet.
