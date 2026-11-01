# Kill-Switch and Incident Tabletop

**Status:** Complete — five scenarios recorded; 0/5 passed; kill-switch procedure exercised; implementation gap open  
**Purpose:** Prove that the Owner can detect, contain, and preserve evidence in the five highest-risk scenarios before Stage 0 closes.  
**Participants:** Owner (Incident Commander), a scribe (human or agent with no decision authority), and an advisor if available.  
**Duration:** One session per scenario, or one combined session if attention holds.  
**Rule:** This is a discussion-based exercise. Do not touch production systems or real customer data.

**Solo-owner constraint:** There is no second human approver (D-011). Scenarios that require a second human will fail that part of the pass criteria by design. Record the failure and the compensating block; do not mark the scenario passed. The exercise tests detection, containment, and evidence preservation, not the existence of a role the Owner declined to create.

**Session 1:** 2026-10-23  
**Incident Commander:** HatemShalaby  
**Scribe:** Agent (no decision authority)  
**Advisor:** none  
**Status:** Scenarios 1–5 recorded. Tabletop complete. 0/5 passed. The kill-switch procedure was exercised; the executable control is absent. Remediation actions remain open.

---

## 1. Setup

Before starting, have open:

- `AUTHORITY_MATRIX.yaml`
- `INCIDENT_PLAN.md`
- `RISK_TAXONOMY.yaml`
- `EVIDENCE_STANDARD.md`
- The kill-switch definition in `INCIDENT_PLAN.md` §6
- A blank incident record

Confirm:

- who is the Incident Commander;
- who is the scribe;
- how the kill switch is triggered;
- where evidence is preserved;
- who can revoke credentials;
- how the Owner reaches counsel.

---

## 2. Scenario 1 — Forged approval or evidence

**Inject:** “A design partner says the report you sent shows an approval that they never gave. The report hash matches the pack, but the approval record looks altered.”

**Questions:**

1. How do you detect whether the approval or the evidence was altered?
2. What do you preserve first?
3. Do you stop distribution? How?
4. Who do you notify, and who decides?
5. What claim or report must be corrected?
6. What test prevents recurrence?

**Pass criteria:**

- the response distinguishes artifact tampering from approval tampering;
- evidence is preserved before repair;
- distribution stops;
- the claims registry and affected report are corrected;
- a regression test is added.

**Scenario 1 response record — recorded**

- **Q1 — detection:** Owner would check the report and pack hashes. Approval is outside the seal, so the pack cannot prove whether approval changed. The Owner would preserve the records and compare them with the design partner’s approval record.
- **Finding:** artifact tampering is detectable from the pack hash; approval tampering is not detectable from the pack. No separate approval system exists that can independently verify the partner’s approval. This is a P0-2 gap.
- **Q2 — preservation:** Owner would preserve the original report, evidence pack, approval record or token, audit ledger, and access logs; hash each; store them in a write-once or access-controlled location; work from copies only.
- **Finding:** no defined preservation location exists. This is a recorded gap.
- **Q3 — distribution stop:** Owner would stop all further sends, tell the design partner to stop using the report and preserve their copy, revoke any access link, and hold any replacement until the evidence is reviewed. The Owner would not ask the partner to delete the report.
- **Finding:** distribution control is manual. No automated send or link-revocation control exists.
- **Q4 — notification and decision:** Owner decides. Notify the design partner and preserve the notification record. Involve counsel if legal or contractual exposure may exist; counsel is not yet named. Notify an auditor if an external claim is involved; the auditor role is vacant. Notify a regulator if required after assessing the facts, with counsel if available. Record every notification.
- **Finding:** counsel is not named and the auditor role is vacant. The Owner is the sole decision-maker; no second approver exists. These are recorded gaps.
- **Q5 — claim and report correction:** Owner would retract the report, mark it superseded, check and correct any related approval or sealed-evidence claims in the claims registry, record that the external send was unauthorized because 0 claims are approved for external use, and issue no replacement until the approval and evidence are verified.
- **Finding:** the external send itself is a governance breach. There is no automated claims-registry gate preventing an unauthorized external report.
- **Q6 — recurrence test:** Owner would add two regression tests: changing approval after sealing must make verification fail; an external report must be blocked when the claims registry has zero approved claims. The approval test is an open action because it will fail until P0-2 is fixed.
- **Finding:** the approval regression test cannot pass on the current build. It becomes a P0-2 acceptance test, not a completed control.
- **Scenario 1 outcome:** Not passed. Partial response with open actions. The response distinguishes artifact tampering from approval tampering, but the current build cannot detect approval tampering; preservation location and automated distribution/claims gates do not exist; the regression tests are planned, not added.

---

## 3. Scenario 2 — Stolen Owner session

**Inject:** “A login from an unfamiliar location used the Owner’s session to approve a payment and a production release.”

**Questions:**

1. How do you revoke the session and the credentials?
2. How do you stop the payment and the release?
3. How do you determine what the attacker approved?
4. How do you preserve the approval and ledger records?
5. Who do you notify?
6. How do you recover the Owner account without repeating the compromise?

**Pass criteria:**

- session and credentials are revoked;
- payment and release are stopped;
- all actions from the session are identified;
- evidence is preserved;
- recovery uses a separate, verified channel;
- a second approver is required before resuming R3.

**Scenario 2 response record — recorded**

- **Q1 — revoke session and credentials:** Owner would revoke all active sessions by clearing the session store; rotate the Owner password and any tokens or API keys; disable the account until recovery is complete; and record what was revoked and when.
- **Finding:** the current system can clear sessions but has no revocation list or token rotation. This is the P0-6 gap.
- **Q2 — stop payment and release:** Owner would invoke the documented kill switch for payments and deployment, freeze the payment queue and release pipeline, revoke their credentials, and require Owner verification before resuming. No live payment or deployment system exists today; the authority matrix is the current control.
- **Finding:** the kill switch is documented, not implemented as a live control. Resuming payment or release is R3 and remains blocked without a second approver.
- **Q3 — determine what was approved:** Owner would pull and preserve the session’s audit events, approval records, payment and release records, and ledger entries; correlate them by session ID, actor ID, timestamp, and approval token; compare against the ledger and any external anchor.
- **Finding:** there is no external anchor, approval is outside the seal, session-to-action binding is unconfirmed, and there is no revocation list.
- **Q4 — preserve approval and ledger records:** Owner would capture before repair; preserve approval records and tokens, ledger, session store, access logs, and payment and release records; hash each item; work from copies; keep originals in a write-once or access-controlled location with chain of custody recorded; not edit the ledger or overwrite backups.
- **Finding:** no defined preservation location exists.
- **Q5 — notification:** Owner decides. Notify the payment provider or bank to freeze or reverse the payment, and the deployment platform to lock the release. Notify the design partner if their data or report is affected. Involve counsel (not yet named) and an auditor if an external claim is involved (role vacant). Notify law enforcement or a regulator after assessing the facts with counsel. Record every notification.
- **Finding:** counsel is not named and the auditor role is vacant.
- **Q6 — account recovery:** Owner would recover through a separate, verified channel; reset the password; rotate all credentials and tokens; review active sessions and devices; confirm the attacker no longer has access; and record the recovery.
- **Finding:** there is no MFA, device binding, revocation list, or second approver.
- **Scenario 2 outcome:** Not passed. Session revocation, payment/release stop, action reconstruction, evidence preservation, and recovery are planned but not implemented. The second-approver requirement fails by design under D-011; R3 remains blocked.

---

## 4. Scenario 3 — Prompt-injected agent with outbound tools

**Inject:** “An agent summarizes a prospect’s web page. The page contains hidden text instructing the agent to email the customer list to an external address. The agent has an outbound email tool.”

**Questions:**

1. What stops the send before it happens?
2. Is the agent inside an envelope? Which one?
3. What content is treated as data versus instruction?
4. How do you identify what the agent read and what it attempted?
5. How do you revoke the tool and preserve evidence?
6. What test proves the injection is blocked next time?

**Pass criteria:**

- the outbound tool is allowlisted and capped;
- retrieved content cannot issue instructions;
- the attempt is logged before the send;
- the kill switch or envelope stop works;
- the agent’s memory is checked for injected instructions;
- an injection regression test is added.

**Scenario 3 response record — recorded**

- **Q1 — stop the send:** Owner would keep outbound tools disabled by default. Enable them only with an allowlisted destination, per-action Owner approval, an envelope cap, and a pre-send gate that logs each attempt. Treat retrieved web content as data, not instructions.
- **Finding:** the current build has no outbound agent tool or envelope runtime. Outbound actions are disabled by absence, not by a tested gate.
- **Q2 — envelope:** No. No envelope runtime exists. The agent is a local prototype with no autonomy level, spend cap, tool allowlist, or tested stop control. Until an envelope exists, it is limited to local read-only prototype work and cannot take outbound actions.
- **Finding:** no envelope runtime exists. This is a control gap, not an enforced boundary.
- **Q3 — data versus instruction:** Only the Owner’s system and developer instructions are instructions. Web pages, emails, documents, tool output, and retrieved content are data. The agent must never follow instructions found in data.
- **Finding:** the current build has prompt wording but no enforced content boundary.
- **Q4 — identify read and attempted actions:** Owner would log every retrieval and every tool attempt before execution, recording the URL or source, content hash, agent ID, timestamp, and decision; preserve the logs.
- **Finding:** audit events are appended after actions; there is no retrieval logging or pre-send gate.
- **Q5 — revoke tool and preserve evidence:** Owner would disable the outbound tool at the policy or envelope layer, revoke its credentials, stop the agent, preserve the retrieval logs, attempt logs, access logs, and current memory, hash each item, and keep the originals.
- **Finding:** no tool runtime or envelope exists; no defined preservation location exists.
- **Q6 — injection regression test:** Owner would add an injection regression test with hidden instructions in retrieved content. The test must assert that no outbound send occurs, an attempt is logged before the send, the pre-send gate blocks it, the agent’s memory is unchanged, and the kill switch stops the run. The current build has no outbound tool, so this is an acceptance test for the envelope.
- **Finding:** the test cannot run against the current build because no outbound tool or envelope exists. It becomes an envelope acceptance test, not a completed control.
- **Scenario 3 outcome:** Not passed. Outbound tools are disabled by absence, not by a tested gate. No envelope runtime, no enforced data/instruction boundary, no pre-action retrieval logging, no pre-send gate, no defined preservation location, and no injection regression test exist. The response defines the required controls; the build does not implement them.

---

## 5. Scenario 4 — Ledger corruption or truncation

**Inject:** “The ledger verification fails at event 412. The last anchor was created before event 400. The file is shorter than the last backup.”

**Questions:**

1. How do you distinguish corruption from truncation or rewrite?
2. What evidence do you preserve?
3. How do you compare against the external anchor?
4. Which reports or claims depend on the affected range?
5. Do you stop operations? Which ones?
6. How do you restore without destroying the evidence?

**Pass criteria:**

- the failure is detected by verification, not by trust;
- the anchor comparison localizes the break;
- the affected reports are identified;
- restoration works from a backup without overwriting the original;
- the incident is recorded;
- no claim is made until the evidence is re-verified.

**Scenario 4 response record — recorded**

- **Q1 — distinguish corruption from truncation or rewrite:** Owner would run ledger verification and compare the chain, line count, each event hash, the last event ID and hash, and the last external anchor. A bad hash at event 412 indicates corruption at or before that event; a shorter file with a valid prefix suggests truncation; a valid chain with a different hash suggests a rewrite.
- **Finding:** the current build has local hash-chain verification but no external anchor, so a clean truncation after the last line or a full rewrite cannot be independently distinguished.
- **Q2 — preserve evidence:** Owner would preserve the current ledger file, its hash, line count, last event ID and hash, and the verification output; the backups, anchor records, process logs, filesystem metadata, and any restored copies; not edit or overwrite the original; keep originals in a write-once or access-controlled location; and work from copies.
- **Finding:** no defined preservation location exists.
- **Q3 — compare against the external anchor:** Owner would fetch the anchor record from the independent store and compare the last anchored event ID and hash against the same event in the ledger. A match confirms the prefix up to the anchor is intact; a missing or different event localizes the break between the anchor and the current head.
- **Finding:** the current build has no external anchor, so this comparison cannot be performed. The local chain is the only reference.
- **Q4 — affected reports and claims:** Owner would identify every sealed report, evidence pack, external claim, approval, and dashboard metric derived from events after the last valid anchor; mark them stale or superseded; suspend external use; list the affected claims-registry entries; and make no claim until the evidence is re-verified.
- **Finding:** the claims registry exists, but there is no event-to-report or event-to-claim dependency map.
- **Q5 — stop operations:** Owner would stop all writes to the affected ledger, stop report generation from it, stop external claims and distribution, and stop any action whose evidence depends on the affected range. Local read-only work and unrelated ledgers continue.
- **Finding:** the server and CLI can keep writing to the ledger, and nothing stops automatically when verification fails. This is a fail-open gap.
- **Q6 — restore without destroying evidence:** Owner would restore from a known-good backup into a new file, never overwrite the original, verify the restored chain against the external anchor, record the gap between the last good event and the restored head, append a restoration event, and keep the corrupted original and every copy preserved.
- **Finding:** there is no external anchor, no tested restore procedure, and no automatic write stop.
- **Scenario 4 outcome:** Not passed. Local verification detects a bad hash or a truncated line, but without an external anchor a clean truncation after the last line or a full rewrite is invisible. There is no defined preservation location, no event-to-report or event-to-claim map, no fail-closed write stop, and no tested restore procedure. The incident is not recorded in an incident log.

---

## 6. Scenario 5 — Fraudulent invoice or bank change

**Inject:** “A vendor emails a new bank account and an urgent invoice. The amount is within the normal range. The email domain is one character off.”

**Questions:**

1. How do you verify the bank change out of band?
2. Who can approve the payment?
3. What stops the payment if the Owner is unavailable?
4. How do you preserve the email and the approval record?
5. Who do you notify?
6. What control prevents a repeat?

**Pass criteria:**

- bank changes require callback verification to a known contact;
- payment is Owner-executed, not agent-executed;
- a suspicious request is frozen, not expedited;
- evidence is preserved;
- the vendor and bank are notified through verified channels;
- a second human is required for payment above the threshold.

**Scenario 5 response record — recorded**

- **Q1 — verify the bank change out of band:** Owner would call the vendor using a known number from an existing contract or accounting record, not contact details in the email; confirm with a second vendor contact if possible; and require a signed bank-change form.
- **Finding:** there is no vendor or contract system, verified contact database, or payment system.
- **Q2 — who can approve:** The Owner only. No agent, assistant, or employee can approve or execute a payment. Approval must be explicit, recorded, and tied to the verified invoice and bank change.
- **Finding:** no payment system exists; the authority matrix is Owner-only; no agent has a payment tool. Because there is no second human, payment above the threshold fails the pass criterion by design and remains blocked.
- **Q3 — Owner unavailable:** Nothing proceeds. The payment waits because authority is Owner-only. There is no delegate, agent, or emergency override. The vendor is told the payment is delayed.
- **Finding:** there is no payment system or backup approver, and the authority matrix forbids delegation. This is a deliberate safety block with a business-continuity cost.
- **Q4 — preserve email and approval record:** Owner would preserve the original email with full headers, the one-character-off domain, any attachments, the invoice, the bank-change request, the callback notes, the signed form, the approval record, and the ledger events; hash each item; keep originals in a write-once or access-controlled location; work from copies; and not click links or open attachments.
- **Finding:** no defined preservation location exists.
- **Q5 — notification:** Owner would notify the vendor through the verified phone number, not the email; notify the bank or payment provider if any payment or bank change was submitted; involve counsel (not yet named) and the auditor if an external claim is involved (role vacant); and report to law enforcement or a regulator after counsel assesses the facts if fraud is confirmed. Every notification is recorded. The suspected fraudster is not tipped off.
- **Finding:** counsel is not named and the auditor role is vacant.
- **Q6 — prevent a repeat:** Owner would maintain a verified vendor master with bank details and callback numbers; require a signed bank-change form; verify changes by calling a known number; require Owner approval plus a second human above the threshold; block email-only changes; train on lookalike domains; and add a vendor-change regression test.
- **Finding:** there is no vendor master, and the second-human control is blocked by design under D-011.
- **Scenario 5 outcome:** Not passed. Owner-only authority and the absence of a payment system prevent execution, but the pass criteria require a second human above the threshold, which is unavailable by D-011. There is no vendor master, verified contact database, payment system, defined preservation location, or vendor-change regression test. The response is a policy plan, not implemented controls.

---

## 7. Record

Use one row per scenario.

| Field | Scenario 1 | Scenario 2 | Scenario 3 | Scenario 4 | Scenario 5 |
|---|---|---|---|---|---|
| Date | 2026-10-23 | 2026-10-23 | 2026-10-23 | 2026-10-23 | 2026-10-23 |
| Participants | HatemShalaby (IC); Agent scribe | HatemShalaby (IC); Agent scribe | HatemShalaby (IC); Agent scribe | HatemShalaby (IC); Agent scribe | HatemShalaby (IC); Agent scribe |
| Detected? | Partial — artifact hash yes; approval tampering not detectable from pack | Partial — session and ledger review possible; no external anchor or approval coverage | No — no outbound tool or envelope; no pre-action retrieval log or pre-send gate | Partial — local chain detects bad hash or truncated line; no anchor so clean truncation or rewrite is invisible | Partial — lookalike domain and urgent bank change detectable by inspection; no automated domain or vendor check |
| Time to contain | N/A — tabletop; manual stop defined | N/A — tabletop; kill switch documented | N/A — tabletop; tool disabled by absence | N/A — tabletop; no automatic ledger write stop | N/A — tabletop; no live payment system |
| Kill switch used? | No — no active distribution system; manual stop | Documented, not implemented; no live payment or release system | No — no envelope stop exists; tool disabled by absence | No — no ledger fail-closed control exists | No — no live payment; authority block is the control |
| Evidence preserved? | Planned; no defined location | Planned; no defined location | Planned; no defined location; no retrieval or attempt logs | Planned; no defined location | Planned; no defined location |
| Notification decision | Owner decides; partner; counsel/auditor gaps | Owner decides; bank/platform/partner; counsel and auditor gaps | Owner decides; affected prospect; counsel/auditor gaps | Owner decides; affected report and claim owners; counsel/auditor gaps | Owner decides; vendor via verified phone; bank if needed; counsel/auditor gaps |
| What failed | P0-2 approval outside seal; no independent approval record; no preservation location; manual distribution; no claims gate; tests not added | P0-6 auth; no revocation list or token rotation; no MFA or device binding; no external anchor; no live kill switch; no second approver | No envelope; no enforced data/instruction boundary; no pre-send gate; no retrieval logging; no preservation location; no injection test | No external anchor; no preservation location; no event-to-report or claim map; no fail-closed writes; no tested restore; no incident record | No vendor master or verified contacts; no payment system; no second human (D-011); no preservation location; no regression test |
| Actions | Fix P0-2; define preservation location; add distribution stop; add claims gate; add tests; name counsel/auditor; record external send as unauthorized | Revoke and rotate; implement kill switch; add external anchor; define preservation location; name counsel/auditor; keep R3 blocked | Build envelope; enforce data/instruction boundary; add pre-send gate and retrieval logging; define preservation location; add injection regression test | Add external anchor; define preservation location; add dependency map; fail closed on verification failure; test restore; record incident | Build vendor master; callback verification; signed bank-change form; block email-only changes; add regression test; second human blocked |
| Action owner | HatemShalaby | HatemShalaby; second-human item blocked by D-011 | HatemShalaby | HatemShalaby | HatemShalaby; second-human item blocked by D-011 |
| Owner sign-off | Pending — scenario not passed | Pending — scenario not passed | Pending — scenario not passed | Pending — scenario not passed | Pending — scenario not passed |

---

## 8. Closure

**Outcome (2026-10-23):** All five scenarios were discussed. None passed. The exercise exposed missing controls rather than proving them. The tabletop is complete under this section. E-05 and C-01 are met for the tabletop test. The executable kill switch is absent, so a live drill remains required before production.

**Closure standard:** Completion is not the same as passing. A completed tabletop may record failed scenarios. It must not mark a scenario passed when a required control is absent. The Owner may close Stage 0 with a completed tabletop that records failures, provided every failed control has an action and owner, the incident plan is corrected, the kill switch procedure is exercised, and no external claim or R3 action depends on an absent control.

The tabletop is complete when:

- [x] all five scenarios have a record;
- [x] every failed control has an action and an owner;
- [x] the kill-switch procedure has been exercised at least once (tabletop walkthrough; executable control absent);
- [x] the incident plan has been corrected where the exercise exposed a gap;
- [x] the Owner signs the record.

### 8.1 Kill-switch procedure walkthrough (2026-10-23)

| Step | Record |
|---|---|
| Trigger | Confirmed unauthorized outbound send, payment, ledger verification failure with external reliance, or stolen Owner session with active writes. |
| Authority | Owner invokes. An automated policy may invoke on a hard limit. No one else. |
| Actions | Declare the incident; record the time; invoke the kill switch; confirm the stops; preserve evidence; notify. |
| Stops | Agent tools, outbound messages, deployment, payments, external API writes, and onboarding. |
| Does not stop | Read-only verification and the ledger event that records the stop. |
| Evidence | Timestamp, trigger, operator, actions taken, systems stopped, and gaps. |
| Recovery | Cause contained; fix tested; evidence preserved; monitoring in place; Owner approves. R3 remains blocked. |
| Result | Procedure exercised. The executable kill switch is absent. A live drill is required before production. |

A failed tabletop is useful. A tabletop that finds nothing is a warning that the scenarios were too soft.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Signature | HatemShalaby |
| Record completed on | 2026-10-23 |
| Scenarios passed | 0 / 5 |
| Follow-up actions | Implement the kill switch and run a live drill before production; fix P0-2; define the preservation location; add an external anchor; build the agent envelope; build the vendor master; keep the second-human control blocked by D-011; re-run the tabletop after the controls exist. |
