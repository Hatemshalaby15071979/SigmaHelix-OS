# Threat Model

**Version:** 0.1.0  
**Status:** Reviewed; no residual risks accepted  
**Reviewed:** 2026-10-23  
**Scope:** Dynamic Company OS, `CompliProof` as the first venture, and the Stage 1 control plane.

This is a working threat model, not a compliance artifact. It identifies what can go wrong, what controls exist or are required, and what risk remains.

---

## 1. Assets

| Asset | Why it matters | Class |
|---|---|---|
| Audit ledger and evidence packs | The basis of every trust claim | Restricted |
| Customer source data | Contractual and regulatory exposure | Confidential / Regulated |
| Approval tokens and signing keys | Authority to act | Restricted |
| Credentials and secrets | Access to systems and data | Restricted |
| Source code and build pipeline | Integrity of the product | Internal |
| Model prompts and memory | Can leak data or carry injected instructions | Confidential / Restricted |
| Financial records and bank access | Direct monetary loss | Restricted |
| Public claims and brand | Legal and reputational exposure | Public |
| Owner identity and accounts | Single point of compromise | Restricted |
| Availability of the cockpit and ledger | Operational control | Internal |

---

## 2. Actors

| Actor | Motivation | Capability |
|---|---|---|
| External attacker | Data, money, disruption | Network, phishing, credential stuffing, supply chain |
| Malicious or careless customer user | Access, curiosity, retaliation | Authenticated access to their tenant |
| Insider (human) | Financial, grievance, error | Legitimate access |
| Agent error | Task completion pressure | Tool use, data access, external calls |
| Prompt injection via retrieved content | Manipulate agent behavior | Control of a web page, document, email, or ticket |
| Model/provider | Data retention, drift, outage | Access to prompts and outputs |
| Supply-chain attacker | Code execution, data exfiltration | Dependency, package, build system |
| Competitor | Information, disruption | Public scraping, social engineering |
| Auditor | Verification | Read-only access |
| Regulator | Compliance | Legal authority |

**Assumption:** the Owner is a single point of failure and a high-value target. Solo-owner mode increases the impact of account takeover and coercion.

---

## 3. Trust boundaries

```
[Owner browser]
      |
      | TLS, MFA, session
      v
[Cockpit / API] ---> [Approval service] ---> [Canonical ledger] ---> [External anchor]
      |                    |                        |
      |                    v                        v
      |             [Policy engine]           [Evidence store]
      |
      v
[Agent runtime] ---> [Tool adapters] ---> [External systems]
      |
      v
[Model provider / local model]
```

Boundaries:

1. Browser to cockpit.
2. Cockpit to approval service.
3. Approval service to ledger.
4. Agent runtime to tools.
5. Tool adapters to external systems.
6. Agent runtime to model provider.
7. Evidence store to external verifier.
8. Company to customer/tenant.
9. Build pipeline to production.
10. Human role to human role.

Every boundary needs authentication, authorization, input validation, logging, and a failure mode.

---

## 4. Abuse cases and controls

### 4.1 Evidence and audit

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-01 | Attacker edits an evidence artifact after sealing | False audit trail | Hash verification; seal binds approval and artifact; external anchor | Anchor provider compromise |
| T-02 | Operator rewrites or truncates the ledger | Undetected history loss | Single writer; hash chain; anchored head; independent verifier | Insider with signing keys |
| T-03 | Approval is replayed to authorize a different action | Unauthorized action | Token bound to action hash; nonce; single use; expiry | Stolen token before expiry |
| T-04 | Test run writes to the production ledger | Contaminated evidence | Isolated test ledger; environment guard; CI check | Misconfiguration |
| T-05 | Report shows global events, not task events | Misleading report | Task-scoped query; report hash; golden tests | Query bug |
| T-06 | Evidence is deleted to hide a failure | Cover-up | Two-key deletion; legal hold; deletion receipt; ledger event | Owner coercion |
| T-07 | Seal excludes a material field (e.g., approval) | False integrity claim | Seal manifest enumerates all material fields; tamper test | Unknown future field |

### 4.2 Identity and access

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-08 | Credential stuffing on the cockpit | Account takeover | MFA; rate limiting; lockout; breached-password check | Phishing |
| T-09 | Open registration creates an attacker account | Unauthorized access | Registration disabled by default; invite-only | Misconfiguration |
| T-10 | Session cookie theft | Impersonation | Secure/HttpOnly/SameSite; short idle timeout; rotation; CSRF token | Endpoint compromise |
| T-11 | Agent uses a human credential | Non-repudiation loss | Agents use service identities; human credentials never exposed to tools | Secret leakage |
| T-12 | Owner account is sole admin and is lost | Lockout | Break-glass recovery; sealed recovery codes; backup approver | Physical loss |
| T-13 | Role confusion grants operator auditor rights | Unauthorized evidence access | RBAC; deny by default; access review | Policy bug |

### 4.3 Agent and model

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-14 | Prompt injection in a web page or document | Agent takes unauthorized action | Treat retrieved content as data; tool allowlist; no raw instruction execution; approval gates | Novel injection |
| T-15 | Agent expands its own scope or budget | Unbounded action | Envelope limits; policy engine; runtime budget; kill switch | Policy gap |
| T-16 | Agent fabricates a source or quote | False research | Source retrieval log; verbatim quote check; corroboration; human review | Subtle misreading |
| T-17 | Agent sends an unapproved external message | Reputational/legal harm | Outbound allowlist; template hash; recipient consent; first-batch review | Tool bypass |
| T-18 | Memory poisoning persists a malicious instruction | Persistent misbehavior | Memory classification; no untrusted instructions as policy; review; expiry | Gradual drift |
| T-19 | Model provider retains or trains on data | Data leakage | DPA; no regulated data; provider review; local model option | Provider breach |
| T-20 | Model drift degrades quality | Bad decisions | Evaluation set; version pinning; canary; rollback | Undetected drift |

### 4.4 Build and supply chain

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-21 | Malicious dependency | Code execution/exfiltration | Lockfile; SBOM; dependency scanning; pinned versions; review | Zero-day |
| T-22 | Compromised build runner | Backdoored release | Isolated runner; short-lived credentials; provenance; signed artifacts | Runner compromise |
| T-23 | Secrets committed to source | Credential theft | Secret scanning; pre-commit hook; rotation; no secrets in prompts | Historical leaks |
| T-24 | Unreviewed merge to main | Defect or backdoor | Protected branch; review; CI; signed commits | Reviewer fatigue |
| T-25 | Production deploy without canary/rollback | Outage | Release envelope; canary; rollback proof; two-key | Unknown failure mode |

### 4.5 Data and privacy

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-26 | Customer data used in a demo | Confidentiality breach | Synthetic data; classification; demo labeling; egress control | Accidental copy |
| T-27 | Cross-tenant data leak | Contract/regulatory breach | Tenant isolation; tests; per-tenant keys; access review | Shared cache bug |
| T-28 | Regulated data sent to a model | Regulatory breach | DPA; classification gate; prompt redaction; provider review | Misclassification |
| T-29 | Data residency violation | Contract/regulatory breach | Residency decision; deployment diagram; subprocessor list | Provider region change |
| T-30 | Backup contains deleted data | Retention violation | Backup policy; deletion propagation; restore test | Backup immutability |

### 4.6 Finance and external action

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-31 | Fraudulent invoice or bank change | Direct loss | Owner executes payment; callback verification; dual control when available | Social engineering |
| T-32 | Unauthorized discount or contract term | Margin/legal loss | Approval matrix; exception escalation; contract review | Ambiguity |
| T-33 | Public claim exceeds evidence | Legal/reputational harm | Claims registry; E2+ evidence; Owner approval; retraction plan | Misreading evidence |
| T-34 | Support agent promises a refund or feature | Liability | KB limits; escalation; no commitments; sample review | Edge-case language |
| T-35 | Incident notification is delayed | Regulatory/contract breach | Incident plan; severity; Owner declaration; counsel | Detection delay |

### 4.7 Availability and operations

| ID | Abuse case | Impact | Controls | Residual |
|---|---|---|---|---|
| T-36 | Ledger or cockpit outage | Loss of control | Backups; restore test; status page; on-call | Solo-owner availability |
| T-37 | Ransomware encrypts evidence | Loss of audit trail | Immutable/offline backup; least privilege; restore test | Backup compromise |
| T-38 | Kill switch fails | Runaway agent | Tested kill switch; multiple stop paths; tabletop | Unknown path |
| T-39 | Owner unavailable for an R3 decision | Stalled operations | Default deny; scheduled review; backup approver when named | Delay |

---

## 5. Highest-risk scenarios

### 5.1 False assurance

The company claims audit-grade evidence while the underlying seal, ledger, or verification is defective. A customer relies on it in an audit and fails. This is the highest reputational and legal risk because the product's core promise is trust.

**Controls:** evidence standard; E3/E4 requirement; independent verification; claims registry; no audit-grade claim without an external auditor.

### 5.2 Solo-owner compromise

An attacker takes over the Owner's account and uses legitimate authority to approve payments, releases, or data access.

**Controls:** MFA; hardware key; short sessions; approval token binding; anomaly alerts; break-glass recovery; second approver for R3 before any external scale.

### 5.3 Prompt-injected agent with external tools

An agent reads a malicious document and sends data or money outside the company.

**Controls:** no direct tool access without policy; outbound allowlist; envelope caps; human approval for external actions; content provenance; kill switch.

### 5.4 Evidence contamination

Test events, demo data, or multiple ledgers corrupt the audit record. The company cannot prove what happened.

**Controls:** one ledger; isolated test environment; environment guards; ledger namespace; retention; independent verification.

---

## 6. Controls by stage

| Control | Stage 0 | Stage 1 | Stage 3 | Stage 4+ |
|---|---|---|---|---|
| Constitution and authority matrix | Adopt | Enforce | Enforce | Enforce |
| Canonical ledger | Specify | Build | Use | Use |
| External anchor | Select provider | Implement | Verify | Verify |
| Approval tokens | Specify | Build | Use | Use |
| Cockpit auth and RBAC | Specify | Build | Use | Use |
| Kill switch | Tabletop | Build/test | Use | Use |
| Claims registry | Draft | Enforce | Enforce | Enforce |
| Data classification | Adopt | Enforce | Enforce | Enforce |
| Vendor review | Specify | Apply | Apply | Apply |
| Independent audit | Plan | Engage | Review | Review |

---

## 7. Residual risks

These risks are not accepted. They are recorded so the Owner can decide.

| Risk | Why it remains | Decision needed |
|---|---|---|
| Owner is a single point of failure | Solo-owner mode | Name a backup approver before R3 |
| No independent auditor | Not yet engaged | Engage before any audit-grade claim |
| No external anchor provider | Not yet selected | Select in Stage 1 |
| No production on-call | No production yet | Define before first release |
| Model provider dependency | Quality/cost/convenience | Review before regulated data |
| Local hosting | Simplicity | Revisit before customer access |
| Small team | Capacity | Prioritize the narrow wedge |

---

## 8. Review and testing

1. Review this threat model at every stage gate.
2. Re-review after any security incident, architecture change, or new data class.
3. Test the kill switch in a tabletop before Stage 0 closes and in a live drill before production.
4. Run abuse-case tests for the top five scenarios before each release.
5. Record accepted risks with Owner signature and an expiry/review condition.

---

## 9. Sign-off

| Field | Value |
|---|---|
| Reviewer | HatemShalaby |
| Role | Owner |
| Reviewed on | 2026-10-23 |
| Version | 0.1.0 |
| Accepted residual risks | None accepted. All residual risks remain recorded and unaccepted. |
