"""Build an inspectable Order DB (SQLite) with realistic MES wafer ids.

Lots are unique (A123456…). Wafer id is ``{lot}.{slot:02d}`` e.g. A123456.01.
Open with: sqlite3 Design/generated/order_db.sqlite
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_DB = ROOT / "Design" / "generated" / "order_db.sqlite"
OUT_MD = ROOT / "Design" / "generated" / "ORDER_DB.md"

# 情境庫 MOCK 的現場零點，與 scenario_runner 同一天
from vai_hold.application.scenario_runner import SCENARIO_T0
from vai_hold.domain.smm_memo import mes_wafer_id, wafer_number


def _harness(path: Path):
    tests = ROOT / "tests"
    if str(tests) not in sys.path:
        sys.path.insert(0, str(tests))
    from harness import Harness
    from vai_hold.adapters.fake_world.world import FakeWorld
    from vai_hold.application.ports.clock import ManualClock
    from vai_hold.application.settings import load_settings
    from vai_hold.composition.bootstrap import build_app

    clock = ManualClock()
    clock.set(SCENARIO_T0)
    settings = load_settings(
        overrides={
            "runtime": {"mode": "DEV"},
            "persistence": {"backend": "sqlite", "sqlite_path": str(path)},
            "smm_exception_defense": {"notify": {"emails": ["lit.onduty@example.com"]}},
        }
    )
    world = FakeWorld(clock=clock)
    app = build_app(settings=settings, world=world, clock=clock)
    return Harness(app=app, world=world, clock=clock, settings=settings)


def _wafers(lot: str, n: int) -> list[str]:
    return [mes_wafer_id(lot, i) for i in range(1, n + 1)]


def export_order_db(path: Path | None = None) -> Path:
    path = Path(path) if path else OUT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    h = _harness(path)

    # --- 六張單，各一個現場故事；wafer id = A123456.01 ---
    lots = {
        "A123456": 3,  # C09 Defect 無 SMM Hold
        "A123457": 3,  # T12 有掃完時間、無 Alarm Type
        "A123458": 3,  # C03 還沒掃完
        "A123459": 3,  # C06 全 OK 結案
        "A123460": 3,  # C11 Defect + SMM Hold 交接
        "A123461": 3,  # C08 線上把 Default Hold 解掉
    }
    for lot, n in lots.items():
        h.world.add_lot(lot, wafers=_wafers(lot, n))

    h.set_hold()
    h.confirm_hold()

    # C08 必須在還是 WAIT_AI、Hold 被線上解掉時跑 CONFIRM；不能先 Release 再假裝結案。
    h.world.holds = [
        x
        for x in h.world.holds
        if not (x.lot_id == "A123461" and x.hold_user == h.settings.hold_user)
    ]
    h.confirm_hold()

    h.world.complete_ai("A123456", result="DEFECT")
    h.world.complete_ai("A123457", missing_result=mes_wafer_id("A123457", 3))
    h.world.complete_ai("A123458", skip=[mes_wafer_id("A123458", 3)])
    h.world.complete_ai("A123459")
    h.world.complete_ai("A123460")
    h.world.scan_wafer("A123460", mes_wafer_id("A123460", 1), result="DEFECT")
    h.world.add_defect_hold("A123460", memo="Please check #1")
    h.clock.advance(minutes=2)

    h.check_ai()
    h.confirm_release()

    _add_views(path)
    _write_readme(path, OUT_MD if path == OUT_DB else path.with_suffix(".md"))
    return path


def _add_views(path: Path) -> None:
    from vai_hold.adapters.persistence.schema_sync import install_investigation_views

    install_investigation_views(path)


def _write_readme(db: Path, md: Path) -> None:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    orders = conn.execute("SELECT * FROM v_order_overview").fetchall()
    wafers = conn.execute(
        "SELECT o.lot_id, w.wafer_id, w.ai_result "
        "FROM order_wafer w JOIN hold_order o ON o.order_id=w.order_id "
        "ORDER BY o.lot_id, w.wafer_id"
    ).fetchall()
    incs = conn.execute("SELECT * FROM v_open_incidents").fetchall()
    conn.close()

    def tbl(headers: list[str], rows: list[list[str]]) -> str:
        line = "| " + " | ".join(headers) + " |"
        sep = "| " + " | ".join("---" for _ in headers) + " |"
        body = "\n".join("| " + " | ".join(r) + " |" for r in rows)
        return "\n".join([line, sep, body]) if rows else "（空）"

    order_rows = [
        [
            r["lot_id"],
            r["work_state"] or "",
            r["data_error"] or "",
            r["lifecycle"] or "",
            r["close_reason"] or "",
            r["last_rule_id"] or "",
        ]
        for r in orders
    ]
    wafer_rows = [
        [
            r["lot_id"],
            r["wafer_id"],
            str(wafer_number(r["wafer_id"]) or ""),
            r["ai_result"] or "",
        ]
        for r in wafers
    ]
    inc_rows = [
        [r["lot_id"] or "", r["incident_type"], r["status"], r["reason"] or "", str(r["occurrence_count"])]
        for r in incs
    ]
    md.write_text(
        f"""# Order DB 樣本（給人看的）

檔案：`{db.as_posix()}`

Wafer id 是現場格式 `A123456.01`；片號是小數點後面的 `01` → memo `#1`。

| Lot | 故事 | 你該看到 |
|---|---|---|
| A123456 | C09 掃完 Defect、已滿 settle | 申請解除；`close_reason=SCAN_COMPLETED` |
| A123457 | T12 `.03` 有 ScanCompletedTime | 當掃完；滿 settle 可解 |
| A123458 | C03 還缺一片 | `WAIT_AI`，沒 Release |
| A123459 | 全 OK 且滿 settle | `CLOSED` / `SCAN_COMPLETED` |
| A123460 | Defect + 現場 SMM Hold | `CLOSED` / `SCAN_COMPLETED`；SMM Hold 未動 |
| A123461 | 線上把 Default Hold 解掉 | `MANUAL_CLOSED`（沒有結案 GUI，Hold 沒了就結案） |

## hold_order

{tbl(["lot_id", "work_state", "data_error", "lifecycle", "close_reason", "last_rule_id"], order_rows)}

## order_wafer（含 parse 出的片號）

{tbl(["lot_id", "wafer_id", "slot#", "ai_result"], wafer_rows)}

## 還開著的 incident

{tbl(["lot_id", "type", "status", "reason", "count"], inc_rows)}

## 建議 SQL

```sql
SELECT lot_id, work_state, data_error, lifecycle, close_reason FROM v_order_overview;
SELECT * FROM v_order_errors;
SELECT * FROM v_wafer_flags;
SELECT * FROM v_open_incidents;
SELECT lot_id, wafer_id, ai_result, scan_completed_at FROM order_wafer ORDER BY lot_id, wafer_id;
```
""",
        encoding="utf-8",
    )


if __name__ == "__main__":
    out = export_order_db()
    print(out)
