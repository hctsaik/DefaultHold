from __future__ import annotations

from vai_hold.domain.enums import AiState, BindingStatus, Lifecycle, ProtectionState, ReceiptOutcome, WorkState
from vai_hold.adapters.fake_world.world import default_flow_steps, FlowStep

from harness import Harness, make_harness


def _happy_until_hold(h: Harness, lot="LOT1", wafers=25):
    h.world.add_lot(lot, wafers=wafers)
    h.set_hold()
    h.confirm_hold()
    return h.order(lot)


def test_t01_happy_path_25_ok(h: Harness):
    order = _happy_until_hold(h)
    assert order.work_state == WorkState.WAIT_AI
    assert order.protection_state == ProtectionState.CONFIRMED
    h.world.complete_ai("LOT1")
    h.check_ai()
    order = h.order()
    assert order.work_state == WorkState.RELEASE_SENT
    h.confirm_release()
    order = h.order()
    assert order.lifecycle == Lifecycle.CLOSED
    assert order.close_reason == "AI_OK"
    assert h.world.release_calls
    assert all(c.memo != h.settings.hold_memo for c in h.world.release_calls)
    # did not close without verify
    assert order.last_rule_id == "A2-11"


def test_enhl_conflict_sends_othl_in_same_set_round(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = ["rejected_conflict", "accepted"]
    h.set_hold()
    assert [c.hold_code for c in h.world.set_hold_calls] == ["ENHL", "OTHL"]
    assert h.order().work_state == WorkState.HOLD_VERIFY_PENDING
    assert h.world.set_hold_calls[-1].hold_code == "OTHL"


def test_t02_enhl_conflict_othl_ok(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = ["rejected_conflict", "accepted"]
    h.set_hold()
    assert [c.hold_code for c in h.world.set_hold_calls] == ["ENHL", "OTHL"]
    h.confirm_hold()
    order = h.order()
    assert order.protection_state == ProtectionState.CONFIRMED
    cmds = h.commands()
    codes = [c.hold_code for c in cmds]
    assert "ENHL" in codes and "OTHL" in codes
    hist = h.history()
    assert any(a.normalized_error == "CODE_CONFLICT" for a in hist)
    assert order.work_state != WorkState.HOLD_FAILED


def test_incident_resolves_when_all_wafers_scanned(h: Harness):
    _happy_until_hold(h)
    h.clock.advance(minutes=31)
    h.defense()
    assert "HOLD_OVERDUE" in {i.incident_type for i in h.incidents()}
    h.world.complete_ai("LOT1")
    h.check_ai()
    assert "HOLD_OVERDUE" not in {i.incident_type for i in h.incidents()}


def test_skip_default_hold_when_smm_hold_already_at_station(h: Harness):
    h.world.add_lot("LOT1")
    h.world.add_defect_hold("LOT1", ope_no="OP200")
    h.set_hold()
    order = h.order()
    assert order is not None
    assert not h.world.set_hold_calls
    assert order.state_reason == "skip_default_hold_smm_present"
    assert order.work_state == WorkState.WAIT_AI


def test_t03_all_codes_fail():
    h = make_harness(extra_overrides={"hold": {"codes": ["ENHL", "OTHL", "HOLD3"]}})
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_conflict"
    h.set_hold()
    assert [c.hold_code for c in h.world.set_hold_calls] == ["ENHL", "OTHL", "HOLD3"]
    order = h.order()
    assert order.work_state == WorkState.HOLD_FAILED
    types = {i.incident_type for i in h.incidents()}
    assert "HOLD_FAILED" in types


def test_t04_timeout_but_hold_exists_no_resend(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    h.confirm_hold()
    order = h.order()
    assert order.protection_state == ProtectionState.CONFIRMED
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    assert h.world.set_hold_calls[0].hold_code == "ENHL"


def test_t05_timeout_still_unknown(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    h.world.list_status["LOT1"] = "unknown"
    h.confirm_hold()
    order = h.order()
    assert order.work_state in {WorkState.HOLD_VERIFY_PENDING, WorkState.OBSERVATION_UNKNOWN}
    assert order.work_state != WorkState.HOLD_FAILED
    assert order.protection_state.value in {"UNKNOWN", "SET_PENDING"}


def test_t06_restart_finds_existing_hold(h: Harness):
    h.world.add_lot("LOT1")
    h.set_hold()
    # crash after MES, before treating as confirmed: command in-flight
    order = h.order()
    assert order.work_state == WorkState.HOLD_VERIFY_PENDING
    h.confirm_hold()
    assert h.order().protection_state == ProtectionState.CONFIRMED
    assert len(h.world.set_hold_calls) == 1


def test_ai_query_unknown_is_not_empty_scan(h: Harness):
    _happy_until_hold(h)
    h.app.ai.unavailable_lots.add("LOT1")
    h.check_ai()
    order = h.order()
    assert order.work_state == WorkState.WAIT_AI
    assert order.ai_state == AiState.UNKNOWN
    assert not h.world.release_calls


def test_t09_one_wafer_missing(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", skip=["W25"])
    h.check_ai()
    order = h.order()
    assert order.work_state == WorkState.WAIT_AI
    assert not h.world.release_calls


def test_t10_count_equal_but_duplicate_and_missing(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", skip=["W25"], extra_duplicate="W01")
    h.check_ai()
    assert h.order().work_state == WorkState.WAIT_AI
    assert not h.world.release_calls


def test_t11_empty_roster(h: Harness):
    h.world.add_lot("LOT1", wafers=[])
    h.set_hold()
    h.confirm_hold()
    h.check_ai()
    assert h.order().work_state == WorkState.WAIT_AI
    assert not h.world.release_calls


def test_t12_completed_without_result(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", missing_result="W03")
    h.check_ai()
    assert h.order().work_state == WorkState.RELEASE_SENT
    assert h.world.release_calls
    with h.app.uow_factory.new() as uow:
        flags = [w for w in uow.wafers.list_by_order(h.order().order_id) if w.missing_alarm_type]
    assert [w.wafer_id for w in flags] == ["W03"]


def test_defect_no_smm_before_two_minutes_does_not_release(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.check_ai()
    order = h.order()
    assert order.work_state == WorkState.WAIT_AI
    assert order.data_error is None
    assert not h.world.release_calls
    assert "DEFECT_HOLD_UNCONFIRMED" not in {i.incident_type for i in h.incidents()}


def test_c09_after_two_minutes_releases_scan_completed(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.clock.advance(minutes=2)
    h.check_ai()
    order = h.order()
    assert order.work_state == WorkState.RELEASE_SENT
    assert order.close_reason == "SCAN_COMPLETED"
    assert order.data_error is None
    assert h.world.release_calls
    assert "DEFECT_HOLD_UNCONFIRMED" not in {i.incident_type for i in h.incidents()}


def test_wait_ai_set_pipeline_does_not_rewrite_order(h: Harness):
    order = _happy_until_hold(h)
    version = order.row_version
    sent = len(h.world.set_hold_calls)
    h.set_hold()
    h.set_hold()
    assert h.order().row_version == version
    assert len(h.world.set_hold_calls) == sent


def test_wait_ai_confirm_does_not_rewrite_order(h: Harness):
    order = _happy_until_hold(h)
    version = order.row_version
    h.confirm_hold()
    h.confirm_hold()
    assert h.order().row_version == version


def test_t13_rework_isolation(h: Harness):
    h.world.add_lot("LOT1", rework_count=0)
    h.set_hold()
    h.confirm_hold()
    h.world.complete_ai("LOT1", rework_count=0)
    h.world.add_lot("LOT1", rework_count=1, event_id="evt-rw1")
    h.set_hold()
    h.confirm_hold()
    o0 = h.order("LOT1", rw=0)
    o1 = h.order("LOT1", rw=1)
    assert o0 and o1 and o0.order_id != o1.order_id
    assert o1.work_state == WorkState.WAIT_AI
    # rw1 不得因為 rw0 的 AI 完成而被當成可解除
    h.check_ai()
    assert h.order("LOT1", rw=1).work_state != WorkState.RELEASE_VERIFY_PENDING
    assert h.order("LOT1", rw=1).lifecycle == Lifecycle.OPEN


def test_operation_start_from_inbound_event_not_clock_now(h: Harness):
    h.world.add_lot("LOT1")
    start = h.world.events[0].event_time
    h.clock.advance(minutes=5)
    h.set_hold()
    order = h.order()
    assert order.operation_start_at == start
    assert order.created_at != start


def test_next_process_step_smm_hold_is_after_current_not_after_default_hold():
    from vai_hold.adapters.fake_world.world import FlowStep

    steps = [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP150", "Etch", "PROCESS_TOOL", 1),
        FlowStep("OP200", "August", "METROLOGY", 2),
        FlowStep("OP500", "CMP", "PROCESS_TOOL", 3),
    ]
    h = make_harness(extra_overrides={"smm_hold": {"step": "NextProcessStep"}})
    h.world.add_lot("LOT1", steps=steps)
    h.set_hold()
    h.confirm_hold()
    h.world.complete_ai("LOT1", result="DEFECT")
    h.world.add_defect_hold("LOT1", ope_no="OP150")
    h.check_ai()
    # D04：只有 Default Hold 站（OP200）的 SMM Hold 算接手
    assert h.order().work_state == WorkState.WAIT_AI


def test_next_process_step_does_not_treat_hold_after_default_hold_as_smm():
    from vai_hold.adapters.fake_world.world import FlowStep

    steps = [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP150", "Etch", "PROCESS_TOOL", 1),
        FlowStep("OP200", "August", "METROLOGY", 2),
        FlowStep("OP500", "CMP", "PROCESS_TOOL", 3),
    ]
    h = make_harness(extra_overrides={"smm_hold": {"step": "NextProcessStep"}})
    h.world.add_lot("LOT1", steps=steps)
    h.set_hold()
    h.confirm_hold()
    h.world.complete_ai("LOT1", result="DEFECT")
    h.world.add_defect_hold("LOT1", ope_no="OP500")
    h.check_ai()
    assert h.order().work_state == WorkState.WAIT_AI


def test_wafer_based_smm_memo_transfer_accumulates_slots(h: Harness):
    from vai_hold.domain.smm_memo import mes_wafer_id

    lot = "A123456"
    wafers = [mes_wafer_id(lot, i) for i in range(1, 4)]
    h.world.add_lot(lot, wafers=wafers)
    h.set_hold()
    h.confirm_hold()
    h.world.scan_wafer(lot, wafers[0], result="DEFECT")
    h.world.add_defect_hold(lot, memo="Please check #1")
    h.check_ai()
    assert h.order(lot).work_state == WorkState.WAIT_AI
    assert h.world.transfer_calls == []
    h.world.scan_wafer(lot, wafers[1], result="DEFECT")
    h.check_ai()
    assert h.world.transfer_calls
    smm = [x for x in h.world.holds if x.hold_code == "SMMH"]
    assert smm and smm[0].memo == "Please check #1,#2"
    h.check_ai()
    assert smm[0].memo == "Please check #1,#2"
    assert h.order(lot).work_state == WorkState.WAIT_AI
    assert not h.world.release_calls


def test_retry_hold_uses_frozen_memo_not_new_settings(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_transient"
    h.set_hold()
    original = h.world.set_hold_calls[0].memo
    h.settings.hold_memo = "CHANGED MEMO SHOULD NOT BE SENT"
    h.set_hold()
    assert len(h.world.set_hold_calls) >= 2
    assert h.world.set_hold_calls[-1].memo == original
    assert h.world.set_hold_calls[-1].memo != "CHANGED MEMO SHOULD NOT BE SENT"
    assert h.world.set_hold_calls[-1].idempotency_key == h.world.set_hold_calls[0].idempotency_key


def test_set_hold_retries_same_command_at_most_three_times(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_transient"
    for _ in range(5):
        h.set_hold()
    assert len(h.world.set_hold_calls) == 3
    cmds = [c for c in h.commands() if c.action_type.value == "SET_HOLD"]
    assert len(cmds) == 1
    hist = h.history()
    assert max(a.attempt_no for a in hist) == 3
    assert h.order().work_state == WorkState.HOLD_FAILED


def test_timeout_not_found_retries_then_stops(h: Harness):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    h.confirm_hold()
    h.set_hold()
    h.confirm_hold()
    h.set_hold()
    h.confirm_hold()
    h.set_hold()
    assert len(h.world.set_hold_calls) == 3
    assert h.order().work_state == WorkState.HOLD_FAILED


def test_t14_defect_handoff_only_releases_preventive(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.world.add_defect_hold("LOT1")
    defect_before = [x for x in h.world.holds if x.hold_user == "AOA"]
    h.check_ai()
    h.confirm_release()
    assert h.order().lifecycle == Lifecycle.CLOSED
    assert h.order().close_reason == "TRANSFERRED"
    assert any(x.hold_user == "AOA" and x.hold_code == "SMMH" for x in h.world.holds)
    assert len([x for x in h.world.holds if x.hold_user == "AOA"]) == len(defect_before)


def test_t15_defect_without_formal_hold(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.check_ai()
    assert h.order().work_state == WorkState.WAIT_AI
    assert not h.world.release_calls


def test_t16_release_timeout_then_closed(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.world.release_response["LOT1"] = "timeout"
    h.check_ai()
    assert h.order().work_state == WorkState.RELEASE_SENT
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    h.confirm_release()
    assert h.order().lifecycle == Lifecycle.CLOSED


def test_t17_release_rejected_hold_remains(h: Harness):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.world.release_response["LOT1"] = "rejected_permission"
    h.check_ai()
    h.confirm_release()
    order = h.order()
    assert order.work_state == WorkState.RELEASE_FAILED
    assert order.lifecycle == Lifecycle.OPEN
    assert any(i.incident_type == "RELEASE_FAILED" for i in h.incidents())


def test_t18_foreign_enhl_not_ours(h: Harness):
    h.world.add_lot("LOT1")
    h.world.add_foreign_hold("LOT1", hold_code="ENHL", memo="SOME OTHER MEMO", ope_no="OP200")
    h.set_hold()
    h.confirm_hold()
    order = h.order()
    assert order.protection_state == ProtectionState.CONFIRMED
    assert len(h.world.set_hold_calls) == 1
    assert h.world.set_hold_calls[0].hold_code == "ENHL"
    assert not h.world.release_calls
    memos = [x.memo for x in h.world.holds if x.hold_code == "ENHL"]
    assert "SOME OTHER MEMO" in memos
    assert h.settings.hold_memo in memos


def test_t18b_foreign_enhl_our_enhl_conflict_then_othl(h: Harness):
    h.world.add_lot("LOT1")
    h.world.add_foreign_hold("LOT1", hold_code="ENHL", memo="SOME OTHER MEMO", ope_no="OP200")
    h.world.set_response["LOT1"] = ["rejected_conflict", "accepted"]
    h.set_hold()
    h.confirm_hold()
    assert h.order().protection_state == ProtectionState.CONFIRMED
    assert [c.hold_code for c in h.world.set_hold_calls] == ["ENHL", "OTHL"]
    assert not h.world.release_calls
    assert any(x.memo == "SOME OTHER MEMO" for x in h.world.holds)
