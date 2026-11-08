"""Command-line entry point for SigmaHelix.

Every subcommand is a thin, explicit wrapper around a service in
:mod:`sigmahelix.core`. Nothing here keeps state of its own: the database is
the single source of truth, so the CLI and the desktop app always agree.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .core.config import ConfigError, load_settings
from .core.storage import (
    AuditLog,
    BackupError,
    Database,
    DatabaseBackup,
    MigrationRunner,
    ProjectScanner,
    TaskRepository,
)
from .core.storage.repositories import NoteRepository, ProjectRepository

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


# --------------------------------------------------------------------------
# output helpers
# --------------------------------------------------------------------------
def _table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """Render a plain-text table that stays readable in any terminal."""
    cells = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in cells:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in cells
    )
    return "\n".join(lines)


def _ok(label: str, detail: str = "") -> str:
    return f"  [ok]   {label}" + (f"  {detail}" if detail else "")


def _warn(label: str, detail: str = "") -> str:
    return f"  [warn] {label}" + (f"  {detail}" if detail else "")


def _fail(label: str, detail: str = "") -> str:
    return f"  [fail] {label}" + (f"  {detail}" if detail else "")


def _open_database() -> Database:
    database = Database(load_settings().database_path)
    database.initialize()
    return database


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def command_gui(_: argparse.Namespace) -> int:
    """Start the desktop app."""
    try:
        from .app.ui import SigmaHelixApp
    except ImportError as exc:
        print(
            "The desktop interface needs CustomTkinter, which is missing.\n"
            f"  missing: {exc.name}\n"
            "  reinstall with: pip install --force-reinstall sigmahelix",
            file=sys.stderr,
        )
        return EXIT_FAILURE
    SigmaHelixApp().run()
    return EXIT_OK


def command_chat(_: argparse.Namespace) -> int:
    """Start the interactive console REPL."""
    from .app.console import main as console_main

    console_main()
    return EXIT_OK


def command_version(_: argparse.Namespace) -> int:
    print(f"sigmahelix {__version__}")
    return EXIT_OK


def command_status(_: argparse.Namespace) -> int:
    settings = load_settings()
    database = _open_database()
    with database.connection() as connection:
        schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
    tasks = TaskRepository(database).list_all()
    notes = NoteRepository(database).list_all()
    projects = ProjectRepository(database).list_all()
    audit = AuditLog(database).verify()

    print(f"sigmahelix {__version__}")
    print(f"database   {settings.database_path}")
    print(f"config     {settings.config_path}")
    print(f"schema     v{schema}")
    print(f"tasks      {len(tasks)}")
    print(f"notes      {len(notes)}")
    print(f"projects   {len(projects)}")
    print(
        "audit      "
        + (
            f"valid ({audit.entries_checked} entries)"
            if audit.valid
            else f"BROKEN at sequence {audit.error_sequence}: {audit.reason}"
        )
    )
    return EXIT_OK if audit.valid else EXIT_FAILURE


def command_scan(args: argparse.Namespace) -> int:
    roots = [Path(raw).expanduser().resolve() for raw in args.paths]
    missing = [path for path in roots if not path.is_dir()]
    if missing:
        for path in missing:
            print(f"not a directory: {path}", file=sys.stderr)
        return EXIT_USAGE

    database = _open_database()
    batch = ProjectScanner(database).scan(roots)
    rows = [
        (
            scan.name,
            scan.health,
            scan.health_score,
            scan.git_branch or "-",
            "dirty" if scan.git_dirty else "clean",
            ",".join(scan.manifests) or "-",
        )
        for scan in batch.scans
    ]
    print(_table(("PROJECT", "HEALTH", "SCORE", "BRANCH", "GIT", "MANIFESTS"), rows))
    print(f"\n{len(batch.scans)} project(s) in {batch.duration_seconds:.3f}s")
    return EXIT_OK


def command_backup(args: argparse.Namespace) -> int:
    database = _open_database()
    manifest = DatabaseBackup().export(database, args.destination.resolve())
    print(json.dumps(asdict(manifest), indent=2, sort_keys=True, default=str))
    return EXIT_OK


def command_restore(args: argparse.Namespace) -> int:
    manifest = DatabaseBackup().restore(
        args.source.resolve(), args.destination.resolve()
    )
    print(json.dumps(asdict(manifest), indent=2, sort_keys=True, default=str))
    return EXIT_OK


def command_audit(args: argparse.Namespace) -> int:
    database = _open_database()
    audit = AuditLog(database)
    if args.audit_command == "verify":
        result = audit.verify()
        if result.valid:
            print(f"audit chain valid — {result.entries_checked} entries verified")
            return EXIT_OK
        print(
            f"audit chain BROKEN at sequence {result.error_sequence}: {result.reason}",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    entries = audit.list_entries(limit=args.limit)
    rows = [
        (
            entry.sequence,
            entry.occurred_at.strftime("%Y-%m-%d %H:%M:%S"),
            entry.action,
            entry.entity_type,
            entry.record_hash[:12],
        )
        for entry in entries
    ]
    print(_table(("SEQ", "WHEN", "ACTION", "ENTITY", "HASH"), rows))
    return EXIT_OK


def command_db(args: argparse.Namespace) -> int:
    database = _open_database()
    runner = MigrationRunner(database)
    if args.db_command == "upgrade":
        version = runner.upgrade()
        print(f"schema upgraded to v{version}")
        return EXIT_OK
    print(f"schema v{runner.current_version()} (latest v{runner.latest_version})")
    return EXIT_OK


def command_doctor(_args: argparse.Namespace) -> int:
    """Report what works on this machine. Never raises, never writes."""
    problems = 0
    print(f"sigmahelix {__version__}  ·  python {sys.version.split()[0]}")
    print(f"executable  {sys.executable}")

    # configuration and database
    try:
        settings = load_settings()
        print(_ok("configuration", str(settings.config_path)))
    except ConfigError as exc:
        problems += 1
        print(_fail("configuration", str(exc)))
        return EXIT_FAILURE

    database = Database(settings.database_path)
    try:
        database.initialize()
        with database.connection() as connection:
            schema = int(connection.execute("PRAGMA user_version").fetchone()[0])
        print(_ok("database", f"v{schema} at {database.path}"))
    except (sqlite3.Error, OSError) as exc:
        problems += 1
        print(_fail("database", str(exc)))

    # audit chain
    try:
        result = AuditLog(database).verify()
        if result.valid:
            print(_ok("audit chain", f"{result.entries_checked} entries"))
        else:
            problems += 1
            print(_fail("audit chain", f"sequence {result.error_sequence}"))
    except Exception as exc:  # noqa: BLE001 - doctor must never crash
        problems += 1
        print(_fail("audit chain", str(exc)))

    # optional runtime dependencies
    for module, label, hint in (
        ("customtkinter", "desktop UI", "reinstall sigmahelix"),
        ("speech_recognition", "speech input", "pip install 'sigmahelix[voice]'"),
        ("pyttsx3", "text to speech", "pip install 'sigmahelix[voice]'"),
        ("keyring", "secret storage", "reinstall sigmahelix"),
    ):
        try:
            __import__(module)
            print(_ok(label, module))
        except Exception:  # noqa: BLE001 - any import failure is the same answer
            problems += 1
            print(_warn(label, f"missing — {hint}"))

    # local model server
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")
    parsed = host.split("://", 1)[-1]
    hostname, _, port_text = parsed.partition(":")
    port = int(port_text or 11434)
    try:
        with socket.create_connection((hostname, port), timeout=0.5):
            print(_ok("local model server", host))
    except OSError:
        print(_warn("local model server", f"{host} not reachable — keyword mode only"))

    # tools
    for tool in ("git", "notify-send"):
        path = shutil.which(tool)
        print(_ok(tool, path) if path else _warn(tool, "not on PATH"))

    print()
    if problems:
        print(f"{problems} problem(s) need attention")
        return EXIT_FAILURE
    print("all checks passed")
    return EXIT_OK


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sigmahelix",
        description="Local-first personal operating system.",
        epilog="Run 'sigmahelix doctor' if something does not work.",
    )
    parser.add_argument(
        "--version", action="version", version=f"sigmahelix {__version__}"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("gui", help="start the desktop app (default)")
    subparsers.add_parser("chat", help="start the console REPL")
    subparsers.add_parser("status", help="show database, counts and audit state")
    subparsers.add_parser("doctor", help="check the local environment")
    subparsers.add_parser("version", help="print the version")

    scan = subparsers.add_parser("scan", help="scan project directories")
    scan.add_argument("paths", nargs="+", help="absolute or relative project roots")

    backup = subparsers.add_parser("backup", help="write a verified database snapshot")
    backup.add_argument("--destination", type=Path, required=True)

    restore = subparsers.add_parser("restore", help="restore a snapshot to a new path")
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)

    audit = subparsers.add_parser("audit", help="inspect the audit chain")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    audit_sub.add_parser("verify", help="verify the whole hash chain")
    audit_list = audit_sub.add_parser("list", help="list recent entries")
    audit_list.add_argument("--limit", type=int, default=20)

    db = subparsers.add_parser("db", help="database maintenance")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="apply pending migrations")
    db_sub.add_parser("info", help="show the schema version")

    return parser


COMMANDS = {
    "gui": command_gui,
    "chat": command_chat,
    "status": command_status,
    "doctor": command_doctor,
    "version": command_version,
    "scan": command_scan,
    "backup": command_backup,
    "restore": command_restore,
    "audit": command_audit,
    "db": command_db,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "gui"
    handler = COMMANDS[command]
    try:
        return handler(args)
    except (BackupError, FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"sigmahelix {command}: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
