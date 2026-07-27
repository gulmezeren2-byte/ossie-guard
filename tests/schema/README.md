# Vendored SARIF schema

`sarif-2.1.0.json` is the official **Static Analysis Results Format (SARIF)
Version 2.1.0** JSON Schema, vendored so the test suite and CI can validate
ossie-guard's `--format sarif` output **offline and deterministically** (no
network fetch to flake on).

- Upstream `$id`: `https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json`
- Fetched from: <https://json.schemastore.org/sarif-2.1.0.json>
- Retrieved: 2026-07-24

It is used by `tests/test_sarif_schema.py` and by the `sarif` job in
`.github/workflows/ci.yml`. Nothing in the shipped package imports it — it is a
test fixture only, and is excluded from the wheel.

To refresh it, re-download from the URL above and re-run the tests.
