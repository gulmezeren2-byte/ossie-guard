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
* **literals** -- the numeric constants used in *arithmetic*. A hard-coded
  `* 1.08` in one dialect and `* 1.18` in another is a classic drift; reported as
  a WARNING. Only arithmetic operands count, because a raw literal *set* is
  sensitive to harmless idiom: `SUM(CASE WHEN x THEN amt ELSE 0 END)` carries a
  structural `0` that the equivalent `SUM(amt) FILTER (WHERE x)` does not, and
  `is_active = TRUE` carries no number where `is_active = 1` does. Constants used
  in comparisons belong to the predicate axis below, which normalises exactly
  those spellings.
* **predicates** -- the comparisons a metric filters on, normalised. This closes
  the two gaps the other three axes leave open: a *string* constant that drifted
  (`region = 'EU'` vs `region = 'US'` -- same columns, no numeric literals) and a
  drifted *operator* (`amt > 100` vs `amt >= 100`). Only comparison nodes are
  read, so a dialect-specific format string (`DATE_FORMAT(d, '%Y-%m')`) is never
  compared, and the three idiomatic ways of writing the same filter --
  `CASE WHEN`, `FILTER (WHERE ...)`, `IF(...)` -- reduce to the same predicate.
  Reported as a WARNING.

This is deliberately a *heuristic drift detector, not an equivalence prover*
(true SQL equivalence is undecidable). ossie-guard is honest about that limit --
see the README's "What it does and does not catch".
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import expressions as exp

from .findings import Severity

# Comparison nodes whose operands make up the predicate signature.
_CMP = (
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.In, exp.Like, exp.ILike, exp.Is,
)
# Flipping a comparison so `100 < amt` and `amt > 100` agree.
_FLIP = {"GT": "LT", "LT": "GT", "GTE": "LTE", "LTE": "GTE", "EQ": "EQ", "NEQ": "NEQ"}

# Arithmetic nodes whose literal operands are a real scaling factor, as opposed to
# the structural constants (`ELSE 0`) and comparison values that idiom moves around.
_ARITH = (exp.Mul, exp.Div, exp.Add, exp.Sub, exp.Mod, exp.Pow)


def _number(text: str) -> str:
    """Normalise a numeric literal so 100 and 100.0 agree, 1.08 and 1.18 do not."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return str(text)
    return str(int(value)) if value == int(value) else repr(value)


def _operand(node) -> str:
    """A dialect-independent token for one side of a comparison."""
    if node is None:
        return ""
    if isinstance(node, exp.Column):
        return node.name.lower()
    # TRUE and 1 mean the same filter; engines differ on how a boolean is spelled.
    if isinstance(node, exp.Boolean):
        return "1" if node.this else "0"
    if isinstance(node, exp.Null):
        return "null"
    if isinstance(node, exp.Literal):
        return _number(node.name) if node.is_number else f"'{node.name}'"
    try:
        rendered = node.sql()
    except Exception:  # noqa: BLE001 - any un-renderable node falls back to repr
        rendered = repr(node)
    return " ".join(rendered.lower().split())


def _predicate(node) -> str:
    """Normalise one comparison into a comparable token."""
    op = type(node).__name__.upper()
    left = _operand(node.this)

    if isinstance(node, exp.In):
        # Order inside an IN list carries no meaning.
        items = sorted(_operand(item) for item in (node.expressions or []))
        return f"IN({left},[{','.join(items)}])"

    right = _operand(node.args.get("expression"))
    # Canonicalise literal-on-the-left ("100 < amt" -> "amt > 100").
    if op in _FLIP and left and right:
        left_is_col = isinstance(node.this, exp.Column)
        right_is_col = isinstance(node.args.get("expression"), exp.Column)
        if right_is_col and not left_is_col:
            op, left, right = _FLIP[op], right, left
    return f"{op}({left},{right})"


@dataclass(frozen=True)
class Signature:
    """The drift-relevant shape of one dialect's expression."""

    aggregates: tuple  # sorted class names, DISTINCT-tagged, e.g. ("SUM",)
    columns: frozenset  # lowercased referenced column names
    literals: frozenset  # numeric literal texts, e.g. {"1.08"}
    predicates: frozenset  # normalised comparisons, e.g. {"EQ(region,'EU')"}


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
    literals = set()
    for node in tree.find_all(_ARITH):
        for side in (node.this, node.args.get("expression")):
            if isinstance(side, exp.Literal) and side.is_number:
                literals.add(_number(side.name))
    literals = frozenset(literals)
    predicates = frozenset(_predicate(node) for node in tree.find_all(_CMP))
    return Signature(
        tuple(sorted(aggregates)), columns, literals, predicates
    )


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

    pred_by = {d: sigs[d].predicates for d in dialects}
    if len({frozenset(v) for v in pred_by.values()}) > 1:
        shared = set.intersection(*[set(v) for v in pred_by.values()])
        everywhere = set().union(*pred_by.values())
        findings.append(
            (
                "PREDICATE_DRIFT",
                Severity.WARNING,
                "filter conditions differ across dialects; not shared by all: "
                + ", ".join(sorted(everywhere - shared)),
                {"per_dialect": {d: sorted(pred_by[d]) for d in dialects}},
            )
        )

    return findings
