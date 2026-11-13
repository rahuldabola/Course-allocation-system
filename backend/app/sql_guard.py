"""Validation for LLM-generated SQL.

The assistant only ever executes SQL that passes `prepare_select`, which parses
the query into an AST (sqlglot) and enforces, structurally rather than with
keyword regexes:

  * exactly one statement, and it is a SELECT / set operation (UNION …);
  * no SELECT … INTO and no row locks (FOR UPDATE / FOR SHARE);
  * every table referenced is one of the application tables (or a CTE defined
    in the query) — so no pg_catalog / information_schema reads;
  * every function called is on an allowlist — so no pg_read_file(),
    pg_sleep(), set_config(), dblink(), query_to_xml(), lo_import() and the like.

The SQL that runs is re-generated from the validated AST, not the raw model
output, so parser differentials (comments, odd quoting) can't smuggle anything
past the checks. Execution adds two more layers on Postgres: a READ ONLY
transaction and a statement timeout (see app/ai_assistant.py).
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

ALLOWED_TABLES = frozenset(
    {"categories", "students", "courses", "course_quotas", "preferences", "allocations"}
)

# Function names as reported by sqlglot: `sql_name()` for functions it models,
# the literal (upper-cased) name for ones it doesn't (exp.Anonymous).
ALLOWED_FUNCTIONS = frozenset(
    {
        # aggregates
        "COUNT",
        "COUNT_IF",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "ARRAY_AGG",
        "GROUP_CONCAT",
        "STRING_AGG",
        "STDDEV",
        "STDDEV_POP",
        "STDDEV_SAMP",
        "VARIANCE",
        "VARIANCE_POP",
        "VAR_POP",
        "VAR_SAMP",
        "PERCENTILE_CONT",
        "PERCENTILE_DISC",
        "MEDIAN",
        "MODE",
        "BOOL_AND",
        "BOOL_OR",
        "LOGICAL_AND",
        "LOGICAL_OR",
        "ANY_VALUE",
        # window
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "PERCENT_RANK",
        "CUME_DIST",
        "NTILE",
        "LAG",
        "LEAD",
        "FIRST_VALUE",
        "LAST_VALUE",
        "NTH_VALUE",
        # conditional / casting
        "CASE",
        "IF",
        "COALESCE",
        "NULLIF",
        "GREATEST",
        "LEAST",
        "CAST",
        "TRY_CAST",
        # math
        "ROUND",
        "ABS",
        "FLOOR",
        "CEIL",
        "CEILING",
        "TRUNC",
        "POW",
        "POWER",
        "SQRT",
        "MOD",
        "SIGN",
        "DIV",
        "SAFE_DIVIDE",
        # text
        "LOWER",
        "UPPER",
        "LENGTH",
        "CHAR_LENGTH",
        "TRIM",
        "LTRIM",
        "RTRIM",
        "CONCAT",
        "CONCAT_WS",
        "SUBSTRING",
        "SUBSTR",
        "LEFT",
        "RIGHT",
        "REPLACE",
        "INITCAP",
        "STRPOS",
        "POSITION",
        "SPLIT_PART",
        "LPAD",
        "RPAD",
        "REVERSE",
        # dates
        "EXTRACT",
        "DATE_PART",
        "DATE_TRUNC",
        "TIMESTAMP_TRUNC",
        "AGE",
        "CURRENT_DATE",
        "CURRENT_TIMESTAMP",
        "NOW",
        "TO_CHAR",
        "DATE",
        "DATEDIFF",
        "DATE_DIFF",
        "TS_OR_DS_TO_DATE",
        "STR_TO_TIME",
        "TIME_TO_STR",
    }
)


# sqlglot models some operators (AND, OR, EXISTS, ~, @>…) as Func subclasses.
# Operators resolve to fixed built-ins, not arbitrary server functions, so
# they're exempt from the function allowlist; their operands are still checked.
_OPERATOR_TYPES = (exp.Binary, exp.Connector, exp.Predicate, exp.Unary)


class UnsafeSQLError(ValueError):
    """Raised when a query fails validation; the message says why."""


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).upper()
    return node.sql_name().upper()


def prepare_select(sql: str, *, dialect: str = "postgres", target: str | None = None) -> str:
    """Validate `sql` (written in `dialect`) and return it re-rendered for `target`.

    Raises UnsafeSQLError if the query is not a single, read-only SELECT over
    the application tables using only allowlisted functions.
    """
    if not sql or not sql.strip():
        raise UnsafeSQLError("empty query")
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except SqlglotError as e:
        raise UnsafeSQLError(f"could not parse SQL: {e.__class__.__name__}") from None

    if len(statements) != 1:
        raise UnsafeSQLError("exactly one statement is allowed")
    root = statements[0]
    if not isinstance(root, exp.Query):
        raise UnsafeSQLError(f"only SELECT queries are allowed (got {root.key.upper()})")

    for select in root.find_all(exp.Select):
        if select.args.get("into"):
            raise UnsafeSQLError("SELECT … INTO is not allowed")
        if select.args.get("locks"):
            raise UnsafeSQLError("row locking clauses are not allowed")

    # Anything that isn't a query node must not appear anywhere in the tree.
    forbidden = (exp.DML, exp.DDL, exp.Command, exp.Set, exp.Pragma, exp.Transaction)
    for node in root.walk():
        if isinstance(node, forbidden):
            raise UnsafeSQLError(f"{node.key.upper()} is not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        name = str(table.name).lower()
        schema = str(table.db).lower()
        if schema and schema != "public":
            raise UnsafeSQLError(f"schema '{schema}' is not allowed")
        if not name:
            raise UnsafeSQLError("table-valued functions are not allowed")
        if name not in ALLOWED_TABLES and not (name in cte_names and not schema):
            raise UnsafeSQLError(f"table '{name}' is not allowed")

    for func in root.find_all(exp.Func):
        if isinstance(func, _OPERATOR_TYPES):
            continue
        name = _function_name(func)
        if name not in ALLOWED_FUNCTIONS:
            raise UnsafeSQLError(f"function '{name.lower()}' is not allowed")

    return root.sql(dialect=target or dialect)
