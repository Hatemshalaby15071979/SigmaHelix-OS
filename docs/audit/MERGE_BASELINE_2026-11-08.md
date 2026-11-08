# Merge baseline — 2026-11-08

Recorded before any consolidation work. Purpose: prove that nothing was lost when
`company-os/` and `company-os-app/` are retired, and give every later phase a
reference point to diff against.

## Sources

| Tree | Files hashed | Notes |
|---|---:|---|
| `Career/company-os/` | 45 | documentation only, no executable code |
| `Career/company-os-app/` | 21 | `venv/`, `build/`, `dist/`, `__pycache__/`, `.pytest_cache/` excluded — environment and build output, not source |
| `Career/sigmahelix/` | 196 | `.git/`, `__pycache__/`, `.ruff_cache/` excluded |

Total: 262 files.

## Manifest

`MERGE_BASELINE_2026-11-08.sha256` — SHA-256 of every file, in `sha256sum` format,
paths relative to `Career/`. Verify with:

```bash
cd /run/media/hatem/2A3AE01E311C617F/Career
sha256sum -c sigmahelix/docs/audit/MERGE_BASELINE_2026-11-08.sha256
```

Manifest digest: `824654c9a83aee2fe50796e5207f5dad12d2776030b272a820bea3e101eb13fb`

## Archive

Both source folders were copied to `Career/_archive_pre_merge/` before any edit:

- `_archive_pre_merge/company-os/` (664 KB)
- `_archive_pre_merge/company-os-app/` (248 KB)

The archive excludes the 141 MB `venv/` and the 107 MB `build/` + `dist/` trees.
Those are reproducible from `requirements.txt` and `CompanyOS.spec`, which are
included.

## Git reference

Repository: `Career/sigmahelix`, branch `main`, HEAD `9924f5d`, 37 commits,
working tree clean at tagging time.

Tag: `pre-merge-2026-11-08` — the exact commit the consolidation started from.
Any phase can be rolled back with:

```bash
git -C SigmaHelix reset --hard pre-merge-2026-11-08
```

## Known state at baseline

- `sigmahelix` core: 122 tests passing, 89% coverage, mypy clean.
- `sigmahelix/apps/desktop`: 26 tests, security fork frozen 2026-11-02.
- `company-os-app`: 58 tests, last edited 2026-11-08, not under version control,
  two known hard crashes (`console_os.py` reads `agent.model`; `main.py` reads
  `T.colors["text"]`).
- `company-os`: byte-identical superset relationship with
  `sigmahelix/docs/governance/` — 44/45 identical, 1 older, 0 unique files.
