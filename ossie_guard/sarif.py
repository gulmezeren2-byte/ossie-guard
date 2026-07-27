"""Render findings as SARIF 2.1.0 for GitHub code-scanning.

SARIF (Static Analysis Results Interchange Format) is what GitHub's
`upload-sarif` action ingests to populate the Security tab. Emitting it lets
ossie-guard's findings show up inline on a pull request, annotated on the exact
line of the offending expression -- the same experience CodeQL gives.

The document is built to GitHub's documented requirements: a single run with a
named driver, one self-describing rule per finding code (with the `help.text`
GitHub requires), and one result per finding with a repo-relative physical
location and a `note`/`warning`/`error` level. A line-only region is enough --
GitHub's own minimal example uses exactly that.
"""

from __future__ import annotations

import posixpath

from .baseline import fingerprint
from .findings import Finding, Severity

_INFO_URI = "https://github.com/gulmezeren2-byte/ossie-guard"
_HELP_URI = _INFO_URI + "#what-it-checks"

# Severity -> SARIF result level (GitHub's set is note / warning / error).
_LEVEL = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "note",
}
# Severity -> the non-security "problem.severity" property GitHub understands.
_PROBLEM = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "recommendation",
}

# Rule metadata, keyed by finding code: (short, full, tags).
_RULES = {
    "AGGREGATE_DRIFT": (
        "The aggregate function differs across a metric's dialects.",
        "A metric that is SUM on one engine and AVG on another silently returns "
        "a different number per warehouse. Almost always a bug.",
        ["semantic-layer", "correctness", "cross-dialect"],
    ),
    "COLUMN_DRIFT": (
        "A metric's dialects reference different columns.",
        "Often a copy-paste that left one dialect on the wrong column. A dialect "
        "can legitimately reference a differently named physical column, so this "
        "is a warning, not an error.",
        ["semantic-layer", "correctness", "cross-dialect"],
    ),
    "LITERAL_DRIFT": (
        "A numeric constant differs across a metric's dialects.",
        "A hard-coded rate that drifted between dialects (e.g. 1.08 vs 1.18).",
        ["semantic-layer", "correctness", "cross-dialect"],
    ),
    "PREDICATE_DRIFT": (
        "A metric's dialects filter on different conditions.",
        "The comparisons a metric filters on are not the same in every dialect - a "
        "drifted string constant (region = 'EU' vs 'US') or operator (> vs >=) "
        "changes which rows are counted. Idiomatic differences (CASE WHEN vs "
        "FILTER vs IF) are normalised away, so this points at a real difference.",
        ["semantic-layer", "correctness", "cross-dialect"],
    ),
    "UNSAFE_FUNCTION": (
        "An expression calls a side-effecting function.",
        "A metric expression that can read a file, open a socket, run a shell, or "
        "re-enter the executor is not a pure read.",
        ["semantic-layer", "security", "purity"],
    ),
    "NONDETERMINISTIC": (
        "An expression is non-reproducible.",
        "Uses NOW()/CURRENT_DATE/RANDOM()/UUID() or similar; the same model run "
        "can return different numbers. Can be intentional, so it is a warning.",
        ["semantic-layer", "reproducibility"],
    ),
    "PARSE_ERROR": (
        "An expression could not be parsed.",
        "Drift and determinism checks were skipped for it. Ossie's own validator "
        "is the place that reports SQL syntax errors.",
        ["semantic-layer"],
    ),
}


def _uri(model_path: str) -> str:
    """Return a repo-relative, forward-slashed URI for the model file."""
    normalized = model_path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    # A leading drive or root is stripped so GitHub can match it against the
    # checked-out tree; CI invokes ossie-guard with a repo-relative path anyway.
    return posixpath.normpath(normalized).lstrip("/")


def to_sarif(file_findings, *, tool_version: str) -> dict:
    """Build one SARIF 2.1.0 document across one or more linted files.

    `file_findings` is an iterable of `(model_path, findings)` pairs. All
    results share a single run with a single rules table; each result points at
    its own file via a repo-relative artifactLocation.
    """
    file_findings = list(file_findings)
    all_findings = [f for _, findings in file_findings for f in findings]

    codes = []  # preserves first-seen order -> stable ruleIndex
    for finding in all_findings:
        if finding.code not in codes:
            codes.append(finding.code)

    rules = []
    for code in codes:
        short, full, tags = _RULES.get(code, (code, code, ["semantic-layer"]))
        # A rule's default level and problem.severity follow its first finding.
        first = next(f for f in all_findings if f.code == code)
        rules.append(
            {
                "id": code,
                "name": code,
                "shortDescription": {"text": short},
                "fullDescription": {"text": full},
                "help": {"text": f"{full} See {_HELP_URI}."},
                "defaultConfiguration": {"level": _LEVEL[first.severity]},
                "helpUri": _HELP_URI,
                "properties": {
                    "tags": tags,
                    "problem.severity": _PROBLEM[first.severity],
                },
            }
        )

    results = []
    for model_path, findings in file_findings:
        uri = _uri(model_path)
        for finding in findings:
            results.append(
                {
                    "ruleId": finding.code,
                    "ruleIndex": codes.index(finding.code),
                    "level": _LEVEL[finding.severity],
                    "message": {"text": f"{finding.entity}: {finding.message}"},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": uri},
                                "region": {"startLine": finding.line or 1},
                            }
                        }
                    ],
                    "partialFingerprints": {
                        # Same identity a baseline file uses, so the two agree.
                        "ossieGuard/v1": fingerprint(uri, finding)
                    },
                }
            )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "ossie-guard",
                        "version": tool_version,
                        "semanticVersion": tool_version,
                        "informationUri": _INFO_URI,
                        "rules": rules,
                    }
                },
                "automationDetails": {"id": "ossie-guard/"},
                "results": results,
            }
        ],
    }
