# ossie-guard — instructions for AI coding agents

`ossie-guard` is a linter for **Apache Ossie** (Open Semantic Interchange)
semantic models. Ossie's own `validation/validate.py` checks that each dialect
expression *parses*; this tool checks the two things it cannot: whether a
metric's dialects actually **agree**, and whether every expression is a **pure,
reproducible read**.

## Tech stack

- Python ≥ 3.9, no framework. Runtime deps are **only** `pyyaml` + `sqlglot`
  (deliberately the same two Ossie itself uses) — do not add a third without a
  strong reason; `[dev]` extras (`pytest`, `jsonschema`) are test-only.
- Packaged with `hatchling`. Console script: `ossie-guard` → `ossie_guard.cli:main`.

## Layout

| Path | Role |
|------|------|
| `ossie_guard/linter.py` | orchestration: line-aware YAML load, structure-agnostic walk of every `expression.dialects` carrier, runs the checks |
| `ossie_guard/signature.py` | cross-dialect **drift** via a structural signature (aggregates / columns / numeric literals) |
| `ossie_guard/purity.py` | side-effecting-function denylist + non-determinism detection |
| `ossie_guard/parsing.py` | parse one scalar expression with sqlglot (bare, then wrapped in `SELECT`) |
| `ossie_guard/dialects.py` | Ossie dialect → sqlglot dialect; `SKIP` for MDX/Tableau/MAQL |
| `ossie_guard/findings.py` | `Finding` / `Severity` model |
| `ossie_guard/sarif.py` | SARIF 2.1.0 rendering for GitHub code scanning |
| `ossie_guard/cli.py` | argparse CLI, output formats, exit codes |
| `action.yml` | composite GitHub Action (lint + upload SARIF) |
| `tests/fixtures/` | `clean.yaml` (must stay finding-free), `drift.yaml`, `unsafe.yaml` |
| `tests/schema/` | vendored OASIS SARIF 2.1.0 schema (test-only) |

## Commands

```console
pip install -e ".[dev]"
python -m pytest -q                                   # full suite
ossie-guard tests/fixtures/drift.yaml                 # human report (exits 1)
ossie-guard tests/fixtures/*.yaml --format sarif -o out.sarif --fail-level none
```

## Conventions that matter here

- **Honesty over coverage.** This project's whole premise is that it does not
  overclaim. The drift check is a *heuristic, not an equivalence prover*; the
  README documents what it cannot catch. Keep that section truthful — if you add
  a check, add its limits too.
- **False positives are the cardinal sin.** A finding on a *valid* model destroys
  the tool's value. Benign dialect spelling (`COALESCE` vs `NVL`) must never be
  flagged. Apache Ossie's own `flights` and `tpcds` examples must keep producing
  **zero findings** — verify before claiming a change is safe.
- **Severity contract:** `ERROR` = high-confidence bug (aggregate drift, unsafe
  function). `WARNING` = a human should look (column/literal drift,
  non-determinism). `INFO` = informational (`PARSE_ERROR`). Do not promote a
  warning to an error without evidence that it is rarely legitimate.
- **Finding codes are a public API.** They appear in SARIF, JSON, and users' CI
  gates. Renaming one is a breaking change; add new codes instead, and give each
  a `_RULES` entry in `sarif.py` (GitHub requires `help.text`).
- **Every finding carries a line.** `linter.py` uses a `SafeLoader` subclass that
  stamps mappings with `__line__`; that synthetic key must be skipped when
  walking. Safety/determinism findings anchor to the exact dialect expression,
  drift findings to the metric.
- **SARIF must stay schema-valid.** `tests/test_sarif_schema.py` validates output
  against the vendored OASIS schema and CI re-checks it with `check-jsonschema`.
  Changing the SARIF shape means running those.
- Docstrings explain *why* a design choice was made, not what the line does.
  Match that voice.

## Gotchas

- `sqlglot` parses Ossie expressions as **scalar fragments**, not statements —
  always go through `parsing.parse_expr`, never `sqlglot.parse_one` directly.
- `MDX` / `TABLEAU` / `MAQL` cannot be parsed by sqlglot: AST checks are skipped
  for them, but the **lexical** safety net still runs (the input that defeats a
  parser is often the payload).
- In the composite action, `run:` steps execute in the *consumer's* workspace —
  install the bundled tool via `$GITHUB_ACTION_PATH`. `hashFiles()` cannot see
  files under `RUNNER_TEMP`, so the SARIF upload is gated on a step output.
- Actions in workflows are SHA-pinned with a `# vX.Y.Z` comment. Keep that style.
