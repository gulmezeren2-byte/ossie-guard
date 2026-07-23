from __future__ import annotations

import json
from pathlib import Path

from ossie_guard.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_clean_model_exits_zero(capsys):
    rc = main([str(FIXTURES / "clean.yaml")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "OK" in out


def test_drift_model_exits_one(capsys):
    rc = main([str(FIXTURES / "drift.yaml")])
    assert rc == 1
    assert "AGGREGATE_DRIFT" in capsys.readouterr().out


def test_json_output_is_valid(capsys):
    rc = main([str(FIXTURES / "drift.yaml"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert any(item["code"] == "AGGREGATE_DRIFT" for item in payload)
    assert all({"severity", "code", "entity", "message"} <= item.keys() for item in payload)


def test_strict_promotes_warnings_to_failure(capsys):
    # With safety off, unsafe.yaml yields only NONDETERMINISTIC warnings.
    args = [str(FIXTURES / "unsafe.yaml"), "--no-safety"]
    assert main(args) == 0  # warnings alone do not fail by default
    capsys.readouterr()
    assert main(args + ["--strict"]) == 1  # ...but they do under --strict


def test_missing_file_exits_two(capsys):
    rc = main([str(FIXTURES / "does_not_exist.yaml")])
    assert rc == 2
    assert "no such file" in capsys.readouterr().err
