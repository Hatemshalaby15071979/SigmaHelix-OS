# Stage 2 — Company OS Build + Simulated Deployment
*Owner: HatemShalaby | Spend cap: $40/mo | Framework: Python desktop (CustomTkinter)*
*Status: PLAN — awaiting build execution*

## Direction (per owner instruction)
Build BOTH now:
1. **Personal company OS** — local desktop app used by you starting today, for everything.
2. **Sellable version** — same core, tested against simulated tenant data, packaged as `.exe` so it can be sold once the first buyer appears.
No more waiting for external partners/clients. Simulated data substitutes for real clients until a buyer exists.

## Phase 0 — Governance blockers (resolve before build)

| ID | Task | Deliverable | Status |
|----|------|-------------|--------|
| G-6 | Auditor path: simulated audit + FreeTSA anchor (external auditor vacant — not a blocker). Verification flags added. | `stage-2/AUDIT_PATH.md`, `stage-2/ANCHOR_FREETSA.md` | Pending |
| G-7 | Archive both ledgers (G-7) | `stage-2/LEDGERS_ARCHIVED.md` | Pending |
| G-8 | Rebuild all 7 P0s clean-room v1 | `stage-2/P0_REBUILD.md` | Pending |
| G-9 | Confirm Helix Prime verification + FreeTSA anchor verification | `stage-2/VERIFICATION.md` | Pending |
| G-10 | Spend cap $40/mo documented + enforced | `stage-2/BUDGET.md` | Pending |
| G-11 | Direction change documented: built for you now; sellable tested version | `stage-2/VENTURE_DIRECTION.md` | Pending |
| G-12 | Simulated tenant data accepted as real-client substitute | `stage-2/SIMULATED_TENANT_DATA.md` | Pending |

## Phase 1 — Company OS build (Python desktop)

| # | Component | Files | Details |
|---|-----------|-------|---------|
| 1.1 | App shell + voice input icon + listen-to-reply | `company-os-app/main.py`, `company-os-app/voice.py` | CustomTkinter window; mic icon button (toggle); speech-to-text input; agent replies shown + **TTS playback** ("listen" button) |
| 1.2 | Personal assistant agent | `company-os-app/agent.py` | Local agent wrapper; routes input to tools (tasks, notes, projects, calendar, launcher) |
| 1.3 | Project monitor (all 11 cloned_repos) | `company-os-app/projects.py` | Scans `/cloned_repos/`; lists status, last modified, git branch; one-click open project folder |
| 1.4 | To-do tracker (daily/weekly/monthly) + calendar alarms | `company-os-app/todo.py`, `company-os-app/calendar.py` | Task CRUD; repeat daily/weekly/monthly; Windows `ToastNotifier`-style alarms + sound |
| 1.5 | Study Studio / L&D Command Center launcher | `company-os-app/launcher.py` | One-click button opens Study-Studio + L-D-Command-Center apps; extensible per project |
| 1.6 | Released apps explorer (`.exe` shortcuts) | `company-os-app/explorer.py` | Scans all 11 repos for `dist/`/`build/` `.exe` files; lists them; one-click launch; creates desktop shortcuts |
| 1.7 | Independent notes area | `company-os-app/notes.py` | Save / edit / delete free-form notes, no task binding |
| 1.8 | ADHD-friendly design | `company-os-app/theme.py` | High-contrast dark theme, large buttons, minimal clutter, clear section headers, focus mode |
| 1.9 | Packaging → `.exe` | `PyInstaller` spec | Single-file `.exe` output; included in `company-os-app/dist/` |

### All 11 cloned_repos to monitor/explore
Blue Waves Music Production, CompliProof, Dynamic-Ops-Automation-Engine, Helix-Education, Helix-Prime, L-D-Command-Center, RTA_command_center, Study-Studio, cx-sentiment-sentinel, live-support-assistant, wfm-forecasting-calculator, work-samples (12 actually present — all included).

## Phase 2 — Simulated deployment & install verification

| # | Task | Evidence |
|---|------|----------|
| 2.1 | Package OS as `.exe` (PyInstaller) | `company-os-app/dist/CompanyOS.exe` |
| 2.2 | Install + run locally | `INSTALL_VERIFICATION.md` |
| 2.3 | Accept simulated tenant data (`External tenant data`) as real-client substitute | `stage-2/SIMULATED_TENANT_DATA.md` |
| 2.4 | Run chaos-proof test vs simulated data (callcenter + sportacademy) | `evidence/CHAOS_TEST_LOG.md` |
| 2.5 | Confirm kill-switch + live drill (simulated) | `stage-2/KILLSWITCH_DRILL.md` |
| 2.6 | Confirm $40/mo budget not exceeded | `stage-2/BUDGET.md` |
| 2.7 | Final verification: voice, notes, projects, explorer, launcher all work | `evidence/FINAL_VERIFICATION.md` |

## Definition of done
- `.exe` built, installed, running locally
- Voice input icon works; listen-to-reply playback works
- All 11 repos visible in project monitor + explorer
- To-do + calendar alarms functioning
- Notes area CRUD working
- Simulated tenant data accepted & tested
- Governance docs (G-6..G-12) complete
- No external partner/client dependency remains
