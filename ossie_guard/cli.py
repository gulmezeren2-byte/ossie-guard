"""Command-line interface: `ossie-guard <model.yaml>`.

Exit codes:
    0  no errors (warnings allowed unless --strict)
    1  at least one ERROR finding, or any finding under --strict
    2  usage / file error
"""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .findings import Severity
from .linter import lint_file

_MARK = {Severity.ERROR: "ERROR  ", Severity.WARNING: "WARNING", Severity.INFO: "INFO   "}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ossie-guard",
        description=(
            "Honesty & safety linter for Apache Ossie semantic models. "
            "Catches cross-dialect metric drift and impure/non-deterministic "
            "expressions that schema validation cannot see. Run it after "
            "Ossie's own validate.py."
        ),
    )
    parser.add_argument("model", help="path to an Ossie semantic-model YAML file")
    parser.add_argument(
        "--json", action="store_true", help="emit findings as a JSON array"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on warnings too (default: only errors fail)",
    )
    parser.add_argument(
        "--no-safety", action="store_true", help="skip the side-effecting-function check"
    )
    parser.add_argument(
        "--no-determinism", action="store_true", help="skip the non-determinism check"
    )
    parser.add_argument(
        "--no-drift", action="store_true", help="skip the cross-dialect drift check"
    )
    parser.add_argument(
        "--version", action="version", version=f"ossie-guard {__version__}"
    )
    return parser


def _print_human(model: str, findings: list) -> None:
    errors = sum(1 for f in findings if f.severity is Severity.ERROR)
    warnings = sum(1 for f in findings if f.severity is Severity.WARNING)
    infos = sum(1 for f in findings if f.severity is Severity.INFO)

    print(f"ossie-guard {__version__} - {model}\n")
    if not findings:
        print("  OK  no drift, safety, or determinism issues found\n")
        return

    for finding in findings:
        print(f"  {_MARK[finding.severity]}  {finding.code}  -  {finding.entity}")
        print(f"           {finding.message}")
        if finding.path:
            print(f"           at {finding.path}")
        print()

    parts = []
    if errors:
        parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
    if warnings:
        parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
    if infos:
        parts.append(f"{infos} info")
    print("  " + ", ".join(parts))


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        findings = lint_file(
            args.model,
            check_safety=not args.no_safety,
            check_determinism=not args.no_determinism,
            check_drift=not args.no_drift,
        )
    except FileNotFoundError:
        print(f"ossie-guard: no such file: {args.model}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - surface any load/parse error cleanly
        print(f"ossie-guard: could not lint {args.model}: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2, ensure_ascii=False))
    else:
        _print_human(args.model, findings)

    has_error = any(f.severity is Severity.ERROR for f in findings)
    if has_error or (args.strict and findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
