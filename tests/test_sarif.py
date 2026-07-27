from __future__ import annotations

import json
from pathlib import Path

from ossie_guard import __version__, lint_file
from ossie_guard.sarif import to_sarif

FIXTURES = Path(__file__).parent / "fixtures"


def _sarif(*names):
    pairs = [(str(FIXTURES / n), lint_file(str(FIXTURES / n))) for n in names]
    return to_sarif(pairs, tool_version=__version__)


def test_document_is_wellformed():
    doc = _sarif("drift.yaml")
    assert doc["version"] == "2.1.0"
    assert doc["$schema"].endswith("sarif-2.1.0.json")
    driver = doc["runs"][0]["tool"]["driver"]
    assert driver["name"] == "ossie-guard"
    assert driver["rules"]


def test_rules_carry_every_github_required_field():
    driver = _sarif("drift.yaml")["runs"][0]["tool"]["driver"]
    for rule in driver["rules"]:
        assert rule["id"]
        assert rule["shortDescription"]["text"]
        assert rule["fullDescription"]["text"]
        assert rule["help"]["text"]  # GitHub marks help.text required
        assert rule["defaultConfiguration"]["level"] in ("error", "warning", "note")


def test_results_have_valid_locations_levels_and_rule_binding():
    run = _sarif("drift.yaml")["runs"][0]
    rules = run["tool"]["driver"]["rules"]
    assert run["results"]
    for result in run["results"]:
        assert result["ruleId"]
        assert result["message"]["text"]
        assert result["level"] in ("error", "warning", "note")
        # ruleId and ruleIndex must agree (GitHub warns on inconsistency)
        assert 0 <= result["ruleIndex"] < len(rules)
        assert rules[result["ruleIndex"]]["id"] == result["ruleId"]
        phys = result["locations"][0]["physicalLocation"]
        uri = phys["artifactLocation"]["uri"]
        assert uri and "\\" not in uri  # repo-relative, forward slashes
        assert phys["region"]["startLine"] >= 1


def test_aggregate_drift_is_error_level():
    results = _sarif("drift.yaml")["runs"][0]["results"]
    agg = [r for r in results if r["ruleId"] == "AGGREGATE_DRIFT"]
    assert agg and agg[0]["level"] == "error"


def test_document_spans_multiple_files():
    run = _sarif("drift.yaml", "unsafe.yaml")["runs"][0]
    uris = {
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        for r in run["results"]
    }
    assert len(uris) == 2


def test_clean_model_yields_a_valid_empty_run():
    doc = _sarif("clean.yaml")
    run = doc["runs"][0]
    assert run["results"] == []
    assert run["tool"]["driver"]["name"] == "ossie-guard"  # still well-formed


def test_document_is_json_serializable():
    json.dumps(_sarif("drift.yaml", "unsafe.yaml", "clean.yaml"))
