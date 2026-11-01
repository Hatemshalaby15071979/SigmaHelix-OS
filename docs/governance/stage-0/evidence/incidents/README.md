# Incident Evidence Staging

Default preservation location for Stage 0 incident evidence.

## Rules

1. Create one directory per incident: `INC-<YYYYMMDD>-<short-id>/`.
2. Capture before repair.
3. Keep originals. Work from copies.
4. Write a `SHA256SUMS` manifest covering every captured file.
5. Record the absolute path, capture time, and custodian in the incident record.
6. Keep the location access-controlled. Do not store credentials or secrets here.
7. Do not store regulated data. Stage 0 permits synthetic or redacted evidence only.
8. Do not edit or delete the original ledger. Preserve it as captured.

## Layout

```
INC-20261023-example/
  SHA256SUMS
  manifest.md
  ledger/
  approvals/
  logs/
  notifications/
  notes/
```

`manifest.md` records what was captured, why, by whom, and the chain of custody.
