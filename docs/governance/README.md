# Dynamic Company OS

**Status:** Stage 0 closed 2026-10-23 as a governance gate; Stage 1 authorized and started 2026-10-23 within zero-spend local scope  
**Owner:** HatemShalaby (solo-owner mode)  
**Product code changes:** Truth-freeze `TF-06`/`TF-07` plus user-visible claim corrections; nothing deployed

This directory holds the operating artifacts of the Dynamic Company OS. The governing audit and execution plan are in [`../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md`](../COMPLIPROOF_AUDIT_AND_DYNAMIC_OS_PLAN.md).

---

## Structure

```
company-os/
├── README.md
├── stage-0/
│   ├── README.md
│   ├── CONSTITUTION.md
│   ├── AUTHORITY_MATRIX.yaml
│   ├── RISK_TAXONOMY.yaml
│   ├── EVIDENCE_STANDARD.md
│   ├── CLAIMS_REGISTRY.yaml
│   ├── DATA_CLASSIFICATION.md
│   ├── THREAT_MODEL.md
│   ├── INCIDENT_PLAN.md
│   ├── KILL_SWITCH_TABLETOP.md
│   ├── P0_REGISTER.yaml
│   ├── HELIX_PRIME_BASELINE.md
│   ├── TRUTH_FREEZE_WORK_ORDER.md
│   ├── STAGE_STATUS.yaml
│   ├── DECISION_LOG.md
│   └── evidence/
│       └── TF-04-dashboard-demo-label.png
├── stage-1/
│   └── README.md
└── ventures/
    └── compliproof/
        └── venture.yaml
```

---

## Current state

| Item | State |
|---|---|
| `CompliProof` role | First dogfood venture; not the OS foundation |
| Human authority | Owner only |
| Stage 0 | Closed 2026-10-23 as a governance gate; all exit criteria met; tabletop complete 0/5 |
| Stage 1 | Authorized and started 2026-10-23; zero-spend local scope; G-6 and G-8 open |
| R3 actions | Blocked; the Owner declined to name a second approver (D-011) |
| External claims | Blocked; registry approved; 0 claims approved for external use |
| Product code | `TF-06`/`TF-07` truth-freeze changes only; not deployed |
| P0 findings | 7 open; 0 accepted as known risk |
| External auditor | Vacant; no appointment or access; G-6 path unresolved |
| Second approver | Declined |

---

## What is true today

- The audit is evidence-based and includes reproducible defects.
- The governance packet is adopted: Constitution, Authority Matrix, Risk Taxonomy, Evidence Standard, and Data Classification are signed.
- The Claims Registry and P0 Register are approved.
- The truth freeze is executed: false README claims removed, demo data labeled, registration disabled by default, wildcard CORS removed, cookies hardened, and test-ledger writes isolated.
- The Owner accepted the executed truth-freeze change manifest as C-02 on 2026-10-23, with no changes requested.
- The CompliProof suite passed locally on the last recorded run, and both production ledgers were byte-for-byte unchanged by that run. Tests were not rerun after the documentation-only closure edits.
- Stage 1 was authorized and started on 2026-10-23 within the signed zero-spend local scope; G-6 and G-8 remain open and block Stage 1 closure.
- No customer, external claim, deployment, or payment is authorized.

## What is not true today

- `CompliProof` is not production-ready.
- `CompliProof` is not audit-grade.
- The OS is not built.
- There is no second key, the auditor role is vacant, and no external anchor is selected. The auditor appointment and access path remain unresolved at G-6; no appointment or access has occurred.
- The five-scenario tabletop is complete; none passed. The kill-switch procedure was exercised, but the executable control is absent; a live drill is required before production.
- Stage 0 is closed as a governance gate; Stage 1 is started within its signed zero-spend local scope.

---

## Start here

1. [`stage-0/README.md`](stage-0/README.md) — status and exit gate.
2. [`stage-0/CONSTITUTION.md`](stage-0/CONSTITUTION.md) — governing principles.
3. [`stage-0/AUTHORITY_MATRIX.yaml`](stage-0/AUTHORITY_MATRIX.yaml) — who may decide what.
4. [`stage-0/CLAIMS_REGISTRY.yaml`](stage-0/CLAIMS_REGISTRY.yaml) — every external claim and its status.
5. [`stage-0/TRUTH_FREEZE_WORK_ORDER.md`](stage-0/TRUTH_FREEZE_WORK_ORDER.md) — executed corrections and evidence; Owner accepted C-02 on 2026-10-23.
6. [`ventures/compliproof/venture.yaml`](ventures/compliproof/venture.yaml) — the first venture definition.
7. [`stage-1/README.md`](stage-1/README.md) — Stage 1 authorization, start instruction, scope, and gates.
