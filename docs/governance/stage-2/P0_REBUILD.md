# P0 Rebuild — Clean-room v1 — G-8

## Directive
Rebuild all 7 P0s in clean-room v1. Do not patch the demo; rebuild from scratch.

## 7 P0s to Rebuild

### P0-1: packaging_deployment
- **Title**: Package cannot be installed and Docker image cannot build
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: python -m build produces wheel; pip install in clean venv succeeds; docker build succeeds

### P0-2: evidence_integrity
- **Title**: Seal excludes approval and key verification can never fail
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: changing approval changes the seal hash; tampering fails verification

### P0-3: audit_ledger
- **Title**: Audit is post-action, not concurrency-safe, not externally anchored, and split
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: intent event is durable before execution; concurrent append produces valid ordered chain

### P0-4: reporting_reconciliation
- **Title**: Headline metric is wrong; served report drops totals, rows, pack, and hash
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: perfect 2-vs-2 renders 100.0% directly and when served; CSV contains source values

### P0-5: server_reporting
- **Title**: HTML report route crashes and all report routes are unauthenticated
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: every report route requires authentication and authorization; CORS explicit not wildcard

### P0-6: authentication
- **Title**: Authentication is not suitable for a compliance product
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: passwords use Argon2id or bcrypt; sessions server-side hashed at rest rotated and expire; RBAC enforced; MFA required

### P0-7: ui_security
- **Title**: Dashboard is unusable out of the box and the unauthenticated surface is too broad
- **Disposition**: rebuild_in_v1
- **Target**: clean-room v1
- **Acceptance**: dashboard has working login and logout; every non-public route requires authentication

## Clean-room v1 Directive
- Start from truth-frozen state (2026-10-23)
- Apply all truth_freeze_mitigation changes that were applied on 2026-10-23
- Rebuild affected slices from scratch, not patches
- All acceptance tests must pass in clean-room environment
- Evidence bundles must match regenerated artifacts