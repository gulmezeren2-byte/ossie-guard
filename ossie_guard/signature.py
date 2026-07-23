"""Cross-dialect drift detection via a structural signature.

The whole point of an Ossie metric carrying several dialect expressions is that
they *differ per engine* -- so a naive "do these render to the same SQL?" check
would fire on every legitimate `NVL` vs `COALESCE`. That would be dishonest: a
warning that is almost always noise trains people to ignore it.

Instead we reduce each dialect's expression to a small *structural signature*
that ignores benign dialect spelling but still captures the mistakes that
schema validation cannot see:

* **aggregates** -- the classes of aggregate function used (SUM / AVG / COUNT /
  COUNT-DISTINCT / MIN / MAX). You almost never *mean* to SUM on one warehouse
  and AVG on another for the same metric; when that happens it is a bug, so a
  mismatch here is an ERROR.
* **columns** -- the set of column names referenced. A copy-paste that left one
  dialect summing `ss_ext_sales_price` and another `ss_sales_price` is invisible
  to a parser but shows up here. Reported as a WARNING (a dialect *can*
  legitimately reference a differently named physical column).
* **literals** -- the numeric constants. A hard-coded `* 1.08` in one dialect and
  `* 1.18` in another is a classic drift; reported as a WARNING.

This is deliberately a *heuristic drift detector, not an equivalence prover*
(true SQL equivalence is undecidable). ossie-guard is honest about that limit --
see the README's "What it does and does not catch".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import expressions as exp

from .findings import Severity


@dataclass(frozen=True)
class Signature:
    """The drift-relevant shape of one dialect's expression."""

    aggregates: tuple  # sorted class names, DISTINCT-tagged, e.g. ("SUM",)
    columns: frozenset  # lowercased referenced column names
    literals: frozenset  # numeric literal texts, e.g. {"1.08"}


def extract(tree) -> Signature:
    """Reduce a parsed expression to its structural signature."""
    aggregates = []
    for agg in tree.find_all(exp.AggFunc):
        name = type(agg).__name__.upper()
        if agg.find(exp.Distinct) is not None:
            name += "|DISTINCT"
        aggregates.append(name)

    columns = frozenset(
        col.name.lower() for col in tree.find_all(exp.Column) if col.name
    )
    literals = frozenset(
        lit.name for lit in tree.find_all(exp.Literal) if lit.is_number
    )
    return Signature(tuple(sorted(aggregates)), columns, literals)


def compare(sigs: "dict[str, Signature]") -> list:
    """Compare per-dialect signatures. Returns (code, severity, message, detail)
    tuples for every axis that diverges. Empty when there is nothing to compare
    (fewer than two parseable dialects) or all dialects agree."""
    findings = []
    if len(sigs) < 2:
        return findings

    dialects = sorted(sigs)

    agg_by = {d: sigs[d].aggregates for d in dialects}
    if len(set(agg_by.values())) > 1:
        findings.append(
            (
                "AGGREGATE_DRIFT",
                Severity.ERROR,
                "aggregate functions differ across dialects: "
                + "; ".join(f"{d}={list(agg_by[d]) or '(none)'}" for d in dialects),
                {"per_dialect": {d: list(agg_by[d]) for d in dialects}},
            )
        )

    col_by = {d: sigs[d].columns for d in dialects}
    if len({frozenset(v) for v in col_by.values()}) > 1:
        shared = set.intersection(*[set(v) for v in col_by.values()])
        everywhere = set().union(*col_by.values())
        not_shared = sorted(everywhere - shared)
        findings.append(
            (
                "COLUMN_DRIFT",
                Severity.WARNING,
                "referenced columns differ across dialects; not shared by all: "
                + ", ".join(not_shared),
                {"per_dialect": {d: sorted(col_by[d]) for d in dialects}},
            )
        )

    lit_by = {d: sigs[d].literals for d in dialects}
    if len({frozenset(v) for v in lit_by.values()}) > 1:
        findings.append(
            (
                "LITERAL_DRIFT",
                Severity.WARNING,
                "numeric constants differ across dialects: "
                + "; ".join(f"{d}={sorted(lit_by[d]) or '(none)'}" for d in dialects),
                {"per_dialect": {d: sorted(lit_by[d]) for d in dialects}},
            )
        )

    return findings
