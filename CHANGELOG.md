# Changelog

All notable changes to `ossie-guard` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
[Semantic Versioning](https://semver.org/).

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
