"""Expression purity: a metric definition should be a pure, reproducible read.

Two honesty problems a schema validator (which only asks "does this parse?")
cannot see:

* **Side-effecting functions** -- a scalar expression that reads a server file,
  opens an outbound socket, runs a shell, or re-enters the executor. A metric
  should never do this; if it can, "this is just a read-only measure" is false.
  The denylist and the lexical net are ported from the sibling project
  `readonly-sql-guard` (https://github.com/gulmezeren2-byte/readonly-sql-guard),
  which exists to make exactly this guarantee measurable. Reported as ERROR.

* **Non-deterministic functions** -- `NOW()`, `RANDOM()`, `CURRENT_DATE`,
  `UUID()` and friends. They parse fine and they are read-only, but they make
  the metric non-reproducible: the same model run twice returns different
  numbers. That is a measurement-honesty red flag worth surfacing, though it can
  be intentional ("revenue as of today"), so it is a WARNING, not an ERROR.
"""

from __future__ import annotations

import re

from sqlglot import expressions as exp

# --- side-effecting functions (ported from readonly-sql-guard) --------------
_DANGEROUS_FUNCS = frozenset(
    {
        # PostgreSQL - server-side file I/O and large objects
        "pg_read_file", "pg_read_binary_file", "pg_stat_file", "pg_ls_dir",
        "pg_ls_logdir", "pg_ls_waldir", "pg_ls_tmpdir", "pg_ls_archive_statusdir",
        "lo_import", "lo_export", "lo_get", "lo_put", "lo_from_bytea", "lo_unlink",
        # PostgreSQL - outbound connections (SSRF / exfiltration)
        "dblink", "dblink_exec", "dblink_connect", "dblink_connect_u",
        "dblink_send_query", "dblink_open", "dblink_fetch",
        # PostgreSQL - re-enters the executor, or edits the session
        "query_to_xml", "query_to_xmlschema", "query_to_xml_and_xmlschema",
        "set_config", "pg_reload_conf", "pg_rotate_logfile", "pg_logical_emit_message",
        "pg_terminate_backend", "pg_cancel_backend",
        "pg_sleep", "pg_sleep_for", "pg_sleep_until",
        # MSSQL - ad-hoc remote/bulk sources, shell, registry, trace files
        "openrowset", "opendatasource", "openquery", "openxml",
        "xp_cmdshell", "xp_dirtree", "xp_fileexist", "xp_subdirs", "xp_regread",
        "xp_regwrite", "xp_regdeletekey", "xp_regdeletevalue", "xp_regenumvalues",
        "sp_executesql", "sp_oacreate", "sp_oamethod", "sp_configure",
        "fn_trace_gettable", "fn_get_audit_file", "fn_xe_file_target_read_file",
        # MySQL / MariaDB - file reads, UDF shells, and unbounded time sinks
        "load_file", "sys_exec", "sys_eval", "benchmark", "sleep",
        # SQLite - loading an extension is arbitrary code execution
        "load_extension", "readfile", "writefile", "edit", "fts3_tokenizer",
    }
)

# Lexical net for the same names, requiring a "(" so a column called "sleep" is
# untouched. This also catches OPENROWSET, which sqlglot cannot parse at all.
_DANGEROUS_LEXICAL = re.compile(
    r"\b(" + "|".join(sorted(_DANGEROUS_FUNCS)) + r")\s*\(", re.IGNORECASE
)

# --- non-deterministic functions --------------------------------------------
# Called with parens and usually parsed by sqlglot as an Anonymous function.
_NONDET_CALL = frozenset(
    {
        "now", "getdate", "getutcdate", "sysdatetime", "sysutcdatetime",
        "rand", "random", "uuid", "uuid_string", "gen_random_uuid", "newid",
        "sys_guid", "clock_timestamp", "statement_timestamp", "transaction_timestamp",
        "timeofday", "unix_timestamp", "current_database", "current_catalog",
        "current_schema", "session_user",
    }
)
# Valid without parens (SQL keyword form), so they parse as a bare identifier.
_NONDET_BARE = frozenset({"sysdate", "systimestamp"})
# sqlglot node classes that are inherently non-deterministic.
_NONDET_NODE_LABEL = {
    "CurrentTimestamp": "current_timestamp",
    "CurrentDate": "current_date",
    "CurrentTime": "current_time",
    "CurrentDatetime": "current_datetime",
    "CurrentUser": "current_user",
    "Rand": "random",
    "Uuid": "uuid",
}
_NONDET_NODES = tuple(
    getattr(exp, name) for name in _NONDET_NODE_LABEL if hasattr(exp, name)
)


def _func_name(node) -> str:
    if isinstance(node, exp.Anonymous):
        return (node.name or "").lower()
    return type(node).__name__.lower()


def dangerous_hits(tree, raw_expr: str) -> "set[str]":
    """Names of side-effecting functions the expression calls. `tree` may be
    None (unparseable) -- the lexical net still runs on the raw text, which is
    the point: the input that defeats the parser is often the payload."""
    hits: set[str] = set()
    if tree is not None:
        for func in tree.find_all(exp.Func):
            name = _func_name(func)
            if name in _DANGEROUS_FUNCS:
                hits.add(name)
    for match in _DANGEROUS_LEXICAL.finditer(raw_expr or ""):
        hits.add(match.group(1).lower())
    return hits


def nondeterministic_hits(tree) -> "set[str]":
    """Names of non-deterministic constructs in a parsed expression."""
    hits: set[str] = set()
    if tree is None:
        return hits
    if _NONDET_NODES:
        for node in tree.find_all(_NONDET_NODES):
            hits.add(_NONDET_NODE_LABEL[type(node).__name__])
    for func in tree.find_all(exp.Anonymous):
        name = (func.name or "").lower()
        if name in _NONDET_CALL:
            hits.add(name)
    for col in tree.find_all(exp.Column):
        if col.name and col.name.lower() in _NONDET_BARE:
            hits.add(col.name.lower())
    return hits
