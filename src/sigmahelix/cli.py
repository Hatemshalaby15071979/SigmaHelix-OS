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
def command_web(args: argparse.Namespace) -> int:
    """Serve the local web interface and open it in the browser."""
    from .app.webui import serve

    port = int(getattr(args, "port", 0) or 0)
    open_browser = not bool(getattr(args, "no_browser", False))
    return serve(port=port, open_browser=open_browser)


def command_gui(_: argparse.Namespace) -> int:
    """Start the legacy desktop window (CustomTkinter)."""
    try:
        from .app.ui import SigmaHelixApp
    except ImportError as exc:
        print(
            "The desktop interface needs CustomTkinter, which is missing.\n"
            f"  missing: {exc.name}\n"
            "  the web interface needs no extra packages: run 'sigmahelix'",
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


def command_skills(args: argparse.Namespace) -> int:
    """Inspect, install and prove the skills that ride on every model call."""
    from .app.skills import SkillError, SkillLibrary, user_skills_dir

    if args.skills_command == "install":
        source = args.source.expanduser().resolve()
        if not source.is_file():
            print(f"not a file: {source}", file=sys.stderr)
            return EXIT_USAGE
        target_dir = user_skills_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        shutil.copyfile(source, target)
        try:
            SkillLibrary().skills(refresh=True)
        except SkillError as exc:
            target.unlink(missing_ok=True)
            print(f"not a usable skill: {exc}", file=sys.stderr)
            return EXIT_FAILURE
        print(f"installed {target}")
        return EXIT_OK

    library = SkillLibrary()
    if args.skills_command == "list":
        print(library.report())
        return EXIT_OK

    if args.skills_command == "show":
        skill = library.get(args.name)
        if skill is None:
            print(f"no such skill: {args.name}", file=sys.stderr)
            return EXIT_USAGE
        print(f"name        {skill.name}")
        print(f"source      {skill.source}")
        print(f"token       {skill.token}")
        print(f"path        {skill.path}")
        print(f"size        {skill.size} chars")
        print(f"description {skill.description}")
        print()
        print(skill.body)
        return EXIT_OK

    return _verify_skills(library, probe=args.probe)


def _verify_skills(library, probe: bool) -> int:
    """Check composition, then optionally prove it reaches each live backend."""
    from .app.agent import Agent

    skills = library.skills(refresh=True)
    if not skills:
        print("no skills found", file=sys.stderr)
        return EXIT_FAILURE

    agent = Agent()
    prompt = agent.system_prompt()
    composition = agent.last_composition
    if composition is None or prompt != composition.prompt:
        print(_fail("composition", "the agent did not build a prompt"))
        return EXIT_FAILURE
    missing = [s.name for s in skills if s.name not in composition.prompt]
    print(f"skills      {len(skills)}")
    print(f"prompt      {len(composition.prompt)} chars")
    print(f"included    {len(composition.included)}")
    if composition.truncated:
        print(_warn("truncated", ", ".join(composition.truncated)))
    for name in missing:
        print(_fail(name, "not present in the composed prompt"))
    if missing:
        return EXIT_FAILURE

    if not probe:
        print(_ok("composition", "every skill is in the system prompt"))
        print("add --probe to ask each live model to repeat its SKILL tokens")
        return EXIT_OK

    question = (
        "Prove you loaded your skills: reply with each SKILL token exactly as "
        "written, one per line, and nothing else."
    )
    messages = [{"role": "system", "content": composition.prompt}]
    messages.append({"role": "user", "content": question})
    failures = 0

    local_ok, local_detail = _probe_backend("local", agent, messages, composition)
    failures += 0 if local_ok else 1
    print(
        _ok("local model", local_detail)
        if local_ok
        else _fail("local model", local_detail)
    )

    from .app.models import active_cloud_providers

    if active_cloud_providers():
        cloud_ok, cloud_detail = _probe_backend("cloud", agent, messages, composition)
        failures += 0 if cloud_ok else 1
        print(
            _ok("cloud model", cloud_detail)
            if cloud_ok
            else _fail("cloud model", cloud_detail)
        )
    else:
        print(_warn("cloud model", "no verified provider key — skipped"))

    return EXIT_OK if failures == 0 else EXIT_FAILURE


def _probe_backend(kind: str, agent, messages, composition) -> tuple[bool, str]:
    """Ask one backend to repeat the tokens; the reply is the proof."""
    try:
        if kind == "local":
            reply = agent._ollama_chat(messages, timeout=90)
        else:
            reply, error = agent._cloud_chat(messages)
            if not reply:
                return False, f"no reply: {error}"
    except Exception as exc:  # noqa: BLE001 - a probe reports, never raises
        return False, f"{type(exc).__name__}: {exc}"

    text = (reply or "").lower()
    found = [token for token in composition.tokens if token.lower() in text]
    if len(found) == len(composition.tokens):
        return True, f"{agent.model_name} echoed all {len(found)} tokens"
    missing = [t for t in composition.tokens if t not in found]
    return False, f"{len(found)}/{len(composition.tokens)} tokens, missing {missing}"


def command_ledger(args: argparse.Namespace) -> int:
    """Inspect the metacognition ledger. Reports never invent numbers."""
    from .app.metacognition import Ledger

    ledger = Ledger(_open_database())
    action = args.ledger_command
    try:
        return _run_ledger_command(ledger, args, action)
    except ValueError as exc:
        # A typo must not print a traceback.
        print(f"ledger: {exc}", file=sys.stderr)
        return EXIT_USAGE


def _run_ledger_command(ledger, args, action: str) -> int:
    if action == "verify":
        result = ledger.verify()
        if result["valid"]:
            print(
                f"ledger valid — chain {result['entries_checked']} entries, "
                f"{result['turns_checked']} turn proof(s), "
                f"{result['unclosed']} unclosed"
            )
            if not result["complete"]:
                print(
                    "note: the ledger is not complete — "
                    f"{result['unclosed']} unclosed turn(s), "
                    f"{len(result['orphans'])} orphan anchor(s), "
                    f"{len(result['duplicates'])} duplicate anchor(s)"
                )
            if result["legacy"]:
                print(
                    f"note: {result['legacy']} turn(s) were recorded before the "
                    "step digest existed; their steps are not covered by the proof"
                )
            return EXIT_OK
        if not result["chain_valid"]:
            print("ledger BROKEN: the audit chain does not verify", file=sys.stderr)
        else:
            print(
                f"ledger BROKEN: {result['mismatch'].get('reason', 'proof mismatch')} "
                f"at {result['mismatch']['turn_id']}",
                file=sys.stderr,
            )
        return EXIT_FAILURE

    if action == "report":
        metrics = ledger.report(args.period)
        recs = (
            ledger.recommend(args.period, metrics=metrics)
            if args.analyze
            else ledger.recommendations()
        )
        if args.json:
            print(json.dumps({"report": metrics, "recommendations": recs}, indent=2))
            return EXIT_OK
        outcomes = " · ".join(
            f"{k} {v}" for k, v in sorted(metrics["outcomes"].items())
        )
        print(
            f"{metrics['period']} · {metrics['turns']} turn(s) · "
            f"success {metrics['success_rate']:.0%} · "
            f"truncated {metrics['truncation_rate']:.0%} · "
            f"pushback {metrics['pushback_rate']:.0%}"
        )
        print(f"outcomes: {outcomes or 'none'}")
        if metrics["tool_calls"]:
            tools = " · ".join(
                f"{name} {bucket['total']}"
                + (f" ({bucket['failed']} failed)" if bucket["failed"] else "")
                for name, bucket in sorted(metrics["tool_calls"].items())
            )
            print(f"tools: {tools}")
        if metrics["repeated_intents"]:
            print(f"repeated intents: {len(metrics['repeated_intents'])}")
        if not recs:
            hint = (
                "no rule fired for this period"
                if args.analyze
                else "run with --analyze to compute them"
            )
            print(f"recommendations: none ({hint})")
            return EXIT_OK
        print(f"\nrecommendations ({len(recs)}):")
        for rec in recs:
            print(f"  [{rec['id']}] {rec['kind']} · {rec['status']}")
            print(f"    {rec['title']}")
            print(f"    {rec['body']}")
        return EXIT_OK

    if action == "show":
        row = ledger.turn(args.turn_id)
        if args.json:
            print(json.dumps(row, indent=2))
            return EXIT_OK
        print(f"{row['id']} · turn {row['turn_index']} · {row['outcome']}")
        print(f"at      {row['started_at']}")
        print(f"user    {row['user_text']}")
        print(f"reply   {row['reply']}")
        if row["plan"]:
            print(f"plan    {row['plan']}")
        for step in row["steps"]:
            mark = "✓" if step["ok"] else "✗"
            print(
                f"  {step['seq']}. {step['action']} "
                f"[{mark} · {step['duration_ms']}ms] {step['summary']}"
            )
        return EXIT_OK

    if action == "feedback":
        ledger.add_feedback(args.turn_id, args.verdict, reason=args.reason)
        print(f"recorded {args.verdict} for {args.turn_id}")
        return EXIT_OK

    if action == "decide":
        # approve | reject | reopen — the ledger owns the legal transitions.
        result = ledger.decide(args.rec_id, args.decision, note=args.note)
        print(f"{args.rec_id} {result['status']}")
        return EXIT_OK

    if action == "apply":
        # apply an approved recommendation — only whitelisted, reversible kinds.
        result = ledger.apply(args.rec_id, note=args.note)
        print(f"{args.rec_id} {result['status']} — {result['effect']}")
        return EXIT_OK

    return EXIT_USAGE


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

    # skills ride on every model call, so a broken one is a real problem
    try:
        from .app.skills import SkillLibrary

        library = SkillLibrary()
        skills = library.skills(refresh=True)
        composition = library.compose("")
        if not skills:
            problems += 1
            print(_fail("skills", "none found — models get no operating rules"))
        elif composition.truncated:
            problems += 1
            print(_warn("skills", f"over budget: {', '.join(composition.truncated)}"))
        else:
            print(
                _ok("skills", f"{len(skills)} active, {len(composition.prompt)} chars")
            )
        for error in library.errors:
            problems += 1
            print(_fail("skill file", error))
    except Exception as exc:  # noqa: BLE001 - doctor must never crash
        problems += 1
        print(_fail("skills", str(exc)))

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
    parser.add_argument("--port", type=int, default=0, help="web port (0 = pick one)")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open the browser"
    )
    subparsers = parser.add_subparsers(dest="command")

    web = subparsers.add_parser("web", help="serve the web interface (default)")
    web.add_argument("--port", type=int, default=argparse.SUPPRESS)
    web.add_argument("--no-browser", action="store_true", default=argparse.SUPPRESS)
    subparsers.add_parser("gui", help="start the legacy desktop window")
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

    ledger = subparsers.add_parser(
        "ledger", help="inspect Tommy's metacognition ledger and recommendations"
    )
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_sub.add_parser("verify", help="verify the audit chain and every turn proof")
    ledger_report = ledger_sub.add_parser("report", help="metrics and recommendations")
    ledger_report.add_argument("--period", default="7d", help="7d, 24h or 2w")
    ledger_report.add_argument("--json", action="store_true")
    ledger_report.add_argument(
        "--analyze",
        action="store_true",
        help="recompute recommendations instead of showing stored ones",
    )
    ledger_show = ledger_sub.add_parser("show", help="print one turn and its steps")
    ledger_show.add_argument("turn_id")
    ledger_show.add_argument("--json", action="store_true")
    ledger_feedback = ledger_sub.add_parser("feedback", help="judge one turn")
    ledger_feedback.add_argument("turn_id")
    ledger_feedback.add_argument("verdict", choices=("good", "pushback"))
    ledger_feedback.add_argument("--reason", default="")
    ledger_decide = ledger_sub.add_parser(
        "decide", help="approve, reject or reopen a recommendation"
    )
    ledger_decide.add_argument("rec_id")
    ledger_decide.add_argument("decision", choices=("approve", "reject", "reopen"))
    ledger_decide.add_argument("--note", default="")
    ledger_apply = ledger_sub.add_parser(
        "apply", help="apply an approved, whitelisted recommendation"
    )
    ledger_apply.add_argument("rec_id")
    ledger_apply.add_argument("--note", default="")

    db = subparsers.add_parser("db", help="database maintenance")
    db_sub = db.add_subparsers(dest="db_command", required=True)
    db_sub.add_parser("upgrade", help="apply pending migrations")
    db_sub.add_parser("info", help="show the schema version")

    skills = subparsers.add_parser("skills", help="inspect and prove model skills")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    skills_sub.add_parser("list", help="list every discovered skill")
    skills_show = skills_sub.add_parser("show", help="print one skill in full")
    skills_show.add_argument("name")
    skills_verify = skills_sub.add_parser(
        "verify", help="check composition and probe each live model"
    )
    skills_verify.add_argument(
        "--probe", action="store_true", help="ask each live model to echo its tokens"
    )
    skills_install = skills_sub.add_parser("install", help="add a skill markdown file")
    skills_install.add_argument("source", type=Path)

    return parser


COMMANDS = {
    "web": command_web,
    "gui": command_gui,
    "chat": command_chat,
    "status": command_status,
    "doctor": command_doctor,
    "version": command_version,
    "scan": command_scan,
    "backup": command_backup,
    "restore": command_restore,
    "audit": command_audit,
    "ledger": command_ledger,
    "db": command_db,
    "skills": command_skills,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "web"
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
