"""Parse a single Ossie scalar expression with sqlglot.

Ossie expressions are scalar fragments ("SUM(x)", "airport_code", a CASE), not
whole statements, so we parse the bare fragment first and fall back to wrapping
it in a SELECT -- the same two-step Ossie's own validate.py uses.
"""

from __future__ import annotations

import sqlglot
from sqlglot import expressions as exp


def parse_expr(expr: str, sqlglot_dialect):
    """Return the root sqlglot node for a scalar expression, or None if it will
    not parse in the given dialect."""
    try:
        return sqlglot.parse_one(expr, read=sqlglot_dialect)
    except Exception:
        pass
    try:
        stmt = sqlglot.parse_one(f"SELECT {expr}", read=sqlglot_dialect)
        selects = getattr(stmt, "selects", None) or []
        if selects:
            node = selects[0]
            # Unwrap a trailing alias ("<expr> AS foo") so checks see the value.
            return node.this if isinstance(node, exp.Alias) else node
        return stmt
    except Exception:
        return None
