# Security Policy

## Supported Versions

SigmaHelix-OS is currently in beta (`v1.0.x`). Only the latest released version
on the `main` branch receives security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Use GitHub's private vulnerability reporting instead:

1. Open the **Security** tab of this repository.
2. Click **Report a vulnerability**.
3. Fill in the form with as much detail as possible: affected version, steps to
   reproduce, and potential impact.

This opens a **private security advisory** visible only to maintainers. If private
reporting is unavailable for this repository, contact the maintainer directly and
encrypt the report if possible.

### What to expect

- **Acknowledgement:** within 72 hours of a valid report.
- **Triage & initial assessment:** within 7 days.
- **Status updates:** at least every 7 days while the issue is open.
- **Fix & disclosure:** once a fix ships, we credit the reporter (unless anonymity
  is requested) and publish a short advisory.

## Scope

**In scope**

- Secrets handling (OS keyring storage, redaction in logs and the append-only
  ledger).
- The local web UI / CLI attack surface (loopback-only serving, per-session
  tokens).
- Launcher execution (whitelisted environment, `shell=False`).
- Audit / hash-chain integrity.

**Out of scope**

- Vulnerabilities in third-party dependencies (please report upstream, but feel
  free to flag them to us).
- Social engineering or physical access to the user's machine.
- Theoretical concerns without a concrete reproduction.

## Notes

SigmaHelix-OS is a **local-first, single-user** application. Its threat model
assumes an attacker does not already have full control of the user's machine. See
[`docs/security/THREAT_MODEL_V1.md`](docs/security/THREAT_MODEL_V1.md) for the
full model.
