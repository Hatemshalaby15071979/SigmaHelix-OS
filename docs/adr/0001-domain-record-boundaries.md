# ADR 0001: Domain record boundaries

- Status: Accepted
- Date: 2026-11-02

## Context

The durable core needs stable records before its SQLite schema and repositories are introduced. The v1 product is local and single-user, but the master plan explicitly keeps a tenant scope on records. Evidence is a source-backed claim, and approvals must bind a human decision to an exact proposed payload.

## Decision

Use Python standard-library frozen dataclasses and enums for the v1 domain records. Each record uses a UUID, UTC-aware timestamps, and the `local` tenant scope by default. Constructors validate domain invariants and reject invalid values at the boundary. Events accept only JSON-compatible payloads. Approval records bind an action name, risk level, payload SHA-256, expiry, and consistent decision metadata. Evidence records retain a source reference and optional artifact SHA-256.

## Consequences

- The core adds no runtime validation dependency to the hash-locked environment.
- SQLite persistence can map these explicit values without an ORM.
- Schema evolution remains explicit in the migration layer; model validation alone is not a migration.
- v1 records remain single-user despite carrying a scope key.
