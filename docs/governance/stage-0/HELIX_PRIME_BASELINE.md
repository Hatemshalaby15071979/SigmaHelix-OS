# Helix Prime Baseline

**Status:** Unverified — document review only  
**Purpose:** Record what is known, what is claimed, and what must be proven before Helix Prime is used as the governance kernel.  
**Decision:** Helix Prime is a **candidate kernel**, not an approved dependency.

---

## 1. What was inspected

- `CompliProof/helix-prime/AGENTS.md`
- `CompliProof/helix-prime/docs/HELIX_CODEX_OS_MASTER_BLUEPRINT.md`
- `CompliProof/helix-prime/control_plane/governance.py`
- `CompliProof/helix-prime/organization/role-catalog.yaml`

The review focused on governance primitives, role separation, approval limits, audit behavior, and production readiness claims.

---

## 2. What Helix Prime appears to provide

- A governance gate with fail-closed role, cost, and confidence boundaries.
- Role definitions with approval limits and separation-of-duties constraints.
- Approval and oversight concepts.
- A kill-switch concept.
- Audit and evidence concepts.
- Governed memory and capability packs.
- Release gates and a console.
- A role catalog with peer-call authority.

These are relevant primitives. They are not, by themselves, a company OS.

---

## 3. Claims that remain unverified

| Claim | Status | Why it matters |
|---|---|---|
| 1,897 tests pass | **Unverified** | The suite was not run in this review. |
| Production-ready governance | **Contradicted by its own docs** | The project describes itself as pre-pilot. |
| Nine external production gates are satisfied | **Unverified** | External signatures were not inspected. |
| Fail-closed role enforcement | **Code-reviewed, not executed** | Needs adversarial tests. |
| Audit integrity | **Code-reviewed, not independently verified** | Needs the evidence standard applied. |
| Kill switch works | **Documented, not tested** | Needs a tabletop and a live drill. |
| License and provenance are compatible | **Unverified** | Needed before reuse. |

---

## 4. What must be proven before adoption

1. The test suite runs from a clean environment and passes, or every failure is triaged.
2. CI is reproducible and pinned.
3. Dependencies are locked; an SBOM is produced.
4. Governance boundaries are tested adversarially: role escalation, cost limit, confidence limit, oversight-only enforcement.
5. Audit and evidence behavior meets the OS evidence standard.
6. The kill switch is tested.
7. License and provenance are reviewed.
8. The nine external gates are identified, with owners and evidence.
9. A integration boundary is defined: what the OS calls, what it owns, and what it does not reuse.

---

## 5. Integration stance

- Reuse governance primitives where they are proven.
- Do not inherit production-readiness claims.
- Do not copy code without license and provenance review.
- Do not let Helix Prime become a second ledger.
- Keep the OS authority matrix and evidence standard authoritative over any inherited behavior.

---

## 6. Verification record

| Check | Result | Evidence |
|---|---|---|
| Document review | Complete | This file; audit appendix |
| Test suite | Not run | — |
| CI reproducibility | Not checked | — |
| Dependency lock/SBOM | Not checked | — |
| License/provenance | Not checked | — |
| Adversarial governance tests | Not run | — |
| Kill-switch test | Not run | — |
| External production gates | Not verified | — |

**Conclusion:** Helix Prime may be a useful kernel, but it is not approved for production use. Stage 1 must verify it before integration.
