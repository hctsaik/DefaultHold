from __future__ import annotations

from pathlib import Path

from vai_hold.adapters.persistence.sqlite.scenario_catalog import SqliteScenarioCatalog
from vai_hold.application.scenario_runner import run_catalog
from vai_hold.tools.seed_scenario_catalog import seed_catalog, seed_cases


def test_catalog_seed_roundtrip(tmp_path):
    db = tmp_path / "catalog.sqlite"
    cat = SqliteScenarioCatalog(db)
    n = seed_catalog(cat)
    assert n == len(seed_cases())
    assert cat.get("T01") is not None
    assert cat.get("HOLD_RETRY3") is not None
    assert cat.get("XFER_ACCUM") is not None


def test_all_catalog_scenarios_match_expected_facts(tmp_path):
    db = tmp_path / "catalog.sqlite"
    cat = SqliteScenarioCatalog(db)
    seed_catalog(cat)
    results = run_catalog(cat, tmp_path=tmp_path)
    failed = [r for r in results if not r.passed]
    msg = "\n".join(f"{r.scenario_id} {r.title}: " + "; ".join(r.diffs) for r in failed)
    assert not failed, msg
    assert len(results) == len(cat.list_enabled())
    assert len(results) >= 40


def test_all_catalog_scenarios_on_sqlite_order_db(tmp_path):
    """Order DB 用 SQLite（Oracle 彩排），現場仍是 MOCK。每題獨立一個 DB 檔。"""
    db = tmp_path / "catalog.sqlite"
    cat = SqliteScenarioCatalog(db)
    seed_catalog(cat)
    results = run_catalog(cat, tmp_path=tmp_path / "orders", backend="sqlite")
    failed = [r for r in results if not r.passed]
    msg = "\n".join(f"{r.scenario_id} {r.title}: " + "; ".join(r.diffs) for r in failed)
    assert not failed, msg
    by_id = {r.scenario_id: r for r in results}
    for sid in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11"):
        assert sid in by_id, sid
        assert by_id[sid].passed, sid
    assert by_id["C09"].actual.get("close_reason") == "SCAN_COMPLETED"
    assert by_id["C09"].actual.get("work_state") == "RELEASE_SENT"



