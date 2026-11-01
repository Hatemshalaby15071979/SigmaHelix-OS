# Hash-chained audit log

Schema migration v2 adds `audit_log`, a globally ordered append-only table. Every row records a tenant label, action, entity reference, UTC timestamp, canonical JSON payload, previous digest, and current SHA-256 digest. The digest commits to the schema version marker and all row fields. Sequence allocation and predecessor lookup run under `BEGIN IMMEDIATE`, so concurrent writers serialize. `append_in_transaction()` lets a caller commit an audit record atomically with its domain change.

`AuditLog.verify()` checks contiguous sequence numbers, canonical payload encoding, predecessor links, and every digest from the all-zero genesis hash. SQLite triggers reject updates and deletes; the verifier also detects altered, removed-middle, reordered, and non-canonical rows. The query API is tenant scoped, while verification checks the global chain.

Payload validation rejects secret-like field names and recognized credential patterns before persistence, consistent with the rule that credentials stay in the OS keyring.

The chain provides tamper evidence for changed or partially removed records. It is not a digital signature or an external anchor: an attacker able to rewrite the database and recompute the entire chain can forge a replacement history. External anchoring is outside P1-006.
