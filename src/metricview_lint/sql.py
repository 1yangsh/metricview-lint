"""Light-weight lexical helpers for Databricks SQL expressions.

The linter never parses SQL fully; it only needs a few reliable signals
(which functions are called, what MEASURE() references, which qualifiers are
used). String literals and comments are blanked out first so their contents
never produce false matches.
"""

from __future__ import annotations

import re

_LITERALS = re.compile(
    r"""'(?:[^'\\]|\\.|'')*'      # single-quoted string
      | "(?:[^"\\]|\\.|"")*"      # double-quoted string (Spark SQL default)
      | --[^\n]*                  # line comment
      | /\*.*?\*/                 # block comment
    """,
    re.VERBOSE | re.DOTALL,
)


def strip_literals(expr: str) -> str:
    """Blank out string literals and comments, keeping backtick identifiers."""
    return _LITERALS.sub(lambda m: "''" if m.group(0)[0] in "'\"" else " ", expr)


_CALL = re.compile(r"(?<![\w.`])([A-Za-z_][A-Za-z0-9_]*)\s*\(")


def function_calls(expr: str) -> set[str]:
    """Lower-cased names of every function called in `expr`."""
    return {m.group(1).lower() for m in _CALL.finditer(strip_literals(expr))}


# Aggregate functions in Databricks SQL. MEASURE() counts as one: it
# re-aggregates an existing measure.
AGGREGATES = frozenset(
    [
        "any",
        "any_value",
        "approx_count_distinct",
        "approx_percentile",
        "approx_top_k",
        "array_agg",
        "avg",
        "bit_and",
        "bit_or",
        "bit_xor",
        "bitmap_construct_agg",
        "bitmap_or_agg",
        "bool_and",
        "bool_or",
        "collect_list",
        "collect_set",
        "corr",
        "count",
        "count_if",
        "count_min_sketch",
        "covar_pop",
        "covar_samp",
        "every",
        "first",
        "first_value",
        "histogram_numeric",
        "hll_sketch_agg",
        "hll_union_agg",
        "kurtosis",
        "last",
        "last_value",
        "listagg",
        "max",
        "max_by",
        "mean",
        "measure",
        "median",
        "min",
        "min_by",
        "mode",
        "percentile",
        "percentile_approx",
        "percentile_cont",
        "percentile_disc",
        "product",
        "regr_avgx",
        "regr_avgy",
        "regr_count",
        "regr_intercept",
        "regr_r2",
        "regr_slope",
        "regr_sxx",
        "regr_sxy",
        "regr_syy",
        "skewness",
        "some",
        "std",
        "stddev",
        "stddev_pop",
        "stddev_samp",
        "string_agg",
        "sum",
        "try_avg",
        "try_sum",
        "var_pop",
        "var_samp",
        "variance",
        "kll_sketch_agg_bigint",
        "kll_sketch_agg_double",
        "kll_sketch_agg_float",
        "theta_sketch_agg",
        "theta_union_agg",
        "theta_intersection_agg",
    ]
)

# Functions whose result depends on who runs the query; they block materialization.
INVOKER_DEPENDENT = frozenset(
    [
        "current_user",
        "user",
        "session_user",
        "current_groups",
        "is_member",
        "is_account_group_member",
        "current_recipient",
    ]
)

NON_DETERMINISTIC = frozenset(
    [
        "rand",
        "randn",
        "random",
        "uuid",
        "shuffle",
        "current_timestamp",
        "current_date",
        "now",
        "localtimestamp",
        "getdate",
        "curdate",
    ]
)

_MEASURE_REF = re.compile(r"\bMEASURE\s*\(\s*(`(?:[^`]|``)+`|[A-Za-z_][\w.]*)\s*\)", re.I)


def measure_refs(expr: str) -> list[str]:
    """Names passed to MEASURE(...), with backticks removed (may be `source.x` qualified)."""
    out = []
    for m in _MEASURE_REF.finditer(strip_literals(expr)):
        raw = m.group(1)
        out.append(raw[1:-1].replace("``", "`") if raw.startswith("`") else raw)
    return out


_OVER = re.compile(r"\)\s*OVER\s*(\(|[A-Za-z_])", re.I)


def has_window_function(expr: str) -> bool:
    return bool(_OVER.search(strip_literals(expr)))


_IDENT = r"(?:`(?:[^`]|``)+`|[A-Za-z_][A-Za-z0-9_]*)"
_QUALIFIED = re.compile(rf"(?<![\w.`])({_IDENT}(?:\s*\.\s*{_IDENT})+)")


def qualified_refs(expr: str) -> list[list[str]]:
    """Dotted references such as `source.col` or `customer.nation.n_name`, split into parts."""
    out = []
    for m in _QUALIFIED.finditer(strip_literals(expr)):
        parts = [p.strip() for p in re.findall(_IDENT, m.group(1))]
        out.append([p[1:-1] if p.startswith("`") else p for p in parts])
    return out


_AGG_ARG = re.compile(
    r"(?<![\w.`])([A-Za-z_]\w*)\s*\(\s*(?:DISTINCT\s+)?(`(?:[^`]|``)+`|[A-Za-z_]\w*)\s*\)", re.I
)


def aggregated_identifiers(expr: str) -> list[tuple[str, str]]:
    """(function, identifier) pairs for calls like SUM(`Total revenue`) or AVG(x)."""
    out = []
    for m in _AGG_ARG.finditer(strip_literals(expr)):
        fn, arg = m.group(1).lower(), m.group(2)
        if fn in AGGREGATES and fn != "measure":
            out.append((fn, arg[1:-1] if arg.startswith("`") else arg))
    return out


def is_wildcard(expr: object) -> bool:
    """`source.*`, `customer.*`, `x.* EXCEPT (a, b)` or `struct_col.*`."""
    return isinstance(expr, str) and bool(
        re.match(
            rf"^\s*{_IDENT}(\s*\.\s*{_IDENT})*\s*\.\s*\*(\s+EXCEPT\s*\(.*\))?\s*$",
            expr,
            re.I | re.S,
        )
    )
