from __future__ import annotations

from datetime import timedelta

from vai_hold.application.ports.clock import ManualClock
from vai_hold.composition.bootstrap import build_app
from vai_hold.domain.enums import FunctionCode, Lifecycle, WorkState
from vai_hold.domain.models import HoldCommand, InboundEvent

from harness import make_harness
from test_t01_t18 import _happy_until_hold


def test_t07_two_workers_single_order():
    h = make_harness()
    h.world.add_lot("LOT1")
    app2 = build_app(
        settings=h.settings,
        world=h.world,
        clock=h.clock,
        uow_factory=h.app.uow_factory,
        worker_id="worker-2",
    )
    h.set_hold()
    app2.run(FunctionCode.SET_DEFAULT_HOLD.value)
    assert h.open_count() == 1
    cmds = h.commands()
    set_cmds = [c for c in cmds if c.action_type.value == "SET_HOLD"]
    assert len(set_cmds) == 1


def test_t08_in_flight_not_resent():
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    assert len(h.world.set_hold_calls) == 1
    app2 = build_app(
        settings=h.settings,
        world=h.world,
        clock=h.clock,
        uow_factory=h.app.uow_factory,
        worker_id="worker-2",
    )
    app2.run(FunctionCode.SET_DEFAULT_HOLD.value)
    assert len(h.world.set_hold_calls) == 1
    inflight = h.commands()
    assert any(c.action_state.value in {"UNKNOWN", "PREPARED", "ACKNOWLEDGED"} for c in inflight)


def test_t30_orphan_hold_not_auto_released():
    h = make_harness()
    h.world.add_lot("ORPH")
    h.world.holds.append(
        HoldCommand(
            lot_id="ORPH",
            route_id="RT1",
            ope_no="OP200",
            memo=h.settings.hold_memo,
            hold_code="ENHL",
            hold_user="ABO",
        )
    )
    before = len(h.world.holds)
    h.defense()
    assert "ORPHAN_HOLD" in h.incident_types()
    assert len(h.world.holds) == before


def test_t31_closed_with_remaining_hold():
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.check_ai()
    h.confirm_release()
    assert h.order().lifecycle == Lifecycle.CLOSED
    h.world.holds.append(
        HoldCommand(
            lot_id="LOT1",
            route_id="RT1",
            ope_no="OP200",
            memo=h.settings.hold_memo,
            hold_code="ENHL",
            hold_user="ABO",
        )
    )
    h.defense()
    assert "STATE_CONFLICT" in h.incident_types()


def test_t35_agent_stall_after_heartbeat_gap():
    h = make_harness()
    h.world.add_lot("LOT1")
    h.set_hold()
    h.clock.advance(minutes=6)
    h.defense()
    assert "AGENT_STALL" in h.incident_types()


def test_t36_roster_change_manual_review():
    h = make_harness()
    h.world.add_lot("LOT1", wafers=25)
    h.set_hold()
    now = h.clock.now()
    h.world.events.append(
        InboundEvent(
            source_event_id="evt-split",
            lot_id="LOT1",
            observed_at=now,
            created_at=now,
            origin_ope_no="OP100",
            rework_count=0,
            event_time=now,
            payload="W01,W02",
        )
    )
    h.set_hold()
    assert h.order().work_state == WorkState.MANUAL_REVIEW
    assert "MANUAL_REVIEW" in h.incident_types()


def test_t37_stale_event_does_not_rebuild(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.set_hold()
    h.confirm_hold()
    order = h.order()
    assert order.work_state == WorkState.WAIT_AI
    past = h.clock.now() - timedelta(hours=2)
    h.world.events.append(
        InboundEvent(
            source_event_id="evt-late",
            lot_id="LOT1",
            observed_at=h.clock.now(),
            created_at=h.clock.now(),
            origin_ope_no="OP100",
            rework_count=0,
            event_time=past,
            payload=",".join(f"W{i:02d}" for i in range(1, 26)),
        )
    )
    h.set_hold()
    assert h.order().work_state == WorkState.WAIT_AI
    assert "observation.stale" in caplog.text
