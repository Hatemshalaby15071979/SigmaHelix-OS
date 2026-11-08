"""The `sigmahelix ledger` CLI: verify and report read the same isolated DB.

Uses the autouse ``isolated_user_data`` fixture from conftest, so the CLI never
touches the founder's real ledger or projects.
"""

from __future__ import annotations

import argparse
import json

import pytest

from sigmahelix.app.metacognition import Ledger
from sigmahelix.cli import EXIT_OK, command_ledger
from sigmahelix.core.config import load_settings
from sigmahelix.core.storage.database import Database


@pytest.fixture
def database():
    db = Database(load_settings().database_path)
    db.initialize()
    return db


@pytest.fixture
def ledger(database):
    return Ledger(database)


def _ns(**kw):
    defaults = {
        "ledger_command": "verify",
        "period": "7d",
        "analyze": False,
        "json": False,
        "turn_id": None,
        "verdict": None,
        "reason": "",
        "rec_id": None,
        "decision": None,
        "note": "",
    }
    defaults.update(kw)
    return argparse.Namespace(**defaults)


def test_cli_ledger_verify_and_report(ledger, capsys):
    # Seed a turn so the report has something to aggregate.
    ledger.open_turn("s1", "fix the demo", "loop", "cloud")
    ledger.close_turn(ledger.turns()[-1]["id"], reply="done", outcome="acted")

    # `verify` exits 0 and prints a confidence line.
    assert command_ledger(_ns(ledger_command="verify")) == EXIT_OK
    out = capsys.readouterr().out
    assert "ledger valid" in out

    # `report --json --analyze` exits 0 and prints parseable JSON with both
    # the metrics and the computed recommendations.
    code = command_ledger(_ns(ledger_command="report", analyze=True, json=True))
    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["report"]["turns"] == 1
    assert isinstance(payload["recommendations"], list)
