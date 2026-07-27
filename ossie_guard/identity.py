"""Finding identity -- one normalisation, shared by the baseline and SARIF.

Two places need to name a finding: a baseline file (is this one already known?)
and the SARIF report (is this the same alert as last run?). If they normalise the
model's path differently they silently disagree, and a baselined finding
reappears as a new SARIF alert. So both go through here.

The path is made repo-relative and POSIX-style, and a finding's identity leaves
out its **line number** on purpose: reformatting a model, or adding a metric
above another, must not resurrect a suppressed finding.
"""

from __future__ import annotations

import posixpath


def normalize_path(path: str) -> str:
    """Return a repo-relative, forward-slashed form of `path`.

    Idempotent, so it is safe to apply to an already-normalised value. The
    leading separator is stripped because GitHub matches a SARIF
    `artifactLocation.uri` against the checked-out tree; an absolute
    `/home/runner/work/...` would never match.
    """
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return posixpath.normpath(normalized).lstrip("/")


def fingerprint(path: str, finding) -> str:
    """A stable, line-independent identity for one finding."""
    return (
        f"{normalize_path(path)}:{finding.code}:{finding.entity}:{finding.path}"
    )
