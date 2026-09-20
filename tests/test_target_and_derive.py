from __future__ import annotations

from datetime import datetime, timezone

from vai_hold.domain.enums import HoldKind, SourceStatus
from vai_hold.domain.models import FlowStep, FlowView, SourceResult
from vai_hold.domain.target import choose_hold_target, next_process_step


def _flow(current: str, steps: list[FlowStep] | None = None) -> SourceResult:
    steps = steps or [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP200", "August", "METROLOGY", 1),
        FlowStep("OP300", "Overlay", "METROLOGY", 2),
        FlowStep("OP400", "CDSEM", "METROLOGY", 3),
    ]
    return SourceResult(
        status=SourceStatus.FOUND,
        value=FlowView("RT1", "v1", current, steps),
        observed_at=datetime.now(timezone.utc),
    )


def test_t21_all_config_passed_holds_current():
    t = choose_hold_target(_flow("OP400"), station_priority=["August", "Overlay", "CDSEM"])
    assert t and t.ope_no == "OP400" and t.kind == HoldKind.CURRENT


def test_t22_skip_passed_high_priority():
    t = choose_hold_target(_flow("OP300"), station_priority=["August", "Overlay", "CDSEM"])
    assert t and t.ope_no == "OP300" and t.kind == HoldKind.CURRENT


def test_t22_future_lower_priority():
    t = choose_hold_target(_flow("OP100"), station_priority=["August", "Overlay", "CDSEM"])
    assert t and t.ope_no == "OP200" and t.kind == HoldKind.FUTURE


def test_t23_no_config_uses_process_tool():
    steps = [
        FlowStep("OP100", "Etch", "PROCESS_TOOL", 0),
        FlowStep("OP150", "Clean", "PROCESS_TOOL", 1),
    ]
    t = choose_hold_target(_flow("OP100", steps), station_priority=["August"])
    assert t and t.ope_no == "OP100" and t.reason == "first_process_tool"


def test_next_process_step_excludes_current():
    steps = [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP200", "August", "METROLOGY", 1),
        FlowStep("OP500", "Etch", "PROCESS_TOOL", 2),
    ]
    flow = FlowView("RT1", "v1", "OP100", steps)
    nxt = next_process_step(flow)
    assert nxt and nxt.ope_no == "OP500"


def test_next_process_step_from_current_not_from_default_hold():
    """OP150 is after OP100; OP500 is after Default Hold OP200. Must pick OP150."""
    from vai_hold.domain.target import smm_hold_ope_no

    steps = [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP150", "Etch", "PROCESS_TOOL", 1),
        FlowStep("OP200", "August", "METROLOGY", 2),
        FlowStep("OP500", "CMP", "PROCESS_TOOL", 3),
    ]
    flow = FlowView("RT1", "v1", "OP100", steps)
    nxt = next_process_step(flow)
    assert nxt and nxt.ope_no == "OP150"
    assert smm_hold_ope_no(flow, "OP200", "NextProcessStep") == "OP150"
    assert smm_hold_ope_no(flow, "OP200", "DefaultHoldStep") == "OP200"


def test_next_process_step_none_when_no_later_process_tool():
    steps = [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP200", "August", "METROLOGY", 1),
    ]
    flow = FlowView("RT1", "v1", "OP100", steps)
    assert next_process_step(flow) is None


def test_smm_memo_accumulates_slots():
    from vai_hold.domain.smm_memo import (
        format_smm_memo,
        memo_needs_transfer,
        parse_smm_slots,
    )

    assert parse_smm_slots("Please check #1") == [1]
    assert parse_smm_slots("Please check #1,#2") == [1, 2]
    assert format_smm_memo("Please check {slots}", [1, 2]) == "Please check #1,#2"
    assert memo_needs_transfer("Please check #1", [1, 2])
    assert not memo_needs_transfer("Please check #1,#2", [1, 2])
    assert not memo_needs_transfer("SMM AI DEFECT HOLD", [1, 2])


def test_defect_slots_use_wafer_number_not_roster_index():
    from vai_hold.domain.models import WaferAiView
    from vai_hold.domain.smm_memo import defect_slots, mes_wafer_id, wafer_number

    assert wafer_number("W03") == 3
    assert wafer_number("A123456.01") == 1
    assert wafer_number("A123456.12") == 12
    assert mes_wafer_id("A123456", 1) == "A123456.01"
    now = datetime.now(timezone.utc)
    views = [
        WaferAiView("W03", scan_completed_at=now, result="DEFECT", rework_count=0),
    ]
    assert defect_slots(["W03", "W05"], views, rework_count=0) == [3]
    mes_views = [
        WaferAiView("A123456.01", scan_completed_at=now, result="DEFECT", rework_count=0),
    ]
    assert defect_slots(["A123456.01", "A123456.02"], mes_views, rework_count=0) == [1]


def test_unknown_flow_is_not_no_config():
    r = SourceResult(status=SourceStatus.UNKNOWN, value=None)
    assert choose_hold_target(r, station_priority=["August"]) is None
