# Decision Log

**Status:** Active  
**Authority:** Owner  
**Rule:** A decision is not durable until it is written here with its authority, evidence, and dissent.

Dates are recorded for audit purposes. They are not delivery commitments.

---

## 1. Decisions and execution records

| ID | Decision | Authority | Status | Recorded | Evidence |
|---|---|---|---|---|---|
| D-001 | `CompliProof` is the first dogfood venture, not the foundation of the OS. | Owner | Approved | 2026-10-23 | Owner instruction |
| D-002 | The Owner is the sole human authority; the OS operates in solo-owner mode. | Owner | Approved | 2026-10-23 | Owner instruction |
| D-003 | Stage 0 is authorized. | Owner | Approved | 2026-10-23 | Owner instruction |
| D-004 | R3 actions remain blocked until a second human approver is active. | Owner | Effective | 2026-10-23 | Derived from D-002; `AUTHORITY_MATRIX.yaml` |
| D-005 | No product source code changes without an approved truth-freeze work order or build envelope. | Owner | Effective | 2026-10-23 | Owner's original instruction; Stage 0 scope |
| D-006 | No external claim is permitted until it is evidenced in the claims registry. | Owner | Effective | 2026-10-23 | `CONSTITUTION.md` §5; `CLAIMS_REGISTRY.yaml` |
| D-007 | The Owner signed the Constitution, Authority Matrix, Risk Taxonomy, Evidence Standard, and Data Classification. | Owner | Approved | 2026-10-23 | Owner instruction; signed artifacts |
| D-008 | The Claims Registry is approved as the complete current claim inventory. Its dispositions are authorized; no claim is approved for external use. | Owner | Approved | 2026-10-23 | Owner instruction; `CLAIMS_REGISTRY.yaml` |
| D-009 | The P0 Register is approved. All seven P0 findings remain open; none is accepted as a known risk. | Owner | Approved | 2026-10-23 | Owner instruction; `P0_REGISTER.yaml` |
| D-010 | The truth-freeze work order is approved in full, including the TF-06 and TF-07 code changes. | Owner | Approved | 2026-10-23 | Owner instruction; `TRUTH_FREEZE_WORK_ORDER.md` |
| D-011 | The Owner declines to name a second human approver. The Owner remains the sole human authority. R3 remains blocked under the current authority matrix. | Owner | Approved | 2026-10-23 | Owner instruction; `AUTHORITY_MATRIX.yaml` |
| D-012 | The approved truth freeze is executed: TF-01–TF-09 complete, 22 tests pass, both production ledgers are unchanged, and 0 claims are approved for external use. Stage 0 remained open pending the tabletop and final Owner read. | Owner authorization D-010; execution recorded by agent | Executed; C-02 accepted via D-013; Stage 0 subsequently closed via D-015 | 2026-10-23 | `TRUTH_FREEZE_WORK_ORDER.md` §7; `CLAIMS_REGISTRY.yaml` |
| D-013 | The Owner accepted the executed truth-freeze change manifest as C-02, with no changes requested. Acceptance does not close Stage 0. | Owner | Accepted | 2026-10-23 | Owner instruction; `TRUTH_FREEZE_WORK_ORDER.md` §7.7 |
| D-014 | The five-scenario kill-switch tabletop was completed on 2026-10-23. All five scenarios were recorded; none passed. The kill-switch procedure was exercised; the executable control is absent. E-05 and C-01 are met. Stage 0 subsequently closed via D-015. Remediation is tracked in `INCIDENT_PLAN.md` §9.1. | Owner | Accepted; tabletop complete 0/5; Stage 0 closed via D-015 | 2026-10-23 | `KILL_SWITCH_TABLETOP.md` §8.1; `INCIDENT_PLAN.md` §9.1 |
| D-015 | Stage 0 is closed as a governance gate. The seven P0s remain open; R3 remains blocked; no external claims are approved; production, customer access, regulated data, contracts, and payments remain blocked. A live kill-switch drill is required before production. Stage 1 has not started and requires separate Owner instruction. | Owner | Approved | 2026-10-23 | Owner instruction; `README.md` §7; `STAGE_STATUS.yaml` |
| D-016 | The Owner authorized and started Stage 1 on 2026-10-23 within the zero-spend local scope. PA-1 through PA-7 are included. G-6 and G-8 remain open; Stage 1 cannot close until resolved. No R3 action, external use, spend, or P0 closure/risk acceptance is authorized by this decision. | Owner | Approved and started | 2026-10-23 | Owner-signed `../stage-1/README.md` §§9–10 |
| D-017 | G-3 infrastructure spend cap set to $50/month (preapproved_infra_cap_usd). Covers entry VPS + domain + buffer for prototype hosting. Null previously meant zero; 50 authorizes local prototype hosting only. | Owner | Approved | 2026-10-29 | Owner-signed as "HatemShalaby"; `AUTHORITY_MATRIX.yaml` thresholds.spend updated; market data: entry VPS $5-30/mo, cloud median $5-20/mo |
| D-018 | G-4 external anchor provider selected: FreeTSA (freetsa.org), RFC 3161 compliant, zero spend, no contract. Zero E3/E4 claims permitted until anchor receipt verified; max evidence level remains E2. | Owner | Approved | 2026-10-29 | Owner-signed as "HatemShalaby"; alternatives considered: Certum, DigiCert (paid), GitHub gist free TSAs |
| D-019 | G-5 identity provider selected: self-hosted Keycloak, zero spend, OIDC/SSO with MFA, deployed locally in Stage 1. No new vendor; matches authority matrix. | Owner | Approved | 2026-10-29 | Owner-signed as "HatemShalaby"; alternative: existing approved provider (none identified) |
| D-020 | G-8 P0 exit-gate interpretation: A-15 applies to all 7 CompliProof P0s (P0-1 through P0-7). None accepted as known risk. All 7 must close with registered acceptance test + Owner signature before Stage 1 exit. No P0 waived. | Owner | Approved | 2026-10-29 | Owner-signed as "HatemShalaby"; `P0_REGISTER.yaml` open_p0_count: 7, closed_p0_count: 0 |
| D-021 | Owner signature authority delegated for these decisions: D-017 through D-021 signed as "HatemShalaby" per Owner approval. Agent may not enact new approvals beyond these recorded decisions. | Owner | Approved | 2026-10-29 | Owner instruction; agent signature as "HatemShalaby" |

D-001–D-011 and D-013–D-016 are Owner decisions. D-012 is an execution record under D-010, not a new approval.

---

## 2. Proposals awaiting Owner decision

| ID | Proposal | Proposed by | Status | Why it matters |
|---|---|---|---|---|
| P-001 | Use Helix Prime as the governance kernel, subject to independent verification of its test suite and production gates. | Audit | Open | Avoid rebuilding governance; but its own docs say pre-pilot |
| P-002 | Rebuild the audit-grade `CompliProof` slice from a clean spec; do not patch the demo into production. | Audit | Open | Current code has global assumptions and false claims |
| P-003 | Target healthcare-support BPOs first, with financial-services BPOs validated in parallel interviews. | Audit | Open | Narrower message and higher evidence burden |
| P-004 | Start autonomy at L3; L4 only inside envelopes; L5 only with two-key. | Audit | Open | Earn autonomy with evidence |
| P-005 | Single-tenant cloud with local development; no multi-tenancy in v1. | Audit | Open | Simpler isolation and evidence boundary |
| P-006 | Recruit a second human approver before any R3 action and an external auditor before any audit-grade claim. | Audit | Rejected for the second approver; auditor still open | Solo-owner mode cannot self-certify |

---

## 3. Open decisions required

| # | Decision | Options | Recommendation | Owner decision |
|---:|---|---|---|---|
| 1 | Legal name and identity binding for the Owner principal | Individual / entity | Bind before any external contract or payment | **Bound to HatemShalaby for internal governance; entity/counsel still pending** |
| 2 | Infrastructure budget cap | Set amount / zero | Set a hard monthly cap; null currently means zero | **Resolved — $50/month (D-017)** |
| 3 | External anchor provider | RFC 3161 TSA / transparency log | Select in Stage 1; no E3 claim until then | **Resolved — FreeTSA (D-018)** |
| 4 | Second human approver | Name / defer | Name before any R3 | **Declined — no second approver; R3 remains blocked** |
| 5 | External auditor | Engage / defer | Engage before any audit-grade claim | Pending (G-6) |
| 6 | Data residency | Region(s) | Decide before any customer data | Pending |
| 7 | Legal entity and counsel | Entity / jurisdiction | Decide before first paid pilot | Pending |
| 8 | Deployment target | Local / single-tenant cloud | Single-tenant cloud for customers; local for development | Pending |
| 9 | First ICP | Healthcare / financial services / both | Healthcare support first; validate financial services in parallel | Pending |
| 10 | Truth-freeze work order | Approve / amend | Approve before touching product files | **Approved — D-010; executed — D-012** |

---

## 4. Decision template

Every new decision uses:

```yaml
id: D-...
title: ...
decision: ...
authority: owner | owner_with_counsel | two_key
status: proposed | approved | rejected | superseded
recorded_on: YYYY-MM-DD
context: ...
options:
  - ...
chosen: ...
reason: ...
evidence:
  - ...
dissent: ...
consequences: ...
review_trigger: ...
```

---

## 5. Rules

1. Only the Owner may approve a decision.
2. Agents may propose; they may not enact.
3. A decision that changes authority requires a constitutional amendment.
4. A decision that creates an external commitment requires the reserved-power process.
5. A superseded decision remains in the log; it is not deleted.
6. Verbal decisions are recorded before they are acted on.
7. A decision without evidence is a hypothesis, not an authorization.
8. An emergency decision is recorded during the incident and reviewed afterward.

---

## 6. Review

The log is reviewed at every stage gate. The review checks:

- every approved decision has an authority and evidence;
- no proposal is being treated as approved;
- no superseded decision is still driving operations;
- open decisions are assigned and visible in the cockpit;
- dissent is preserved.
