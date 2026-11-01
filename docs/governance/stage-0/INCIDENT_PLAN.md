# Incident Response Plan

**Version:** 0.1.1  
**Status:** Adopted; tabletop complete 2026-10-23, 0/5 passed; procedure exercised; executable control absent  
**Owner:** HatemShalaby  
**Scope:** Dynamic Company OS, `CompliProof`, all ventures, agents, data, and infrastructure

This plan covers security, privacy, evidence-integrity, financial, and operational incidents. It is an internal plan. Legal notification decisions require counsel.

---

## 1. Principles

1. **Preserve evidence first.** Do not delete, rebuild, or "clean up" before capturing state.
2. **Contain before explaining.** Stop the harm, then investigate.
3. **One incident commander.** In solo-owner mode, the Owner is the commander.
4. **Default deny.** When unsure, freeze the affected capability.
5. **Do not notify externally without counsel** where legal, contractual, or regulatory duties may apply.
6. **Write it down.** Every decision, time, and action goes into the incident record.
7. **No blame before facts.** The postmortem is blameless; accountability is separate.

---

## 2. Severity

| Severity | Definition | Examples | Response |
|---|---|---|---|
| **SEV1** | Confirmed or imminent material harm to customers, data, money, or the integrity of evidence used externally. | Data breach; unauthorized payment; production compromise; forged evidence in a customer report; ransomware. | Immediate containment; Owner command; counsel; customer/regulator assessment; kill switch. |
| **SEV2** | Serious risk or limited impact; containment is possible; external impact not yet confirmed. | Leaked credential; unauthorized access attempt that succeeded partially; major outage; evidence chain break without external reliance. | Contain within the operating window; preserve evidence; Owner decision on notification. |
| **SEV3** | Contained internal impact; no confirmed external exposure. | Failed policy control; internal data leak; agent out-of-envelope action stopped by policy. | Contain; record; fix; review. |
| **SEV4** | Near miss or weak signal. | Suspicious login blocked; test failure that could have shipped; stale claim found before publication. | Record; triage; improve control. |

Severity is set by impact, not by how easy the incident is to explain.

---

## 3. Roles

| Role | Solo-owner assignment | Responsibilities |
|---|---|---|
| Incident Commander | Owner | Declares severity; makes containment decisions; owns external communication. |
| Scribe | Agent (no decision authority) | Maintains timeline, decisions, evidence references. |
| Engineering Lead | Owner + agent | Diagnoses, contains, recovers. |
| Communications | Owner | Customer, partner, and public communication after counsel review. |
| Legal | External counsel | Notification duties, privilege, contract interpretation. |
| Auditor | External auditor when active | Independent review; no operational authority. |
| Finance | Owner | Payment stop, fraud contact, insurance. |

**Solo-owner gap:** if the Owner is unavailable or compromised, operations freeze. A backup approver and a recovery path must be named before R3 operations.

---

## 4. Detection sources

- Cockpit alerts and anomalies.
- Ledger verification failure.
- Hash or anchor mismatch.
- Approval token replay.
- Outbound message complaint or bounce spike.
- Spend anomaly.
- Failed login or MFA anomaly.
- Dependency or secret scan.
- Customer report.
- Auditor finding.
- Agent self-report.
- Bank or payment provider alert.

---

## 5. Response phases

### 5.1 Detect

Record:

- what was observed;
- when;
- by whom or what;
- the affected system, venture, and data class;
- the initial severity;
- the evidence location.

### 5.2 Triage

Answer:

1. Is harm ongoing?
2. What data, money, access, or evidence is affected?
3. Is an external party involved?
4. Is the evidence used in an external claim?
5. Is the cause contained or still active?

If the answer is unknown, escalate the severity.

### 5.3 Declare

The Owner declares the incident and severity. A declaration creates:

- an incident ID;
- a ledger event;
- an incident channel or record;
- a scribe;
- a containment objective.

### 5.4 Contain

Containment options, least destructive first:

1. Pause the specific agent or workflow.
2. Revoke the specific credential or session.
3. Disable the specific integration.
4. Freeze outbound communication.
5. Freeze deployments.
6. Freeze payments.
7. Invoke the kill switch.
8. Isolate the environment or network segment.

Do not delete evidence. Do not rebuild the ledger. Do not "fix" the artifact before capturing it.

### 5.5 Preserve

Capture:

- ledger head and full relevant range;
- evidence pack and manifests;
- application and access logs;
- approval tokens and audit records;
- affected files and their hashes;
- network and configuration state;
- chat, email, and ticket records;
- the incident timeline.

Store the capture in a write-once or access-controlled location. Record the hash of every capture.

**Default preservation location:** `company-os/stage-0/evidence/incidents/<incident-id>/`. Create the directory when the incident is declared. Write a `SHA256SUMS` manifest covering every captured file. Record the absolute path, capture time, and custodian in the incident record. If the default location is unavailable, use an access-controlled write-once store and record its path. The location must be outside the running service's writable data path.

### 5.6 Assess

Assess:

- root cause;
- blast radius;
- data subjects and classifiers;
- contractual notification duties;
- regulatory notification duties;
- financial exposure;
- evidence integrity;
- whether any approval, report, or external claim depends on the affected range;
- whether the approval record is inside or outside the sealed evidence pack.

Counsel decides legal notification. The Owner decides business communication after counsel input.

### 5.7 Notify

Notification matrix:

| Audience | Who decides | Trigger |
|---|---|---|
| Owner | Incident Commander | Always |
| Internal team | Owner | SEV1–SEV3 |
| Affected customer | Owner + counsel | Confirmed or likely material impact |
| Regulator | Owner + counsel | Legal requirement |
| Insurer | Owner | Potential claim |
| Auditor | Owner | Evidence integrity or control failure |
| Payment provider or bank | Owner | Suspected fraudulent payment or bank change |
| Vendor or partner | Owner, through a verified channel | Their account, data, payment, or report is affected |
| Law enforcement | Owner + counsel | Crime or threat |
| Public | Owner + counsel | Material public impact; not for reassurance |

Do not use contact details from the suspicious message. Use a known contact from the contract, accounting record, or vendor master.

Do not speculate. State what is known, what is not known, what is being done, and when the next update will come.

### 5.8 Recover

Recovery requires:

- the cause is contained;
- the fix is tested;
- the evidence is preserved;
- the data is restored or the service is safely rebuilt;
- monitoring is in place;
- the Owner approves resumption;
- for R3, a second approver is active.

**Ledger restoration:** Restore from a known-good backup into a new file. Never overwrite the original. Verify the restored chain against the external anchor. Record the gap between the last good event and the restored head. Append a restoration event. Keep the corrupted original and every copy. Do not resume report generation or external claims until the restored evidence is re-verified. Until an external anchor exists, a clean truncation or rewrite cannot be independently detected.

### 5.9 Review

A postmortem is required for SEV1 and SEV2, and recommended for SEV3.

The postmortem includes:

- summary;
- timeline;
- root cause;
- contributing factors;
- detection and response assessment;
- what worked;
- what failed;
- action items with named owners and closure evidence;
- evidence references;
- whether any claim or report must be corrected.

No dates are required in the action list. Each action closes when its evidence exists.

---

## 6. Kill switch

### 6.1 What it stops

- Agent tool execution.
- Outbound email, messaging, and publishing.
- Deployment pipeline.
- Payment preparation and execution.
- External API writes.
- New customer or data onboarding.

### 6.2 What it does not do

- It does not delete evidence.
- It does not stop read-only verification.
- It does not stop the ledger from recording the stop.
- It does not authorize a rollback that destroys evidence.

### 6.3 Who can trigger

- Owner.
- An automated policy when a hard limit is breached (spend cap, outbound cap, error threshold).
- A future on-call operator after training.

### 6.4 Test requirement

The kill switch must be tested:

1. in a tabletop before Stage 0 closes;
2. in a controlled live drill before the first production release;
3. after any change to the control plane.

A failed test is a P0 defect. The 2026-10-23 tabletop exercised the kill-switch procedure. The executable control is absent, so the controlled live drill remains required before the first production release.

### 6.5 Fail-closed ledger writes

Any ledger verification failure stops writes to that ledger, report generation from it, and external claims or distribution that depend on it. Read-only verification continues. The stop is recorded as an incident. Resumption requires the Owner to verify the restored chain and record the decision. Until an external anchor exists, a clean truncation or rewrite cannot be independently detected; that remains a P0 defect.

---

## 7. Evidence preservation rules

1. Capture before repair.
2. Hash every capture.
3. Keep the original; work from a copy.
4. Record chain of custody.
5. Do not delete logs, even if they are noisy.
6. Do not edit the ledger.
7. Do not overwrite backups.
8. Do not discuss the incident in a channel that is not preserved.
9. Legal hold overrides ordinary retention.
10. Deletion during an incident is prohibited.

---

## 8. Communications

### 8.1 Internal update template

```
Incident: INC-...
Severity: SEV...
Status: investigating / contained / recovering / closed
What happened:
What is affected:
What is not affected:
What we are doing:
What we need:
Next update:
```

### 8.2 Customer template

```
We are writing about an incident that may affect [service/data].
What we know:
What we are doing:
What you can do:
What we will do next:
Contact:
```

Every customer communication is reviewed by the Owner and, where legal or contractual duties may apply, by counsel.

### 8.3 Prohibited communication

- Blaming a customer or employee.
- Guessing at cause.
- Promising a timeline that is not evidenced.
- Minimizing impact.
- Claiming containment before it is verified.
- Deleting or editing prior statements without a correction record.

---

## 9. Tabletop record

**Status:** Complete 2026-10-23. All five scenarios recorded; **0/5 passed**; kill-switch procedure exercised; executable control absent. Full record: `KILL_SWITCH_TABLETOP.md`.

| # | Scenario | Objective | Status |
|---:|---|---|---|
| 1 | Forged approval or evidence | Test detection, containment, and external claim correction | Not passed |
| 2 | Stolen Owner session | Test revocation, payment stop, and recovery | Not passed |
| 3 | Prompt-injected agent with outbound tools | Test envelope stop and kill switch | Not passed |
| 4 | Ledger corruption or truncation | Test anchor comparison and preservation | Not passed |
| 5 | Fraudulent invoice or bank change | Test payment stop and verification callback | Not passed |

Record for each:

- participants;
- scenario;
- what was detected;
- time to contain;
- what failed;
- actions;
- evidence;
- Owner sign-off.

### 9.1 Findings and corrections

| Gap exposed | Correction | Status |
|---|---|---|
| Approval record is outside the sealed pack; no independent approval record | Fix P0-2; add approval coverage and verification | Open |
| No defined preservation location | Default location in §5.5 with a `SHA256SUMS` manifest | Plan corrected; directory created |
| Manual distribution; no automated claims gate | Add a pre-send claims gate | Open |
| No revocation list, token rotation, MFA, or device binding | Fix P0-6 | Open |
| Kill switch documented but not implemented | Procedure exercised in the tabletop; implement the executable control and run a live drill | Procedure tested; implementation open |
| No external anchor | Add an independent anchor | Open |
| No agent envelope; no enforced data/instruction boundary; no pre-send gate | Build the envelope and injection regression test | Open |
| No event-to-report or event-to-claim map | Add a dependency map | Open |
| No fail-closed ledger writes or tested restore | §6.5 fail-closed rule; test restore | Plan corrected; implementation open |
| No vendor master or verified contact database | Build the vendor master and callback verification | Open |
| No second human for payment above threshold | Keep payment and R3 blocked under D-011 | Blocked by design |
| Counsel not named; auditor vacant | Name counsel; decide the auditor role | Open |

---

## 10. Post-incident corrections

If an incident affects an external claim or report:

1. stop distribution;
2. identify recipients;
3. correct the report;
4. notify recipients;
5. update the claims registry;
6. add a regression test;
7. record the correction in the decision log.

---

## 11. Plan maintenance

Review this plan:

- at every stage gate;
- after every SEV1 or SEV2;
- after a material architecture change;
- after a change in human roles;
- before the first production release.

---

## 12. Sign-off

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Signature | HatemShalaby |
| Adopted on | 2026-10-23 |
| Tabletop record completed on | 2026-10-23 |
| Tabletop outcome | Complete; 0/5 passed; procedure exercised; executable control absent; E-05 and C-01 met |
| Version | 0.1.1 |
