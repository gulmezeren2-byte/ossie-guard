"""Command-line interface: `ossie-guard <model.yaml>`.

Output formats:
    text   human-readable report (default)
    json   a JSON array of findings
    sarif  SARIF 2.1.0 for GitHub code-scanning (upload with upload-sarif)

Exit codes:
    0  no errors (warnings allowed unless --strict); always 0 under --exit-zero
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
from .sarif import to_sarif

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
    parser.add_argument(
        "models",
        nargs="+",
        metavar="model",
        help="path(s) to Ossie semantic-model YAML file(s)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "sarif"],
        default="text",
        help="output format (default: text)",
    )
    parser.add_argument(
        "--json", action="store_true", help="shorthand for --format json"
    )
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="shorthand for --format sarif (SARIF 2.1.0 for GitHub code-scanning)",
    )
    parser.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        help="write output to FILE instead of stdout",
    )
    parser.add_argument(
        "--fail-level",
        choices=["error", "warning", "note", "none"],
        help="minimum severity that makes the run fail "
        "(error=default; warning=--strict; none=--exit-zero)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="shorthand for --fail-level warning",
    )
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="shorthand for --fail-level none (generate SARIF without failing)",
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


def _resolve_format(args) -> str:
    if args.sarif:
        return "sarif"
    if args.json:
        return "json"
    return args.format


def _resolve_fail_level(args) -> str:
    if args.fail_level:
        return args.fail_level
    if args.exit_zero:
        return "none"
    if args.strict:
        return "warning"
    return "error"


_FAIL_SEVERITIES = {
    "error": {Severity.ERROR},
    "warning": {Severity.ERROR, Severity.WARNING},
    "note": {Severity.ERROR, Severity.WARNING, Severity.INFO},
    "none": set(),
}


def _render_human(file_findings) -> str:
    lines = []
    for model, findings in file_findings:
        lines.append(f"ossie-guard {__version__} - {model}\n")
        if not findings:
            lines.append("  OK  no drift, safety, or determinism issues found\n")
            continue
        for finding in findings:
            location = f"{model}:{finding.line}" if finding.line else finding.path
            lines.append(f"  {_MARK[finding.severity]}  {finding.code}  -  {finding.entity}")
            lines.append(f"           {finding.message}")
            if location:
                lines.append(f"           at {location}")
            lines.append("")
        counts = [
            (Severity.ERROR, "error"),
            (Severity.WARNING, "warning"),
            (Severity.INFO, "info"),
        ]
        parts = []
        for severity, label in counts:
            n = sum(1 for f in findings if f.severity is severity)
            if n:
                parts.append(f"{n} {label}" + ("s" if n != 1 and label != "info" else ""))
        lines.append("  " + ", ".join(parts) + "\n")
    return "\n".join(lines).rstrip()


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    output = _resolve_format(args)

    file_findings = []
    load_error = False
    for model in args.models:
        try:
            findings = lint_file(
                model,
                check_safety=not args.no_safety,
                check_determinism=not args.no_determinism,
                check_drift=not args.no_drift,
            )
        except FileNotFoundError:
            print(f"ossie-guard: no such file: {model}", file=sys.stderr)
            load_error = True
            continue
        except Exception as exc:  # noqa: BLE001 - surface any load/parse error cleanly
            print(f"ossie-guard: could not lint {model}: {exc}", file=sys.stderr)
            load_error = True
            continue
        file_findings.append((model, findings))

    if output == "sarif":
        doc = to_sarif(file_findings, tool_version=__version__)
        text = json.dumps(doc, indent=2, ensure_ascii=False)
    elif output == "json":
        flat = []
        for model, findings in file_findings:
            for finding in findings:
                record = finding.to_dict()
                record["file"] = model
                flat.append(record)
        text = json.dumps(flat, indent=2, ensure_ascii=False)
    else:
        text = _render_human(file_findings)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    else:
        print(text)

    # A missing/unreadable file is a usage error regardless of --fail-level.
    if load_error:
        return 2
    fail_on = _FAIL_SEVERITIES[_resolve_fail_level(args)]
    all_findings = [f for _, findings in file_findings for f in findings]
    if any(f.severity in fail_on for f in all_findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
