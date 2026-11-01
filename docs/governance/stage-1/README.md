# Stage 1 — Control Plane and Cockpit v0

**Authorization — approved and started**

**Status:** AUTHORIZED — STARTED 2026-10-23 — zero-spend local scope  
**Prepared:** 2026-10-23  
**Prepared for:** HatemShalaby, Owner  
**Signed:** 2026-10-23 — §9 Approved; §10 Start Stage 1  
**Decision ID:** D-016; recorded in [`DECISION_LOG.md`](../stage-0/DECISION_LOG.md)
**Governing plan:** [`COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md`](../../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md)  
**Stage 0 record:** [`STAGE_STATUS.yaml`](../stage-0/STAGE_STATUS.yaml), [`DECISION_LOG.md`](../stage-0/DECISION_LOG.md), [`README.md`](../stage-0/README.md)  
**Governing controls:** [`THREAT_MODEL.md`](../stage-0/THREAT_MODEL.md), [`AUTHORITY_MATRIX.yaml`](../stage-0/AUTHORITY_MATRIX.yaml), [`EVIDENCE_STANDARD.md`](../stage-0/EVIDENCE_STANDARD.md), [`CLAIMS_REGISTRY.yaml`](../stage-0/CLAIMS_REGISTRY.yaml), [`DATA_CLASSIFICATION.md`](../stage-0/DATA_CLASSIFICATION.md)

> This document is authorized and started. The Owner signed §9 (Approved) and §10 (Start Stage 1) on 2026-10-23 with the conditions and scope limits recorded in those sections. Work proceeds only within the zero-spend, local, test-mode boundaries in this document: no spend before G-3, no anchor requests before G-4, and no identity-provider integration before G-5. R3 actions, production, customer access, regulated data, contracts, payments, and external claims remain prohibited. G-6 and G-8 remain open, and Stage 1 cannot close until they are resolved. This authorization closes no P0 and accepts no risk.

---

## 1. Objective

Stage 1 establishes the Dynamic Company OS **control plane and cockpit v0** as the system of record, authority, audit, and control surface.

Success means the OS can:

- record consequential actions in one canonical ledger, with intent before action;
- enforce the authority matrix and approval envelopes in code;
- issue and verify single-use approval tokens;
- authenticate and authorize human and service identities with RBAC;
- anchor sealed evidence externally;
- stop execution through an executable kill switch;
- enforce the claims registry and data classification;
- give the Owner a cockpit to inspect and control these functions.

`CompliProof` is the first dogfood venture. It is **not** the production-readiness goal, **not** the OS foundation, and **not** authorized for production, customer access, regulated data, contracts, payments, or external claims.

---

## 2. Scope

### 2.1 In scope

Work begins only after the separate start instruction. All components use local, self-hosted, or existing approved services at zero spend; a new vendor, paid service, or contract is R3 and blocked (see §2.2), and the spend cap is zero until G-3 is signed (see §2.3).

**Scope provenance.** Items 1–11 and 15–16 correspond to the governing plan's Stage 1 build list and deliverables ([plan §8](../../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md), Stage 1). Items 12–14, and the elements of items 1 and 2 tagged below, are **proposed additions** that are not in the plan's Stage 1 build list. They are cataloged in §2.4. A proposed addition takes effect only if the Owner signs this authorization without excluding it.

1. **Helix Prime verification.** Run the suite, fix CI, pin dependencies, produce a lockfile and SBOM, review license and provenance, and test governance boundaries adversarially. Decide per primitive whether to reuse, fix, or replace. The per-primitive reuse/fix/replace decision is the plan's verification rule ([plan §6.3](../../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md)); the license and provenance review and the adversarial governance-boundary tests are **proposed additions** (PA-6, PA-7).
2. **Canonical ledger.** One ledger; intent and result events; single-writer or transactional append; append-only hash chain; verification CLI; pagination and indexed queries; test isolation; migration or explicit archival of the two existing ledgers with a preservation record. Test isolation is an adopted governing-control requirement ([`EVIDENCE_STANDARD.md`](../stage-0/EVIDENCE_STANDARD.md) §6.3) and a registered P0-3 acceptance element. Pagination and indexed queries, and the migration or archival step, are **proposed additions** (PA-4, PA-5).
3. **External anchor.** Select a no-contract public mechanism or an existing approved provider, then implement anchoring, receipt storage, verification, and failure handling. The current maximum evidence level remains E2 until an anchor is verified.
4. **Approval service.** Requests, envelopes, single-use tokens bound to the action hash, expiry, revocation, separation of duties, and a two-key mechanism. No R3 action is executed.
5. **Policy engine.** Machine-readable rules, fail-closed behavior, and tests against the authority matrix.
6. **Identity and RBAC.** SSO or OIDC with MFA for humans, using self-hosted Keycloak or an existing approved provider. RBAC defines `owner`, `approver`, `operator`, `auditor`, and `viewer`; service accounts are scoped; credentials are short-lived. Every route is authenticated and authorized. No new vendor is introduced.
7. **Secrets.** A self-hosted vault or an existing approved managed secret store. No secrets in prompts, logs, or the repository.
8. **Sandbox.** Container runner with no default network, an egress allowlist, and resource limits.
9. **Observability.** Traces, metrics, logs, cost, and alerts. Test actions are traceable end to end.
10. **Backups and restore.** A backup and restore runbook, with a passing restore drill.
11. **Cockpit v0.** Command Deck, Approvals, Audit, Kill Switch, and Ventures list. It is a control surface, not a read-only dashboard.
12. **Kill switch.** An executable, out-of-band control that stops agent tools, outbound messages, deployment, payments, external API writes, and onboarding. It does not stop read-only verification or the ledger event that records the stop. The plan's Stage 1 build list includes the Kill Switch cockpit page and a kill-switch runbook; implementing the executable control and adding a controlled Stage 1 drill are **proposed additions** (PA-1).
13. **Claims registry enforcement.** A gate that blocks any external claim without an approved registry entry. This implements the incident-plan correction to add a pre-send claims gate ([`INCIDENT_PLAN.md`](../stage-0/INCIDENT_PLAN.md) §9.1); it is a **proposed addition** (PA-2). The registry currently has **0 claims approved for external use**.
14. **Data-classification enforcement.** Classification at the source, an inventory, a policy gate, and a default of **Restricted** when classification is unknown. Product and workload data is synthetic or test only; control-plane records are classified under `DATA_CLASSIFICATION.md`, with the ledger and evidence marked Restricted. No customer or regulated data. This enforces the adopted data classification plan-wide; the automated gate is a **proposed addition** (PA-3).
15. **Integrations in test mode.** GitHub, cloud, secret manager, and email in test mode, using existing approved services only. No live external side effect.
16. **Runbooks and evidence.** Backup and restore, kill switch, incident, and the acceptance evidence for every Stage 1 gate.

### 2.2 Out of scope and prohibited

- No **R3 actions**. R3 remains blocked under D-011. No single-key R3. No constitutional amendment is proposed.
- No **new vendor, contract, or spend**. A new vendor at any amount and a contract or DPA are R3 under the authority matrix. R3 is blocked. This affects a managed identity provider, a paid anchor service, and any auditor engagement that involves a fee, a contract, or vendor onboarding. A no-fee, no-contract auditor appointment is at most a candidate path pending G-6 (§6.2) — not compliant or usable until the blocked-access and Restricted-evidence questions are resolved; this draft appoints no auditor. The only paths under this draft are self-hosted or existing approved components and a no-contract public anchor; anything else stops and escalates.
- No **production deployment**, customer access, regulated data, contracts, payments, or external claims.
- No claim that `CompliProof` is production-ready, audit-grade, certified, or externally verified.
- No `CompliProof` product-code change. Any such change requires a separate build envelope under D-005.
- No P0 is closed, remediated, waived, or accepted as a known risk by this authorization or the start instruction. During Stage 1, a control-plane P0 security finding may close only after its registered acceptance test passes and the Owner signs the closure record. The seven `CompliProof` P0s remain open unless separately closed under their own registered acceptance tests and Owner sign-off. Any change to the P0 Register itself requires a separate Owner decision.
- No change to the Constitution, Authority Matrix, Risk Taxonomy, Evidence Standard, Data Classification, Claims Registry, or P0 Register without a separate Owner decision.
- No live external side effects. Email and integrations are test mode only.
- No customer or regulated data. Product and workload data is synthetic or test only; control-plane records are classified under the data classification, with the ledger and evidence marked Restricted.
- No unverified Helix Prime primitive. Verification is a gate, not a formality.
- No claim that the production live kill-switch drill has occurred. That drill remains a prerequisite for production.
- No multi-tenant SaaS, public SaaS, or autonomous external action.
- No spend above the Owner-approved cap. The current cap is `null`, which means **zero**, not unlimited.

### 2.3 Zero-spend boundary

The infrastructure cap (`thresholds.spend.preapproved_infra_cap_usd` in [`AUTHORITY_MATRIX.yaml`](../stage-0/AUTHORITY_MATRIX.yaml)) is `null`, which means **zero**, not unlimited. Until the Owner signs a cap at G-3, no Stage 1 action may create any amount of spend, including metered or paid usage billed to an existing account. No new vendor, paid service, contract, or DPA is authorized by this draft under any reading of the cap; a new vendor at any amount is R3, and R3 remains blocked.

| Lane | Work | Decision it waits on |
|---|---|---|
| **Proceeds at zero spend** | Canonical ledger, approval service and token mechanics, policy engine, identity model and RBAC logic, self-hosted vault, sandbox, self-hosted observability, local backups and restore, Cockpit v0 build and API parity, Helix Prime verification, runbooks. The kill-switch implementation, claims gate, and classification gate also run locally at zero spend, but remain proposed additions (§2.4) regardless of spend. | None — these proceed after G-1 and G-2, at zero incremental spend, before the listed provider decisions. |
| **Existing approved services, test mode** | Test-mode integrations limited to existing free allocations, local runners, or the Owner's existing hardware | First expected charge pauses at G-3 |
| **Pauses pending the cap** | Anything that would create a charge: metered cloud use, paid tiers, paid CI compute, choosing a paid managed secret store or paid managed observability over the self-hosted option | G-3 |
| **Pauses pending anchor decision** | Implementing the external anchor and making any anchor request, even to a no-contract public service; until a verified receipt exists, the maximum evidence level is E2 | G-4 |
| **Pauses pending identity decision** | Cockpit authentication integration against the selected provider. Selecting self-hosted Keycloak or another option, and deploying it locally, is the G-5 decision itself; the payload work (identity model, RBAC logic, token mechanics) proceeds | G-5 |
| **Blocked outright (R3)** | Any new vendor, paid service, contract, or DPA at any amount | Not resolvable by the cap alone; requires a separate compliant Owner decision, which this draft does not authorize |

**Approved-provider caveat.** Stage 0 did not produce a list of approved services, and the authority matrix names approved principals, not approved service providers. Every "existing approved provider or service" in this draft is therefore a recordable choice at the corresponding gate (G-3, G-4, or G-5), or is recorded in the decision log, not an assumed permission.

### 2.4 Proposed additions

The prior draft's claim of "no new scope" was inaccurate. The following items are **not** in the governing plan's Stage 1 build list or deliverables; they enter scope only through a signed authorization that does not exclude them. If the Owner signs with a condition excluding an item, that item is out of scope and its related acceptance criterion is recorded as **`unmet — excluded by Owner condition`**, not as `failed`.

| ID | Proposed addition | Appears in | Why it is here |
|---|---|---|---|
| PA-1 | Implementing the executable kill switch and running a controlled Stage 1 drill | §2.1 item 12; §4.6; A-11 | The plan's Stage 1 build list includes the Kill Switch cockpit page and a kill-switch runbook. The plan's controlled live drill requirement is before the first production release ([`INCIDENT_PLAN.md`](../stage-0/INCIDENT_PLAN.md) §6.4), and Stage 0 records the executable control as absent and deferred. This draft pulls the implementation and a controlled drill forward into Stage 1. |
| PA-2 | Claims-registry enforcement gate | §2.1 item 13; A-12 | Implements the open incident-plan correction "Add a pre-send claims gate" ([`INCIDENT_PLAN.md`](../stage-0/INCIDENT_PLAN.md) §9.1). Not named in the plan's Stage 1 build list. |
| PA-3 | Data-classification enforcement | §2.1 item 14; A-13 | Enforces [`DATA_CLASSIFICATION.md`](../stage-0/DATA_CLASSIFICATION.md) and the plan's privacy controls ([plan §6.14](../../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md), §12.3). Not named in the Stage 1 build list. |
| PA-4 | Migration or archival of the two existing ledgers with a preservation record | §2.1 item 2; §4.3; G-7; A-01 | Concretizes the plan's "one canonical ledger" requirement, given the two existing ledgers. Necessary, but not itemized in the plan. |
| PA-5 | Ledger pagination and indexed queries | §2.1 item 2 | Not in the plan's Stage 1 build list. |
| PA-6 | License and provenance review inside Helix Prime verification | §2.1 item 1; A-14 | Traces to the plan's supply-chain section ([plan §12.5](../../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md)), not to the Stage 1 build list. |
| PA-7 | Adversarial governance-boundary tests for Helix Prime | §2.1 item 1; A-14 | Implements threat-model controls (an agent cannot approve; an out-of-envelope action is blocked). Not in the Stage 1 build list. |

---

## 3. Carry-forward inputs

These inputs are tracked in Stage 1. They are **not** remediated, passed, or accepted by this authorization.

### 3.1 Five tabletop findings

Source: [`KILL_SWITCH_TABLETOP.md`](../stage-0/KILL_SWITCH_TABLETOP.md) and [`INCIDENT_PLAN.md`](../stage-0/INCIDENT_PLAN.md) §9.1. All five scenarios were recorded as **not passed** on 2026-10-23.

| ID | Scenario | Finding carried forward | Status |
|---|---|---|---|
| T-1 | Forged approval or evidence | Approval is outside the seal; no independent approval record; no preservation location; manual distribution; no automated claims gate; regression tests pending | Open — not remediated |
| T-2 | Stolen Owner session | No revocation list, token rotation, MFA, or device binding; kill switch documented but not executable; no external anchor; no second approver | Open — not remediated |
| T-3 | Prompt-injected agent with outbound tools | No agent envelope; no enforced data and instruction boundary; no pre-send gate; no retrieval logging; no preservation location; no injection regression test | Open — not remediated |
| T-4 | Ledger corruption or truncation | No external anchor; no preservation location; no event-to-report or event-to-claim map; no fail-closed writes; no tested restore; no incident record | Open — not remediated |
| T-5 | Fraudulent invoice or bank change | No vendor master or verified contacts; no payment system; no second human; no preservation location; no regression test | Open — not remediated |

**Stage 1 treatment:** the workstreams in §4 may build controls that address these gaps. The findings remain open until the corresponding acceptance evidence exists and the Owner signs the closure record. The second-human gap in T-2 and T-5 remains blocked by D-011.

### 3.2 Seven open P0s

Source: [`P0_REGISTER.yaml`](../stage-0/P0_REGISTER.yaml). The register remains authoritative: `open_p0_count: 7`, `closed_p0_count: 0`. None is accepted as a known risk.

| ID | Finding | Owner | Status | Stage 1 treatment |
|---|---|---|---|---|
| P0-1 | Package cannot be installed and Docker image cannot build | Owner | Open | Remains a `CompliProof` product finding. Stage 1 does not close it. Closure requires its acceptance test and Owner sign-off. |
| P0-2 | Seal excludes approval and key verification can never fail | Owner | Open | Carried as a seal and approval-coverage requirement. Stage 1 work may produce evidence, but the P0 closes only against its own acceptance test and Owner sign-off. |
| P0-3 | Audit is post-action, not concurrency-safe, not externally anchored, and split | Owner | Open | Carried as the canonical-ledger requirement. Stage 1 does not close it until the ledger acceptance tests and anchor evidence exist. |
| P0-4 | Headline metric is wrong; served report drops totals, rows, pack, and hash | Owner | Open | Remains a `CompliProof` product finding. Stage 1 does not close it. Closure requires its acceptance test and Owner sign-off. |
| P0-5 | HTML report route crashes and all report routes are unauthenticated | Owner | Open | Remains a `CompliProof` product finding. Stage 1 does not close it. Closure requires its acceptance test and Owner sign-off. |
| P0-6 | Authentication is not suitable for a compliance product | Owner | Open | Carried as the identity, session, MFA, and RBAC requirement. Stage 1 work may produce evidence, but the P0 closes only against its own acceptance test and Owner sign-off. |
| P0-7 | Dashboard is unusable out of the box and the unauthenticated surface is too broad | Owner | Open | Carried as the cockpit authentication and route-inventory requirement. Stage 1 work may produce evidence, but the P0 closes only against its own acceptance test and Owner sign-off. |

**Rule:** Stage 1 may consume a P0 as a requirement or test input. The authorization and the start instruction close, remediate, waive, or accept **no** P0, and no P0 is accepted as a known risk. A control-plane P0 security finding may close during Stage 1 only after its registered acceptance test passes and the Owner signs the closure record — the same rule as [`P0_REGISTER.yaml`](../stage-0/P0_REGISTER.yaml). The seven `CompliProof` P0s remain open unless separately closed under their own registered acceptance tests and Owner sign-off.

**Why the product P0s are not expected to close in Stage 1:** the registered target of every P0 in the register is the clean-room v1 build and `CompliProof` code, which this draft does not change. Their registered acceptance tests and closure evidence point at `CompliProof` artifacts, so their remaining open state at Stage 1 exit is a carry-forward input, not a waiver. Whether the subject of P0-2, P0-3, P0-6, and P0-7 counts as control-plane scope for A-15 is the pending G-8 decision (§6.1). Any closure, under any reading, requires the registered acceptance test plus the Owner's closure signature, and a separate Owner decision to change the register.

---

## 4. Work sequence and boundaries

The sequence is derived from the plan's Stage 1 section and the ordered action queue in §14, items 6–8. Scope beyond the plan's Stage 1 build list and deliverables is labeled as a proposed addition in §2.4 and takes effect only through the signed authorization. Where the plan lists a workstream without a strict internal order, dependency order is used.

### 4.1 Sequence

| Phase | Work | Depends on | Boundary |
|---|---|---|---|
| 0 | Authorization and pre-start decisions | — | This document is signed, then a separate start instruction is signed. No work before both. |
| 1 | Canonical ledger and external anchor | Phase 0 | One ledger; intent and result events; single writer or transaction; verification CLI; migration or archival record. Ledger work proceeds at zero spend; anchor implementation starts only after G-4 is signed. |
| 2 | Approval service, policy engine, identity and RBAC, secrets | Phase 1 | Token format and policy rules may be built before identity is live. Human token issuance and approval are gated on identity, MFA, and RBAC. No R3. |
| 3 | Sandbox, observability, backups and restore | Phases 1–2 | No default network; egress allowlist; resource limits; traces; restore drill. |
| 4 | Cockpit v0 | Phases 2–3 | Command Deck, Approvals, Audit, Kill Switch, and Ventures. Every UI action maps to an API command with the same policy checks. Cockpit build and API parity proceed at zero spend; the authentication integration starts only after G-5 is signed. |
| 5 | Enforcement surfaces | Phases 2–4 | Executable kill switch; claims-registry gate; data-classification enforcement. The cockpit Kill Switch page is not usable until the executable control exists. |
| 6 | Helix Prime verification | Phase 0 | Full suite, CI, lockfile, SBOM, license and provenance, adversarial governance tests, audit and evidence behavior, kill-switch test, external gates, integration boundary. |
| 7 | Stage 1 verification and exit | Phases 1–6 | All acceptance criteria in §5; P0 review; Owner and auditor sign-off. |

### 4.2 Helix Prime sequence conflict

Baseline: [`HELIX_PRIME_BASELINE.md`](../stage-0/HELIX_PRIME_BASELINE.md). Helix Prime is a candidate kernel, not an approved dependency.

The Stage 1 build list names Helix Prime verification first. The ordered action queue places full verification at item 8, after the canonical ledger and cockpit. This draft preserves the action-queue order and resolves the conflict with a hard boundary:

- Building the canonical ledger and approval service **from scratch** is permitted without waiting for full Helix Prime verification.
- Reusing a Helix Prime primitive is **not** permitted until that primitive's own verification passes.
- Full Helix Prime verification must be complete before Stage 1 exit.
- If verification fails, the primitive is fixed or replaced. It is not papered over.

### 4.3 Canonical ledger disposition

The two existing ledgers must be handled explicitly. Before migration, the Owner decides one of:

1. migrate both into the canonical ledger with a migration record; or
2. archive one as non-canonical with a preservation record.

Either way, the original files are preserved as evidence. The 56 historical `r-test-*` events in the root ledger are not deleted. The disposition step itself is a proposed addition (PA-4): the plan requires one canonical ledger and two ledgers already exist, so a recorded disposition is how Stage 1 ends with exactly one ledger.

### 4.4 External anchor selection

Before anchor implementation, the Owner selects one of:

- an RFC 3161 Time-Stamp Authority that requires no contract, account, payment, or vendor onboarding;
- a public transparency mechanism that requires no contract, account, payment, or vendor onboarding; or
- an equivalent no-contract external anchor approved by the Owner.

The decision is recorded in the Owner's decision log. Until a Stage 1 log is opened, the existing [`DECISION_LOG.md`](../stage-0/DECISION_LOG.md) is the record. Until an anchor receipt is verified, the maximum evidence level is **E2**. No E3 or E4 claim is permitted.

**Vendor boundary.** A new vendor at any amount is R3, and R3 is blocked. A managed anchor service that requires a contract, account, payment, vendor onboarding, or data-processing terms is therefore out of scope. The permissible path under this draft is a no-contract public anchor or an existing approved provider, and only if the Owner records that it creates no vendor relationship, contract, payment, or data-processing obligation. If no such path exists, anchor implementation stops and the Owner records a blocker; Stage 1 does not claim E3. The same boundary applies to identity: a managed OIDC provider is a new vendor and R3; use self-hosted Keycloak or an existing approved provider unless the Owner records a separate compliant decision.

### 4.5 Approval tokens and the two-key limit

The approval token must match the authority matrix:

- bound to `action_hash`;
- single use;
- signed;
- nonce required;
- replay protection;
- TTL of 900 seconds;
- fields: `token_id`, `action_hash`, `envelope_id`, `approver_id`, `approver_role`, `issued_at`, `expires_at`, `nonce`, `signature`.

The two-key mechanism is built and tested with non-production fixtures. No real R3 action is executed. The `approver` role is vacant because D-011 declined a second human approver. A real two-key path remains unexercised until the Owner reverses D-011 and records the change in the decision log.

### 4.6 Kill switch boundary

Stage 1 implements and tests the executable kill switch in a controlled environment. It must stop:

- agent tool execution;
- outbound email, messaging, and publishing;
- deployment;
- payment preparation and execution;
- external API writes;
- new customer or data onboarding.

It must not delete evidence, stop read-only verification, or stop the ledger from recording the stop. A controlled Stage 1 drill is required. A **production** live drill remains a prerequisite for the first production release, not a Stage 1 authorization to produce.

**Provenance.** The executable kill switch and this controlled Stage 1 drill are a proposed addition (PA-1). The plan's own live-drill requirement attaches before the first production release ([`INCIDENT_PLAN.md`](../stage-0/INCIDENT_PLAN.md) §6.4); this draft adds the Stage 1 implementation and drill. If the Owner excludes PA-1 at signature, A-11 is recorded as `unmet — excluded by Owner condition` and the production prerequisite is unchanged.

---

## 5. Acceptance criteria

Stage 1 closes only when the evidence exists. No delivery dates are assigned.

| ID | Criterion | Required evidence |
|---|---|---|
| A-01 | One canonical ledger exists; intent is durable before action; 100 concurrent appends produce one valid chain with unique sequence numbers; a mid-action process kill leaves a recoverable intent; tests cannot write to the production ledger; verification detects truncation, rewrite, and reorder by anchor comparison | Concurrency test, mid-action kill test, tamper test, test-isolation test, ledger inventory, migration or archival record |
| A-02 | An external anchor is selected and implemented without a new vendor contract or R3; the receipt is stored; verification detects an anchor mismatch; E3 capability is demonstrated without making an E3 claim; if no compliant anchor path exists, the criterion remains unmet | Provider decision, anchor receipt, verification report, failure-handling test, vendor/R3 boundary record |
| A-03 | Approval tokens are single-use, action-hash bound, signed, nonce-bearing, and expire after 900 seconds; replay is rejected; revocation works; separation of duties is enforced; the Owner cannot be the secondary approver; an agent cannot approve | Token tests, replay test, revocation test, SOD test |
| A-04 | The policy engine is machine-readable and fail-closed; an out-of-envelope action is blocked; ambiguous authority is blocked and escalated; the rules are tested against the authority matrix | Policy test matrix, denial records |
| A-05 | Identity uses SSO or OIDC with MFA for humans; RBAC enforces `owner`, `approver`, `operator`, `auditor`, and `viewer`; service accounts are scoped; credentials are short-lived; every route is authenticated; the auditor is read-only; no UI-only authority; no new vendor is introduced | Auth test suite, route inventory, RBAC test, access review, vendor boundary record |
| A-06 | Secrets live in a self-hosted vault or an existing approved managed store; no secret is in the repository, logs, prompts, or memory; rotation is tested; no new vendor is introduced | Secret scan, vault configuration, rotation test, vendor boundary record |
| A-07 | The sandbox has no default network, an egress allowlist, and resource limits | Sandbox test, network policy, limit test |
| A-08 | 100% of test actions are traced end to end; correlation IDs link intent, approval, execution, result, and evidence; logs, metrics, traces, cost, and alerts exist | Trace coverage report, correlation-ID sample, alert test |
| A-09 | Backup and restore work; the restore drill passes; the restored chain is verified against the anchor; the restoration is recorded | Restore drill log, restored-chain verification, ledger restoration event |
| A-10 | Cockpit v0 contains Command Deck, Approvals, Audit, Kill Switch, and Ventures; a non-engineer can complete the tested tasks; every UI action maps to an API command with the same policy checks | Usability test, API parity test, screen inventory |
| A-11 | The kill switch is executable and stops the specified systems in a controlled test; read-only verification and the stop event continue; the production live drill remains required | Controlled drill log, stop matrix, incident record |
| A-12 | The claims-registry gate blocks any external claim without an approved entry; the registry still shows 0 claims approved for external use; an unregistered claim is blocked in a test | Gate test, registry snapshot, blocked-claim record |
| A-13 | Data classification is enforced at the source; every dataset has a class and owner; unknown data is treated as Restricted and blocked; Confidential, Regulated, or Restricted data cannot enter a prompt in Stage 1; product and workload data is synthetic or test only; control-plane records are classified, with the ledger and evidence marked Restricted; no customer or regulated data | Classification tests, data inventory, prompt-gate test, synthetic-data labels, control-plane record classification |
| A-14 | Helix Prime verification is complete: suite, CI, lockfile, SBOM, license and provenance, adversarial governance tests, audit and evidence behavior, kill-switch test, external gates, integration boundary; each reused primitive is verified or replaced | Verification record, CI run, SBOM, license review, adversarial test log |
| A-15 | No open control-plane P0 security finding remains at exit. A control-plane P0 may close only after its registered acceptance test passes and the Owner signs the closure record; the authorization and the start instruction close or waive nothing. The seven `CompliProof` P0s remain open unless separately closed under their own registered acceptance tests and Owner sign-off. No P0 is waived or accepted as a known risk. The A-15 reading of "control-plane" is pending at G-8 | P0 register snapshot, control-plane finding review, closure records where applicable |
| A-16 | The Owner and the auditor sign the Stage 1 exit record; if no compliant auditor path exists, this criterion is unmet and Stage 1 does not close until the Owner resolves it through a separately authorized decision; no auditor is invented and no silent waiver is recorded | Signed exit record; G-6 auditor-path decision record |

**Proposed-addition dependency.** A-11, A-12, and A-13 as a whole, and the license/provenance and adversarial-test elements of A-14 and the migration-or-archival-record element of A-01, depend on the proposed additions in §2.4. If the Owner excludes one of them at signature, the affected criterion or element is recorded as `unmet — excluded by Owner condition`, not as `failed`, and the excluded work drops out of the sequence in §4.

---

## 6. Decision gates

| Gate | Decision | When | Owner action |
|---|---|---|---|
| G-1 | Authorize Stage 1 | Before any work | Approve, reject, or request changes; sign and date §9 |
| G-2 | Start Stage 1 | After G-1 | Sign the separate start instruction in §10 |
| G-3 | Infrastructure budget cap | Before any spend | Set a hard monthly cap; `null` means zero; a new vendor at any amount is R3 and blocked |
| G-4 | External anchor provider | Before anchor implementation | Select a no-contract public anchor or existing approved provider; a new vendor or contract is R3 and blocked |
| G-5 | Identity and SSO provider | Before cockpit authentication integration | Select self-hosted Keycloak or an existing approved provider; a new managed provider is R3 and blocked |
| G-6 | Auditor path | Before Stage 1 close | Resolve the blocked-access and Restricted-evidence questions and confirm or reject the candidate no-fee, no-contract appointment — candidate only; not compliant or usable until this G-6 record exists (see §6.2) — or record that no compliant path exists and defer or amend the exit gate; no silent waiver and no invented auditor |
| G-7 | Canonical ledger disposition | Before migration | Migrate both ledgers or archive one as non-canonical; preserve originals |
| G-8 | P0 exit-gate interpretation | Before Stage 1 close | Decide whether A-15 applies to control-plane P0s only or all seven `CompliProof` P0s |
| G-9 | Helix Prime reuse | After verification | Reuse, fix, or replace each primitive; record the decision |
| G-10 | Stage 1 close | After all acceptance criteria | Owner and auditor sign the exit record |

### 6.1 P0 exit-gate interpretation

The plan's Stage 1 exit gate says "No open P0 security findings." The P0 Register contains seven open `CompliProof` findings, several of which are product findings rather than control-plane findings. The draft does **not** silently waive them, and neither reading accepts a P0 as a known risk or waives a closure requirement.

**Working classification (draft reading, pending G-8):** P0-2 (seal and approval coverage), P0-3 (audit ledger), P0-6 (authentication), and P0-7 (cockpit unauthenticated surface) map onto Stage 1 control-plane requirements; P0-1 (packaging), P0-4 (report correctness), and P0-5 (report routes) are `CompliProof` product findings with no direct control-plane equivalent in the Stage 1 build list.

**Proposed interpretation for Owner decision:** A-15 applies to P0 security findings in the Stage 1 control-plane scope. The seven `CompliProof` P0s remain open as carried inputs and are not waived. If the Owner intends A-15 to require closure of all seven, Stage 1 cannot close until they are closed with their own acceptance tests and signatures. Under either reading, any closure follows the register's rule: the registered acceptance test passes and the Owner signs the closure record. Changing the register itself requires a separate Owner decision.

### 6.2 Auditor gate

The plan requires the Owner and auditor to sign the Stage 1 exit, and the threat model records the same control ("Independent audit: Engage" at Stage 1). The auditor role is vacant (`AUTHORITY_MATRIX.yaml` `external_auditor`); the decision log lists "External auditor — Engage / defer" as an open Owner decision with the recommendation "Engage before any audit-grade claim." The exit criterion stays explicit either way: no engagement, no valid signature, no Stage 1 close.

**What actually creates an R3 action (source-checked):** a contract signature (DR-16), a payment (DR-15), a production access grant (DR-18), a public claim (DR-17), and a new vendor at any amount under `thresholds.spend`. The prior draft's assertion that any auditor engagement necessarily creates a contract and a vendor relationship was **not supported by the source documents** and is withdrawn. The authority matrix instead:

- defines the auditor as a `human_or_firm`, read-only principal who cannot approve operations and whose independence must be documented;
- leaves the appointment of human roles to the Owner's reserved power ("appoint and revoke human roles");
- itself directs "recruit an external auditor before any audit-grade claim" among solo-mode mitigations; and
- forbids the Owner from acting as the independent auditor of their own work, so self-certification is not available.

**Candidate path (candidate only — for the Owner to confirm or reject at G-6):** the Owner would appoint an independent human reviewer to the vacant `auditor` role with:

- no fee, no contract, no DPA, no paid service, and no vendor onboarding (zero spend unchanged);
- a documented independence statement in the decision log at appointment;
- read-only, logged access; no write access, no approval authority, no operational role in the action chain;
- an exit-record signature limited to the auditor function defined in the matrix.

**Status of this path: candidate only. It is not compliant and not usable until the Owner resolves, in G-6, the blocked-access question and the Restricted-evidence question.** A no-fee, no-contract appointment does not, on the face of the authority matrix, create a vendor relationship, contract, or payment, and the matrix does not list role appointment as an R3 action — but that does not make it compliant. The questions G-6 must resolve before any appointment or access are:

1. the **blocked-access question** — whether granting the auditor scoped, read-only access to control-plane systems and records sits inside or outside the solo-mode blocked "access grant";
2. the **Restricted-evidence question** — whether the auditor's verification role may include access to Restricted-classed records (the ledger and evidence are Restricted under [`DATA_CLASSIFICATION.md`](../stage-0/DATA_CLASSIFICATION.md)), and under what scoping, logging, and handling rules; and
3. for completeness, whether any arrangement nonetheless constitutes a "new vendor" under `new_vendor_any_amount: R3` — the matrix is not explicit.

Guardrails that would apply to such access (scoped, read-only, logged) describe a candidate design; they do not authorize it. Until G-6 is recorded, no appointment may proceed, no access is granted, and the A-16 auditor signature cannot be exercised through this path.

**If no compliant path exists or the Owner defers:** A-16 remains unmet, Stage 1 does not close, and the Owner resolves the gate through a separately authorized decision — for example a written amendment to the Stage 1 exit gate recorded with reason per [`CONSTITUTION.md`](../stage-0/CONSTITUTION.md) §12 and the decision log. This draft neither waives the requirement nor appoints an auditor, and the Owner signing this document does not by itself create an auditor path. The threat-model row is the same requirement, not a license to bypass this gate.

---

## 7. Constraints

1. **No R3.** R3 remains blocked under D-011. No production release, contract signature, payment, public claim, access grant, regulated data use, or evidence deletion.
2. **No production or customer access.** No deployment, onboarding, customer data, or external user.
3. **No customer or regulated data.** Product and workload data is synthetic or test only; control-plane records are classified under the data classification, with the ledger and evidence marked Restricted.
4. **No external claims.** The claims registry has 0 approved for external use. No external claim, testimonial, report, or public statement is authorized.
5. **No production-readiness claim.** `CompliProof` remains a prototype with open P0s. It is not audit-grade.
6. **No P0 closure by this authorization; no risk acceptance.** The authorization and the start instruction close, remediate, waive, or accept no P0. A control-plane P0 security finding may close during Stage 1 only after its registered acceptance test passes and the Owner signs the closure record. The seven `CompliProof` P0s remain open unless separately closed under their own registered acceptance tests and Owner sign-off. No P0 is accepted as a known risk.
7. **No governance changes without a separate Owner decision.** The Constitution, Authority Matrix, Risk Taxonomy, Evidence Standard, Data Classification, Claims Registry, and P0 Register remain authoritative.
8. **No live external side effects.** Integrations are test mode only.
9. **No unverified Helix Prime primitive.** Verification precedes reuse.
10. **No production live-drill claim.** The production kill-switch drill remains a prerequisite for the first production release.
11. **No work before the separate start instruction.** This draft is not a start.
12. **No spend above the Owner cap.** `null` means zero.
13. **No secrets in prompts, logs, or the repository.**
14. **No UI-only authority.** Every UI action maps to an API command with the same policy checks.
15. **No agent approval.** Agents may implement within envelopes; they may not approve.
16. **No multi-tenant SaaS or public SaaS.**
17. **No new vendor, contract, or spend without a separate compliant decision.** A new vendor at any amount and a contract or DPA are R3, which is blocked.

---

## 8. Owner and authority

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Role | Owner; sole human authority |
| Operating mode | Solo-owner |
| Second approver | Declined under D-011; R3 remains blocked |
| External auditor | Vacant; required for Stage 1 exit under the current plan; a candidate path exists — a no-fee, no-contract appointment with documented independence — but it is not compliant or usable until G-6 resolves the blocked-access and Restricted-evidence questions (§6.2); this draft appoints no auditor |
| Stage 1 accountable owner | HatemShalaby |
| Implementers | Agents only inside approved envelopes; no approval authority. Contractors require a contract and are R3-blocked. |
| Authority source | [`AUTHORITY_MATRIX.yaml`](../stage-0/AUTHORITY_MATRIX.yaml) |

Any change to scope, authority, or a decision gate requires a written Owner decision. A constitutional change requires the amendment process in the Constitution.

---

## 9. Authorization decision

**Authorization statement:** I authorize Stage 1 to proceed within the scope, constraints, and acceptance criteria in this document, subject to the separate start instruction in §10.

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Decision ID | Not assigned in this file; record it in [`DECISION_LOG.md`](../stage-0/DECISION_LOG.md) |
| Decision | ☒ Approved  ☐ Rejected  ☐ Changes required |
| Owner signature | HatemShalaby |
| Date | 2026-10-23 |
| Conditions or dissent | PA-1 through PA-7 included. Initial work is limited to zero-spend local tasks. G-6 and G-8 remain open; no Stage 1 closure until resolved. No R3 actions or external use. |

**Effect of signature:** Authorizes the Stage 1 scope in this document only. It does **not** start Stage 1. It does **not** authorize any R3 action, production deployment, customer access, regulated data, contract, payment, or external claim. It does **not** close any P0 or accept any risk. It does **not** change any claim.

---

## 10. Separate start instruction

**Start statement:** I instruct Stage 1 to start within the scope and limits recorded in this document.

Stage 1 started on the signing of this separate instruction (2026-10-23), within the scope and limits recorded here.

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Start instruction | ☒ Start Stage 1  ☐ Do not start |
| Owner signature | HatemShalaby |
| Date | 2026-10-23 |
| Scope limits | Zero-spend local work only. Pause spend, anchor requests, and identity-provider integration for G-3, G-4, and G-5 decisions. No R3 actions, production, customer access, regulated data, contracts, payments, or external claims. |

**Effect:** Stage 1 is now started (2026-10-23) within the scope limits above and the boundaries in §2 and §4. The authorization in §9 alone did not start Stage 1; this instruction did. Work under way is limited to zero-spend local tasks until G-3, G-4, and G-5 are signed.

---

## 11. Review checklist

- [ ] Scope matches the plan's Stage 1 section and §14 action queue 6–8; added scope is identified as proposed additions with their sources (§2.1, §2.4).
- [ ] The zero-spend boundary separates zero-spend work from work that pauses for G-3, G-4, or G-5 (§2.3).
- [ ] The five tabletop findings are listed and remain open.
- [ ] All seven P0s are listed and remain open; none is accepted as a known risk; the P0 rules are consistent — authorization and the start instruction close or waive nothing, and closure requires the registered acceptance test plus Owner sign-off (§2.2, §3.2, §7).
- [ ] R3, production, customer access, regulated data, contracts, payments, and external claims remain blocked.
- [ ] No production-readiness or audit-grade claim is made.
- [ ] The production live kill-switch drill remains a prerequisite for production.
- [x] §9 signed and dated 2026-10-23: Approved with the recorded conditions.
- [x] §10 signed and dated 2026-10-23: Start Stage 1 with the recorded scope limits.
- [ ] The auditor gate is explicit and unresolved; the no-fee path is stated as candidate only — not compliant or usable until G-6 resolves the blocked-access and Restricted-evidence questions; no auditor is appointed and no waiver is recorded (§6.2).
- [ ] The vendor/R3 boundary is explicit for the anchor, identity, and auditor.
- [ ] The P0 exit-gate interpretation is explicit and pending (G-8).
- [ ] The Helix Prime sequence conflict is resolved with a verification boundary.
- [ ] No code, test, or product change is made by this draft.

---

## 12. Document control

| Field | Value |
|---|---|
| Document | Stage 1 authorization |
| Version | 1.0.0 |
| Status | Authorized and started 2026-10-23 — zero-spend local scope |
| Prepared | 2026-10-23 |
| Signed | 2026-10-23 — §9 Approved; §10 Start Stage 1 |
| Revised | 2026-10-23 — review revision: P0-rule reconciliation (§2.2, §3.2, §6.1, §7, A-15), auditor-gate reassessment against the governing plan and authority matrix (§6.2, G-6), zero-spend boundary (§2.3), and scope provenance (§2.1, §2.4, §4); final clarification: the no-fee auditor appointment is candidate only — not compliant or usable until G-6 resolves the blocked-access and Restricted-evidence questions (§6.2) |
| Owner decision | Approved 2026-10-23 (§9; conditions recorded there) |
| Start instruction | Signed 2026-10-23 (§10) |
| Supersedes | None |
| Related decision | D-015 closed Stage 0; §9 and §10 signed 2026-10-23. The decision-log entry for this authorization is a pending Owner record-keeping step. Stage 0 records are unchanged by this document. |
