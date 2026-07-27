"""The predicate axis, and the false positives it let us remove.

Two properties are asserted here, and the second matters more than the first:
a real filter difference is reported, and a *purely idiomatic* difference is not.
A finding on a valid model is the one failure mode that makes a linter useless.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ossie_guard import lint_file
from ossie_guard.parsing import parse_expr
from ossie_guard.signature import compare, extract

FIXTURES = Path(__file__).parent / "fixtures"


def sig(expr, dialect=None):
    return extract(parse_expr(expr, dialect))


def codes(a, b, dialect_b=None):
    return {c for c, *_ in compare({"ANSI_SQL": sig(a), "OTHER": sig(b, dialect_b)})}


# --- real drift the other axes could not see -------------------------------

@pytest.mark.parametrize(
    "a,b",
    [
        # a string constant in the filter (no numbers, same columns)
        ("SUM(CASE WHEN region = 'EU' THEN amt ELSE 0 END)",
         "SUM(CASE WHEN region = 'US' THEN amt ELSE 0 END)"),
        # an operator that changes which rows are counted
        ("SUM(CASE WHEN amt > 100 THEN amt END)",
         "SUM(CASE WHEN amt >= 100 THEN amt END)"),
        # a different value inside an IN list
        ("SUM(CASE WHEN status IN (1, 2) THEN amt END)",
         "SUM(CASE WHEN status IN (1, 3) THEN amt END)"),
        # filtering on a different column
        ("SUM(CASE WHEN region = 'EU' THEN amt END)",
         "SUM(CASE WHEN country = 'EU' THEN amt END)"),
    ],
    ids=["string-constant", "operator", "in-list", "other-column"],
)
def test_real_filter_drift_is_reported(a, b):
    assert "PREDICATE_DRIFT" in codes(a, b)


# --- idiom that must NEVER be reported -------------------------------------

@pytest.mark.parametrize(
    "a,b,dialect_b",
    [
        ("SUM(CASE WHEN status = 1 THEN amt ELSE 0 END)",
         "SUM(amt) FILTER (WHERE status = 1)", None),
        ("SUM(CASE WHEN status = 1 THEN amt ELSE 0 END)",
         "SUM(IF(status = 1, amt, 0))", "bigquery"),
        ("SUM(CASE WHEN is_active = TRUE THEN amt END)",
         "SUM(CASE WHEN is_active = 1 THEN amt END)", None),
        ("SUM(CASE WHEN amt > 100 THEN amt END)",
         "SUM(CASE WHEN amt > 100.0 THEN amt END)", None),
        ("SUM(CASE WHEN amt > 100 THEN amt END)",
         "SUM(CASE WHEN 100 < amt THEN amt END)", None),
        ("SUM(CASE WHEN status IN (1, 2) THEN amt END)",
         "SUM(CASE WHEN status IN (2, 1) THEN amt END)", None),
        # a dialect-specific format string is not a filter and must be ignored
        ("MAX(DATE_FORMAT(d, '%Y-%m'))", "MAX(FORMAT_DATE('%Y-%m', d))", "bigquery"),
    ],
    ids=[
        "case-vs-filter", "case-vs-if", "true-vs-1", "100-vs-100.0",
        "flipped-operands", "in-list-order", "format-string",
    ],
)
def test_dialect_idiom_is_not_drift(a, b, dialect_b):
    assert codes(a, b, dialect_b) == set()


# --- the literal axis now only reads arithmetic ----------------------------

def test_arithmetic_constant_drift_still_reported():
    assert "LITERAL_DRIFT" in codes("SUM(amt * 1.08)", "SUM(amt * 1.18)")


def test_structural_zero_is_not_a_literal():
    # `ELSE 0` is structure, not a scaling factor: it must not enter the
    # literal signature (this was a false positive before the predicate axis).
    assert sig("SUM(CASE WHEN x = 1 THEN amt ELSE 0 END)").literals == frozenset()
    assert sig("SUM(amt * 1.08)").literals == frozenset({"1.08"})


# --- end to end ------------------------------------------------------------

def test_fixture_reports_only_the_two_real_drifts():
    findings = lint_file(str(FIXTURES / "predicates.yaml"))
    flagged = {f.entity for f in findings}
    assert flagged == {"eu_revenue", "large_orders"}, (
        "idiomatic metrics must stay clean; got " + str(
            [(f.entity, f.code) for f in findings]
        )
    )
    assert all(f.code == "PREDICATE_DRIFT" for f in findings)
