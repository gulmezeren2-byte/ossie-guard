"""Mapping from Ossie's dialect enum to a sqlglot read-dialect.

Kept deliberately identical in spirit to Apache Ossie's own
`validation/validate.py`: the SQL-family dialects are parsed with sqlglot, and
the three non-SQL surfaces (MDX, Tableau, MAQL) are skipped because sqlglot
cannot read them -- so ossie-guard makes no structural claim about them.
"""

from __future__ import annotations

# Sentinel: this Ossie dialect is a real language sqlglot cannot parse, so we
# skip the AST-based checks for it (drift, determinism) and only run the
# language-agnostic lexical safety net.
SKIP = object()

# Ossie dialect name -> sqlglot dialect (None means sqlglot's default / ANSI).
_MAP: dict[str, object] = {
    "ANSI_SQL": None,
    "SNOWFLAKE": "snowflake",
    "BIGQUERY": "bigquery",
    "DATABRICKS": "databricks",
    "MDX": SKIP,
    "TABLEAU": SKIP,
    "MAQL": SKIP,
}


def resolve(ossie_dialect: str | None):
    """Return the sqlglot dialect for an Ossie dialect name.

    - a string / None  -> parse with that sqlglot dialect
    - SKIP             -> sqlglot cannot parse this language; skip AST checks
    Unknown names fall back to ANSI (None); Ossie's schema validator is the
    place that rejects an out-of-enum dialect, not this linter.
    """
    return _MAP.get(ossie_dialect, None)


def is_parseable(ossie_dialect: str | None) -> bool:
    return resolve(ossie_dialect) is not SKIP
