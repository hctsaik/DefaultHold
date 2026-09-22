"""SQLite is the Oracle rehearsal: same tables, columns, uniques. No Python ALTER."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from vai_hold.domain.errors import SchemaError

ROOT = Path(__file__).resolve().parents[4]
SQLITE_SCHEMA = ROOT / "Design" / "schema" / "sqlite.sql"
ORACLE_SCHEMA = ROOT / "Design" / "schema" / "oracle.sql"

_SKIP_COL = frozenset({"constraint", "primary", "unique", "check", "foreign"})
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLE_HEAD = re.compile(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)\s*\(", re.I)
_INDEX = re.compile(
    r"CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+ON\s+(\w+)\s*\(([^)]+)\)",
    re.I,
)
_UNIQUE_INLINE = re.compile(r"\bUNIQUE\s*\(([^)]+)\)", re.I)


def _table_bodies(sql: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _TABLE_HEAD.finditer(sql):
        name = m.group(1).lower()
        start = m.end()
        depth = 1
        i = start
        while i < len(sql) and depth:
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
            i += 1
        out[name] = sql[start : i - 1]
    return out


def parse_columns(sql: str) -> dict[str, list[str]]:
    tables: dict[str, list[str]] = {}
    for name, body in _table_bodies(sql).items():
        cols: list[str] = []
        for raw in body.splitlines():
            line = raw.split("--", 1)[0].strip().rstrip(",")
            if not line:
                continue
            first = line.split()[0]
            if not _IDENT.match(first) or first.lower() in _SKIP_COL:
                continue
            cols.append(first.lower())
        tables[name] = cols
    return tables


def parse_indexes(sql: str) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """name -> (table, unique|index, columns)."""
    out: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for m in _INDEX.finditer(sql):
        unique = "unique" if m.group(1) else "index"
        name = m.group(2).lower()
        table = m.group(3).lower()
        cols = tuple(c.strip().lower() for c in m.group(4).split(",") if c.strip())
        out[name] = (table, unique, cols)
    return out


def parse_uniques(sql: str) -> dict[str, set[tuple[str, ...]]]:
    """table -> set of unique column tuples (table UNIQUE + unique indexes)."""
    found: dict[str, set[tuple[str, ...]]] = {}
    for table, body in _table_bodies(sql).items():
        keys: set[tuple[str, ...]] = set()
        for m in _UNIQUE_INLINE.finditer(body):
            cols = tuple(c.strip().lower() for c in m.group(1).split(",") if c.strip())
            if cols:
                keys.add(cols)
        found[table] = keys
    for _name, (table, kind, cols) in parse_indexes(sql).items():
        if kind == "unique" and cols:
            found.setdefault(table, set()).add(cols)
    return found


# SQLite 才有：正式 Oracle 重用 MV_NXT_PARAM_BT，不建 agent_control。
SQLITE_ONLY_TABLES = frozenset({"agent_control"})
# 正式 Oracle 表名 → SQLite 短名（比欄位時對齊）
ORACLE_TO_SQLITE_TABLE = {
    "mv_nxt_def_hold_order_bt": "hold_order",
    "mv_nxt_def_hold_incident_bt": "incident",
}


def _sqlite_table_name(oracle_or_sqlite: str) -> str:
    return ORACLE_TO_SQLITE_TABLE.get(oracle_or_sqlite, oracle_or_sqlite)


def dual_ddl_diffs(sqlite_sql: str | None = None, oracle_sql: str | None = None) -> list[str]:
    sqlite_sql = sqlite_sql if sqlite_sql is not None else SQLITE_SCHEMA.read_text(encoding="utf-8")
    oracle_sql = oracle_sql if oracle_sql is not None else ORACLE_SCHEMA.read_text(encoding="utf-8")
    s_cols = parse_columns(sqlite_sql)
    o_raw = parse_columns(oracle_sql)
    o_cols = {_sqlite_table_name(k): v for k, v in o_raw.items()}
    diffs: list[str] = []
    s_tables = set(s_cols) - SQLITE_ONLY_TABLES
    o_tables = set(o_cols)
    if s_tables != o_tables:
        diffs.append(f"tables sqlite-only={sorted(s_tables - o_tables)} oracle-only={sorted(o_tables - s_tables)}")
    for table in sorted(set(s_cols) & set(o_cols)):
        if s_cols[table] != o_cols[table]:
            diffs.append(f"{table} columns sqlite={s_cols[table]} oracle={o_cols[table]}")
    s_idx = {k: v for k, v in parse_indexes(sqlite_sql).items() if v[0] not in SQLITE_ONLY_TABLES}
    o_idx = {
        k: (_sqlite_table_name(tbl), kind, cols)
        for k, (tbl, kind, cols) in parse_indexes(oracle_sql).items()
    }
    if set(s_idx) != set(o_idx):
        diffs.append(
            f"indexes sqlite-only={sorted(set(s_idx) - set(o_idx))} oracle-only={sorted(set(o_idx) - set(s_idx))}"
        )
    for name in sorted(set(s_idx) & set(o_idx)):
        if s_idx[name] != o_idx[name]:
            diffs.append(f"index {name} sqlite={s_idx[name]} oracle={o_idx[name]}")
    s_uq = {k: v for k, v in parse_uniques(sqlite_sql).items() if k not in SQLITE_ONLY_TABLES}
    o_uq = {_sqlite_table_name(k): v for k, v in parse_uniques(oracle_sql).items()}
    for table in sorted(set(s_uq) | set(o_uq)):
        if s_uq.get(table, set()) != o_uq.get(table, set()):
            diffs.append(f"{table} unique sqlite={sorted(s_uq.get(table, set()))} oracle={sorted(o_uq.get(table, set()))}")
    return diffs


INVESTIGATION_VIEWS_SQL = """
CREATE VIEW IF NOT EXISTS v_order_overview AS
SELECT
    lot_id,
    origin_operation_id AS ope_no,
    rework_count,
    lifecycle,
    work_state,
    data_error,
    close_reason,
    last_rule_id,
    state_reason,
    target_hold_operation_id,
    operation_start_at,
    last_evaluated_at
FROM hold_order
ORDER BY lot_id;

CREATE VIEW IF NOT EXISTS v_order_errors AS
SELECT lot_id, work_state, data_error, last_rule_id, lifecycle, state_reason
FROM hold_order
WHERE data_error IS NOT NULL
   OR work_state IN ('HOLD_FAILED', 'RELEASE_FAILED', 'OBSERVATION_UNKNOWN', 'STATE_CONFLICT');

CREATE VIEW IF NOT EXISTS v_wafer_flags AS
SELECT
    o.lot_id,
    json_extract(j.value, '$.wafer_id') AS wafer_id,
    json_extract(j.value, '$.ai_result') AS ai_result,
    json_extract(j.value, '$.scan_completed_at') AS scan_completed_at
FROM hold_order o, json_each(o.wafers_json) j
WHERE json_extract(j.value, '$.ai_result') = 'DEFECT'
ORDER BY o.lot_id, wafer_id;

CREATE VIEW IF NOT EXISTS v_open_incidents AS
SELECT incident_type, status, lot_id, order_id, reason, occurrence_count, first_seen_at
FROM incident
WHERE status = 'OPEN'
ORDER BY lot_id, incident_type;
"""


def install_investigation_views(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(INVESTIGATION_VIEWS_SQL)
    conn.commit()
    conn.close()


def require_sqlite_schema(conn: sqlite3.Connection) -> None:
    """Fail if the file was created from an old DDL. Do not ALTER to paper over it."""
    expected = parse_columns(SQLITE_SCHEMA.read_text(encoding="utf-8"))
    for table, cols in expected.items():
        actual = [str(r[1]).lower() for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if not actual:
            raise SchemaError(
                f"SQLite missing table {table}. Recreate the DB from Design/schema/sqlite.sql "
                "(SQLite is the Oracle rehearsal; do not ALTER in Python)."
            )
        missing = [c for c in cols if c not in actual]
        if missing:
            raise SchemaError(
                f"SQLite {table} missing columns {missing}. "
                "Change Design/schema/sqlite.sql AND oracle.sql together, then recreate the DB. "
                "Do not ALTER TABLE in Python."
            )
