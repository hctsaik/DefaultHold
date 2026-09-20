"""Keep one SQLite Order DB per catalog scenario (Oracle rehearsal artifacts)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vai_hold.adapters.persistence.sqlite.scenario_catalog import SqliteScenarioCatalog
from vai_hold.application.scenario_runner import run_catalog
from vai_hold.tools.seed_scenario_catalog import seed_cases, seed_catalog

ROOT = Path(__file__).resolve().parents[3]
CATALOG_DB = ROOT / "Design" / "generated" / "scenario_catalog.sqlite"
ORDERS_ROOT = ROOT / "Design" / "generated" / "scenario_orders"
STAGE = ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11")


def order_db_path(orders_root: Path, scenario_id: str) -> Path:
    return Path(orders_root) / scenario_id / "order.db"


def persist_catalog_sqlite(
    *, orders_root: Path | None = None, catalog_db: Path | None = None
) -> tuple[list, Path, Path]:
    orders_root = Path(orders_root) if orders_root else ORDERS_ROOT
    catalog_db = Path(catalog_db) if catalog_db else CATALOG_DB
    orders_root.mkdir(parents=True, exist_ok=True)
    catalog_db.parent.mkdir(parents=True, exist_ok=True)
    cat = SqliteScenarioCatalog(catalog_db)
    seed_catalog(cat)
    results = run_catalog(cat, tmp_path=orders_root, backend="sqlite")
    from vai_hold.adapters.persistence.schema_sync import install_investigation_views

    for r in results:
        db = order_db_path(orders_root, r.scenario_id)
        if db.is_file():
            install_investigation_views(db)
    write_index(orders_root, results, cat)
    return results, catalog_db, orders_root


def write_index(orders_root: Path, results, catalog) -> Path:
    enabled = {c.scenario_id for c in catalog.list_enabled()}
    disabled = [c for c in catalog.list_all() if not c.enabled]
    rows = []
    for r in results:
        db = order_db_path(orders_root, r.scenario_id)
        ok = "通過" if r.passed else "失敗"
        html = f"Design/generated/evidence/{r.scenario_id}.html"
        rows.append(
            f"| `{r.scenario_id}` | {r.title} | {ok} | `{db.as_posix()}` | `{html}` |"
        )
    disabled_rows = "\n".join(
        f"| `{c.scenario_id}` | {c.title} | 題庫關掉，不算驗收 |" for c in disabled
    ) or "| （無） | | |"
    md = ORDERS_ROOT.parent / "SCENARIO_ORDERS.md"
    if orders_root.resolve() == ORDERS_ROOT.resolve():
        out = md
    else:
        out = Path(orders_root) / "INDEX.md"
    failed = [r.scenario_id for r in results if not r.passed]
    missing_db = [
        r.scenario_id for r in results if not order_db_path(orders_root, r.scenario_id).is_file()
    ]
    out.write_text(
        f"""# 每一題的 SQLite Order DB

現場仍是 MOCK。Order DB 是 SQLite（Oracle 彩排）。每題一個檔，互不覆蓋。

- 題庫／是否通過：`Design/generated/scenario_catalog.sqlite` 的 `scenario_run`
- 本目錄：`{orders_root.as_posix()}`
- 啟用 {len(enabled)} 題，通過 {len(results) - len(failed)}，失敗 {len(failed) or 0}
- 缺檔：{', '.join(missing_db) or '無'}

未跑（enabled=0）：

{disabled_rows}

| ID | 情境 | 結果 | Order DB | HTML |
|---|---|---|---|---|
{chr(10).join(rows)}

題庫 `scenario_catalog.sqlite` **沒有** hold_order。查 C09 請開該題 `order.db`：

```sql
SELECT * FROM v_order_errors;
SELECT * FROM v_wafer_flags;
SELECT * FROM v_open_incidents;
SELECT lot_id, work_state, data_error, lifecycle FROM hold_order;
```
""",
        encoding="utf-8",
    )
    return out


def verify_persisted(results, orders_root: Path, catalog) -> list[str]:
    """Return human-readable problems. Empty = meets rehearsal bar."""
    problems: list[str] = []
    enabled = catalog.list_enabled()
    enabled_ids = [c.scenario_id for c in enabled]
    got = [r.scenario_id for r in results]
    if got != enabled_ids:
        problems.append(f"ran {got} != enabled {enabled_ids}")
    seed_enabled = [c.scenario_id for c in seed_cases() if c.enabled]
    if set(enabled_ids) != set(seed_enabled):
        problems.append(f"catalog enabled {enabled_ids} != seed {seed_enabled}")
    failed = [r for r in results if not r.passed]
    if failed:
        problems.append("failed: " + ", ".join(f"{r.scenario_id}:{r.diffs}" for r in failed))
    for sid in STAGE:
        if sid not in got:
            problems.append(f"missing stage {sid}")
    c09 = next((r for r in results if r.scenario_id == "C09"), None)
    if c09 is None:
        problems.append("C09 not run")
    elif c09.actual.get("close_reason") != "SCAN_COMPLETED":
        problems.append(f"C09 close_reason={c09.actual.get('close_reason')!r}")
    for r in results:
        db = order_db_path(orders_root, r.scenario_id)
        if not db.is_file():
            problems.append(f"{r.scenario_id} missing {db}")
            continue
        conn = sqlite3.connect(db)
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "hold_order" not in tables:
                problems.append(f"{r.scenario_id} {db} has no hold_order")
            cols = [row[1] for row in conn.execute("PRAGMA table_info(hold_order)")]
            if "data_error" not in cols:
                problems.append(f"{r.scenario_id} hold_order missing data_error")
            if r.scenario_id == "C09":
                row = conn.execute("SELECT close_reason, work_state, data_error FROM hold_order").fetchone()
                if not row or row[0] != "SCAN_COMPLETED":
                    problems.append(f"C09 sqlite close_reason={row!r}")
                if not row or row[1] != "RELEASE_SENT":
                    problems.append(f"C09 sqlite work_state={row!r}")
                if row and row[2]:
                    problems.append(f"C09 sqlite data_error should be empty: {row[2]!r}")
        finally:
            conn.close()
    disabled = {c.scenario_id for c in catalog.list_all() if not c.enabled}
    if "T25" not in disabled:
        problems.append("T25 should stay disabled")
    return problems
