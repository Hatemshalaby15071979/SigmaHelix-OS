# Data Classification and Handling

**Version:** 0.1.0  
**Status:** Adopted  
**Adopted:** 2026-10-23  
**Default when unknown:** Restricted — stop processing.

This document defines how data is classified, stored, accessed, used in models, retained, and deleted.

It is an internal control. It is not legal advice. Regulated data handling requires counsel and a customer-specific DPA.

---

## 1. Classes

| Class | Definition | Examples | Default handling |
|---|---|---|---|
| **Public** | Intended for public release. | Website copy, published reports, open-source code. | No restriction beyond accuracy and claims review. |
| **Internal** | Company business data not intended for the public. | Plans, internal memos, non-sensitive metrics, code. | Authenticated access; no external sharing without approval. |
| **Confidential** | Commercial or customer data under NDA or expectation of confidentiality. | Contracts, pricing, pipeline, customer names, QA exports, support tickets. | Need-to-know; encrypted; no model training; external sharing requires approval. |
| **Regulated** | Data subject to a regulatory regime. | PHI, financial account data, government identifiers, call recordings with sensitive content. | DPA, residency decision, access logging, encryption, minimum necessary, Owner approval. |
| **Restricted** | Data whose exposure would be severe. | Secrets, private keys, audit evidence, legal hold, board materials, credentials. | Named access only; hardware-backed storage where possible; no prompts; no exports without two-key. |

### 1.1 Classification rules

1. Classify at the source, before storage.
2. A dataset inherits the highest class of any field it contains.
3. A combination of low-class fields may become confidential or regulated; classify the combination.
4. When a customer labels data, honor the stricter of the customer label and this policy.
5. When classification is unknown, treat it as **Restricted** and stop.
6. Reclassify on contract change, new regulation, or incident.

---

## 2. Handling matrix

| Control | Public | Internal | Confidential | Regulated | Restricted |
|---|---|---|---|---|---|
| Encryption in transit | Required | Required | Required | Required | Required |
| Encryption at rest | Optional | Required | Required | Required | Required |
| Authenticated access | No | Yes | Yes | Yes | Yes |
| MFA | No | Recommended | Required | Required | Required |
| Access logging | No | Yes | Yes | Yes | Yes |
| Need-to-know | No | Recommended | Yes | Yes | Yes |
| External sharing | Approved | Approval | Approval + DPA | DPA + Owner | Two-key + Owner |
| Model prompt use | Allowed | Allowed with review | Prohibited by default | Prohibited without DPA + Owner | Prohibited |
| Model training | Allowed if licensed | Prohibited by default | Prohibited | Prohibited | Prohibited |
| Demo use | Allowed | Synthetic only | Synthetic only | Prohibited | Prohibited |
| Retention | Per claim | Per policy | Contract | Contract + regulation | Legal hold |
| Deletion | Normal | Owner | Owner + contract | Two-key + legal hold | Two-key + legal hold |

---

## 3. Data inventory

Every venture maintains an inventory with:

| Field | Meaning |
|---|---|
| `data_id` | Stable identifier |
| `name` | Human-readable name |
| `class` | Public / Internal / Confidential / Regulated / Restricted |
| `source` | System, customer, or collection method |
| `purpose` | Why it is collected |
| `legal_basis` | Contract, consent, legitimate interest, or other |
| `residency` | Storage and processing location |
| `retention` | Period and trigger |
| `access` | Roles and named humans |
| `model_use` | None / prompt / training / prohibited |
| `owner` | Named human accountable |
| `deletion_method` | How deletion is executed and verified |

No dataset enters production without an inventory entry.

---

## 4. AI and model use

### 4.1 Rules

1. No customer data in a model prompt without:
   - a contract that permits it;
   - a DPA where required;
   - a classification check;
   - Owner approval;
   - a documented retention and training posture from the provider.
2. No cross-customer training.
3. No secrets, credentials, or restricted data in prompts, logs, or memory.
4. Prompts and outputs are evidence artifacts when they influence a consequential decision.
5. A model may not be the sole decision-maker for an R3 action.
6. Model providers are vendors: they require a security and data-processing review.
7. Prompt injection is a data-handling risk. Retrieved content is untrusted input, never instruction.

### 4.2 Model/provider changes

A change of model or provider requires:

- a data-flow review;
- a retention and training review;
- a quality evaluation on the venture's test set;
- Owner approval if data handling changes;
- a rollback plan.

---

## 5. Demo and synthetic data

1. Demo data must be labeled `simulated: true` in the artifact and in the UI.
2. Demo data must not be derived from real customer data without written permission and de-identification review.
3. Screenshots used externally must show the simulated label.
4. Financial demo data must not be presented as actual revenue, pipeline, or runway.
5. A demo environment must be visually distinct from a production environment.

**Known issue:** `CompliProof/workspace/finance/finance.json` shows `mrr: 5000` and `customers: 10`, while the README says "Pre-revenue." This is a truth-freeze blocker.

---

## 6. Residency and retention

### 6.1 Residency

Residency is an Owner decision before any customer data is onboarded. It considers:

- customer contract;
- regulation;
- subprocessors;
- backup location;
- support access;
- model provider location.

No residency claim may be made without a deployment diagram and subprocessor list.

### 6.2 Retention

| Data | Default | Notes |
|---|---|---|
| Audit evidence | Retain; do not delete | Legal hold overrides |
| Customer data | Contract term + required period | Deletion verified |
| Backups | Policy period | Restore tested |
| Logs | 90 days minimum, unless evidence | Security logs may need longer |
| Demo data | Until replaced | Clearly labeled |
| Prompts | Minimum necessary | No regulated data by default |

Retention periods are set by contract and counsel. The default is to retain rather than delete when uncertain.

---

## 7. Access

1. Least privilege.
2. Named accounts; no shared credentials.
3. MFA for all human access to Confidential, Regulated, or Restricted data.
4. Access reviews at each stage gate and after role changes.
5. Revocation within one hour of a role change or incident.
6. Auditors are read-only.
7. Agents use service identities with scoped, short-lived credentials.
8. No production access from a personal account.

---

## 8. Deletion and legal hold

Deletion requires:

1. a verified legal-hold check;
2. a retention-policy check;
3. two-key human approval for audit evidence or regulated data;
4. a deletion receipt;
5. a ledger event that references the deleted evidence ID;
6. confirmation that backups follow the same policy.

Deletion never removes the ledger event that records the deletion.

---

## 9. Incident handling

A suspected data incident triggers `INCIDENT_PLAN.md`.

Minimum actions:

- stop the data flow;
- preserve evidence;
- identify the data classes and subjects;
- assess contractual and regulatory notification duties with counsel;
- notify the Owner;
- do not delete anything.

---

## 10. Vendor and subprocessor rules

Before a vendor receives Confidential, Regulated, or Restricted data:

- security review;
- DPA;
- subprocessor list;
- residency check;
- retention and deletion terms;
- breach notification terms;
- exit and data-return plan;
- Owner approval.

---

## 11. Acceptance tests

1. Every dataset in the inventory has a class and an owner.
2. Unknown data is blocked, not guessed.
3. A regulated dataset cannot be used in a prompt without the required approvals.
4. Demo data is labeled in the artifact and the UI.
5. A deletion request produces a receipt and preserves the ledger event.
6. An access review finds no shared accounts.
7. A backup restore test succeeds.
8. A vendor without a DPA cannot receive confidential data.

---

## 12. Adoption

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Signature | HatemShalaby |
| Adopted on | 2026-10-23 |
| Version | 0.1.0 |

**Adoption statement:** I adopt this classification scheme. I understand that unclassified data is treated as Restricted and that regulated data requires counsel, a DPA, and my explicit approval.
