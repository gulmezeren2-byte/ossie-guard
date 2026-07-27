# Changelog

All notable changes to `ossie-guard` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-07-24

Turns ossie-guard from a CLI into something that plugs into a team's pipeline:
findings now land on the pull request itself.

### Added
- **SARIF 2.1.0 output** (`--format sarif`) for GitHub code scanning, so findings
  are annotated inline on the offending line. Built to GitHub's documented
  requirements (named driver, self-describing rules with `help.text`,
  repo-relative locations, `error`/`warning`/`note` levels, stable fingerprints)
  and **validated against the official OASIS SARIF 2.1.0 schema** in the test
  suite and again with an independent validator in CI.
- **Source line numbers on every finding** (`Finding.line`, shown as
  `model.yaml:24`, carried into JSON and SARIF). A line-aware YAML loader anchors
  safety and determinism findings to the exact dialect expression, and drift
  findings to the metric.
- **A composite GitHub Action** (`uses: gulmezeren2-byte/ossie-guard@v0.2.0`) that
  lints a file/directory and uploads the SARIF. It is dogfooded in CI: the action
  must produce a report, fail on a drifting model, and pass on a clean one.
- **pre-commit hook** (`.pre-commit-hooks.yaml`, `id: ossie-guard`).
- **Multiple model files per run** (`ossie-guard models/*.yaml`) — one aggregated
  SARIF document across all of them.
- `--output/-o` to write the report to a file, and `--fail-level`
  (`error`/`warning`/`note`/`none`) as the single gate control; `--strict` and
  `--exit-zero` remain as shorthands.
- A `[dev]` extra for the test-only dependencies; the package itself still needs
  only `pyyaml` + `sqlglot`.

### Changed
- The text report now points at `file:line` instead of only the dotted YAML path.
- `to_sarif()` takes `(model_path, findings)` pairs so one document can span
  several files.

### Fixed
- The action gates its upload on a step output rather than `hashFiles()`, which
  cannot see files under `RUNNER_TEMP` (outside the workspace) and would have
  silently skipped every upload.

## [0.1.0] - 2026-07-23

Initial release.

### Added
- **Cross-dialect drift detection** via a structural signature that ignores
  benign dialect spelling: `AGGREGATE_DRIFT` (error), `COLUMN_DRIFT` (warning),
  `LITERAL_DRIFT` (warning).
- **Expression purity checks**: `UNSAFE_FUNCTION` (error) for side-effecting
  functions (denylist ported from
  [readonly-sql-guard](https://github.com/gulmezeren2-byte/readonly-sql-guard)),
  and `NONDETERMINISTIC` (warning) for non-reproducible constructs
  (`NOW()`, `CURRENT_DATE`, `RANDOM()`, `UUID()`, …).
- Structure-agnostic walker that finds every `expression.dialects` carrier
  regardless of where it sits in the model.
- `ossie-guard` CLI with `--json`, `--strict`, and per-check toggles; exit codes
  `0`/`1`/`2` for CI.
- Library API: `lint_file`, `lint_model`, `Finding`, `Severity`.
- Verified to produce **zero findings** on the official Apache Ossie `flights`
  and `tpcds` example models.
