import pytest
from scripts.ledger import LedgerError, next_ready_task, validate_ledger


def make_task(task_id, status, depends_on=None, workstream="main"):
    return {
        "id": task_id,
        "title": task_id,
        "status": status,
        "depends_on": depends_on or [],
        "acceptance": ["criterion"],
        "evidence": f"evidence/{task_id}.md",
        "workstream": workstream,
    }


def make_ledger(*tasks):
    return {
        "version": 1,
        "project": "test",
        "gates": [{"id": "P0", "tasks": list(tasks)}],
    }


def test_selects_first_ready_task_with_completed_dependencies(tmp_path):
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/P0-001.md").write_text(
        "- Command: run\n- Output: passed\n- SHA-256: " + "a" * 64,
        encoding="utf-8",
    )
    ledger = make_ledger(
        make_task("P0-001", "done"),
        make_task("P0-002", "ready", ["P0-001"]),
        make_task("P0-003", "ready", ["P0-004"]),
        make_task("P0-004", "blocked"),
    )

    validate_ledger(ledger, tmp_path)
    assert next_ready_task(ledger)["id"] == "P0-002"


def test_active_task_prevents_selecting_a_second_task(tmp_path):
    active = make_task("P0-001", "in_progress")
    ready = make_task("P0-002", "ready")
    ledger = make_ledger(active, ready)

    validate_ledger(ledger, tmp_path)
    assert next_ready_task(ledger) is None


def test_done_task_requires_evidence(tmp_path):
    ledger = make_ledger(make_task("P0-001", "done"))

    with pytest.raises(LedgerError, match="no evidence file"):
        validate_ledger(ledger, tmp_path)


def test_rejects_multiple_active_tasks_in_one_workstream(tmp_path):
    ledger = make_ledger(
        make_task("P0-001", "in_progress"),
        make_task("P0-002", "in_progress"),
    )

    with pytest.raises(LedgerError, match="multiple in_progress"):
        validate_ledger(ledger, tmp_path)


def test_rejects_unknown_dependency(tmp_path):
    ledger = make_ledger(make_task("P0-001", "ready", ["P9-999"]))

    with pytest.raises(LedgerError, match="unknown dependencies"):
        validate_ledger(ledger, tmp_path)


def test_done_evidence_requires_command_output_and_hash(tmp_path):
    evidence_path = tmp_path / "evidence/P0-001.md"
    evidence_path.parent.mkdir()
    evidence_path.write_text("verified", encoding="utf-8")

    with pytest.raises(LedgerError, match="command, output, and SHA-256"):
        validate_ledger(make_ledger(make_task("P0-001", "done")), tmp_path)


def test_rejects_dependency_cycle(tmp_path):
    ledger = make_ledger(
        make_task("P0-001", "ready", ["P0-002"]),
        make_task("P0-002", "ready", ["P0-001"]),
    )

    with pytest.raises(LedgerError, match="contain a cycle"):
        validate_ledger(ledger, tmp_path)
