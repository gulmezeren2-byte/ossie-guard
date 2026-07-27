"""Baseline behaviour: a ratchet, not a mute button.

The contract that matters: baselined findings stop failing CI, but anything new
still does, and the identity used is line-independent so reformatting a model
does not resurrect suppressed findings.
"""

from __future__ import annotations

import json
from pathlib import Path

from ossie_guard import __version__, lint_file
from ossie_guard.baseline import build, fingerprint, load
from ossie_guard.cli import main
from ossie_guard.sarif import to_sarif

FIXTURES = Path(__file__).parent / "fixtures"
DRIFT = str(FIXTURES / "drift.yaml")
UNSAFE = str(FIXTURES / "unsafe.yaml")
CLEAN = str(FIXTURES / "clean.yaml")


def test_write_then_pass(tmp_path, capsys):
    bl = tmp_path / "baseline.json"

    # without a baseline the drifting model fails
    assert main([DRIFT]) == 1
    capsys.readouterr()

    # record it, then the same model passes
    assert main([DRIFT, "--write-baseline", str(bl)]) == 0
    capsys.readouterr()
    assert main([DRIFT, "--baseline", str(bl)]) == 0


def test_new_findings_still_fail(tmp_path, capsys):
    bl = tmp_path / "baseline.json"
    main([DRIFT, "--write-baseline", str(bl)])
    capsys.readouterr()
    # unsafe.yaml was never baselined, so it must still fail
    assert main([DRIFT, UNSAFE, "--baseline", str(bl)]) == 1
    out = capsys.readouterr().out
    assert "UNSAFE_FUNCTION" in out
    assert "AGGREGATE_DRIFT" not in out  # the baselined one is suppressed


def test_identity_ignores_line_numbers(tmp_path):
    findings = lint_file(DRIFT)
    entries = build([(DRIFT, findings)])["findings"]
    assert entries
    assert all(":" in e for e in entries)
    # no entry embeds a line number
    for finding in findings:
        assert str(finding.line) not in fingerprint(DRIFT, finding).rsplit(":", 1)[-1]


def test_baseline_and_sarif_agree_on_identity():
    findings = lint_file(DRIFT)
    doc = to_sarif([(DRIFT, findings)], tool_version=__version__)
    sarif_fps = {
        r["partialFingerprints"]["ossieGuard/v1"] for r in doc["runs"][0]["results"]
    }
    assert sarif_fps == set(build([(DRIFT, findings)])["findings"])


def test_stale_entries_are_reported(tmp_path, capsys):
    bl = tmp_path / "baseline.json"
    main([DRIFT, "--write-baseline", str(bl)])
    capsys.readouterr()
    # linting a different, clean model leaves every entry unmatched
    main([CLEAN, "--baseline", str(bl)])
    assert "no longer occur" in capsys.readouterr().err


def test_missing_and_malformed_baselines_fail_loudly(tmp_path, capsys):
    assert main([DRIFT, "--baseline", str(tmp_path / "nope.json")]) == 2
    assert "no such baseline file" in capsys.readouterr().err

    bogus = tmp_path / "bogus.json"
    bogus.write_text(json.dumps({"something": "else"}), encoding="utf-8")
    assert main([DRIFT, "--baseline", str(bogus)]) == 2
    assert "not an ossie-guard baseline" in capsys.readouterr().err


def test_baseline_file_is_readable_json(tmp_path):
    bl = tmp_path / "baseline.json"
    main([DRIFT, "--write-baseline", str(bl)])
    data = json.loads(bl.read_text(encoding="utf-8"))
    assert data["ossie_guard_baseline"] == 1
    assert isinstance(data["findings"], list) and data["findings"]
    assert load(str(bl)) == set(data["findings"])
