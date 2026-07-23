# ossie-guard

**An honesty & safety linter for [Apache Ossie](https://github.com/apache/ossie) semantic models.**

Apache Ossie (the reference implementation of the Open Semantic Interchange) lets one
metric carry a SQL expression for *several* dialects — ANSI, Snowflake, BigQuery,
Databricks — so the same measure travels across warehouses. Ossie's own
`validation/validate.py` checks that each expression **parses**. It does not check
the two things that actually make a metric trustworthy:

1. **Do the dialects agree?** A metric that is `SUM(amount)` on ANSI but `AVG(amount)`
   on Snowflake parses perfectly and silently returns a different number on every
   engine. Schema validation never sees it.
2. **Is the expression a pure, reproducible read?** A "metric" that calls
   `pg_read_file(...)`, or that depends on `NOW()` / `RANDOM()`, parses fine too —
   but it is either a side-effect or non-reproducible.

`ossie-guard` is the layer that catches both. It is **complementary** to
`validate.py`: run the schema validator first, then run `ossie-guard`.

```console
$ ossie-guard model.yaml
```

```
ossie-guard 0.1.0 - model.yaml

  ERROR    AGGREGATE_DRIFT  -  revenue
           aggregate functions differ across dialects: ANSI_SQL=['SUM']; SNOWFLAKE=['AVG']
           at semantic_model.metrics[0]

  WARNING  COLUMN_DRIFT  -  gross_sales
           referenced columns differ across dialects; not shared by all: ss_ext_sales_price, ss_sales_price
           at semantic_model.metrics[1]

  ERROR    UNSAFE_FUNCTION  -  leaky
           [ANSI_SQL] expression calls side-effecting function 'pg_read_file()'; a metric must be a pure read
           at semantic_model.metrics[2]

  2 errors, 1 warning
```

## Install

Works today, straight from the repo:

```console
pip install git+https://github.com/gulmezeren2-byte/ossie-guard
```

A PyPI release (`pip install ossie-guard`) is on the way — the publish workflow
is wired for Trusted Publishing and fires on the first tagged release.

Dependencies are exactly Ossie's own: `pyyaml` and `sqlglot`, nothing else.

## Use

```console
ossie-guard model.yaml                 # human-readable report
ossie-guard model.yaml --json          # machine-readable, for CI
ossie-guard model.yaml --strict        # warnings fail too (default: only errors fail)
ossie-guard model.yaml --no-determinism # turn a check off
```

Exit code is `0` when clean, `1` when an error is found (or any finding under
`--strict`), `2` on a usage/file error — so it drops straight into CI:

```yaml
# .github/workflows/semantic-model.yml
- run: python validation/validate.py model.yaml      # Ossie: does it parse?
- run: pip install git+https://github.com/gulmezeren2-byte/ossie-guard
- run: ossie-guard model.yaml                         # ossie-guard: does it agree, and is it pure?
```

As a library:

```python
from ossie_guard import lint_file, Severity

findings = lint_file("model.yaml")
for f in findings:
    print(f.severity.value, f.code, f.entity, "-", f.message)

if any(f.severity is Severity.ERROR for f in findings):
    raise SystemExit(1)
```

## What it checks

| Code | Severity | What it means |
|------|----------|---------------|
| `AGGREGATE_DRIFT` | error | The aggregate class differs across a metric's dialects (`SUM` vs `AVG`, `COUNT` vs `COUNT DISTINCT`). Almost always a bug. |
| `UNSAFE_FUNCTION` | error | An expression calls a side-effecting function (file/socket/shell/executor): `pg_read_file`, `dblink`, `xp_cmdshell`, `load_file`, `load_extension`, … |
| `COLUMN_DRIFT` | warning | The set of referenced columns differs across dialects — often a copy-paste that left one dialect on the wrong column. |
| `LITERAL_DRIFT` | warning | A numeric constant differs across dialects (a tax rate that drifted from `1.08` to `1.18`). |
| `NONDETERMINISTIC` | warning | The expression uses `NOW()`, `CURRENT_DATE`, `RANDOM()`, `UUID()`, … — the same run can return different numbers. |
| `PARSE_ERROR` | info | An expression a parser could not read; deeper checks were skipped for it. |

## What it does — and does *not* — catch

`ossie-guard` is honest about its own limits, because a linter that overclaims is
worse than none.

**The drift checks are a heuristic, not an equivalence prover.** True SQL
equivalence is undecidable, and the whole point of multi-dialect expressions is
that they legitimately differ (`COALESCE` on one engine, `NVL` on another). So
`ossie-guard` deliberately compares only a *structural signature* — aggregate
classes, referenced columns, numeric literals — and **ignores benign dialect
spelling**. Concretely:

- ✅ It catches `SUM` vs `AVG`, a wrong column, a drifted constant, `COUNT` vs
  `COUNT DISTINCT`.
- ✅ It does **not** flag `AVG(COALESCE(price, 0))` vs `AVG(NVL(price, 0))` — same
  signature, different spelling. (Verified against the official `flights` and
  `tpcds` example models: **zero findings**.)
- ⚠️ It will **not** catch a semantic difference that leaves the signature
  identical — e.g. a `WHERE`/`FILTER` predicate that differs across dialects, or a
  join grain that changes the meaning. Those need a human or an empirical test.

Treat the errors as high-confidence and the warnings as "a human should look."

## Why this exists

It comes from the same place as its sibling library
**[readonly-sql-guard](https://github.com/gulmezeren2-byte/readonly-sql-guard)** —
the side-effecting-function denylist here is ported from it — and from
[erp-report-engine](https://github.com/gulmezeren2-byte/erp-report-engine): the
belief that *"read-only," "reproducible," and "the same on every engine"* should be
properties a tool **measures**, not adjectives a model claims. A semantic layer is
the one place a wrong number propagates to every dashboard downstream; it deserves
a check that looks past "does it parse."

## Development

```console
pip install -e .
python -m pytest -q
```

## License

Apache-2.0 — the same license as Apache Ossie, so this can live comfortably beside
it. Not an official Apache project; "Apache Ossie" is referenced for
interoperability.
