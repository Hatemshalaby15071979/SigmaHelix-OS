#!/usr/bin/env python3
"""Create verified SigmaHelix database snapshots and restore new copies."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from sigmahelix.core.config import load_settings
from sigmahelix.core.storage import BackupError, Database, DatabaseBackup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "export"):
        backup_parser = subparsers.add_parser(
            name, help="export a consistent DB snapshot"
        )
        backup_parser.add_argument("--destination", type=Path, required=True)
    restore_parser = subparsers.add_parser(
        "restore", help="restore to a new database path"
    )
    restore_parser.add_argument("--source", type=Path, required=True)
    restore_parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        backup = DatabaseBackup()
        if args.command in {"backup", "export"}:
            manifest = backup.export(
                Database(load_settings().database_path), args.destination
            )
        else:
            manifest = backup.restore(args.source, args.destination)
        print(json.dumps(asdict(manifest), sort_keys=True))
    except (BackupError, FileNotFoundError, FileExistsError, ValueError) as exc:
        parser.exit(2, f"sigmahelix {args.command}: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
