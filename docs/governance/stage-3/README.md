# SigmaHelix — Stage 3 Audit & Plan Index

**Date:** 2026-11-01
**Owner:** Hatem Shalaby
**Scope:** `Career/` workspace, `company-os/` governance, `company-os-app/` implementation
**Status:** Audit complete; plan proposed; no production or external claims

---

## Documents

| # | Document | What it answers |
|---|---|---|
| 1 | [`AUDIT_WORKSPACE_PROJECTS_2026-11-01.md`](AUDIT_WORKSPACE_PROJECTS_2026-11-01.md) | Every project in the workspace: real status, connections, repos vs folders, evidence, risks |
| 2 | [`AUDIT_APP_VS_ORIGINAL_2026-11-01.md`](AUDIT_APP_VS_ORIGINAL_2026-11-01.md) | Company OS app audited against the original `company-os` stage plan: what was promised, what exists, what is false |
| 3 | [`SIGMAHELIX_EXECUTION_PLAN_V2.md`](SIGMAHELIX_EXECUTION_PLAN_V2.md) | **Current plan.** No time frames; gate-based autonomous execution; full SWE/DevOps test programme; A-to-Z |
| 4 | [`TOMMY_RUNTIME_SPEC_V2.md`](TOMMY_RUNTIME_SPEC_V2.md) | **Current runtime spec.** Verified model ladder (`qwen3.5:9b`), 100% GPU guard, signed skill/plugin runtime, context budget, think-effort policy |
| 5 | [`SELF_EVALUATION_AND_PLAN_CRITIQUE.md`](SELF_EVALUATION_AND_PLAN_CRITIQUE.md) | Honest critique of v1 and of my own conduct; what v2 still gets wrong; alternatives rejected |
| 6 | [`SIGMAHELIX_MASTER_PLAN_2026-11-01.md`](SIGMAHELIX_MASTER_PLAN_2026-11-01.md) | v1 plan — **superseded** by document 3; kept for history |
| 7 | [`TOMMY_CAREER_COACH_SPEC_2026-11-01.md`](TOMMY_CAREER_COACH_SPEC_2026-11-01.md) | v1 Tommy spec — role, constitution, and career workflows remain valid; runtime superseded by document 4 |
| 8 | [`PROJECT_INVENTORY.csv`](PROJECT_INVENTORY.csv) | Machine-readable inventory for dashboards and future automation |
| 9 | [`CORRECTION_NOTICE_2026-11-01.md`](../stage-2/CORRECTION_NOTICE_2026-11-01.md) and [`FINAL_REPORT.md`](../stage-2/FINAL_REPORT.md) | Read the correction notice with the retained historical report; the notice controls its claims |

---

## The one-paragraph answer

`company-os/` and `company-os-app/` are **not two repositories and not one repository** — they are two sibling folders inside a `Career/` workspace that is **not under version control at all**. `company-os/` holds governance and venture documents; `company-os-app/` holds the Python desktop/console implementation. Conceptually they are one project; operationally they are disconnected, unversioned, and only linked by prose. The 12 projects under `cloned_repos/` are independent Git repositories, but **none has a real remote**, so nothing is connected to GitHub today. The app is a real but shallow prototype: it can chat through a local GPU LLM, hold in-memory tasks/notes, list folder names, and speak on demand. It is **not** the dynamic OS described in the vision: no persistence, no alarms, no scheduler, no GitHub/LinkedIn/n8n/Salesforce/Zendesk, no resume engine, no career coaching, no approval gates, no dynamic project health, and no GUI in the packaged binary.

## What is genuinely true today

- Native Ollama v0.40.13 runs on `127.0.0.1:11435`; `llama3.2:1b` loads at **100% GPU** on the RX 6700 XT.
- `company-os-app` passes **23/23** local tests (20 offline + 3 live-LLM; the new TTS-discipline tests are included).
- The packaged `dist/CompanyOS` is a **51 MB Linux ELF console binary**; it prints, replies, creates a task, and exits cleanly.
- TTS is now strictly on demand: silent replies by default, `listen` to speak, `stop` to cut off.
- Microphone hardware is detected (`arecord -l` shows USB Audio) and PyAudio 0.2.14 is installed.
- The 12 cloned repos have real code and substantial test evidence; Helix-Prime is the strongest at 2,000 passing tests.
- `company-os/` contains a serious governance packet (constitution, authority matrix, risk taxonomy, evidence standard, P0 register).

## What is not true today

- The app is not a "Company OS"; it is a chat shell plus in-memory CRUD.
- The packaged binary is not the GUI and is not a Windows `.exe`.
- No task, note, or calendar item survives a restart.
- No alarm or notification exists.
- The calendar is never populated by task creation.
- The two "launchers" point at files that do not exist (`Study-Studio/app.py`, `L-D-Command-Center/main.py`).
- The `.exe` explorer only searches for `*.exe`; on Linux it finds nothing.
- No project is connected to GitHub, LinkedIn, n8n, Salesforce, or Zendesk.
- No resume, career coaching, approval gate, policy engine, or audit trail exists.
- `FINAL_REPORT.md` claims ten source files; only six exist, and four of the claimed modules were never written.
- There is no version control, no remote, and no backup for `company-os/` or `company-os-app/`.

## Recommended immediate order

1. **Stop the bleeding:** back up the workspace, `git init` a SigmaHelix monorepo, commit the current state, add a private remote.
2. **Tell the truth:** archive or correct `stage-2/FINAL_REPORT.md`; replace claims with the audit matrix in document 2.
3. **Make it durable:** SQLite persistence, scheduler/alarms, dynamic project scan, real launcher profiles.
4. **Then build Tommy:** policy engine and approval queue before any write-capable integration.
5. **Then connect:** GitHub first, n8n second, resume third, LinkedIn import fourth, Salesforce/Zendesk last.

Full sequencing, estimates, and acceptance criteria are in document 3; Tommy's design is in document 4.
