"""Baselines: adopt ossie-guard on a model that already has findings.

A team that runs this for the first time on a mature semantic model may get a
list of pre-existing findings, and "fix all of them before you can turn the
check on" is how a useful check ends up switched off. A baseline records what was
already there so CI only fails on **new** findings -- a ratchet, not a cliff.

The identity of a finding deliberately excludes its line number, so moving a
metric or reformatting the YAML does not resurrect a baselined finding. It is the
same fingerprint the SARIF report carries, so the two views agree.
"""

from __future__ import annotations

import json

_VERSION = 1


def fingerprint(uri: str, finding) -> str:
    """A line-independent identity for one finding."""
    return f"{uri}:{finding.code}:{finding.entity}:{finding.path}"


def build(file_findings) -> dict:
    """Build a baseline document from `(model_path, findings)` pairs."""
    entries = sorted(
        {
            fingerprint(path.replace("\\", "/"), finding)
            for path, findings in file_findings
            for finding in findings
        }
    )
    return {
        "ossie_guard_baseline": _VERSION,
        "note": (
            "Findings listed here are known and do not fail CI. Delete an entry "
            "once it is fixed; ossie-guard reports entries that no longer occur "
            "so this file can be pruned."
        ),
        "findings": entries,
    }


def load(path: str) -> "set[str]":
    """Load a baseline file and return its fingerprints.

    Raises ValueError on a file that is not a baseline document, so a typo'd
    path fails loudly instead of silently suppressing nothing.
    """
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or "ossie_guard_baseline" not in data:
        raise ValueError(f"{path} is not an ossie-guard baseline file")
    return set(data.get("findings") or [])


def apply(file_findings, known: "set[str]"):
    """Split findings into (kept, suppressed_count, stale_fingerprints).

    `kept` mirrors the input shape with baselined findings removed. `stale` is
    the baseline entries that no longer match anything, so they can be pruned.
    """
    kept = []
    suppressed = 0
    seen = set()
    for path, findings in file_findings:
        uri = path.replace("\\", "/")
        remaining = []
        for finding in findings:
            token = fingerprint(uri, finding)
            seen.add(token)
            if token in known:
                suppressed += 1
            else:
                remaining.append(finding)
        kept.append((path, remaining))
    return kept, suppressed, sorted(known - seen)
