# ossie-guard

🇹🇷 **Türkçesi:** [README.tr.md](README.tr.md)

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
ossie-guard 0.3.1 - model.yaml

  ERROR    AGGREGATE_DRIFT  -  revenue
           aggregate functions differ across dialects: ANSI_SQL=['SUM']; SNOWFLAKE=['AVG']
           at model.yaml:8

  WARNING  COLUMN_DRIFT  -  gross_sales
           referenced columns differ across dialects; not shared by all: ss_ext_sales_price, ss_sales_price
           at model.yaml:16

  WARNING  LITERAL_DRIFT  -  revenue_with_tax
           numeric constants differ across dialects: ANSI_SQL=['1.08']; SNOWFLAKE=['1.18']
           at model.yaml:24

  1 error, 2 warnings
```

*(That is the verbatim output for [`tests/fixtures/drift.yaml`](tests/fixtures/drift.yaml)
— every example in this README is real tool output, not a mock-up.)*

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
ossie-guard model.yaml                      # human-readable report
ossie-guard models/*.yaml                   # several models in one run
ossie-guard model.yaml --format json        # machine-readable
ossie-guard model.yaml --format sarif       # SARIF 2.1.0 for GitHub code scanning
ossie-guard model.yaml -o report.sarif      # write to a file instead of stdout
ossie-guard model.yaml --fail-level warning # warnings fail too (default: error)
ossie-guard model.yaml --no-determinism     # turn a check off
ossie-guard models/*.yaml --write-baseline .ossie-guard-baseline.json   # adopt on an existing model
ossie-guard models/*.yaml --baseline .ossie-guard-baseline.json         # fail only on NEW findings
```

Exit code is `0` when clean, `1` when a finding at or above `--fail-level` is
present, `2` on a usage/file error. `--fail-level none` never fails the run
(useful when you only want the report), and `--strict` / `--exit-zero` remain as
shorthands for `warning` / `none`.

### GitHub Action (findings annotated on the pull request)

`ossie-guard` ships as a composite action that lints your models and uploads
SARIF to **code scanning**, so each finding appears inline on the exact line of
the offending expression:

```yaml
# .github/workflows/semantic-model.yml
name: semantic-model
on: [push, pull_request]

permissions:
  contents: read
  security-events: write     # required to upload SARIF
  # actions: read            # additionally required on PRIVATE repositories

jobs:
  ossie-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: gulmezeren2-byte/ossie-guard@v0.3.1
        with:
          path: models          # a file, a directory, or several paths
          fail-level: error     # error | warning | note | none
```

Run it after Ossie's own validator, which answers a different question:

```yaml
      - run: python validation/validate.py models/model.yaml   # does it parse?
      - uses: gulmezeren2-byte/ossie-guard@v0.3.1              # does it agree, and is it pure?
```

Prefer plain steps? The CLI is just as CI-friendly:

```yaml
      - run: pip install git+https://github.com/gulmezeren2-byte/ossie-guard
      - run: ossie-guard models/*.yaml
```

### pre-commit

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gulmezeren2-byte/ossie-guard
    rev: v0.3.1
    hooks:
      - id: ossie-guard
        files: ^models/.*\.ya?ml$      # narrow it to your model directory
```

### As a library

```python
from ossie_guard import lint_file, Severity

findings = lint_file("model.yaml")
for f in findings:
    print(f"{f.severity.value} {f.code} {f.entity} (line {f.line}) - {f.message}")

if any(f.severity is Severity.ERROR for f in findings):
    raise SystemExit(1)
```

Need SARIF from Python?

```python
import json
from ossie_guard import __version__, lint_file
from ossie_guard.sarif import to_sarif

doc = to_sarif([("model.yaml", lint_file("model.yaml"))], tool_version=__version__)
json.dump(doc, open("report.sarif", "w"), indent=2)
```

## What it checks

| Code | Severity | What it means |
|------|----------|---------------|
| `AGGREGATE_DRIFT` | error | The aggregate class differs across a metric's dialects (`SUM` vs `AVG`, `COUNT` vs `COUNT DISTINCT`). Almost always a bug. |
| `UNSAFE_FUNCTION` | error | An expression calls a side-effecting function (file/socket/shell/executor): `pg_read_file`, `dblink`, `xp_cmdshell`, `load_file`, `load_extension`, … |
| `COLUMN_DRIFT` | warning | The set of referenced columns differs across dialects — often a copy-paste that left one dialect on the wrong column. |
| `LITERAL_DRIFT` | warning | A constant used in **arithmetic** differs across dialects (a tax rate that drifted from `* 1.08` to `* 1.18`). |
| `PREDICATE_DRIFT` | warning | The **filter conditions** differ across dialects — a drifted string constant (`region = 'EU'` vs `'US'`) or operator (`> 100` vs `>= 100`) changes which rows are counted. |
| `NONDETERMINISTIC` | warning | The expression uses `NOW()`, `CURRENT_DATE`, `RANDOM()`, `UUID()`, … — the same run can return different numbers. |
| `PARSE_ERROR` | info | An expression a parser could not read; deeper checks were skipped for it. |

## What it does — and does *not* — catch

`ossie-guard` is honest about its own limits, because a linter that overclaims is
worse than none.

**The drift checks are a heuristic, not an equivalence prover.** True SQL
equivalence is undecidable, and the whole point of multi-dialect expressions is
that they legitimately differ (`COALESCE` on one engine, `NVL` on another). So
`ossie-guard` deliberately compares only a *structural signature* — aggregate
classes, referenced columns, arithmetic constants, and filter predicates — and
**ignores benign dialect spelling**. Concretely:

- ✅ It catches `SUM` vs `AVG`, a wrong column, a drifted arithmetic constant,
  `COUNT` vs `COUNT DISTINCT`, and a drifted filter (a string constant or an
  operator).
- ✅ It does **not** flag expressions that differ only in idiom. All of these
  compare **equal**:

  | one dialect | the other | why it's not drift |
  |---|---|---|
  | `AVG(COALESCE(price, 0))` | `AVG(NVL(price, 0))` | same signature, different spelling |
  | `SUM(CASE WHEN s = 1 THEN amt ELSE 0 END)` | `SUM(amt) FILTER (WHERE s = 1)` | same filter, different construct |
  | `SUM(CASE WHEN s = 1 THEN amt ELSE 0 END)` | `SUM(IF(s = 1, amt, 0))` | same filter, BigQuery idiom |
  | `is_active = TRUE` | `is_active = 1` | engines spell booleans differently |
  | `amt > 100` | `100 < amt` | operands written the other way round |
  | `status IN (1, 2)` | `status IN (2, 1)` | order in an `IN` list carries no meaning |
  | `DATE_FORMAT(d, '%Y-%m')` | `FORMAT_DATE('%Y-%m', d)` | a format string is not a filter |

  (Verified against the official `flights` and `tpcds` example models: **zero
  findings**.)
- ⚠️ It will **not** catch a semantic difference that leaves the signature
  identical — e.g. a join grain that changes the meaning, a different `GROUP BY`
  context, or a filter whose *columns, operators and values* all match but whose
  boolean structure differs (`A AND B` vs `A OR B`). Those need a human or an
  empirical test.

Treat the errors as high-confidence and the warnings as "a human should look."

### Adopting it on a model that already has findings

Run it once, record what is already there, and let CI fail only on **new**
findings:

```console
ossie-guard models/*.yaml --write-baseline .ossie-guard-baseline.json
git add .ossie-guard-baseline.json
```

```yaml
      - uses: gulmezeren2-byte/ossie-guard@v0.3.1
        with:
          path: models
          baseline: .ossie-guard-baseline.json
```

A baselined finding is identified without its line number, so reformatting a
model will not resurrect it, and entries that no longer occur are reported so the
file can be pruned. It is a ratchet, not a mute button.

## How it's verified

A linter that claims low false positives should prove it. Every push runs:

| Check | What it proves |
|-------|----------------|
| **62 tests** on Python 3.9 / 3.11 / 3.12 / 3.13 / 3.14 | the checks behave the same on every supported runtime |
| **Zero findings on Apache Ossie's own `flights` + `tpcds` examples** | it is not noisy on valid, real-world models |
| **SARIF validated against the official OASIS 2.1.0 schema** (vendored, offline — plus an independent `check-jsonschema` pass in CI) | the report GitHub ingests is real SARIF, not "probably valid" |
| **The composite action is dogfooded in CI** — it must produce a report, fail on a drifting model, and pass on a clean one | the action works as documented, not just in theory |

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
pip install -e ".[dev]"     # adds pytest + jsonschema (for the SARIF schema test)
python -m pytest -q
```

The package itself depends only on `pyyaml` and `sqlglot`; everything in `[dev]`
is test-only.

## License

Apache-2.0 — the same license as Apache Ossie, so this can live comfortably beside
it. Not an official Apache project; "Apache Ossie" is referenced for
interoperability.
