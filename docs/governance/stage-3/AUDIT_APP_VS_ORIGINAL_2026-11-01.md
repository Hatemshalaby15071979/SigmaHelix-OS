# Company OS App — Audit Against the Original Project — 2026-11-01

**Subject:** `company-os-app/` (Python/CustomTkinter prototype)
**Original authority:** `company-os/stage-2/STAGE_PLAN.md`, `company-os/stage-2/STAGE_STATUS.yaml`, `company-os/stage-2/FINAL_REPORT.md`, `company-os/stage-2/E2E_VERIFICATION_2026-11-01.md`
**Auditor:** AI agent; engineering audit only, not an independent certification
**Fresh test run:** `PYTHONPATH=. venv/bin/python -m pytest tests/ -q` → **23 passed** (2026-11-01)

---

## 1. What the original project asked for

`STAGE_PLAN.md` defined Phase 1 as ten components:

| # | Component | Planned file | Core requirement |
|---|---|---|---|
| 1.1 | App shell + voice | `main.py`, `voice.py` | CustomTkinter window; mic button; **listen-to-reply button**, not automatic TTS |
| 1.2 | Personal assistant | `agent.py` | Local agent routing to tasks, notes, projects, calendar, launcher |
| 1.3 | Project monitor | `projects.py` | Scan all repos; status, last modified, git branch; one-click open |
| 1.4 | To-do tracker + alarms | `todo.py`, `calendar.py` | CRUD; daily/weekly/monthly; calendar alarms with sound |
| 1.5 | Launchers | `launcher.py` | One-click Study Studio + L&D Command Center; extensible |
| 1.6 | Released apps explorer | `explorer.py` | Scan `dist/`/`build/` for `.exe`; list, launch, desktop shortcuts |
| 1.7 | Notes | `notes.py` | Save/edit/delete free-form notes |
| 1.8 | ADHD-friendly design | `theme.py` | High contrast, large buttons, minimal clutter, focus mode |
| 1.9 | Packaging | PyInstaller spec | Single-file `.exe` in `dist/` |
| 1.10 | Simulated tenant data | — | Accept callcenter + sportacademy fixtures as client substitute |

Definition of done: `.exe` built and installed; voice input and listen-to-reply work; all repos visible; alarms function; notes CRUD works; simulated data accepted and tested; governance docs complete.

---

## 2. What actually exists

### 2.1 File inventory

| File | Lines | Contents |
|---|---:|---|
| `agent.py` | 331 | `Agent` class: Ollama JSON protocol, keyword fallback, direct routes |
| `tasks.py` | 273 | **Five classes**: `TasksManager`, `NotesManager`, `ProjectsManager`, `CalendarManager`, `LauncherManager` |
| `main.py` | 272 | CustomTkinter GUI: chat, mic, Listen/Stop, task/note panels, project buttons, launcher buttons, `.exe` scan |
| `voice.py` | 93 | `VoiceEngine`: mic detection, one-shot `record_phrase`, on-demand `speak_text`, `stop_speaking` |
| `console_os.py` | 60 | REPL: silent replies, `listen`, `stop` |
| `theme.py` | 32 | Color/font constants |
| **Source total** | **1,061** | |
| `tests/` | 262 | 23 tests (offline + live LLM) |
| `dist/CompanyOS` | — | 51 MB **ELF console binary** |

**Missing files that the final report claims exist:** `notes.py`, `projects.py`, `calendar.py`, `launcher.py`, `explorer.py`, `todo.py`. They were never written; their functionality is either crammed into `tasks.py` or absent.

### 2.2 What genuinely works today

- **LLM chat:** native Ollama on `127.0.0.1:11435`, `llama3.2:1b`, verified `100% GPU`. JSON directive protocol with keyword fallback when the server is down.
- **Chat GUI:** typed input, threaded reply, chat history in the panel.
- **On-demand TTS:** replies are silent by default; **🔊 Listen** speaks the latest reply; **⏹ Stop** interrupts. Console uses `listen` / `stop`.
- **Microphone detection:** PyAudio 0.2.14 installed; `arecord -l` shows USB Audio; `VoiceEngine.mic_available == True`. A full record→transcribe→agent→reply test was **not** performed.
- **In-memory tasks and notes:** create/list/complete/delete works within one session.
- **Project folder list:** names of directories under `cloned_repos/`, built once at startup; click opens the folder via `xdg-open`.
- **Launcher buttons:** exist in the UI but both targets are wrong (see F-05).
- **`.exe` scan:** globs `*.exe` under `cloned_repos/` and lists results; finds nothing on Linux.
- **Console binary:** starts, prints banner, replies, creates a task, exits cleanly (smoke-tested 2026-11-01).
- **Tests/CI:** 23/23 pass; `ci.sh` and GitHub workflow build the console binary.

### 2.3 What does not work

- No persistence. Every task, note, and calendar entry dies on exit.
- No alarms, notifications, or scheduler.
- Calendar is empty and never receives tasks.
- Project status is a folder name; no branch, dirty state, last commit, test status, or remote.
- Project list is static; a new repo requires an app restart.
- Both launchers fail (`Study-Studio/app.py` and `L-D-Command-Center/main.py` do not exist).
- `.exe` explorer cannot find Linux ELF/AppImage/desktop entries.
- GUI is not in the packaged binary (`CompanyOS.spec` excludes `tkinter` and `customtkinter`; entry is `console_os.py`).
- Binary is Linux ELF, not a Windows `.exe`.
- No GitHub, LinkedIn, n8n, Salesforce, Zendesk, resume, career coaching, approval gate, policy engine, or audit log.
- No settings, config file, secret storage, or logging.
- Hardcoded absolute paths break on any other machine.

---

## 3. Requirement-by-requirement matrix

Legend: **Met** = works and verified; **Partial** = some code, incomplete or unverified; **Not met** = absent; **False claim** = documented as done but not implemented.

| Requirement | Status | Evidence / gap |
|---|---|---|
| CustomTkinter app shell | **Met** | `main.py` builds a 2-column dark GUI |
| Mic input button | **Partial** | Button and `record_phrase` exist; device detected; no end-to-end transcription test |
| Listen-to-reply **button** (not automatic) | **Met** | `🔊 Listen` + `⏹ Stop`; console `listen` / `stop`; 3 regression tests |
| Local LLM assistant | **Met** | Ollama GPU, JSON protocol, fallback |
| Agent routes to tasks/notes/projects/calendar/launcher | **Partial** | Routes exist; calendar and launcher are broken/empty |
| Project monitor with status, last modified, git branch | **False claim** | `ProjectsManager.list_projects` only lists directory names |
| All 12 repos visible | **Partial** | Yes, but static and includes `__pycache__`/test dirs |
| One-click open project folder | **Met** | `xdg-open` on the folder |
| To-do CRUD | **Partial** | In-memory only; lost on restart |
| Daily/weekly/monthly recurrence | **Partial** | Stores a label; never schedules or repeats |
| Calendar alarms with sound | **Not met / False claim** | No scheduler, no notification, no sound; `tasks_by_date` never populated |
| Study Studio launcher | **False claim** | Runs `streamlit run app.py`; no `app.py`; project is Tauri/Next |
| L&D Command Center launcher | **False claim** | Runs `streamlit run main.py`; no `main.py`; project is Tkinter/Windows |
| Released-app explorer | **Partial** | `.exe` glob only; Linux binaries invisible; no launch action, only listing |
| Desktop shortcuts | **Not met** | No shortcut creation code |
| Notes CRUD | **Partial** | In-memory only |
| ADHD-friendly theme | **Partial** | Dark palette and large buttons; no focus mode, no reduced-clutter mode, no keyboard-first navigation |
| Single-file `.exe` | **False claim** | Linux ELF console binary, 51 MB; GUI excluded |
| Simulated tenant data integration | **Not met / False claim** | App has no tenant, callcenter, sportacademy, or fixture code |
| Governance docs G-6..G-12 | **Documents exist** | No executable control; human attestation still open |
| Final verification report | **Overstated** | Claims features that do not exist; see §5 |

---

## 4. Architecture assessment

### 4.1 Current shape

```
main.py ──► Agent ──► TasksManager     (in-memory list)
  │          ├──► NotesManager         (in-memory list)
  │          ├──► ProjectsManager      (hardcoded path, listdir)
  │          ├──► CalendarManager      (empty dict, unused)
  │          ├──► LauncherManager      (two broken commands)
  │          └──► VoiceEngine          (lazy TTS/STT)
  └──► direct Tk widgets
```

- **Single process, no service layer, no event bus, no storage.**
- **Five managers in one 273-line file**, each with a different concern.
- **No typed models**; dictionaries and strings carry all state.
- **No dependency injection**; managers instantiate each other's world directly.
- **No configuration**; absolute paths and env vars are scattered.
- **No concurrency model** beyond ad-hoc threads for LLM and speech.

### 4.2 Why it cannot grow into SigmaHelix as-is

The vision requires durable state, scheduled work, external integrations, approvals, and a career evidence graph. The current architecture has no place to put any of those without a rewrite. Adding them incrementally would produce a second monolith. The correct move is a **core extraction**: keep the GUI shell and voice UX, replace the manager layer with a storage-backed domain core and a policy-governed agent runtime.

### 4.3 What to keep

- The CustomTkinter visual language (dark, large controls, low clutter).
- The local-LLM-first design and GPU-only constraint.
- The on-demand TTS UX and its regression tests.
- The console REPL as a headless mode.
- The CI/packaging habit, upgraded to test the real GUI and real storage.

---

## 5. False or overstated claims (must be corrected)

| Claim in `stage-2/FINAL_REPORT.md` / `E2E_VERIFICATION` | Reality |
|---|---|
| "`notes.py` — Notes manager" | Does not exist; `NotesManager` is in `tasks.py` |
| "`projects.py` — Project monitor (all 11 repos)" | Does not exist; `ProjectsManager` lists names only |
| "`calendar.py` — Calendar (today/tomorrow/week/month)" | Does not exist; `CalendarManager` is empty and unused |
| "`launcher.py` — Study Studio + L-D launcher" | Does not exist; `LauncherManager` is in `tasks.py` and both commands fail |
| "`explorer.py` — Released apps explorer" | Does not exist; a `.exe` glob lives in `ProjectsManager` |
| "`todo.py` — To-do tracker" | Does not exist; `TasksManager` is in `tasks.py` |
| "Calendar with alarms (today/tomorrow/week/month)" | No alarm, no notification, no scheduler; calendar never populated |
| "Voice input icon + listen-to-reply playback" | Mic path unverified end-to-end; listen button now correct |
| "All features operational" | Tasks/notes are in-memory; launchers and calendar fail |
| "GUI framework built … requires system tkinter or PySimpleGUI" | GUI uses CustomTkinter and is **excluded** from the binary |
| "Packaged as `.exe`" | Linux ELF console binary |
| "13 repos listed (all 11 + test dirs)" | Lists directory names including `__pycache__`; not a status monitor |
| "Simulated data integrated" | No app code references tenant fixtures |
| "Governance fully resolved" | Documents exist; human attestation, auditor, and executable controls remain open |

**Impact:** the governance layer now contains a report that says capabilities exist when they do not. Any decision that trusts it (selling the app, claiming readiness, planning integrations) is built on a false premise. The report must be archived with a correction header, not silently edited.

---

## 6. Security and agent-risk audit

| Risk | Current state | Severity |
|---|---|---|
| No human approval before actions | The agent executes any parsed action immediately; launchers spawn subprocesses | **High** |
| Prompt injection | Untrusted text can be interpreted by the LLM; no instruction/data separation; no allowlist | **High** |
| Arbitrary subprocess execution | `LauncherManager` runs fixed commands, but a future tool layer would inherit no sandbox | **Medium** |
| Secrets | No keyring, no `.env` loader, no redaction; integrations would leak tokens into prompts | **High** (before integrations) |
| Auditability | No log of user commands, agent actions, or results | **High** |
| Data loss | In-memory state; no backup/export | **High** |
| Local model trust | GPU-only is correct; no output validation beyond JSON parse | **Medium** |
| Network exposure | App is local; Ollama bound to loopback | **Low** (current) |
| Dependency supply chain | `pip install` unpinned; no lockfile/hash check | **Medium** |

The current app is safe mainly because it can do very little. That changes the moment GitHub/Salesforce/Zendesk write access is added. **The policy engine and approval queue must land before the first write-capable integration**, not after.

---

## 7. Testing and CI audit

- **23 tests pass.** They cover: task/note CRUD, calendar ISO-date query, project listing, launcher path guards, voice lazy init, TTS discipline, live LLM intents, garbage-input resilience.
- **What is not tested:** persistence across restart, scheduler/alarm firing, dynamic project scan, real launcher execution, GUI rendering, microphone transcription, integration adapters, approval gates, resume generation.
- **CI:** `.github/workflows/ci.yml` installs deps, runs offline tests, optionally runs live tests, and builds the console binary. It does **not** run the GUI, does not test packaging of the GUI, and the live tests are allowed to fail (`|| true`).
- **Packaging:** `CompanyOS.spec` builds `console_os.py` with `console=True` and excludes GUI libraries. The artifact is therefore not the product the user sees.

**Verdict:** the test suite is a good regression net for the shallow layer that exists. It is not evidence for the feature set claimed in the final report.

---

## 8. Audit verdict

| Dimension | Grade | Rationale |
|---|---|---|
| Original scope completion | **~35%** | Chat, tasks, notes, folder list, TTS UX exist; alarms, status monitor, launchers, explorer, packaging, tenant data do not |
| Truthfulness of reporting | **Low** | Multiple nonexistent files and features claimed as complete |
| Engineering quality | **Prototype** | Clean small modules, but in-memory, hardcoded, no storage/config/logging |
| Security posture | **Not ready** | No approvals, no audit trail, no secret handling |
| Test credibility | **Moderate for current scope** | 23 real passing tests, but shallow coverage |
| Fitness for the SigmaHelix vision | **~15%** | The vision is a different product; the shell and LLM plumbing are reusable |

**Bottom line:** the previous agent built a usable demo, not a Company OS. The demo is worth keeping as a UX seed. The correct next step is not to patch it feature by feature; it is to extract a durable core, then build Tommy and the integrations on top of a policy-governed runtime.

See [`SIGMAHELIX_MASTER_PLAN_2026-11-01.md`](SIGMAHELIX_MASTER_PLAN_2026-11-01.md) for the rebuild sequence and [`TOMMY_CAREER_COACH_SPEC_2026-11-01.md`](TOMMY_CAREER_COACH_SPEC_2026-11-01.md) for the agent design.
