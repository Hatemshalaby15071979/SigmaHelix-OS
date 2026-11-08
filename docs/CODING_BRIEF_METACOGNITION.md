# Coding brief — make Tommy's reasoning visible, stop the truncation cascade, add the metacognition ledger

**Scope: this repository only (`SigmaHelix`). Do not read, edit, install into, or commit
anything under `cloned_repos/` except a throwaway sandbox project created under
`/tmp` for tests. Do not touch Helix-Codex, Helix-Prime, Helix-Education or any other
sibling project.**

**Status: analysis + specification. No code has been changed by this brief.**

---

## PART A — the prompt (copy this block into the coding agent)

> You are working in `SigmaHelix` only. Read, in this order, and do not grep the whole
> tree before you have read them:
>
> 1. `AGENTS.md` (definition of done, boundaries)
> 2. `CONSTITUTION.md` (§2 "Tommy always shows its thinking", §3 migrations, §4 audit)
> 3. `REPOMAP.md` (file map)
> 4. `docs/CODING_BRIEF_METACOGNITION.md` — Part B and C of this document
>
> Then implement the work packages in the order given (P0-1 … P0-5, then P1-1 … P1-4,
> then P2). Each package lists the exact files and the acceptance test. Do not
> reorder: P0-1 causes most of the other symptoms, and P1 depends on the schema from
> P0-3.
>
> Hard rules:
>
> - Do not change behaviour in Local or Hybrid mode. The multi-step loop and the
>   ledger's *model-visible* features stay Cloud-only; recording may be on in all
>   modes, but never let a Cloud-only capability run in Local/Hybrid.
> - Never print raw model JSON to the user. If a tool call cannot be parsed, that is
>   an error to report and retry, not a reply to display.
> - Never claim a file was created, a test passed, or a commit was made unless a tool
>   result in the same turn proves it. Add the deterministic guard in P0-5.
> - Never auto-apply a metacognition recommendation. The founder approves or rejects;
>   only whitelisted, reversible actions may be applied.
> - Do not invent metrics. Every number in a report comes from a SQL query over
>   `agent_turns` / `agent_steps`, and every recommendation cites turn ids.
> - Do not commit or push unless the founder's message explicitly says to. A commit
>   is a shared-state action.
> - Finish with `./scripts/ci.sh` green and the new tests from Part D passing.
>
> Deliverables: the code, the migration, the tests, the CLI verbs, the web endpoints,
> the UI tab, and updates to `README.md`, `CHANGELOG.md`, `AGENTS.md`, `REPOMAP.md`,
> `docs/adr/0011-agent-metacognition-ledger.md`.

---

## PART B — what is actually broken (evidence, not opinion)

The pasted session is not one bug. It is five defects that amplify each other. Each
one below is reproducible from the current `main` (`c71ac2f`).

### P0-1. Every cloud reply is capped at 500 tokens, so tool calls are cut in half

`src/sigmahelix/app/models.py:1175`

```python
payload = {
    "model": model,
    "messages": messages or [{"role": "user", "content": user_text}],
    "temperature": 0.2,
    "max_tokens": 500,
}
```

500 is the cap for **every** provider and every request, including `file_operations`
with a full CI YAML body and `edit_file` with a multi-line replacement. The token line
in the session (`· 500 out`) is this constant.

The cascade:

1. The model emits `{"action":"file_operations","content":"{...\"content\":\"name: CI\\n...`
2. The HTTP body ends mid-string. `finish_reason` is `length`; nothing checks it.
3. `Agent._parse_json` (`agent.py:766`) does `rfind("}")`, gets an incomplete object,
   `json.JSONDecodeError`, returns `None`.
4. `_agent_loop` (`agent.py:663-666`) treats a `None` parse as "the model answered in
   prose" and returns `f"🤖 {content}"`.
5. The user sees `🤖 {"action":"file_operations",...` and **nothing was executed**.
6. On the next turn the model has no record that the call failed, so it reports that
   the file exists, or admits it invented the earlier reads.

That is exactly the `🤖 {"action":"file_operations"...` and the truncated `"That"`
replies in the transcript. Fix this first; several "model is stupid" symptoms disappear
with it.

**Required**

- Replace the constant with a budget: `max_tokens` default 4096, and 8192 when the
  action is `file_operations` / `edit_file` / `run_command` / `audit_repo`. Put it in
  `Settings` (`core/config.py`) as `cloud_max_tokens`, validated (1024–16384).
- Read `choices[0].finish_reason`; when it is `length`, set `trace["truncated"]=True`
  and return a typed error, not a string.
- In `_agent_loop`, on `truncated`: retry the same step once with `max_tokens * 2`
  (bounded by the setting); if it still truncates, reply
  `"⚠️ The tool call was cut off by the token limit (needed more than N). Nothing was
  executed. Ask me to retry with a larger budget."`
- `_parse_json` must never be the thing that decides to show raw JSON. Add
  `_looks_like_action(text)` (starts with `{` or a fenced block and contains
  `"action"`); if it looks like an action and fails to parse, treat it as a tool-call
  error, not prose.

**Acceptance** — `tests/app/test_agent_loop.py::test_truncated_tool_call_is_retried_and_never_echoed`:
a fake provider returns `finish_reason="length"` with a half JSON; the loop retries,
the second call returns a complete `file_operations`; the file exists; the reply
contains no `{"action"`. A second test asserts the 8192 budget is used for
`file_operations`.

### P0-2. "Thinking" is empty for the model you actually use, and `steps` are never rendered

Three separate causes:

1. `models.py:1206` reads `message["reasoning_content"]` or `message["reasoning"]`.
   `deepseek-chat` returns **neither** — only `deepseek-reasoner` does. So
   `trace["thinking"]` is `""` on every turn in the pasted session.
2. The loop *does* record a step list: `agent.py:673` and `agent.py:696` set
   `last_trace["steps"]`. No surface reads it:
   - `webui/static/app.js:97` — `if (!trace || (!trace.thinking && !trace.total_tokens)) return;`
     and line 99 renders only `trace.thinking`. A steps-only trace is dropped entirely.
   - `console.py:26-40` — thinking + tokens only.
   - `ui.py:922-941` — thinking + tokens only.
3. `steps` is a list of one-line strings (`f"{action}: {first line}"`), with no
   arguments, no duration, no success flag — not enough to audit a decision.

This violates `CONSTITUTION.md` §2 ("Tommy always shows its thinking and token usage;
hiding it is not allowed").

**Required — the honest version.** You cannot obtain hidden chain-of-thought from a
non-reasoning model, and you must not pretend to. Show a **reasoning trail**:

- Extend the loop protocol: every action JSON may carry `"plan": "<one line: why this
  action, what it expects>"`. Record it. This is the model's own stated reason, not a
  reconstruction.
- `last_trace["steps"]` becomes structured:

```python
{"seq": 1, "action": "audit_repo", "plan": "find out what is missing",
 "args": "Helix-Education", "ok": True, "summary": "AUDIT — 42 files, no CI",
 "duration_ms": 38}
```

- Add `finish_reason`, `truncated`, and `evidence` (`files_changed`, `commands`,
  `tests.exit_code`) to `last_trace`.
- Render in all three surfaces: `thinking` (when present, labelled *provider
  reasoning*), then `plan`, then a `<details>` timeline of steps with action / args /
  result / ms / ✓✗, then tokens, then a red **truncated** badge when
  `trace["truncated"]`.
- Fix the `app.js:97` gate to `if (!trace) return;` and render steps even when
  `thinking` and tokens are absent.

**Acceptance** — `tests/app/test_trace.py::test_steps_are_recorded_with_plan_and_args`
and a web test asserting `state.chat()` returns `trace["steps"][0]["action"]`. Manual:
one cloud turn shows ≥1 step in the UI.

### P0-3. The agent has no memory across turns or restarts

`agent.py:261` `self.history = []`; `agent.py:376` sends `self.history[-8:]`;
`agent.py:783` stores `content[:400]`; capped at 10 entries. It is **RAM only**.

So the model's entire context is ≤3.2 KB of the last few turns, discarded on restart.
That is why it says *"I don't have the transcript… each turn I only see the current
message"* — that statement is literally true. It also explains the self-contradictions
between turns ("I read the repo" → "I never read it").

**Required** — persist the conversation and the reasoning trail. This is also the
substrate for the metacognition feature, so do it once, properly (see Part C for the
schema).

- New `app/metacognition.py` with `Ledger` (write + query) over the new tables.
- `Agent.process_command` opens a turn, records route/model/outcome/tokens/steps, and
  closes it in a `finally` so failures are recorded too.
- `_build_messages` loads the last N turns (N=12) from the ledger when in-memory
  history is empty (after restart), with a per-message cap of 4000 chars — not 400.
- Keep the in-memory list as a fast path; the DB is the source of truth.

**Acceptance** — `tests/app/test_metacognition.py::test_conversation_survives_a_restart`:
agent A records 3 turns; a new `Agent` with the same DB sees them in `_build_messages`;
`GET /api/metacognition/turns` returns them oldest-first.

### P0-4. The readiness score and the readiness verdict come from two different rubrics

`app/tools.py:423` computes `missing` and `verdict` from eight checks
(readme, tests, ci, container, env_config, healthcheck, lockfile, build).
`app/tools.py:492` prints `score` from a completely different function,
`core/storage/project_scanner.py:272 _health_score`, which only penalises
readme/manifest/entrypoint/git/dirty/artifacts.

Hence the output the founder caught:

```
⚠️ RTA_command_center · score 100
   missing: tests, env_config, build-or-container
```

100/100 with three missing requirements. And `dirty` subtracts 5, so committing
`.env.example` moved Helix-Education 95 → 100 — git cleanliness is not a production
criterion.

Two more defects in the same output:

- The check key `env_config` is printed verbatim, but `_has_env_template`
  (`tools.py:385`) checks for `.env.example`. The model read the label literally and
  told the founder *"there is no env_config in Helix-Education"* — true, useless, and
  the start of a hallucination spiral.
- `format_assessment` prints `missing` for a not-ready project but `has readme, tests,
  CI, env template and a build path` for a ready one, with no weights, so "why 95?"
  is unanswerable.

**Required**

- One rubric. Compute `score` in `assess_project` as a weighted sum of the same
  `checks` that produce `missing`; `verdict == "production-ready"` iff `missing == []`
  iff `score == 100`. Suggested weights: readme 10, tests 25, ci 20, env template 10,
  build-or-container 25, healthcheck 5, lockfile 5. Sum must be 100.
- Do **not** include git `dirty` in the score. Report it on its own line as context.
- Rename the human label to `env template (.env.example)`, keep the internal key.
- Print the rubric once per report: `score = sum of passed checks (readme 10, tests 25,
  …)`, and for each project list the points lost, not just the key.
- `_handle_assess_projects` (`agent.py:1648`) must use this single function; the
  `score` field must no longer be taken from `scan.health_score` for readiness.

**Acceptance** — `tests/app/test_tools.py::test_score_and_verdict_cannot_disagree`
parametrised over fixture projects: `score == 100 ⇔ verdict == "production-ready" ⇔
missing == []`; a project missing tests scores < 100; `dirty` does not change the score.

### P0-5. Nothing binds a claim to evidence

In the session the model said it had read `RTA_command_center` (CI file,
`tooling/verify_requirements.py`), then later said it had read nothing. It also
reported *"Second project — 100"* with no project name. Nothing in the loop checks that
a final answer's claims are backed by a tool result from that turn.

**Required**

- Deterministic guard in `_agent_loop` before returning a final answer: if `reply`
  matches `\b(created|wrote|edited|fixed|committed|passing|passes|green|100)\b` and
  `steps` contains no successful tool call of the matching kind, do **not** return it.
  Append a system-style user message: *"Your answer claims X but no tool result in this
  turn supports it. Either call the tool or remove the claim."* Allow at most one
  correction round, then return the answer with a visible
  `⚠️ unverified claim: <matched phrase>` prefix.
- Require `evidence` in the final JSON: `{"action":"final","reply":"…","evidence":
  ["run_tests:exit=0","edit_file:src/calc.py"]}`. Missing/empty evidence with a
  success claim → same correction round.
- `_handle_file_operations` and `_handle_edit_file` already return concrete strings;
  make them return a machine-readable prefix (`OK file=… bytes=…`) so the guard can
  match without prose parsing.

**Acceptance** — `tests/app/test_agent_loop.py::test_unverified_claim_is_blocked`:
a fake model returns `{"action":"final","reply":"Fixed it, tests pass."}` with zero
tool calls; the loop asks once more; on the second identical answer the reply is
prefixed `⚠️ unverified claim`.

---

## PART C — the metacognition feature (design)

### C.1 What it is, in one sentence

Every turn Tommy takes is written to an append-only, hash-chained ledger; a periodic
report reads that ledger and produces **evidence-backed recommendations about Tommy
itself** — which skills/plugins/tools to create, update or delete — and the founder
approves or rejects each one. Tommy never applies its own recommendation.

### C.2 Storage — migration 16

Add `Migration(version=16, name="agent_metacognition_ledger_v16", …)` after the
`task_questions_v15` entry (`core/storage/migrations.py:663`). Extend
`_REQUIRED_TABLES` in `core/storage/backup.py` (currently ends at 15, line ~287).

```sql
CREATE TABLE agent_turns (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL CHECK(length(trim(tenant_id)) > 0),
    session_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL CHECK(turn_index >= 0),
    started_at TEXT NOT NULL,
    ended_at TEXT,
    user_text TEXT NOT NULL,
    route TEXT NOT NULL,          -- direct|task|tool|llm|loop|keyword
    model_mode TEXT NOT NULL,     -- local|cloud|hybrid
    provider TEXT,
    model TEXT,
    plan TEXT NOT NULL DEFAULT '',
    reply TEXT NOT NULL DEFAULT '',
    outcome TEXT NOT NULL DEFAULT 'unknown'
        CHECK(outcome IN ('unknown','answered','acted','blocked','failed','refused')),
    error TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    truncated INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0,1)),
    evidence_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(evidence_json)),
    proof_hash TEXT NOT NULL CHECK(length(proof_hash) = 64),
    PRIMARY KEY (id),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, session_id, turn_index)
);
CREATE INDEX idx_agent_turns_time ON agent_turns(tenant_id, started_at);
CREATE INDEX idx_agent_turns_outcome ON agent_turns(tenant_id, outcome, started_at);

CREATE TABLE agent_steps (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    seq INTEGER NOT NULL CHECK(seq > 0),
    kind TEXT NOT NULL CHECK(kind IN
        ('plan','model_call','tool_call','tool_result','decision','final','error')),
    action TEXT NOT NULL DEFAULT '',
    plan TEXT NOT NULL DEFAULT '',
    args TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    ok INTEGER NOT NULL DEFAULT 1 CHECK(ok IN (0,1)),
    duration_ms INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(payload_json)),
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (tenant_id, turn_id, seq),
    FOREIGN KEY (tenant_id, turn_id) REFERENCES agent_turns(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE agent_feedback (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('good','pushback')),
    reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'user' CHECK(source IN ('user','heuristic')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (tenant_id, turn_id) REFERENCES agent_turns(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE agent_recommendations (
    id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    period TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN
        ('new_plugin','update_plugin','delete_plugin','skill','prompt','tool','ux','config')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK(status IN ('proposed','approved','rejected','applied')),
    decided_at TEXT,
    decision_note TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (id)
);
```

`down_sql` drops the four tables (no triggers needed; these are append-only by
convention, and `agent_turns` has a cascade for steps). Add
`rollback_requires_empty=("agent_turns","agent_steps","agent_feedback","agent_recommendations")`.

**Logproof.** Reuse the existing hash-chained `audit_log`
(`core/storage/audit.py:124`) rather than building a second chain. Per completed turn:

```python
proof = sha256(canonical_json(turn_record_without_proof))     # 64 hex
audit.append("agent.turn.completed", "agent_turn", turn_id,
             {"session": sid, "turn": n, "route": route, "outcome": outcome,
              "model": model, "tokens": total, "steps": len(steps),
              "proof": proof}, tenant_id=tenant)
```

`sigmahelix ledger verify` then (a) runs `AuditLog.verify()`, (b) recomputes each
`proof` from the stored row and compares it to the audit payload, and (c) reports the
first mismatch. That is a real proof: id + timestamp + chain position + content hash.

### C.3 Module — `src/sigmahelix/app/metacognition.py`

Public API (all tenant-scoped, all through `Database`):

```python
class Ledger:
    def open_turn(self, session_id, user_text, route, model_mode) -> str
    def add_step(self, turn_id, kind, action="", plan="", args="", summary="",
                 ok=True, duration_ms=0, payload=None) -> None
    def close_turn(self, turn_id, *, reply, outcome, error=None, tokens=(0,0,0),
                   duration_ms=0, truncated=False, evidence=None) -> None
    def turn(self, turn_id) -> dict          # with steps
    def turns(self, since=None, limit=50) -> list[dict]
    def add_feedback(self, turn_id, verdict, reason="", source="user") -> None
    def report(self, period="7d") -> dict    # deterministic metrics only
    def recommend(self, period="7d") -> list[dict]   # deterministic rules
    def decide(self, rec_id, decision, note="") -> dict
    def verify(self) -> dict                 # chain + per-turn proof
```

**Report metrics (all SQL, no model):**

| metric | definition |
|---|---|
| `turns` | count in period |
| `outcomes` | group by `outcome` |
| `success_rate` | `(answered + acted) / turns` |
| `truncation_rate` | `sum(truncated) / turns` |
| `tool_calls` | `agent_steps` where `kind='tool_call'`, grouped by `action` |
| `tool_failure_rate` | per action, `ok=0 / total` |
| `pushback_rate` | `agent_feedback` verdict `pushback` / turns |
| `mean_steps_success` | avg steps for `outcome in ('answered','acted')` |
| `tokens_per_outcome` | avg `total_tokens` grouped by outcome |
| `repeated_intents` | normalised `user_text` (lowercase, strip punctuation, drop stop-words) appearing ≥2 times with ≥1 non-success |
| `recovered` | turns where an earlier failure on the same intent later succeeded |

**Recommendation rules (deterministic, each cites turn ids):**

| rule | kind | when |
|---|---|---|
| `truncation_rate > 0` | `config` | raise `cloud_max_tokens` / use streaming |
| action with `failure_rate ≥ 0.5` and `n ≥ 2` | `tool` | fix that tool first |
| `pushback` on turns with `steps == 0` | `prompt` | "answer only after a tool call or an explicit 'I don't know'" |
| repeated intent, ≥3 turns, no success | `skill` or `new_plugin` | add a capability for that intent |
| plugin with 0 uses in ≥50 turns | `delete_plugin` | candidate for removal (report only) |
| `mean_steps_success > 8` | `prompt` | the plan step is too vague |
| provider error rate > 0 | `config` | provider/model mismatch |

**Narrative (optional, and strictly bounded).** If the founder wants prose, one cloud
call receives the report JSON and must return text that cites `rec.id`s. Before
display, a validator checks that every number in the prose appears in the JSON; if not,
the prose is discarded and the deterministic report is shown alone. This is how you get
a readable report without letting the model invent metrics.

**"Learning on the founder's own language" — the honest answer.** There is no training
loop and there must not be a silent one. What the product can do:

- approved turns + founder rewrites become few-shot examples in a *versioned* skill
  file (`~/.config/sigmahelix/skills/Hatem_specific/`), applied only after explicit
  approval;
- rejected recommendations are kept as negative evidence so the same proposal is not
  repeated;
- nothing is sent anywhere; the ledger is local.

Do not claim the model is "training". It is accumulating an auditable record and a
curated style corpus, which is the only defensible version in a local-first app.

### C.4 Approval workflow

1. `sigmahelix ledger report --period 7d` → metrics + `proposed` recommendations.
2. Founder approves/rejects each: CLI `sigmahelix ledger decide <rec-id> approve|reject
   --note "…"`, or the UI buttons.
3. `apply` is a separate, explicit step and only supports whitelisted kinds:
   - `config` → write the setting (audited);
   - `delete_plugin` / `update_plugin` → `PluginRegistry` toggle (audited);
   - `skill` → write a file under the user skills dir (audited, reversible by deleting
     the file);
   - `prompt` / `tool` / `new_plugin` → **never auto-applied**; produce a task for the
     coding agent with the evidence attached.
4. Every decision and application appends to `audit_log`.

### C.5 Surfaces

- **CLI** (`cli.py`): `sigmahelix ledger verify`, `… report [--period 7d] [--json]`,
  `… show <turn-id>`, `… feedback <turn-id> good|pushback [--reason]`,
  `… decide <rec-id> approve|reject`.
- **Web** (`webui/server.py`, next to the existing `/api/*` GET block at line ~293 and
  `_dispatch_post` at ~336):
  - `GET /api/metacognition?period=7d` → report + recommendations + recent turns
  - `GET /api/metacognition/turns/<id>` → turn + steps
  - `POST /api/metacognition/feedback` `{turn_id, verdict, reason}`
  - `POST /api/metacognition/decide` `{rec_id, decision, note}`
  All token-protected like the existing endpoints.
- **UI** (`webui/static/index.html` nav at line 21, `app.js`, `style.css`): a **Mind**
  tab — period selector, outcome strip, tool-failure table, "recurring failures" list,
  recommendation cards with Approve / Reject, and a per-turn timeline that reuses the
  trace renderer from P0-2.

---

## PART D — tests (write these; they are the definition of done)

| file | tests |
|---|---|
| `tests/core/test_migrations.py` | v16 up/down, contiguous versions, backup required-tables includes the four new tables |
| `tests/core/test_audit.py` | turn proof is appended; tampering with `agent_turns.proof_hash` is detected by `ledger verify` |
| `tests/app/test_metacognition.py` | turn/step round-trip; report maths on a synthetic fixture; truncation rate; pushback rate; repeated intents; recommendation rules produce the expected kinds; `decide` transitions; nothing auto-applies; conversation survives a restart |
| `tests/app/test_agent_loop.py` | truncated call retried, never echoed; large `file_operations` uses the big budget; unverified claim blocked; `plan` recorded per step |
| `tests/app/test_trace.py` | steps include action/args/plan/ok; `finish_reason` and `truncated` present; empty thinking still renders steps |
| `tests/app/test_tools.py` | score ⇔ verdict ⇔ missing invariant; dirty does not move the score; label is "env template" |
| `tests/app/test_webui.py` | new endpoints require the token; feedback and decide round-trip; `state.chat()` returns steps |

Run `./scripts/ci.sh` (format → lint → mypy → compile → pytest → CLI smoke). The gate
is the deliverable, not a suggestion.

---

## PART E — order of work and why

1. **P0-1** truncation. Without it, every other fix is tested against a broken loop.
2. **P0-2** trace rendering. The founder cannot verify any of this until it is visible.
3. **P0-3** ledger + persistence. Schema first, because P1 writes to it.
4. **P0-4** one readiness rubric. Small, isolated, immediately visible in the transcript
   the founder already has.
5. **P0-5** evidence guard. Depends on structured steps from P0-2.
6. **P1** report, recommendations, approval, CLI, web, UI.
7. **P2** docs + ADR.

Do not batch P1 into the same commit as P0. Two commits minimum: `fix(agent):` for
P0-1…P0-5, `feat(metacognition):` for P1/P2.

---

## PART F — what NOT to do

- Do not add a second hash chain. `audit_log` already is one.
- Do not put readiness logic in two places again. One function, one score.
- Do not let the report call the model to compute numbers.
- Do not let `apply` touch source code. Code changes go through the coding agent with
  the founder's explicit instruction.
- Do not enable the cloud loop in Local/Hybrid. Recording yes, cloud behaviour no.
- Do not touch `cloned_repos/`. Tests use `tmp_path`; manual E2E uses a sandbox under
  `/tmp` via `SIGMAHELIX_PROJECTS_DIR`.
- Do not commit or push without an explicit instruction in the founder's message.
