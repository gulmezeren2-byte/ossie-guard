"""Validate the emitted SARIF against the official SARIF 2.1.0 JSON Schema.

`test_sarif.py` asserts the fields GitHub code-scanning needs; this file asserts
the document is valid SARIF at all, against the vendored OASIS schema (see
tests/schema/README.md). Skipped when `jsonschema` is not installed, so the
package itself keeps its two-dependency footprint.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ossie_guard import __version__, lint_file
from ossie_guard.sarif import to_sarif

jsonschema = pytest.importorskip("jsonschema", reason="jsonschema not installed")

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = Path(__file__).parent / "schema" / "sarif-2.1.0.json"


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _doc(*names):
    pairs = [(str(FIXTURES / n), lint_file(str(FIXTURES / n))) for n in names]
    return to_sarif(pairs, tool_version=__version__)


@pytest.mark.parametrize(
    "names",
    [
        ("clean.yaml",),  # a run with zero results must still be valid
        ("drift.yaml",),
        ("unsafe.yaml",),
        ("clean.yaml", "drift.yaml", "unsafe.yaml"),  # multi-file run
    ],
    ids=["clean", "drift", "unsafe", "all"],
)
def test_output_is_valid_sarif_2_1_0(validator, names):
    errors = sorted(validator.iter_errors(_doc(*names)), key=lambda e: e.path)
    assert not errors, "; ".join(
        f"{'/'.join(str(p) for p in e.path)}: {e.message}" for e in errors[:5]
    )
