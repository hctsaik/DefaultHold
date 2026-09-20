"""Run T01-T38 mock cases, parse logs, ensure a case can be traced Facts↔Decision↔Action."""

from __future__ import annotations

import logging

import pytest

from vai_hold.investigate import classify_layer, for_lot, parse_records, required_fields_ok
from vai_hold.domain.enums import ControlMode, Lifecycle, WorkState
from vai_hold.domain.models import HoldCommand, InboundEvent
from vai_hold.application.ports.clock import ManualClock
from vai_hold.composition.bootstrap import build_app
from vai_hold.domain.enums import FunctionCode

from harness import make_harness
from scenario_expect import EXPECT
from test_t01_t18 import _happy_until_hold
from datetime import timedelta


def _rules_in(records) -> set[str]:
    out = set()
    for r in records:
        if r.get("rule_id"):
            out.add(r["rule_id"])
        facts = r.get("facts") or {}
        if isinstance(facts, dict) and facts.get("rule_id"):
            out.add(facts["rule_id"])
    return out


def _events_in(records) -> set[str]:
    return {r.get("event") for r in records if r.get("event")}


def _assert_traceable(caplog, case_id: str):
    recs = parse_records(caplog.text)
    assert recs, f"{case_id}: no JSON log records"
    for r in recs:
        miss = required_fields_ok(r)
        assert not miss, f"{case_id} {r.get('event')} missing {miss}"
    decisions = [r for r in recs if r.get("event") == "decision.applied"]
    for d in decisions:
        assert d.get("facts"), f"{case_id} decision without facts"
        assert d.get("run_id"), f"{case_id} decision without run_id"
        classify_layer(d)
    exp = EXPECT[case_id]
    got_e = _events_in(recs)
    got_r = _rules_in(recs)
    missing_e = exp["events"] - got_e
    missing_r = exp["rules"] - got_r
    assert not missing_e, f"{case_id} missing events {missing_e} have {got_e}"
    assert not missing_r, f"{case_id} missing rules {missing_r} have {got_r}"


def test_drill_t01(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.check_ai()
    h.confirm_release()
    assert h.order().lifecycle == Lifecycle.CLOSED
    _assert_traceable(caplog, "T01")


def test_drill_t02(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = ["rejected_conflict", "accepted"]
    h.set_hold()
    h.confirm_hold()
    _assert_traceable(caplog, "T02")


def test_drill_t03(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness(extra_overrides={"hold": {"codes": ["ENHL", "OTHL", "HOLD3"]}})
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_conflict"
    h.set_hold()
    _assert_traceable(caplog, "T03")


def test_drill_t05(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    h.world.list_status["LOT1"] = "unknown"
    h.confirm_hold()
    _assert_traceable(caplog, "T05")


def test_drill_t09(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", skip=["W25"])
    h.check_ai()
    _assert_traceable(caplog, "T09")


def test_drill_t12(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", missing_result="W03")
    h.check_ai()
    _assert_traceable(caplog, "T12")


def test_drill_t15(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.clock.advance(minutes=2)
    h.check_ai()
    _assert_traceable(caplog, "T15")


def test_drill_t17(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.world.release_response["LOT1"] = "rejected_permission"
    h.check_ai()
    h.confirm_release()
    _assert_traceable(caplog, "T17")


def test_drill_t19(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.holds.clear()
    h.check_ai()
    _assert_traceable(caplog, "T19")


def test_drill_t26(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.clock.advance(minutes=30, seconds=1)
    h.defense()
    _assert_traceable(caplog, "T26")


def test_drill_t27(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    for i in range(3):
        h.world.add_lot(f"L{i}")
        h.set_hold()
        h.confirm_hold()
    h.clock.advance(minutes=31)
    h.defense()
    _assert_traceable(caplog, "T27")


def test_drill_t30(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("ORPH")
    h.world.holds.append(
        HoldCommand(
            lot_id="ORPH", route_id="RT1", ope_no="OP200",
            memo=h.settings.hold_memo, hold_code="ENHL", hold_user="ABO",
        )
    )
    h.defense()
    _assert_traceable(caplog, "T30")


def test_drill_t32(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_conflict"
    h.world.notifier_fail = True
    h.set_hold()
    h.defense()
    h.world.notifier_fail = False
    h.clock.advance(minutes=1)
    h.defense()
    _assert_traceable(caplog, "T32")


def test_drill_t35(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.set_hold()
    h.clock.advance(minutes=6)
    h.defense()
    _assert_traceable(caplog, "T35")


def test_drill_t36(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1", wafers=25)
    h.set_hold()
    now = h.clock.now()
    h.world.events.append(
        InboundEvent(
            source_event_id="evt-split", lot_id="LOT1", observed_at=now, created_at=now,
            origin_ope_no="OP100", rework_count=0, event_time=now, payload="W01,W02",
        )
    )
    h.set_hold()
    _assert_traceable(caplog, "T36")


def test_drill_t37(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.set_hold()
    h.confirm_hold()
    past = h.clock.now() - timedelta(hours=2)
    h.world.events.append(
        InboundEvent(
            source_event_id="evt-late", lot_id="LOT1", observed_at=h.clock.now(),
            created_at=h.clock.now(), origin_ope_no="OP100", rework_count=0,
            event_time=past, payload=",".join(f"W{i:02d}" for i in range(1, 26)),
        )
    )
    h.set_hold()
    _assert_traceable(caplog, "T37")


def test_expect_covers_t01_to_t38():
    for i in range(1, 39):
        assert f"T{i:02d}" in EXPECT


def test_drill_t04(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.set_hold()
    h.confirm_hold()
    _assert_traceable(caplog, "T04")


def test_drill_t07(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    app2 = build_app(
        settings=h.settings, world=h.world, clock=h.clock,
        uow_factory=h.app.uow_factory, worker_id="worker-2",
    )
    h.set_hold()
    app2.run(FunctionCode.SET_DEFAULT_HOLD.value)
    _assert_traceable(caplog, "T07")


def test_drill_t08(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    app2 = build_app(
        settings=h.settings, world=h.world, clock=h.clock,
        uow_factory=h.app.uow_factory, worker_id="worker-2",
    )
    app2.run(FunctionCode.SET_DEFAULT_HOLD.value)
    _assert_traceable(caplog, "T08")


def test_drill_t14(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.world.add_defect_hold("LOT1")
    h.check_ai()
    h.confirm_release()
    _assert_traceable(caplog, "T14")


def test_drill_t16(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.world.release_response["LOT1"] = "timeout"
    h.check_ai()
    h.confirm_release()
    _assert_traceable(caplog, "T16")


def test_drill_t18(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.add_foreign_hold("LOT1", hold_code="ENHL", memo="SOME OTHER MEMO", ope_no="OP200")
    h.set_hold()
    h.confirm_hold()
    _assert_traceable(caplog, "T18")


def test_drill_t20(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    order = h.order()
    h.app.run("VAI_MANUAL_CLOSE", {"order_id": order.order_id, "actor": "eng", "approver": "sp"})
    _assert_traceable(caplog, "T20")


def test_drill_t28(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    with h.app.uow_factory.new() as uow:
        c = uow.control.get("DEFAULT")
        c.mode = ControlMode.DISABLED_NEW_HOLD
        uow.control.save(c, c.control_version)
        uow.commit()
    h.world.add_lot("NEWLOT", event_id="evt-new")
    h.set_hold()
    _assert_traceable(caplog, "T28")


def test_drill_t31(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.check_ai()
    h.confirm_release()
    h.world.holds.append(
        HoldCommand(
            lot_id="LOT1", route_id="RT1", ope_no="OP200",
            memo=h.settings.hold_memo, hold_code="ENHL", hold_user="ABO",
        )
    )
    h.defense()
    _assert_traceable(caplog, "T31")


def test_drill_t34(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    with h.app.uow_factory.new() as uow:
        c = uow.control.get("DEFAULT")
        c.mode = ControlMode.DISABLED_NEW_HOLD
        uow.control.save(c, c.control_version)
        uow.commit()
    h.app.run("VAI_RESUME", {})
    _assert_traceable(caplog, "T34")


def test_drill_t38(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_permission"
    h.set_hold()
    h.confirm_hold()
    _assert_traceable(caplog, "T38")


def test_parse_log_reports_broken_json():
    from vai_hold.investigate import parse_log

    text = "plain\nprefix {\"event\": broken}\nvai_hold.eval.cycle {\"event\": \"eval.cycle\", \"lot_id\": \"LOT1\"}\n"
    report = parse_log(text)
    assert report.parsed == 1
    assert report.skipped_bad_json >= 1
    assert report.skipped_plain >= 1


def test_for_lot_is_exact_id_not_substring():
    recs = [
        {"event": "hold.sent", "lot_id": "LOT10"},
        {"event": "hold.sent", "lot_id": "LOT1"},
        {"event": "eval.cycle", "observed": {"Lot": {"LotId": "LOT1"}}},
    ]
    got = for_lot(recs, "LOT1")
    assert {r.get("event") for r in got} == {"hold.sent", "eval.cycle"}
    assert all(_lot(r) != "LOT10" for r in got)


def _lot(r):
    from vai_hold.investigate import _record_lot

    return _record_lot(r)
