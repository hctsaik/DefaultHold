from __future__ import annotations

from vai_hold.domain.enums import Lifecycle, WorkState

from harness import make_harness
from test_t01_t18 import _happy_until_hold


def test_set_hold_transient_same_command_three_attempts_only(h):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_transient"
    for _ in range(5):
        h.set_hold()
    assert len(h.world.set_hold_calls) == 3
    cmds = [c for c in h.commands() if c.action_type.value == "SET_HOLD"]
    assert len(cmds) == 1
    nos = sorted(a.attempt_no for a in h.history() if a.command_id == cmds[0].command_id)
    assert nos == [1, 2, 3]
    assert h.order().work_state == WorkState.HOLD_FAILED


def test_set_hold_timeout_verify_then_retry_three(h):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    for _ in range(4):
        h.set_hold()
        h.confirm_hold()
    assert len(h.world.set_hold_calls) == 3
    assert h.order().work_state == WorkState.HOLD_FAILED


def test_hold_query_unknown_does_not_retry_send(h):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    h.world.list_status["LOT1"] = "unknown"
    h.confirm_hold()
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    assert h.order().work_state != WorkState.HOLD_FAILED


def test_release_transient_same_command_three_attempts_only(h):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.world.release_response["LOT1"] = "rejected_transient"
    for _ in range(5):
        h.check_ai()
        h.confirm_release()
    assert len(h.world.release_calls) == 3
    rel = [c for c in h.commands() if c.action_type.value == "SET_RELEASE"]
    assert len(rel) == 1
    nos = sorted(a.attempt_no for a in h.history() if a.command_id == rel[0].command_id)
    assert nos == [1, 2, 3]
    assert h.order().lifecycle != Lifecycle.CLOSED
    assert h.order().work_state == WorkState.RELEASE_FAILED


def test_release_timeout_hold_still_visible_is_delay_not_retry(h):
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.world.release_response["LOT1"] = "timeout"
    h.world.set_effect["release:LOT1"] = "none"
    h.check_ai()
    h.confirm_release()
    h.confirm_release()
    assert len(h.world.release_calls) == 1
    assert h.order().lifecycle != Lifecycle.CLOSED
    assert h.order().work_state == WorkState.RELEASE_VERIFY_PENDING


def test_agent_never_sends_transfer_hold(h):
    _happy_until_hold(h)
    h.world.scan_wafer("LOT1", "W01", result="DEFECT")
    h.world.add_defect_hold("LOT1", memo="Please check #1")
    h.check_ai()
    h.world.scan_wafer("LOT1", "W02", result="DEFECT")
    h.world.transfer_response["LOT1"] = "rejected_transient"
    for _ in range(5):
        h.check_ai()
    assert h.world.transfer_calls == []
    tr = [c for c in h.commands() if c.action_type.value == "TRANSFER_HOLD"]
    assert tr == []
    smm = [x for x in h.world.holds if x.hold_code == "SMMH"]
    assert smm and smm[0].memo == "Please check #1"
    assert h.order().lifecycle != Lifecycle.CLOSED
    assert h.order().work_state == WorkState.WAIT_AI
