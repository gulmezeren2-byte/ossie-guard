"""Orchestration: walk a semantic model, run the checks, collect findings.

ossie-guard is *complementary* to Apache Ossie's own `validation/validate.py`:
run the schema validator first (shape, unique names, references, SQL syntax),
then run ossie-guard for the honesty/safety layer it does not cover. The walker
is structure-agnostic on purpose -- it finds every `expression.dialects` block
wherever it lives (fields, metrics, dimensions, in `ontology:` or
`semantic_model:`), so it keeps working as models are laid out differently.
"""

from __future__ import annotations

from .dialects import SKIP, resolve
from .findings import Finding, Severity
from .parsing import parse_expr
from .purity import dangerous_hits, nondeterministic_hits
from .signature import compare, extract


def _walk(node, path: str, name_hint):
    """Yield (entity_name, path, dialect_expressions) for every expression
    carrier found anywhere in the loaded YAML."""
    if isinstance(node, dict):
        name = node.get("name") or name_hint
        expression = node.get("expression")
        if isinstance(expression, dict) and isinstance(
            expression.get("dialects"), list
        ):
            yield (name or "(unnamed)", path or "(root)", expression["dialects"])
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk(value, child_path, name)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]", name_hint)


def lint_model(
    data: dict,
    *,
    check_safety: bool = True,
    check_determinism: bool = True,
    check_drift: bool = True,
) -> "list[Finding]":
    """Lint an already-parsed semantic model (a dict from yaml.safe_load).

    Returns findings ordered by the carrier they belong to. Each expression is
    parsed at most once and shared across the checks.
    """
    findings: list[Finding] = []

    for entity, path, dialect_exprs in _walk(data, "", None):
        signatures = {}

        for dialect_expr in dialect_exprs:
            if not isinstance(dialect_expr, dict):
                continue
            dialect = dialect_expr.get("dialect")
            expr = dialect_expr.get("expression")
            if not isinstance(expr, str) or not expr.strip():
                continue

            sqlglot_dialect = resolve(dialect)
            skip_ast = sqlglot_dialect is SKIP
            tree = None if skip_ast else parse_expr(expr, sqlglot_dialect)

            # Safety: lexical net always runs (even on unparseable / non-SQL
            # expressions); the AST adds precision when we could parse.
            if check_safety:
                for name in sorted(dangerous_hits(tree, expr)):
                    findings.append(
                        Finding(
                            Severity.ERROR,
                            "UNSAFE_FUNCTION",
                            entity,
                            f"[{dialect}] expression calls side-effecting "
                            f"function '{name}()'; a metric must be a pure read",
                            path,
                            {"dialect": dialect, "function": name},
                        )
                    )

            if skip_ast:
                continue

            if tree is None:
                findings.append(
                    Finding(
                        Severity.INFO,
                        "PARSE_ERROR",
                        entity,
                        f"[{dialect}] expression could not be parsed; "
                        f"drift/determinism checks skipped for it",
                        path,
                        {"dialect": dialect, "expression": expr},
                    )
                )
                continue

            if check_determinism:
                for name in sorted(nondeterministic_hits(tree)):
                    findings.append(
                        Finding(
                            Severity.WARNING,
                            "NONDETERMINISTIC",
                            entity,
                            f"[{dialect}] expression is non-reproducible: uses "
                            f"'{name}'; the same run can return different numbers",
                            path,
                            {"dialect": dialect, "construct": name},
                        )
                    )

            signatures[dialect] = extract(tree)

        if check_drift:
            for code, severity, message, detail in compare(signatures):
                findings.append(Finding(severity, code, entity, message, path, detail))

    return findings


def lint_file(
    path: str,
    *,
    check_safety: bool = True,
    check_determinism: bool = True,
    check_drift: bool = True,
) -> "list[Finding]":
    """Load a YAML model from `path` and lint it."""
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, (dict, list)):
        return []
    return lint_model(
        data if isinstance(data, dict) else {"_root": data},
        check_safety=check_safety,
        check_determinism=check_determinism,
        check_drift=check_drift,
    )
