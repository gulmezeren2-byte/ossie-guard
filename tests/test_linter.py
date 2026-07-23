from __future__ import annotations

from pathlib import Path

from ossie_guard import Severity, lint_file, lint_model

FIXTURES = Path(__file__).parent / "fixtures"


def codes(findings):
    return {f.code for f in findings}


def test_clean_model_has_no_errors_or_warnings():
    findings = lint_file(str(FIXTURES / "clean.yaml"))
    assert [f for f in findings if f.severity is not Severity.INFO] == []


def test_drift_model_reports_expected_findings():
    findings = lint_file(str(FIXTURES / "drift.yaml"))
    assert codes(findings) >= {"AGGREGATE_DRIFT", "COLUMN_DRIFT", "LITERAL_DRIFT"}

    by_code = {f.code: f for f in findings}
    assert by_code["AGGREGATE_DRIFT"].severity is Severity.ERROR
    assert by_code["COLUMN_DRIFT"].severity is Severity.WARNING
    assert by_code["LITERAL_DRIFT"].severity is Severity.WARNING
    # the aggregate drift should name the offending metric
    assert by_code["AGGREGATE_DRIFT"].entity == "revenue"


def test_unsafe_model_reports_safety_and_determinism():
    findings = lint_file(str(FIXTURES / "unsafe.yaml"))
    assert "UNSAFE_FUNCTION" in codes(findings)
    assert "NONDETERMINISTIC" in codes(findings)

    unsafe = next(f for f in findings if f.code == "UNSAFE_FUNCTION")
    assert unsafe.severity is Severity.ERROR
    assert unsafe.entity == "leaky"

    nondet = [f for f in findings if f.code == "NONDETERMINISTIC"]
    assert {f.entity for f in nondet} == {"todays_revenue", "coin_flip"}


def test_check_toggles_are_respected():
    only_drift = lint_file(
        str(FIXTURES / "unsafe.yaml"), check_safety=False, check_determinism=False
    )
    assert only_drift == [] or all(
        f.code not in {"UNSAFE_FUNCTION", "NONDETERMINISTIC"} for f in only_drift
    )


def test_walker_finds_nested_expressions():
    # expression carriers buried under arbitrary nesting are still found.
    model = {
        "a": {"b": [{"name": "deep_metric", "expression": {"dialects": [
            {"dialect": "ANSI_SQL", "expression": "SUM(x)"},
            {"dialect": "SNOWFLAKE", "expression": "AVG(x)"},
        ]}}]}
    }
    findings = lint_model(model)
    assert any(f.code == "AGGREGATE_DRIFT" and f.entity == "deep_metric" for f in findings)


def test_skip_dialect_expressions_do_not_crash():
    # MDX/Tableau/MAQL cannot be parsed; they must be skipped, not error out.
    model = {"metrics": [{"name": "m", "expression": {"dialects": [
        {"dialect": "MDX", "expression": "[Measures].[Sales]"},
    ]}}]}
    assert lint_model(model) == []
