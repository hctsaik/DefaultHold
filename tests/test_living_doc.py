from __future__ import annotations

import logging
from pathlib import Path

from vai_hold.decision_tree import DERIVE_LEAVES, mermaid_full_tree
from vai_hold.investigate import mermaid_derive_path, parse_records, render_case, required_fields_ok
from vai_hold.locator import build_locator, first_loc
from harness import make_harness
from test_t01_t18 import _happy_until_hold

ROOT = Path(__file__).resolve().parents[1]


def test_locator_finds_core_rules():
    loc = build_locator()
    assert first_loc(loc, "A1-03")
    assert "derive.py" in first_loc(loc, "A1-03")
    assert first_loc(loc, "A2-02")
    assert "verify_hold.py" in first_loc(loc, "A2-02")


def test_full_tree_contains_all_derive_leaves():
    text = mermaid_full_tree()
    assert "flowchart TB" in text
    for rule, reason, _ in DERIVE_LEAVES:
        assert rule in text
        assert reason.replace("-", "_") in text or reason in text


def test_golden_tree_matches_generator():
    golden = (ROOT / "Design" / "generated" / "decision_tree.mmd").read_text(encoding="utf-8")
    assert golden == mermaid_full_tree(), "tree drifted; run `python -m vai_hold gen-tree` to update the checked-in file"


def test_t01_render_case_has_path_and_locator(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.check_ai()
    h.confirm_release()
    recs = parse_records(caplog.text)
    for r in recs:
        if r.get("event") == "decision.applied":
            miss = required_fields_ok(r)
            assert not miss, miss
    md = render_case(caplog.text, "LOT1")
    assert "```mermaid" in md
    assert "flowchart" in md
    assert "OBSERVED" in md
    assert "STATE" in md
    assert "DECISION" in md
    assert "rule_id" in md
    assert "verify_hold.py" in md
    assert "derive.py" in md
    last = [r for r in recs if r.get("event") == "decision.applied"][-1]
    spine = mermaid_derive_path(last)
    assert last.get("rule_id") in spine or last.get("reason") in spine
    evals = [r for r in recs if r.get("event") == "eval.cycle"]
    assert evals, "program must print eval.cycle with observed/state/decision"
    ev = evals[-1]
    assert ev.get("observed") and ev.get("state") and ev.get("decision")
    assert "rule_id" in ev["decision"]
    lot = ev["observed"].get("Lot") or {}
    assert lot.get("LotId") == "LOT1"
    assert lot.get("OpeNo")
    assert lot.get("RecTime")
    assert lot.get("OperationStartTime")
    # RecTime 必須跟模擬世界同一天，不可用主機牆鐘
    assert str(lot["RecTime"]).startswith("2026-01-01")
    assert "FirstWaferId" not in lot
    st = ev["state"]
    if st.get("expected_count") == 25 and st.get("ai_gate") in {None, "WAITING", "EMPTY"}:
        assert st.get("missing_count") in {25, 0} or st.get("missing_count") >= 0
    mes = ev["observed"].get("DefaultHold") or {}
    assert "Holds" in mes
    assert mes.get("QueryStatus") in {"FOUND", "NOT_FOUND", "UNKNOWN", "STALE"}
    assert "SmmHold" in ev["observed"]
    flow = ev["observed"].get("Flow") or {}
    assert "MainPdId" in flow
    assert "Status" not in flow
    assert "FlowVersion" not in flow
    assert "CurrentToolId" not in flow
    check_evals = [r for r in evals if r.get("function_code") == "CHECK_AI_SCAN_COMPLETE"]
    assert check_evals, "CHECK_AI must print eval.cycle with AiScan"
    ai = (check_evals[-1].get("observed") or {}).get("AiScan") or {}
    assert ai.get("QueryStatus") in {"FOUND", "NOT_FOUND", "UNKNOWN", "STALE"}
    assert "ExpectedCount" in ai
    assert "ScannedCount" in ai
    assert "LatestScanTime" in ai
    assert "RecTime" in ai
    assert "Scans" not in ai
    set_evals = [r for r in evals if r.get("function_code") == "SET_DEFAULT_HOLD_BY_Operation_Start"]
    assert set_evals
    set_obs = set_evals[-1].get("observed") or {}
    assert "AiScan" not in set_obs
    set_holds = (set_obs.get("DefaultHold") or {}).get("Holds") or []
    assert any(row.get("HoldCode") == "ENHL" for row in set_holds), "EVAL after write must show the Hold just set"
    assert "FirstWaferId" not in (set_obs.get("Lot") or {})
    assert "missing_count" not in (set_evals[-1].get("state") or {})
    odb = ev["observed"].get("OrderDb") or {}
    assert "RemainingHoldCodes" not in odb
    assert odb.get("Lifecycle")
    assert odb.get("WorkState")
    assert odb.get("ProtectionState")
    assert odb.get("AiState")
    oid = odb.get("OrderId") or ""
    assert oid.count("-") >= 2
    assert "EQP01" in oid or oid.endswith("-NA")
    fh = (ev["observed"].get("DefaultHold") or {}).get("Holds") or []
    for row in fh:
        assert "ToolId" not in row
        assert "OpeName" in row
    for b in odb.get("Bindings") or []:
        assert "BackupHoldOrder" in b
        assert "Generation" not in b
        assert "RequestedAt" in b
        assert b.get("TimeQuality") == "ESTIMATED"
        assert "MesCreatedAt" not in b
        assert "RequestStatus" not in b
    assert "ours_hold_count" in ev["state"] or "hold_present" in ev["state"]
    assert "missing_count" in ev["state"]
