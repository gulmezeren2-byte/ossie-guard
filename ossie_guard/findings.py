"""The finding model: what ossie-guard reports, and how severe it is.

A finding is a single, honest claim about one expression carrier (a metric,
field, or dimension) in a semantic model. It never asserts more than the check
can actually prove -- a `COLUMN_DRIFT` says "these dialects reference different
columns", not "this metric is wrong", because only a human knows whether the
divergence was intended.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    """How much a finding should be trusted to mean something is broken.

    ERROR   -- high-confidence, low-false-positive (a metric silently computes a
               different aggregate per engine; an expression calls a
               side-effecting function). Fails CI by default.
    WARNING -- worth a human's eyes but can be legitimate (columns/constants
               that differ across dialects; a non-reproducible function). Fails
               CI only under --strict.
    INFO    -- purely informational (an expression a parser could not read, so
               deeper checks were skipped).
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    """One reported issue.

    Attributes:
        severity: see `Severity`.
        code:     a stable machine-readable slug (AGGREGATE_DRIFT, COLUMN_DRIFT,
                  LITERAL_DRIFT, UNSAFE_FUNCTION, NONDETERMINISTIC, PARSE_ERROR).
        entity:   the name of the metric/field/dimension the finding is about.
        message:  a one-line human explanation.
        path:     where in the YAML the carrier lives (dotted, e.g.
                  "semantic_model.metrics[3]").
        detail:   structured extras (e.g. the per-dialect values) for --json.
    """

    severity: Severity
    code: str
    entity: str
    message: str
    path: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "entity": self.entity,
            "message": self.message,
            "path": self.path,
            "detail": self.detail,
        }
