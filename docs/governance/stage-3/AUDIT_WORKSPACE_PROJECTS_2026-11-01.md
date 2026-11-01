# Workspace & Project Audit — 2026-11-01

**Auditor:** AI agent (same class as the system under audit; not an independent human auditor)
**Workspace:** `/run/media/hatem/2A3AE01E311C617F/Career`
**Method:** direct filesystem inspection, `git` object/status inspection, README and evidence review, test runs where already recorded, and fresh runs only for `company-os-app`. No repository was modified during this audit.
**Evidence standard:** a claim is marked **Verified today** only if a command was run in this session; **Recorded** means the project's own dated evidence was read but not re-run; **Unverified** means no current evidence was found.

---

## 1. Repository topology — the direct answer

```
Career/                          ← NOT a Git repository (no .git at root)
├── 00_CONSTITUTION.md           ← workspace authority
├── agents.md                    ← handover log
├── AUDIT_2026-10-30.md          ← prior audit
├── company-os/                  ← governance + venture docs, NOT a Git repo
├── company-os-app/              ← Python app, NOT a Git repo
├── cloned_repos/                ← 12 independent Git repos, no real remotes
│   ├── Helix-Prime/             ← its own .git
│   ├── ... 11 more
│   └── CompliProof/
│       ├── helix-prime/         ← nested clone, placeholder remote
│       └── helix-education/     ← nested clone, placeholder remote
├── External tenant data/        ← synthetic fixtures, not a repo
├── docs/production_readiness/   ← readiness programme, not a repo
├── tools/                       ← fixture/chaos scripts, not a repo
└── .github/workflows/ci.yml     ← stray CI that references missing ld-studio/
```

**Verdict:** `company-os/` and `company-os-app/` are **one project split across two unversioned folders**. They are not separate repositories, and they are not a monorepo either. The only "connection" is documentation: `stage-2/STAGE_PLAN.md` names `company-os-app/` as the build target, and `E2E_VERIFICATION_2026-11-01.md` records its test runs. There is no shared package, no shared config, no CI linking them, and no Git history for either.

This is the single largest structural risk in the workspace: a disk failure or accidental delete loses both the governance record and the app with no recovery path.

---

## 2. Inventory at a glance

| # | Project | Kind | Stack | Commits | Worktree | Last evidence | Honest status |
|---|---|---|---:|---:|---|---|---|
| 1 | **Helix-Prime** | Flagship platform (WFM/RTA/CX engines + app/API) | Python 3.12, FastAPI, pytest | 383 | **62 dirty** | 2,000 passed, 19 deselected; readiness 12/12; tenant fidelity 24/24 (2026-10-31) | Strongest codebase; production **NOT_READY** (9 gates) |
| 2 | **live-support-assistant** | AI support prototype | TypeScript/pnpm, Supabase, Tauri | 234 | clean | typecheck clean; verify 17/17; evidence 12/12 (2026-10-31) | Prototype; **7 cross-tenant failures**; P3/P4/P6/P7 incomplete |
| 3 | **CompliProof** | Compliance/reconciliation product | Python, FastAPI, Docker | 2 | **16 dirty** | 55 tests pass; wheel + Docker smoke (2026-10-31) | **7 P0 open**; NOT_READY; bundles stale Helix copies |
| 4 | **L-D-Command-Center** | L&D desktop app | Python/Tkinter + Ollama | 32 | clean | 1,060 passed, 7 deselected (2026-10-31) | V1 ship in progress; E2E mixed; Windows-oriented |
| 5 | **Study-Studio** | Study desktop app | Tauri + Next.js, Deno | 58 | clean | 986 tests / 47 suites; typecheck + lint clean (2026-10-01 CI) | Active app; Windows installer path; Linux build not verified |
| 6 | **Helix-Education** | Learning engine | Python, event-sourced | 47 | clean | 465 passed (2026-10-01 CI; local 2026-10-31) | Alpha; gRPC not wired; not integrated into Helix-Prime |
| 7 | **wfm-forecasting-calculator** | Erlang C calculator | Python/Streamlit | 45 | clean | 42 passed (2026-10-31) | Cleanest repo; learning exercise |
| 8 | **cx-sentiment-sentinel** | CX KPI pipeline | Python/Parquet/Postgres | 16 | clean | 9 passed (2026-10-31) | Learning exercise; absorbed into Helix-Prime |
| 9 | **Dynamic-Ops-Automation-Engine** | Multi-tenant ops service | FastAPI, Docker | 15 | clean | compile clean; no tests | Learning exercise; service-shaped, not production |
| 10 | **RTA_command_center** | RTA adherence app | Python/Streamlit | 43 | clean | no collected tests; 24 Ruff findings | Learning exercise; import + requirements defects |
| 11 | **Blue Waves Music Production** | Music tooling + skills registry | ComfyUI vendored, Python | 9 | clean | platform 72 passed; engine suite not run | Personal tooling; not a product |
| 12 | **work-samples** | RAG/SQL/proposal samples | Python | 8 | clean | 105/105 RAG tests (recorded) | Reference samples, not shippable |
| 13 | **company-os** | Governance + venture docs | Markdown/YAML | — | no Git | Stage 0 closed; Stage 2 docs | Serious governance, no executable controls |
| 14 | **company-os-app** | Company OS prototype | Python/CustomTkinter + Ollama | — | no Git | **23/23 tests today** | Shallow prototype; feature gaps below |

**Count correction:** the workspace contains **12** cloned repositories, not 11. `agents.md`, `stage-2/STAGE_PLAN.md`, and `stage-2/FINAL_REPORT.md` all use "11" while also listing 12. The app's own project list includes `__pycache__` and test directories as if they were projects.

---

## 3. Per-project reality

### 3.1 Helix-Prime — the flagship

- **What it is:** a workforce/CX platform with six engines (WFM, RTA, CX, etc.), an app/API layer, and a large evidence apparatus.
- **Real evidence:** 2,000 passed, 19 deselected; 12/12 readiness gates; 24/24 tenant-fidelity checks; 128 focused ops tests; simulated design-partner drill 14/14.
- **Current worktree:** 62 modified/untracked entries. This is intentional per `agents.md` but uncommitted work is a loss risk.
- **What it is not:** production-ready. Nine production-only C8 gates remain; no real customer, no external audit, no deployment.
- **Connection:** CompliProof contains a nested, stale clone (372 commits vs 383 now). Helix-Education explicitly says it is **not** integrated into Helix-Prime. CX and WFM concepts were absorbed into Helix-Prime from the learning repos.

### 3.2 live-support-assistant — the support prototype

- **What it is:** a pnpm/Turborepo support assistant with Supabase/Postgres RLS, on-device retrieval, and a Tauri desktop shell.
- **Real evidence:** typecheck clean, 17/17 verification suites, 12/12 evidence claims.
- **What it is not:** production-ready. The phase-7 database run recorded **7 F-1 cross-tenant failures**; P3/P4/P6/P7 are incomplete; the Tauri build could not run because `cargo` is absent.
- **Connection:** references Helix/company-os concepts; no shared package.

### 3.3 CompliProof — the first venture

- **What it is:** a compliance/reconciliation product with dashboard, CLI, Docker, auth, audit ledger, and report persistence.
- **Real evidence:** 55 tests pass; wheel builds and installs; non-root Docker health smoke passes; Bandit 0 findings; pip-audit 0 known vulnerabilities.
- **What it is not:** production-ready. **Seven P0 acceptance items remain open** (independent signatures/anchoring, crash recovery, reconciliation/API/report parity, auth/RBAC, tenant workflows). Full Ruff reports 28 findings. GitHub CI and backup/restore were not executed.
- **Connection:** contains nested `helix-prime` and `helix-education` clones with placeholder remotes (`https://github.com/<YOUR_GITHUB_ORG>/...`). This is duplicated, stale code, not an integration.

### 3.4 L-D-Command-Center — the L&D desktop app

- **What it is:** a Python/Tkinter + local-Ollama learning-and-development workstation with journey, audio, language-lab, career, and playground sections.
- **Real evidence:** 1,060 passed, 7 deselected (recorded 2026-10-31).
- **What it is not:** verified on Linux. README records a **blocked UI launch** (Tcl environment), a **60 s generation timeout**, and "GitHub/LinkedIn connection was UNVERIFIED". Launchers are Windows `.bat` files with `E:\LD_Command_Center` paths.
- **Connection:** the Company OS app claims to launch it via `python -m streamlit run main.py`; **`main.py` does not exist**, so that launcher is broken.

### 3.5 Study-Studio — the study app

- **What it is:** a Tauri + Next.js desktop lesson generator with a Deno workspace and a large test suite.
- **Real evidence:** 986 tests / 47 suites, 85.66% statement coverage, typecheck and lint clean (CI 2026-10-01).
- **What it is not:** verified as a Linux build. The build path documented is a Windows installer (`npm run tauri:build`); `cargo` is absent on this machine. The Company OS app launches `streamlit run app.py`; **`app.py` does not exist**, so that launcher is broken.
- **Connection:** ships a `Helix_Prime.html` static page; otherwise independent.

### 3.6 Helix-Education — the learning engine

- **What it is:** an event-sourced learning-state engine with analytics, cognitive agents, and API layers.
- **Real evidence:** 465 passed (2026-10-01 CI; local 2026-10-31).
- **What it is not:** integrated. README states the gRPC competency service is not wired, external grounding is stubbed, and the engine has **not** been integrated into Helix-Prime. No external audit.
- **Connection:** duplicated (stale) inside CompliProof.

### 3.7 wfm-forecasting-calculator — Erlang C

- **What it is:** a clean Erlang C engine plus Streamlit UI.
- **Real evidence:** 42 passed (2026-10-31). The engine is genuinely correct and self-tested.
- **What it is not:** a product. README labels it a learning exercise.
- **Connection:** the math was absorbed into Helix-Prime's WFM engine.

### 3.8 cx-sentiment-sentinel — CX KPI pipeline

- **What it is:** a five-stage Postgres → Parquet → risk-score → Slack/dashboard pipeline.
- **Real evidence:** 9 passed (2026-10-31).
- **What it is not:** a product. README labels it a learning exercise and says the idea was absorbed into Helix-Prime's CX engine.
- **Connection:** conceptual predecessor to Helix-Prime CX.

### 3.9 Dynamic-Ops-Automation-Engine — multi-tenant ops service

- **What it is:** a FastAPI service with tenant middleware, correlation IDs, typed errors, Erlang C, and webhook fan-out.
- **Real evidence:** compile clean; no test suite. CI builds a Docker image.
- **What it is not:** production. No tests; self-directed learning build.
- **Connection:** service-shaped precursor to Helix-Prime's ops layer.

### 3.10 RTA_command_center — real-time adherence

- **What it is:** a Streamlit RTA adherence calculator with a real calculations engine.
- **Real evidence:** none collected. README documents a launch-directory import bug, an incomplete `requirements.txt`, and 24 Ruff findings.
- **What it is not:** runnable as documented without fixes.
- **Connection:** RTA math absorbed into Helix-Prime.

### 3.11 Blue Waves Music Production — music tooling

- **What it is:** a personal music-production workspace around a vendored ComfyUI engine, plus a pinned agent-skills registry.
- **Real evidence:** platform suite 72 passed; the engine suite has **50 collection errors** because torch/cv2/av/aiohttp/simpleeval are not installed.
- **What it is not:** a product or a library.
- **Connection:** none to the Company OS; it is a separate personal domain.

### 3.12 work-samples — reference samples

- **What it is:** proposal, RAG, SQL, and tooling samples.
- **Real evidence:** RAG sample 105/105 (recorded); SQL checks; no single installable package.
- **What it is not:** shippable. README says so.
- **Connection:** none.

### 3.13 company-os — governance

- **What it is:** a serious governance packet: constitution, 25 decision rights, risk taxonomy, E0–E4 evidence standard, 20-claim registry (0 external claims approved), 7-item P0 register, 39-scenario threat model, incident plan, kill-switch tabletop (0/5 passed), Stage 2 build plan and G-6..G-12 docs.
- **What it is not:** executable. There is no code, no CI, no version control, and the prior audit found **agent-signed owner decisions** (F-01) and **no human re-attestation**. Stage 2's "all governance blockers resolved" means "documents exist", not "controls are enforced".
- **Connection:** it authorizes and describes `company-os-app`, but nothing enforces that link.

### 3.14 company-os-app — the prototype

Detailed in [`AUDIT_APP_VS_ORIGINAL_2026-11-01.md`](AUDIT_APP_VS_ORIGINAL_2026-11-01.md). Headline: 1,061 source LOC, 23 passing tests, in-memory data, no scheduler, no integrations, console-only binary, broken launchers.

---

## 4. Are the projects connected?

### 4.1 Hard connections (code or Git)

| Relationship | Type | Evidence |
|---|---|---|
| CompliProof → Helix-Prime | Nested stale clone | `CompliProof/helix-prime/.git`, 372 commits vs 383 |
| CompliProof → Helix-Education | Nested stale clone | `CompliProof/helix-education/.git`, 46 commits vs 47 |
| Study-Studio → Helix-Prime | Static HTML artifact | `Study-Studio/Helix_Prime.html` |
| Company OS app → 12 repos | Folder listing only | `ProjectsManager` lists directory names; no metadata |
| Company OS app → Study-Studio / L-D | Broken launchers | Targets `app.py` / `main.py` do not exist |

### 4.2 Soft connections (concepts and docs)

- **CX → Helix-Prime:** README says the CX idea was absorbed into Helix-Prime's CX engine.
- **WFM → Helix-Prime:** Erlang C math reimplemented in Helix-Prime's WFM engine.
- **RTA → Helix-Prime:** adherence math reimplemented in Helix-Prime.
- **Dynamic Ops → Helix-Prime:** multi-tenant service patterns reused.
- **Helix-Education → Helix-Prime:** explicitly **not** integrated.
- **L-D → GitHub/LinkedIn:** explicitly **UNVERIFIED** in its own E2E report.
- **company-os → everything:** governance intent only; no enforcement.

### 4.3 What "connected" should mean for SigmaHelix

A real connection is a typed contract: a project registry entry with repo URL, local path, branch, health, run profile, and event stream. Today none of that exists. The plan in document 3 replaces folder listing with a registry and adapters.

---

## 5. Cross-cutting findings

### P0 — loss or falsehood risks

| ID | Finding | Evidence | Impact |
|---|---|---|---|
| W-01 | `Career/`, `company-os/`, and `company-os-app/` are **not Git repositories** | no `.git` at any of the three | One disk event loses governance + app; no diff/review/rollback |
| W-02 | **Zero real remotes** across all 12 repos | `git remote -v` empty; nested remotes are `<YOUR_GITHUB_ORG>` placeholders | No off-machine backup; "connected to GitHub" is false today |
| W-03 | Helix-Prime has **62 dirty files**, CompliProof **16** | `git status --porcelain` | Uncommitted work can be lost; release SHA does not describe the worktree |
| W-04 | `stage-2/FINAL_REPORT.md` claims files that do not exist | claims `notes.py`, `projects.py`, `calendar.py`, `launcher.py`, `explorer.py`, `todo.py`; only `tasks.py` holds managers | Governance record is false; future decisions rest on it |
| W-05 | App claims "all features operational" but tasks/notes/calendar are in-memory | `TasksManager.__init__` sets `self.tasks = []`; no persistence imports | Data loss on every restart; alarms impossible |

### P1 — functional gaps

| ID | Finding | Evidence |
|---|---|---|
| W-06 | Calendar is never populated | `CalendarManager.tasks_by_date = {}`; `schedule_task()` is never called |
| W-07 | No alarm/notification code | no `notify`, `plyer`, `ToastNotifier`, `schedule`, or timer imports |
| W-08 | Launchers are wrong | Study-Studio has no `app.py`; L-D has no `main.py`; both are not Streamlit |
| W-09 | `.exe` explorer is Windows-only | glob `*.exe`; Linux build is ELF; finds nothing |
| W-10 | Project list is static at startup | built once in `_projects_panel()`; no rescan/watch |
| W-11 | Project status is just a folder name | no branch, dirty count, last commit, test status, remote |
| W-12 | Hardcoded absolute paths | `tasks.py:142`, `241-242`; breaks on another machine |
| W-13 | GUI is excluded from the binary | `CompanyOS.spec` excludes `tkinter`, `customtkinter`; builds `console_os.py` only |
| W-14 | Binary is Linux ELF, not `.exe` | `file dist/CompanyOS` → ELF 64-bit LSB executable |

### P2 — engineering debt

| ID | Finding | Evidence |
|---|---|---|
| W-15 | All five managers crammed into `tasks.py` | 273 lines, five classes, unrelated concerns |
| W-16 | No config layer | paths, model, hosts hardcoded or env-only |
| W-17 | No logging or audit trail | actions are not recorded |
| W-18 | No secret handling | no keyring, no `.env` loader, no redaction |
| W-19 | No approval/HITL layer | agent executes every parsed action immediately |
| W-20 | Tests are shallow | 23 tests cover in-memory CRUD and routing; no persistence, scheduler, launcher, or integration tests |
| W-21 | Root `.github/workflows/ci.yml` is stray | references `ld-studio/tests/run_all.py`, which does not exist at root |
| W-22 | Root `.env.example` belongs to L&D Studio | not used by `company-os-app` |
| W-23 | Stale docs use "11 repos" while 12 exist | `agents.md`, `STAGE_PLAN.md`, `FINAL_REPORT.md` |

### P3 — cosmetic / hygiene

| ID | Finding |
|---|---|
| W-24 | `__pycache__` and `.pytest_cache` appear in project lists |
| W-25 | App name is still "Company OS"; the user has chosen **SigmaHelix** |
| W-26 | README language overstates readiness in several repos (each repo has its own warnings, but the workspace-level docs do not reconcile them) |

---

## 6. Verification limits

- This audit did **not** re-run the full test suites of the 12 cloned repos. It relies on their dated evidence (2026-10-31) plus current Git state. Helix-Prime alone is a 2,000-test suite; re-running everything would take hours and change nothing about the structural findings.
- `company-os-app` **was** re-run today: `23 passed` (offline + live GPU LLM).
- No human auditor, lawyer, or certification body reviewed this. It is an engineering audit, not a compliance opinion.
- The 62 dirty Helix-Prime files were not individually reviewed. Their existence is the finding; their content may be legitimate work in progress.
- LinkedIn/Salesforce/Zendesk API availability was not tested because no credentials exist. The plan treats them as integrations to be built, not as current capabilities.

---

## 7. What to do first (workspace level)

1. **Back up** `Career/` to an external drive today (rsync or tar; verify checksum).
2. **Create the SigmaHelix monorepo** (`git init`, `.gitignore`, first commit) and push to a **private** GitHub remote. Do this before any refactor.
3. **Commit or stash** the dirty work in Helix-Prime and CompliProof; record why each dirty file exists.
4. **Freeze false documents:** move `stage-2/FINAL_REPORT.md` to `archive/` and add a header pointing to this audit. Do not delete evidence; label it.
5. **Remove or fix the stray root `.github` and `.env.example`** so CI cannot silently fail on a missing `ld-studio/`.
6. **Add remotes** to the 12 repos (or import them into the monorepo as submodules/vendored snapshots) only after deciding the ownership model. Do not push secrets or synthetic tenant data to public repos.

The build sequence for the app itself is in [`SIGMAHELIX_MASTER_PLAN_2026-11-01.md`](SIGMAHELIX_MASTER_PLAN_2026-11-01.md).
