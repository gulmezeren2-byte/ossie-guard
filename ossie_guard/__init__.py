"""ossie-guard: an honesty & safety linter for Apache Ossie semantic models.

Apache Ossie's own validator answers "does every expression parse?". ossie-guard
answers the two questions it cannot:

* do a metric's dialects actually *agree* (or does it silently compute a
  different aggregate / column / constant per engine)?
* is every expression a *pure, reproducible read* (no file/socket/shell
  side-effects, no non-deterministic functions)?

Public API::

    from ossie_guard import lint_file, lint_model, Finding, Severity

    for f in lint_file("model.yaml"):
        print(f.severity.value, f.code, f.entity, "-", f.message)
"""

from __future__ import annotations

from .findings import Finding, Severity
from .linter import lint_file, lint_model

__version__ = "0.3.1"
__all__ = ["lint_file", "lint_model", "Finding", "Severity", "__version__"]
