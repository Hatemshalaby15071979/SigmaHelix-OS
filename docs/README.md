# Documentation

| Path | What is there |
| --- | --- |
| `CONSOLIDATION.md` | What the three pre-merge trees contained and how they were combined |
| `adr/` | Architecture decision records, numbered, oldest first |
| `architecture/` | How each core service works: schema, audit, scheduler, alarms, scanner, launchers, backup |
| `security/` | Threat notes and the secret-handling policy |
| `execution/` | The gate ledger (`LEDGER.yaml`), session log, and per-task evidence |
| `audit/` | The pre-merge baseline: file counts, checksums, and the safety net |
| `governance/` | Source documents and stage reviews inherited from the earlier trees |

Start with `../README.md` for what the product does, then `architecture/` for
how it is built, and `adr/` for why.

## Conventions

- Every ADR states the decision, the alternatives considered, and the
  consequence we accepted.
- Evidence files record commands that were actually run, with their output.
  They are historical: they describe the tree as it was on that date.
