---
name: devops-engineering
description: Build, ship and operate software repeatably - pipelines, containers, configuration, secrets, observability, rollback and the runbook that makes a release reversible.
order: 22
---

# DevOps engineering

If it is not repeatable from a clean checkout, it is not deployed - it is
running on luck.

## Build

- One command builds the artefact from a clean clone. Pin it in the README.
- Builds are reproducible: pinned tool versions, locked dependencies, no
  network surprises at build time.
- The artefact is immutable and identified by digest or commit SHA. Deploy the
  artefact, never a directory someone edited.

## Configuration

- Config comes from the environment or a mounted file. Never from source.
- Every config value has a documented default, and the default is safe.
- Validate config at startup and fail loudly. A service that boots with a
  broken config fails later, in production, at the worst time.

## Secrets

- Secrets live in a secret store or the OS keyring. Never in the repo, the
  image, the logs or a shell history.
- The application reads a secret by name, not by value.
- Rotating a secret must not require a code change.

## Containers

- One process per container.
- Pin base image digests; rebuild on a schedule to pick up patches.
- Run as non-root, read-only root filesystem where possible.
- Healthcheck reflects real readiness, not "the process started".

## Observability

- Logs are structured and carry a correlation id through every boundary.
- Log the decision, not just the exception: what was attempted, with what
  input, and what happened.
- Metrics that matter: request rate, error rate, duration, saturation.
- Alerts fire on symptoms users feel, not on every internal wobble.

## Release

- Ship small and often. A large release is a large blast radius.
- Canary or staged rollout before full traffic.
- Every release has a rollback that was tested, not imagined.
- A runbook exists before the claim of "done": how to start, stop, inspect,
  roll back and restore data.

## Security baseline

- Least privilege for every token, service account and container.
- Network access is deny by default, allow by exception.
- Dependencies are scanned and patched; an unpatched critical is a finding,
  not a backlog item.

## Evidence

State the exact command and the exact output that proves a deployment works.
"Should be fine" is not evidence.
