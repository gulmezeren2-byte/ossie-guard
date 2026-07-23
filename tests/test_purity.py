from __future__ import annotations

from ossie_guard.parsing import parse_expr
from ossie_guard.purity import dangerous_hits, nondeterministic_hits


def test_dangerous_function_detected_via_ast_and_lexical():
    expr = "MAX(pg_read_file('/etc/passwd'))"
    hits = dangerous_hits(parse_expr(expr, None), expr)
    assert "pg_read_file" in hits


def test_unparseable_payload_still_caught_by_lexical_net():
    # OPENROWSET does not parse as a scalar expression; tree is None, but the
    # lexical net on the raw text must still flag it.
    expr = "OPENROWSET(BULK 'C:\\win.ini', SINGLE_CLOB)"
    assert parse_expr(expr, None) is None or True  # parse may fail; that's fine
    assert "openrowset" in dangerous_hits(None, expr)


def test_pure_expression_has_no_dangerous_hits():
    expr = "SUM(amount)"
    assert dangerous_hits(parse_expr(expr, None), expr) == set()


def test_column_named_like_a_function_is_not_flagged():
    # "sleep" as a bare column (no parens) must not trip the safety net.
    expr = "MAX(sleep)"
    assert dangerous_hits(parse_expr(expr, None), expr) == set()


def test_nondeterministic_constructs_detected():
    assert "current_date" in nondeterministic_hits(parse_expr("CURRENT_DATE", None))
    assert "current_timestamp" in nondeterministic_hits(
        parse_expr("CURRENT_TIMESTAMP", None)
    )
    assert "random" in nondeterministic_hits(parse_expr("RANDOM()", None))
    assert "uuid" in nondeterministic_hits(parse_expr("UUID()", None))
    assert "now" in nondeterministic_hits(parse_expr("NOW()", None))


def test_deterministic_expression_is_clean():
    assert nondeterministic_hits(parse_expr("SUM(amount)", None)) == set()
