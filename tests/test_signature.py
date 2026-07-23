from __future__ import annotations

from ossie_guard.parsing import parse_expr
from ossie_guard.signature import compare, extract


def sig(expr, dialect=None):
    return extract(parse_expr(expr, dialect))


def test_extract_aggregate_and_columns():
    s = sig("SUM(ss_ext_sales_price * 1.08)")
    assert s.aggregates == ("SUM",)
    assert s.columns == frozenset({"ss_ext_sales_price"})
    assert s.literals == frozenset({"1.08"})


def test_count_distinct_is_tagged():
    s = sig("COUNT(DISTINCT order_id)")
    assert s.aggregates == ("COUNT|DISTINCT",)
    # a plain COUNT must have a different signature than COUNT DISTINCT
    assert sig("COUNT(order_id)").aggregates == ("COUNT",)


def test_aggregate_drift_is_detected():
    findings = compare({"ANSI_SQL": sig("SUM(amount)"), "SNOWFLAKE": sig("AVG(amount)")})
    codes = {c for c, *_ in findings}
    assert "AGGREGATE_DRIFT" in codes


def test_identical_expressions_have_no_drift():
    findings = compare(
        {"ANSI_SQL": sig("SUM(amount)"), "SNOWFLAKE": sig("SUM(amount)", "snowflake")}
    )
    assert findings == []


def test_benign_dialect_spelling_is_not_drift():
    # COALESCE vs NVL: same columns, same aggregate, same literal -> no finding.
    findings = compare(
        {
            "ANSI_SQL": sig("AVG(COALESCE(price, 0))"),
            "SNOWFLAKE": sig("AVG(NVL(price, 0))", "snowflake"),
        }
    )
    assert findings == []


def test_column_and_literal_drift_detected():
    col = compare(
        {"ANSI_SQL": sig("SUM(a)"), "BIGQUERY": sig("SUM(b)", "bigquery")}
    )
    assert {c for c, *_ in col} == {"COLUMN_DRIFT"}

    lit = compare(
        {"ANSI_SQL": sig("SUM(a * 1.08)"), "SNOWFLAKE": sig("SUM(a * 1.18)", "snowflake")}
    )
    assert {c for c, *_ in lit} == {"LITERAL_DRIFT"}


def test_single_dialect_has_nothing_to_compare():
    assert compare({"ANSI_SQL": sig("SUM(amount)")}) == []
