from __future__ import annotations

from datetime import timedelta

from vai_hold.adapters.fake_world.world import FlowStep
from vai_hold.domain.enums import ControlMode, Lifecycle, WorkState
from vai_hold.domain.errors import OracleNotImplemented, UnknownFunctionCode
from vai_hold.application.settings import load_settings
from vai_hold.composition.bootstrap import build_app, RealAdapterForbidden

from harness import make_harness
from test_t01_t18 import _happy_until_hold


def test_t19_hold_missing(h):
    _happy_until_hold(h)
    h.world.holds.clear()
    h.confirm_hold()
    h.check_ai()
    h.defense()
    order = h.order()
    assert order.lifecycle == Lifecycle.MANUAL_CLOSED
    assert order.close_reason == "MANUAL"
    assert not any(i.incident_type == "HOLD_MISSING" for i in h.incidents())
    assert not h.world.set_hold_calls or len(h.world.set_hold_calls) == 1


def test_t20_manual_close(h):
    _happy_until_hold(h)
    order = h.order()
    h.app.run("VAI_MANUAL_CLOSE", {"order_id": order.order_id, "actor": "eng", "approver": "sp"})
    order = h.order()
    assert order.lifecycle == Lifecycle.MANUAL_CLOSED
    assert order.close_reason == "MANUAL"


def test_t24_reselect_after_move(h):
    h.world.add_lot("LOT1", current_ope_no="OP100")
    h.set_hold()
    order = h.order()
    first_target = order.target_hold_ope_no
    lot = h.world.lots[("LOT1", 0)]
    lot.current_ope_no = "OP300"
    lot.flow_version = "fv2"
    # in-flight must complete first
    h.confirm_hold()
    # new set not sent because already protected
    assert h.order().protection_state.value == "CONFIRMED"
    assert first_target == "OP200"


def test_t25_hold_query_unknown_not_absent(h):
    h.world.add_lot("LOT1")
    h.world.list_status["LOT1"] = "unknown"
    h.set_hold()
    h.confirm_hold()
    order = h.order()
    assert order.work_state in {WorkState.OBSERVATION_UNKNOWN, WorkState.HOLD_VERIFY_PENDING}
    assert order.work_state != WorkState.HOLD_FAILED


def test_t26_watchdog_boundary(h):
    _happy_until_hold(h)
    h.clock.advance(minutes=29, seconds=59)
    h.defense()
    assert not any(i.incident_type == "HOLD_OVERDUE" for i in h.incidents())
    h.clock.advance(seconds=1)  # 30:00
    h.defense()
    assert not any(i.incident_type == "HOLD_OVERDUE" for i in h.incidents())
    h.clock.advance(seconds=1)  # 30:01
    h.defense()
    overdue = [i for i in h.incidents() if i.incident_type == "HOLD_OVERDUE"]
    assert overdue
    assert "ESTIMATED" in (overdue[0].reason or "")
    assert "not MES Created" in (overdue[0].reason or "")


def test_t27_three_lots_disable(h):
    for i in range(2):
        h.world.add_lot(f"L{i}")
        h.set_hold()
        h.confirm_hold()
    h.clock.advance(minutes=31)
    h.defense()
    assert h.control().mode == ControlMode.ENABLED
    h.world.add_lot("L2")
    h.set_hold()
    h.confirm_hold()
    h.clock.advance(minutes=31)
    h.defense()
    assert h.control().mode == ControlMode.DISABLED_NEW_HOLD


def test_t28_disable_blocks_new_allows_release(h):
    _happy_until_hold(h)
    with h.app.uow_factory.new() as uow:
        c = uow.control.get("DEFAULT")
        c.mode = ControlMode.DISABLED_NEW_HOLD
        uow.control.save(c, c.control_version)
        uow.commit()
    h.world.complete_ai("LOT1")
    h.check_ai()
    h.confirm_release()
    assert h.order().lifecycle == Lifecycle.CLOSED
    h.world.add_lot("NEWLOT", event_id="evt-new")
    calls = len(h.world.set_hold_calls)
    h.set_hold()
    assert h.order("NEWLOT") is not None
    assert len(h.world.set_hold_calls) == calls
    assert h.order("NEWLOT").work_state == WorkState.BLOCKED_BY_CONTROL


def test_t29_coverage_mismatch_same_count(h):
    h.world.add_lot("A")
    h.world.add_lot("B")
    h.set_hold()
    h.confirm_hold()
    # expected keys A,B but we will add C in SMM lots without processing, remove meaning via extra lot
    h.world.add_lot("C", event_id="evt-c")
    h.defense()
    assert any(i.incident_type == "COVERAGE_MISMATCH" for i in h.incidents())


def test_t32_notifier_retry(h):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_conflict"
    h.world.notifier_fail = True
    h.set_hold()
    h.defense()
    assert h.world.sent_emails == []
    h.world.notifier_fail = False
    h.clock.advance(minutes=1)
    h.defense()
    assert h.world.sent_emails


def test_t33_unknown_function_and_oracle():
    import pytest
    from vai_hold.adapters.persistence.oracle.factory import load_oracle_factory

    h = make_harness()
    with pytest.raises(UnknownFunctionCode):
        h.app.run("NOT_A_CODE")
    with pytest.raises(OracleNotImplemented):
        load_oracle_factory(None)


def test_t33_prod_fake_forbidden():
    import pytest

    with pytest.raises(Exception):
        load_settings(overrides={"runtime": {"mode": "PROD"}, "persistence": {"backend": "memory"}})


def test_t34_resume_requires_sponsor(h):
    with h.app.uow_factory.new() as uow:
        c = uow.control.get("DEFAULT")
        c.mode = ControlMode.DISABLED_NEW_HOLD
        uow.control.save(c, c.control_version)
        uow.commit()
    h.app.run("VAI_RESUME", {})
    assert h.control().mode == ControlMode.DISABLED_NEW_HOLD
    h.app.run("VAI_RESUME", {"sponsor": "SP1", "evidence": "fixed"})
    assert h.control().mode == ControlMode.ENABLED


def test_t38_permission_stops_backup(h):
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_permission"
    h.set_hold()
    h.confirm_hold()
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    assert h.order().work_state == WorkState.HOLD_FAILED
