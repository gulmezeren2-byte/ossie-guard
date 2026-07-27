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


def test_sarif_format_via_cli(capsys):
    rc = main([str(FIXTURES / "drift.yaml"), "--sarif"])
    doc = json.loads(capsys.readouterr().out)
    assert doc["version"] == "2.1.0"
    assert rc == 1  # drift carries an error; default fail-level is "error"


def test_fail_level_none_never_fails(capsys):
    assert main([str(FIXTURES / "drift.yaml"), "--fail-level", "none"]) == 0


def test_fail_level_note_fails_on_any_finding(capsys):
    # unsafe.yaml with safety off yields only NONDETERMINISTIC warnings
    assert main([str(FIXTURES / "unsafe.yaml"), "--no-safety", "--fail-level", "note"]) == 1
    capsys.readouterr()
    # a clean model has nothing, so even --fail-level note passes
    assert main([str(FIXTURES / "clean.yaml"), "--fail-level", "note"]) == 0


def test_multiple_files_are_all_reported(capsys):
    rc = main([str(FIXTURES / "clean.yaml"), str(FIXTURES / "drift.yaml")])
    out = capsys.readouterr().out
    assert "clean.yaml" in out and "drift.yaml" in out
    assert rc == 1  # the drift model has an error


def test_output_to_file(tmp_path, capsys):
    target = tmp_path / "results.sarif"
    main([str(FIXTURES / "drift.yaml"), "--sarif", "-o", str(target)])
    doc = json.loads(target.read_text(encoding="utf-8"))
    assert doc["version"] == "2.1.0"
    assert capsys.readouterr().out.strip() == ""  # nothing on stdout


def test_json_output_carries_line_and_file(capsys):
    main([str(FIXTURES / "drift.yaml"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert all("file" in item and "line" in item for item in payload)
    assert all(item["line"] and item["line"] >= 1 for item in payload)
