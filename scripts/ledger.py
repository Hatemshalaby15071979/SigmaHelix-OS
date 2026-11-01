#!/usr/bin/env python3
"""Validate the execution ledger and select its next eligible task."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml

VALID_STATUSES = {"ready", "in_progress", "blocked", "done", "failed"}
DEFAULT_LEDGER = Path(__file__).resolve().parents[1] / "docs/execution/LEDGER.yaml"


class LedgerError(ValueError):
    """Raised when the ledger is malformed or violates execution rules."""


def _all_tasks(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, gate in enumerate(ledger.get("gates", [])):
        if not isinstance(gate, dict):
            raise LedgerError(f"gate at index {index} must be a mapping")
        gate_tasks = gate.get("tasks", [])
        if not isinstance(gate_tasks, list) or any(
            not isinstance(task, dict) for task in gate_tasks
        ):
            raise LedgerError(
                f"gate {gate.get('id', index)} tasks must be a list of mappings"
            )
        tasks.extend(gate_tasks)
    return tasks


def validate_ledger(ledger: dict[str, Any], root: Path) -> None:
    if not isinstance(ledger, dict) or ledger.get("version") != 1:
        raise LedgerError("ledger must be a version 1 mapping")
    gates = ledger.get("gates")
    if not isinstance(gates, list) or not gates:
        raise LedgerError("ledger must contain a non-empty gates list")

    tasks = _all_tasks(ledger)
    ids = [task.get("id") for task in tasks]
    if any(not isinstance(task_id, str) or not task_id for task_id in ids):
        raise LedgerError("every task needs a non-empty string id")
    if len(ids) != len(set(ids)):
        raise LedgerError("task ids must be unique")
    known_ids = set(ids)
    active_by_workstream: dict[str, int] = {}

    for task in tasks:
        status = task.get("status")
        if status not in VALID_STATUSES:
            raise LedgerError(f"{task['id']}: invalid status {status!r}")
        if not task.get("title"):
            raise LedgerError(f"{task['id']}: title is required")
        acceptance = task.get("acceptance")
        if not isinstance(acceptance, list) or not acceptance:
            raise LedgerError(f"{task['id']}: acceptance must be a non-empty list")
        evidence = task.get("evidence")
        if not isinstance(evidence, str) or not evidence:
            raise LedgerError(f"{task['id']}: evidence path is required")
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list) or any(
            not isinstance(item, str) for item in dependencies
        ):
            raise LedgerError(f"{task['id']}: depends_on must be a list")
        unknown = set(dependencies) - known_ids
        if unknown:
            raise LedgerError(f"{task['id']}: unknown dependencies {sorted(unknown)}")
        evidence_path = (root / evidence).resolve()
        if root.resolve() not in evidence_path.parents:
            raise LedgerError(
                f"{task['id']}: evidence path must stay inside the repository"
            )
        if status == "done":
            if not evidence_path.is_file():
                raise LedgerError(
                    f"{task['id']}: done task has no evidence file at {evidence}"
                )
            evidence_text = evidence_path.read_text(encoding="utf-8")
            has_command = re.search(
                r"(?im)^\s*-\s*(?:local )?commands?:", evidence_text
            )
            has_output = re.search(r"(?im)^\s*-\s*output:", evidence_text)
            has_hash_marker = re.search(r"(?i)SHA-256", evidence_text)
            if not (has_command and has_output and has_hash_marker):
                raise LedgerError(
                    f"{task['id']}: evidence must include command, output, and SHA-256"
                )
            if not re.search(r"\b[0-9a-fA-F]{64}\b", evidence_text):
                raise LedgerError(
                    f"{task['id']}: evidence must include a 64-character SHA-256"
                )
        if status == "in_progress":
            workstream = task.get("workstream", "main")
            if not isinstance(workstream, str):
                raise LedgerError(f"{task['id']}: workstream must be a string")
            active_by_workstream[workstream] = (
                active_by_workstream.get(workstream, 0) + 1
            )

    pending = {task["id"]: set(task.get("depends_on", [])) for task in tasks}
    resolved: set[str] = set()
    while pending:
        newly_resolved = {
            task_id
            for task_id, dependencies in pending.items()
            if dependencies <= resolved
        }
        if not newly_resolved:
            raise LedgerError("task dependencies contain a cycle")
        resolved.update(newly_resolved)
        for task_id in newly_resolved:
            del pending[task_id]

    conflicts = [name for name, count in active_by_workstream.items() if count > 1]
    if conflicts:
        raise LedgerError(
            f"multiple in_progress tasks in workstream(s): {', '.join(conflicts)}"
        )


def load_ledger(path: Path) -> dict[str, Any]:
    try:
        ledger = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise LedgerError(f"could not read ledger {path}: {exc}") from exc
    repo_root = path.resolve().parents[2]
    validate_ledger(ledger, repo_root)
    return ledger


def active_task(ledger: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (task for task in _all_tasks(ledger) if task["status"] == "in_progress"), None
    )


def next_ready_task(ledger: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first ready task whose dependencies are all done.

    An active task blocks selection of another task in the same workstream.
    """
    if active_task(ledger) is not None:
        return None
    tasks = _all_tasks(ledger)
    done_ids = {task["id"] for task in tasks if task["status"] == "done"}
    for task in tasks:
        if task["status"] == "ready" and set(task.get("depends_on", [])) <= done_ids:
            return task
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        ledger = load_ledger(args.ledger)
    except LedgerError as exc:
        parser.exit(2, f"ledger error: {exc}\n")

    tasks = _all_tasks(ledger)
    if args.validate_only:
        print(f"valid: {len(tasks)} tasks")
        return 0

    selected = active_task(ledger)
    label = "in_progress" if selected else "next"
    if selected is None:
        selected = next_ready_task(ledger)
    if selected is None:
        print("no eligible ready task")
        return 2
    print(f"{label}: {selected['id']} — {selected['title']}")
    for criterion in selected["acceptance"]:
        print(f"  - {criterion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
