"""The `query_data` MCP tool: structured queries over vault data files (CSV/JSON).

Read-only. `find` discovers a dataset (via its markdown "dataset card");
`query_data` pulls exact rows / aggregates from the raw CSV/JSON the card points
at — filter by column / value / date-range, project columns, sort, paginate, or
aggregate (count / min / max / sum / avg / latest / distinct). KB datasets are
small, so the file is read into memory per call — no index, no new infra
(consistent with the "no vector DB needed at this scale" ethos).

Supports:
- CSV / TSV (header row → columns).
- JSON: a top-level array of objects, OR a nested array located via
  `record_path` (dotted, e.g. "sections.work_incapacity") or common-key
  auto-detect ("result"/"results"/"data"/"rows"/"items"/"entries").
- Dotted column names for nested JSON fields (e.g. "performer.name",
  "id.extension") everywhere a column is named — filters, columns, sort,
  aggregate.

Numeric comparisons coerce tolerantly (Estonian decimal comma "," → ".";
leading lab operators like "<0.4"/">75" are stripped for the comparison).
Date filters (`date_from`/`date_to`) compare ISO date strings lexicographically.
Deeply irregular JSON may still want a one-time flatten-to-CSV first; flat
tables are the sweet spot.
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .vault import VaultPathError, resolve_under_vault


log = logging.getLogger(__name__)

ALLOWED_SUFFIXES = (".csv", ".tsv", ".json")
MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB guard — KB datasets are small
HARD_ROW_CAP = 1000
DEFAULT_LIMIT = 100
_COMMON_RECORD_KEYS = ("result", "results", "data", "rows", "items", "entries")
_OPS = frozenset({
    "eq", "ne", "gt", "gte", "lt", "lte",
    "contains", "icontains", "startswith", "in", "nin", "exists", "missing",
})
_NUM_PREFIX = re.compile(r"^[<>≤≥=~\s]+")
_DATE_LIKE = re.compile(r"\d{1,4}[-/]\d")        # 2024-07, 9/2024 → not a number
_LEADING_NUM = re.compile(r"[+-]?\d+(?:[.,]\d+)?")  # leading number, comma or dot decimal


@dataclass
class QueryDataError(Exception):
    code: str
    reason: str

    def as_dict(self) -> dict:
        return {"code": self.code, "reason": self.reason}


@dataclass
class QueryDataResult:
    path: str
    format: str
    total_rows: int       # rows in the dataset
    total_matched: int    # rows matching the filters (before limit/offset)
    returned: int
    columns: list[str]
    rows: list[dict]
    aggregate: Any = None
    truncated: bool = False
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "format": self.format,
            "total_rows": self.total_rows,
            "total_matched": self.total_matched,
            "returned": self.returned,
            "columns": self.columns,
            "rows": self.rows,
            "aggregate": self.aggregate,
            "truncated": self.truncated,
            "warnings": self.warnings,
        }


def _get_field(row: Any, dotted: str) -> Any:
    """Nested access via dotted key — dicts by key, lists by integer index."""
    cur = row
    for part in str(dotted).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def _coerce_num(v: Any) -> float | None:
    """Best-effort numeric coercion; tolerant of comma decimals and lab operators."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = _NUM_PREFIX.sub("", v.strip())
    if not s or _DATE_LIKE.match(s):
        return None
    m = _LEADING_NUM.match(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def _locate_array(data: Any, record_path: str | None, warnings: list[str]) -> list:
    if record_path:
        located = _get_field(data, record_path) if isinstance(data, (dict, list)) else None
        if not isinstance(located, list):
            raise QueryDataError(
                "BAD_RECORD_PATH",
                f"record_path {record_path!r} did not resolve to a JSON array",
            )
        return located
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in _COMMON_RECORD_KEYS:
            if isinstance(data.get(k), list):
                warnings.append(f"auto-detected record array at top-level key {k!r}")
                return data[k]
        warnings.append("JSON root is an object with no obvious array; treated as a single row")
        return [data]
    raise QueryDataError("BAD_JSON", "JSON root is neither an array nor an object")


def _infer_columns(rows: list[dict]) -> list[str]:
    cols: list[str] = []
    seen: set[str] = set()
    for r in rows[:500]:
        if isinstance(r, dict):
            for k in r:
                if k not in seen:
                    seen.add(k)
                    cols.append(k)
    return cols


def _load_rows(abs_path: Path, record_path: str | None) -> tuple[str, list[dict], list[str], list[str]]:
    suffix = abs_path.suffix.lower()
    size = abs_path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise QueryDataError(
            "TOO_LARGE",
            f"file is {size} bytes (> {MAX_FILE_BYTES} limit); pre-split or filter upstream",
        )
    warnings: list[str] = []
    if suffix in (".csv", ".tsv"):
        delimiter = "\t" if suffix == ".tsv" else ","
        with abs_path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            rows = [dict(r) for r in reader]
            cols = list(reader.fieldnames or [])
        return ("tsv" if suffix == ".tsv" else "csv"), rows, cols, warnings
    if suffix == ".json":
        try:
            data = json.loads(abs_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise QueryDataError("BAD_JSON", f"could not parse JSON: {e}") from None
        arr = _locate_array(data, record_path, warnings)
        rows = [r if isinstance(r, dict) else {"value": r} for r in arr]
        return "json", rows, _infer_columns(rows), warnings
    raise QueryDataError("UNSUPPORTED_FORMAT", f"only {list(ALLOWED_SUFFIXES)} supported, got {suffix!r}")


def _match(row: dict, filt: dict) -> bool:
    col = filt["column"]
    op = filt.get("op", "eq")
    val = filt.get("value")
    actual = _get_field(row, col)

    if op == "exists":
        return actual not in (None, "")
    if op == "missing":
        return actual in (None, "")
    if op in ("in", "nin"):
        vals = val if isinstance(val, list) else [val]
        hit = str(actual) in {str(x) for x in vals}
        return hit if op == "in" else not hit
    if op in ("contains", "icontains", "startswith"):
        a = "" if actual is None else str(actual)
        b = "" if val is None else str(val)
        if op == "contains":
            return b in a
        if op == "icontains":
            return b.lower() in a.lower()
        return a.lower().startswith(b.lower())

    # eq / ne / gt / gte / lt / lte — numeric when both coerce; string otherwise.
    an, bn = _coerce_num(actual), _coerce_num(val)
    both_num = an is not None and bn is not None

    if op in ("eq", "ne"):
        if both_num:
            a, b = an, bn
        else:
            a = "" if actual is None else str(actual)
            b = "" if val is None else str(val)
        return (a == b) if op == "eq" else (a != b)

    # Ordering (gt/gte/lt/lte): compare numerically when both coerce, or as
    # strings when NEITHER does (e.g. ISO dates). If exactly one side is
    # numeric the values aren't comparable — exclude the row rather than fall
    # back to a misleading lexicographic compare (e.g. "100,2 nmol/l" < 50).
    if both_num:
        a, b = an, bn
    elif an is None and bn is None:
        a = "" if actual is None else str(actual)
        b = "" if val is None else str(val)
    else:
        return False
    if op == "gt":
        return a > b
    if op == "gte":
        return a >= b
    if op == "lt":
        return a < b
    if op == "lte":
        return a <= b
    raise QueryDataError("BAD_OP", f"unknown filter op {op!r}; allowed: {sorted(_OPS)}")


def _aggregate(matched: list[dict], spec: str, date_col: str | None) -> dict:
    spec = spec.strip()
    if spec == "count":
        return {"count": len(matched)}
    if ":" not in spec:
        raise QueryDataError(
            "BAD_AGGREGATE",
            "aggregate must be 'count' or 'func:column' (func in min,max,sum,avg,latest,distinct)",
        )
    func, col = (p.strip() for p in spec.split(":", 1))
    if func == "distinct":
        out: list[Any] = []
        seen: set[str] = set()
        for r in matched:
            v = _get_field(r, col)
            key = json.dumps(v, sort_keys=True, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
            if key not in seen:
                seen.add(key)
                out.append(v)
        return {"distinct": out, "n": len(out)}
    if func == "latest":
        order_col = date_col or col
        best, best_key = None, None
        for r in matched:
            k = _get_field(r, order_col)
            if k is None:
                continue
            if best_key is None or str(k) > str(best_key):
                best_key, best = k, r
        return {"latest_by": order_col, "row": best}
    if func in ("min", "max", "sum", "avg"):
        nums = [n for r in matched if (n := _coerce_num(_get_field(r, col))) is not None]
        if not nums:
            return {func: None, "n": 0, "note": f"no numeric values in {col!r}"}
        value = {
            "min": min(nums), "max": max(nums),
            "sum": sum(nums), "avg": sum(nums) / len(nums),
        }[func]
        return {func: value, "n": len(nums)}
    raise QueryDataError("BAD_AGGREGATE", f"unknown aggregate func {func!r}")


def query_data(
    vault_root: Path,
    *,
    path: str,
    record_path: str | None = None,
    filters: list[dict] | None = None,
    columns: list[str] | None = None,
    sort_by: str | None = None,
    descending: bool = False,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    aggregate: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    date_column: str | None = None,
) -> QueryDataResult:
    """Query a CSV/JSON data file under the vault. See module docstring."""
    try:
        abs_path, rel = resolve_under_vault(vault_root, path, must_exist=True, must_be_file=True)
    except VaultPathError as e:
        raise QueryDataError(e.code, e.reason) from None
    if abs_path.suffix.lower() not in ALLOWED_SUFFIXES:
        raise QueryDataError("UNSUPPORTED_FORMAT", f"only {list(ALLOWED_SUFFIXES)} supported")

    fmt, rows, cols, warnings = _load_rows(abs_path, record_path)
    total_rows = len(rows)

    flt: list[dict] = []
    for f0 in filters or []:
        if not isinstance(f0, dict) or not f0.get("column"):
            raise QueryDataError("BAD_FILTER", f"each filter needs a 'column': {f0!r}")
        if f0.get("op", "eq") not in _OPS:
            raise QueryDataError("BAD_OP", f"unknown op {f0.get('op')!r}; allowed: {sorted(_OPS)}")
        flt.append(f0)

    date_col = date_column or ("date" if "date" in cols else None)
    if (date_from or date_to) and not date_col:
        warnings.append("date_from/date_to ignored: no date column found (pass date_column=)")
    if date_col and date_from:
        flt.append({"column": date_col, "op": "gte", "value": date_from})
    if date_col and date_to:
        flt.append({"column": date_col, "op": "lte", "value": date_to})

    matched = [r for r in rows if all(_match(r, f) for f in flt)]
    total_matched = len(matched)

    if aggregate:
        return QueryDataResult(
            path=rel, format=fmt, total_rows=total_rows, total_matched=total_matched,
            returned=0, columns=cols, rows=[],
            aggregate=_aggregate(matched, aggregate, date_col),
            truncated=False, warnings=warnings,
        )

    if sort_by:
        def _key(r: dict):
            v = _get_field(r, sort_by)
            n = _coerce_num(v)
            return (0, n, "") if n is not None else (1, 0.0, "" if v is None else str(v))
        matched.sort(key=_key, reverse=descending)

    limit = max(0, min(int(limit), HARD_ROW_CAP))
    offset = max(0, int(offset))
    window = matched[offset: offset + limit] if limit else matched[offset:]
    truncated = (offset + len(window)) < total_matched

    if columns:
        out_rows = [{c: _get_field(r, c) for c in columns} for r in window]
        out_cols = list(columns)
    else:
        out_rows = window
        out_cols = cols

    return QueryDataResult(
        path=rel, format=fmt, total_rows=total_rows, total_matched=total_matched,
        returned=len(out_rows), columns=out_cols, rows=out_rows,
        aggregate=None, truncated=truncated, warnings=warnings,
    )
