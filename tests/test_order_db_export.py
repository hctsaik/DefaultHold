from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from vai_hold.domain.smm_memo import wafer_number
from vai_hold.tools.export_order_sqlite import export_order_db

from harness import make_harness
from test_t01_t18 import _happy_until_hold


ROOT = Path(__file__).resolve().parents[1]


def test_c09_repeat_check_does_not_repeat_eval_or_incident_log(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    caplog.clear()
    h.check_ai()
    first = [
        r.getMessage()
        for r in caplog.records
        if "eval.cycle" in r.getMessage() or "incident.opened" in r.getMessage()
    ]
    caplog.clear()
    h.check_ai()
    second = [
        r.getMessage()
        for r in caplog.records
        if "eval.cycle" in r.getMessage() or "incident.opened" in r.getMessage()
    ]
    assert first, "first CHECK must record the C09 decision"
    assert second == [], f"repeat CHECK must not rewrite logs: {second}"


def test_export_order_sqlite_has_c09_error_and_dot_slot(tmp_path):
    db = export_order_db(tmp_path / "order_db.sqlite")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    c09 = conn.execute("SELECT * FROM hold_order WHERE lot_id='A123456'").fetchone()
    assert c09 is not None
    assert c09["work_state"] == "DEFECT_HOLD_UNCONFIRMED"
    assert c09["data_error"] == "NO_SMM_HOLD_AFTER_SCAN"
    assert c09["lifecycle"] == "OPEN"
    wafers = conn.execute(
        "SELECT wafer_id FROM order_wafer WHERE order_id=? ORDER BY wafer_id",
        (c09["order_id"],),
    ).fetchall()
    ids = [r["wafer_id"] for r in wafers]
    assert ids == ["A123456.01", "A123456.02", "A123456.03"]
    assert [wafer_number(w) for w in ids] == [1, 2, 3]
    flags = conn.execute(
        "SELECT wafer_id FROM order_wafer WHERE missing_alarm_type=1"
    ).fetchall()
    assert [r["wafer_id"] for r in flags] == ["A123457.03"]
    closed = conn.execute(
        "SELECT lot_id, close_reason FROM hold_order WHERE lifecycle='CLOSED' ORDER BY lot_id"
    ).fetchall()
    reasons = {r["lot_id"]: r["close_reason"] for r in closed}
    assert reasons["A123459"] == "AI_OK"
    assert reasons["A123460"] == "TRANSFERRED"
    manual = conn.execute(
        "SELECT close_reason FROM hold_order WHERE lot_id='A123461'"
    ).fetchone()
    assert manual["close_reason"] == "MANUAL"
    inc = conn.execute(
        "SELECT occurrence_count FROM incident WHERE lot_id='A123456' AND incident_type='DEFECT_HOLD_UNCONFIRMED'"
    ).fetchone()
    assert inc["occurrence_count"] == 1
    conn.close()


def test_write_shared_order_db_for_inspection():
    db = ROOT / "Design" / "generated" / "order_db.sqlite"
    export_order_db(db)
    assert db.exists()
    assert (ROOT / "Design" / "generated" / "ORDER_DB.md").exists()
