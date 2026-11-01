# Evidence Standard

**Version:** 0.1.0  
**Status:** Adopted  
**Adopted:** 2026-10-23  
**Applies to:** every venture, agent, report, claim, approval, and audit event

This standard defines what counts as evidence, how it is recorded, how it is sealed, and how a third party verifies it.

The purpose is not to produce impressive-looking artifacts. The purpose is to make it possible for a skeptical outsider to check what the company says.

---

## 1. Core rules

1. **No claim without a source.** A statement is a hypothesis until it has an artifact.
2. **Intent before action.** A consequential action writes an intent event before it executes.
3. **Result after action.** The result event includes the outcome, the artifact hash, and any deviation.
4. **One canonical ledger.** No module keeps a private consequential ledger.
5. **Hash what you export.** Every exported artifact has a content hash and a manifest.
6. **Anchor what you seal.** A sealed batch has an external timestamp; without it, the artifact is internally consistent, not tamper-evident.
7. **Verify without trust.** A third party can verify a pack without relying on the company's UI or servers.
8. **Preserve the source.** Store the source artifact or a reproducible retrieval record; do not store only a summary.
9. **Separate fact from inference.** Label each.
10. **Expire what can expire.** Market and competitive evidence has a validity window.

---

## 2. Evidence levels

| Level | Name | Definition | Permitted use |
|---|---|---|---|
| E0 | Assertion | A statement with no artifact. | Internal hypothesis only. Never external. |
| E1 | Internal record | An internal note, ticket, or log that is not independently reproducible. | Internal decision support. Not a customer claim. |
| E2 | Reproducible artifact | A source, export, test run, or dataset with a hash, retrieval record, and method. | Product and market claims, with review. |
| E3 | Externally anchored | An E2 artifact included in a sealed batch with an RFC 3161 timestamp or equivalent external anchor. | Security, audit, and evidence claims. |
| E4 | Third-party verified | An E3 artifact reviewed and attested by an independent auditor or qualified third party. | Audit-grade, certification, and regulatory claims. |

**Rules**

- A external product claim requires **E2 or higher**.
- A security, audit, or tamper-evidence claim requires **E3 or higher**.
- A claim of audit-grade, certification, or independent assurance requires **E4**.
- A market-size claim requires a primary source and a stated method. If the method is bottom-up and assumptions are explicit, it may be E2.
- An E0 or E1 artifact may never be presented as proof to a customer, auditor, or regulator.

---

## 3. Claim-to-evidence mapping

Every external claim in the claims registry must link to:

| Field | Requirement |
|---|---|
| `claim_id` | Stable ID in `CLAIMS_REGISTRY.yaml` |
| `claim_text` | Exact text approved for use |
| `evidence_ids` | At least one E2+ artifact for a product claim; E3/E4 for security or audit claims |
| `scope` | Product, version, customer segment, and date range |
| `limitations` | What the evidence does **not** prove |
| `owner` | Named human accountable for the claim |
| `reviewed_on` | Date of last review |
| `expires_on` | Date after which the claim must be re-verified, where applicable |

A claim with no mapping is removed, not softened.

---

## 4. Evidence object

Every evidence artifact is described by a manifest:

```json
{
  "evidence_id": "ev_01J...",
  "venture_id": "v_compliproof",
  "type": "source_export",
  "title": "QA scores export, design partner A",
  "source": {
    "uri": "s3://...",
    "retrieved_at": "2026-10-23T10:00:00Z",
    "retrieved_by": "agent:research-01",
    "retrieval_method": "customer upload"
  },
  "classification": "confidential",
  "content_hash": "sha256:...",
  "size_bytes": 1048576,
  "media_type": "text/csv",
  "quote": null,
  "claim_ids": ["CLM-021"],
  "confidence": "high",
  "corroboration": ["ev_01J..."],
  "limitations": "One customer; not representative of the segment.",
  "expires_on": "2027-04-23",
  "created_by": "agent:research-01",
  "reviewed_by": "owner",
  "reviewed_on": "2026-10-23"
}
```

**Required fields:** `evidence_id`, `venture_id`, `type`, `source.uri`, `source.retrieved_at`, `content_hash`, `classification`, `created_by`.

**Rules**

- `evidence_id` is unique and never reused.
- `content_hash` is computed over the exact bytes stored, not over a summary.
- `quote` is verbatim and must appear in the source.
- `claim_ids` links the artifact to the claims it supports or refutes.
- `limitations` is mandatory for any evidence used in a decision.
- `reviewed_by` must be a human for any evidence used in an external claim.

---

## 5. Canonicalization and hashing

1. Structured payloads are canonicalized before hashing using **RFC 8785 JSON Canonicalization Scheme (JCS)** or a documented equivalent.
2. Text artifacts are hashed over their exact UTF-8 bytes.
3. Binary artifacts are hashed over their exact bytes.
4. Hash format: `sha256:<64 lowercase hex characters>`.
5. The hash algorithm is recorded in the manifest. A future algorithm change requires a versioned migration, not a silent re-hash.
6. A hash proves integrity, not truth. A hash of a false document is still a hash of a false document.

---

## 6. Ledger model

### 6.1 Event types

| Event | When | Required payload |
|---|---|---|
| `action.intent` | Before a consequential action | action hash, actor, role, envelope, scope, expected effect |
| `action.approved` | When a human approves | approval token, approver, action hash, expiry |
| `action.denied` | When approval is refused | reason, approver, action hash |
| `action.result` | After execution | outcome, artifact hash, duration, deviation |
| `action.failed` | On failure | error class, partial effects, rollback status |
| `evidence.created` | When an artifact is registered | evidence manifest |
| `report.generated` | When a report is produced | report hash, task ID, evidence IDs |
| `export.created` | When data leaves the system | export hash, recipient, purpose, classification |
| `deletion.requested` | Before deletion | evidence IDs, legal-hold check, approvals |
| `deletion.completed` | After deletion | deletion receipt, remaining references |
| `incident.opened` | On incident declaration | severity, scope, commander |
| `incident.closed` | On closure | root cause, actions, evidence |
| `anchor.created` | When a batch is externally anchored | batch hash, anchor receipt |

### 6.2 Event fields

Every event includes:

- `event_id` (ULID or UUIDv7)
- `seq` (monotonic per ledger)
- `prev_hash`
- `event_hash`
- `type`
- `occurred_at` (RFC 3339 UTC)
- `actor_id`
- `actor_role`
- `venture_id`
- `correlation_id`
- `payload`
- `payload_hash`
- `schema_version`

### 6.3 Write rules

1. A single writer or a transactional append service owns the ledger.
2. Concurrent writers are serialized; no last-write-wins.
3. An event is durable before the action proceeds.
4. The ledger is append-only. Corrections are new events that reference the original.
5. Test runs use an isolated ledger; tests may never write to a production or shared ledger.
6. A ledger write failure aborts the action.

---

## 7. Sealing and anchoring

### 7.1 Seal

A seal binds:

- the artifact manifest;
- the artifact bytes hash;
- the evidence IDs;
- the claim IDs;
- the approver and approval token;
- the ledger head at seal time.

The seal hash is computed over the canonical seal manifest. Changing any bound field changes the seal hash.

### 7.2 External anchor

A sealed batch is externally anchored with an RFC 3161 timestamp token from an approved Time-Stamp Authority, or an equivalent public transparency mechanism approved by the Owner.

The anchor receipt is stored with the batch. A verification report includes:

- the batch hash;
- the anchor receipt;
- the verification command and output;
- the verifier identity and time.

**Without an anchor, the maximum evidence level is E2.** The company may say "internally consistent" but may not say "tamper-evident" or "externally verified."

### 7.3 Anchor failure

If the anchor service is unavailable:

1. mark the batch `unanchored`;
2. do not make an E3/E4 claim;
3. retry within the evidence gate;
4. record the failure and the retry;
5. if the batch is time-sensitive, escalate to the Owner.

---

## 8. Source quality

### 8.1 Source hierarchy

1. Primary source: the customer's own export, contract, system of record, or direct statement.
2. Regulator or official registry.
3. Peer-reviewed or methodologically documented research.
4. Reputable industry report with a stated method.
5. Vendor marketing or opinion: usable only as a claim about the vendor, not as market fact.

### 8.2 Corroboration

- A market fact used in a thesis requires at least two independent sources, or one primary source plus a documented method.
- A customer pain claim requires at least two independent interviews, or one interview plus observed behavior.
- A security claim requires a test result, not a design document.
- A revenue or pipeline claim requires the underlying records.

### 8.3 Market research rules

1. Record the query, date, source, and exact quote.
2. Distinguish customer statements from the researcher's interpretation.
3. Do not generalize from one interview.
4. Do not present a bottom-up estimate as a market fact; show the formula and assumptions.
5. Record disconfirming evidence, not only supporting evidence.
6. Date-stamp every market claim; markets move.

---

## 9. Confidence language

Use only these labels:

| Label | Meaning |
|---|---|
| **Observed** | Directly witnessed or recorded. |
| **Verified** | Reproduced from a primary source or test. |
| **Corroborated** | Supported by at least two independent sources. |
| **Inferred** | A conclusion from stated evidence, with the reasoning shown. |
| **Hypothesis** | A testable proposition, not yet confirmed. |
| **Unknown** | No sufficient evidence. |

Do not use "probably," "clearly," "obviously," or "industry-standard" as substitutes for evidence.

---

## 10. Test and security evidence

A test artifact is admissible only if it records:

- commit SHA or artifact hash;
- test command;
- environment and dependency lock;
- timestamp;
- pass/fail counts;
- coverage, where relevant;
- the exact output;
- who or what ran it.

A security scan is admissible only if it records:

- scanner and version;
- ruleset or database version;
- scope;
- raw output;
- triage decisions;
- accepted risks with Owner approval.

A penetration test is admissible only if it records:

- scope and rules of engagement;
- tester identity;
- findings with severity;
- remediation evidence;
- retest result.

---

## 11. Verification

### 11.1 Verifier requirements

A third-party verifier must be able to:

1. obtain the evidence pack and manifest;
2. recompute every content hash;
3. walk the ledger chain from the genesis event to the head;
4. verify the anchor receipt;
5. confirm the approval token signatures and binding;
6. confirm that the report was generated from the same evidence;
7. detect any missing, reordered, or altered event.

### 11.2 Verification output

The verifier produces:

- `verified` or `failed`;
- the first failing check;
- the ledger head and anchor;
- the evidence IDs checked;
- the verifier identity and time;
- a machine-readable result and a human-readable summary.

### 11.3 Independence

The verifier must not depend on a mutable company API to establish the truth of the pack. A static export plus published verification instructions is the minimum. A hosted verifier may be offered as a convenience, not as the only path.

---

## 12. Retention and deletion

1. Default: retain audit evidence; do not delete.
2. A contract or legal requirement may set a longer or shorter period.
3. Deletion requires:
   - a legal-hold check;
   - two-key human approval;
   - a deletion receipt;
   - a record of what remains referenced.
4. Deleted evidence is marked `deleted` in the ledger; the ledger event is not deleted.
5. Backups follow the retention policy and are included in restore tests.

---

## 13. Prohibited practices

- Hashing a summary and calling it the artifact hash.
- Storing only a screenshot of a source.
- Editing a report after sealing without a new seal.
- Reusing an evidence ID.
- Writing test events to a shared ledger.
- Calling an unanchored chain "tamper-evident."
- Presenting a design document as a test result.
- Presenting a vendor claim as market fact.
- Deleting a failing test or a contradictory interview.
- Using a customer's data in a demo without written permission.

---

## 14. Acceptance tests for the evidence system

The evidence system is not ready until all of these pass:

1. A tampered artifact fails hash verification.
2. A tampered approval changes the seal hash.
3. A tampered sealed answer key fails verification.
4. A truncated ledger is detected by the anchor comparison.
5. A reordered event is detected.
6. A replayed approval token is rejected.
7. A test run cannot write to the production ledger.
8. A report generated from an audit event reproduces the same totals and evidence IDs.
9. A third party can verify a pack using only the exported files and published instructions.
10. An unanchored pack is labeled E2, not E3.

---

## 15. Adoption

| Field | Value |
|---|---|
| Owner | HatemShalaby |
| Signature | HatemShalaby |
| Adopted on | 2026-10-23 |
| Version | 0.1.0 |

**Adoption statement:** I adopt this standard. I understand that a claim above the evidence level is a false claim, regardless of intent.
