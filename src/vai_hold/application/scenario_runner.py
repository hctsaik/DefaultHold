from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from vai_hold.application.log import observed_facts
from vai_hold.application.scenario_present import describe_step, flatten_script
from vai_hold.application.services import snapshot
from vai_hold.domain.enums import FunctionCode
from vai_hold.domain.models import HoldCommand, InboundEvent, OrderKey
from vai_hold.domain.scenario import ScenarioCase, ScenarioRunResult
from vai_hold.domain.timeutil import utc_now_iso

# 情境庫 MOCK 的「現場零點」：像白班進站，不是 00:00:00Z 哨兵值
SCENARIO_T0 = datetime(2026, 3, 18, 6, 14, 37, tzinfo=timezone.utc)

FN = {
    "set": FunctionCode.SET_DEFAULT_HOLD.value,
    "confirm": FunctionCode.CONFIRM_HOLD.value,
    "check": FunctionCode.CHECK_AI.value,
    "release": FunctionCode.CONFIRM_RELEASE.value,
    "defense": FunctionCode.DEFENSE.value,
    "resume": FunctionCode.RESUME.value,
    "close": FunctionCode.MANUAL_CLOSE.value,
}


def subset_diff(expected: Any, actual: Any, path: str = "$") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected object, got {type(actual).__name__}={actual!r}"]
        diffs: list[str] = []
        for key, value in expected.items():
            diffs.extend(subset_diff(value, actual.get(key), f"{path}.{key}"))
        return diffs
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"{path}: expected list, got {actual!r}"]
        diffs = []
        for i, item in enumerate(expected):
            if isinstance(item, dict):
                if not any(not subset_diff(item, cand) for cand in actual):
                    diffs.append(f"{path}[{i}]: no actual item matches {item!r}")
            elif item not in actual:
                diffs.append(f"{path}: missing {item!r}")
        return diffs
    if expected != actual:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def _lot_kwargs(raw: dict[str, Any]) -> dict[str, Any]:
    from vai_hold.domain.models import FlowStep

    kwargs = dict(raw)
    steps = kwargs.get("steps")
    if steps and isinstance(steps[0], dict):
        kwargs["steps"] = [FlowStep(**s) for s in steps]
    return kwargs


def apply_given(h, given: dict[str, Any]) -> None:
    world = given.get("world") or {}
    for lot in given.get("lots") or []:
        kwargs = _lot_kwargs(lot)
        lot_id = kwargs.pop("lot_id")
        h.world.add_lot(lot_id, **kwargs)
        _note(h, {"op": "add_lot", "lot_id": lot_id, **kwargs})
    for hold in given.get("holds") or []:
        h.world.holds.append(
            HoldCommand(
                lot_id=hold["lot_id"],
                route_id=hold.get("route_id", "RT1"),
                ope_no=hold.get("ope_no", "OP200"),
                memo=hold.get("memo") or h.settings.hold_memo,
                hold_code=hold.get("hold_code", "ENHL"),
                hold_user=hold.get("hold_user", "ABO"),
                hold_type=hold.get("hold_type"),
            )
        )
    for row in given.get("ai") or []:
        h.world.scan_wafer(
            row["lot_id"],
            row["wafer_id"],
            result=row.get("result", "OK"),
            rework_count=int(row.get("rework_count") or 0),
        )
    if world.get("set_response"):
        h.world.set_response.update(world["set_response"])
        for k in world["set_response"]:
            h.world.set_response_i.pop(k, None)
    if world.get("set_effect"):
        h.world.set_effect.update(world["set_effect"])
    if world.get("list_status"):
        h.world.list_status.update(world["list_status"])
    if world.get("release_response"):
        h.world.release_response.update(world["release_response"])
    if world.get("transfer_response"):
        h.world.transfer_response.update(world["transfer_response"])
    if world.get("notifier_fail"):
        h.world.notifier_fail = True


def _note(h, step: dict[str, Any]) -> None:
    if not hasattr(h, "scenario_timeline"):
        h.scenario_timeline = []
    info = describe_step(step)
    repeat = step.get("_repeat")
    title = info["title"]
    if repeat:
        title = f"{title}（第 {repeat} 次）"
    kind = info.get("kind") or "env"
    if step.get("op") == "run" and step.get("_when") is False:
        kind = "given"
    h.scenario_timeline.append(
        {
            "at": utc_now_iso(h.clock.now()),
            "title": title,
            "loc": info.get("loc") or "",
            "via": info.get("via") or "",
            "mes": info.get("mes") or "",
            "kind": kind,
            "op": step.get("op"),
            "when": bool(step.get("_when")),
        }
    )


def _stamp_order_state(h, step: dict[str, Any]) -> None:
    """每一支 function code 跑完，把訂單狀態打在時間軸上（狀態機一格，不是一次做完）。"""
    lot_id = step.get("lot_id") or "LOT1"
    ope = step.get("ope") or "OP100"
    rw = int(step.get("rw") or 0)
    order = h.order(lot_id, ope, rw)
    if not order or not getattr(h, "scenario_timeline", None):
        return
    h.scenario_timeline[-1]["work_state"] = order.work_state.value
    h.scenario_timeline[-1]["protection_state"] = order.protection_state.value
    h.scenario_timeline[-1]["lifecycle"] = order.lifecycle.value
    h.scenario_timeline[-1]["last_rule_id"] = order.last_rule_id
    h.scenario_timeline[-1]["fn"] = step.get("fn") or ""


def _tick(h, *, minutes: int = 0, seconds: int = 0) -> None:
    if minutes or seconds:
        h.clock.advance(minutes=minutes, seconds=seconds)


def _align_cron(h) -> None:
    """Cron 對到下一分鐘 :00，且距現在至少 45 秒（像錯開的 job）。"""
    now = h.clock.now()
    wait = 60 - now.second
    if wait < 45:
        wait += 60
    h.clock.advance(seconds=wait)


def run_script(h, script: list[dict[str, Any]]) -> None:
    if not hasattr(h, "scenario_timeline"):
        h.scenario_timeline = []
    steps = flatten_script(script)
    last_run = max((i for i, s in enumerate(steps) if s.get("op") == "run"), default=-1)
    for i, step in enumerate(steps):
        op = step.get("op")
        if op == "run":
            _align_cron(h)
            step = dict(step)
            step["_when"] = i == last_run
        if op != "complete_ai":
            _note(h, step)
        if op == "add_lot":
            kwargs = _lot_kwargs({k: v for k, v in step.items() if k not in {"op", "lot_id"}})
            h.world.add_lot(step["lot_id"], **kwargs)
        elif op == "run":
            code = FN.get(step.get("fn") or "", step.get("code") or "")
            params = dict(step.get("params") or {})
            if step.get("fn") == "close" and "order_id" not in params:
                order = h.order(step.get("lot_id", "LOT1"), step.get("ope", "OP100"), step.get("rw", 0))
                if order:
                    params["order_id"] = order.order_id
                    params.setdefault("actor", "eng")
                    params.setdefault("approver", "sp")
            h.app.run(code, params)
            _stamp_order_state(h, step)
        elif op == "complete_ai":
            h.world.complete_ai(
                step.get("lot_id", "LOT1"),
                rework_count=int(step.get("rework_count") or 0),
                result=step.get("result", "OK"),
                skip=step.get("skip"),
                extra_duplicate=step.get("extra_duplicate"),
                missing_result=step.get("missing_result"),
            )
            _note(h, step)
        elif op == "scan_wafer":
            h.world.scan_wafer(
                step.get("lot_id", "LOT1"),
                step["wafer_id"],
                result=step.get("result", "DEFECT"),
                rework_count=int(step.get("rework_count") or 0),
            )
        elif op == "add_standard_hold":
            h.world.holds.append(
                HoldCommand(
                    lot_id=step.get("lot_id", "LOT1"),
                    route_id=step.get("route_id", "RT1"),
                    ope_no=step.get("ope_no", "OP200"),
                    memo=h.settings.hold_memo,
                    hold_code=step.get("hold_code", "ENHL"),
                    hold_user=step.get("hold_user", "ABO"),
                )
            )
        elif op == "add_foreign_hold":
            h.world.add_foreign_hold(
                step.get("lot_id", "LOT1"),
                hold_code=step.get("hold_code", "ENHL"),
                memo=step.get("memo", "SOME OTHER MEMO"),
                ope_no=step.get("ope_no"),
            )
        elif op == "add_defect_hold":
            h.world.add_defect_hold(
                step.get("lot_id", "LOT1"),
                rework_count=int(step.get("rework_count") or 0),
                ope_no=step.get("ope_no"),
                memo=step.get("memo", "SMM AI DEFECT HOLD"),
            )
        elif op == "set_world":
            apply_given(h, {"world": {k: v for k, v in step.items() if k != "op"}})
        elif op == "clear_holds":
            h.world.holds.clear()
        elif op == "ai_unavailable":
            h.app.ai.unavailable_lots.add(step.get("lot_id", "LOT1"))
        elif op == "advance":
            kwargs = {k: v for k, v in step.items() if k != "op"}
            h.clock.advance(**kwargs)
        elif op == "settle":
            h.settle()
        elif op == "append_event":
            now = h.clock.now()
            h.world.events.append(
                InboundEvent(
                    source_event_id=step.get("event_id") or f"evt-extra-{len(h.world.events)}",
                    lot_id=step.get("lot_id", "LOT1"),
                    observed_at=now,
                    created_at=now,
                    origin_ope_no=step.get("origin_ope_no", "OP100"),
                    rework_count=int(step.get("rework_count") or 0),
                    event_time=now if not step.get("stale_hours") else now,
                    payload=step.get("payload", ""),
                )
            )
            if step.get("stale_hours"):
                from datetime import timedelta

                h.world.events[-1].event_time = h.clock.now() - timedelta(hours=int(step["stale_hours"]))
        elif op == "disable_control":
            from vai_hold.domain.enums import ControlMode

            with h.app.uow_factory.new() as uow:
                c = uow.control.get("DEFAULT")
                c.mode = ControlMode.DISABLED_NEW_HOLD
                uow.control.save(c, c.control_version)
                uow.commit()
        elif op == "repeat":
            continue
        else:
            raise ValueError(f"unknown scenario op: {op}")
        if op == "scan_wafer":
            _tick(h, seconds=10)


def _action_detail(h, facts: dict | None) -> dict | None:
    """最後一次送到 MES 的那包（Hold／解除／transfer），給查案頁 Decision。"""
    ope_name = None
    if facts:
        ope_name = (facts.get("Flow") or {}).get("FutureHoldOpeName")

    def pack(cmd, *, memo=None, kind="set_hold") -> dict:
        return {
            "Kind": kind,
            "OpeNo": cmd.ope_no,
            "OpeName": ope_name,
            "RouteId": cmd.route_id,
            "HoldCode": cmd.hold_code,
            "HoldUser": cmd.hold_user,
            "HoldMemo": memo if memo is not None else cmd.memo,
        }

    if h.world.transfer_calls:
        cmd, memo = h.world.transfer_calls[-1]
        return pack(cmd, memo=memo, kind="transfer")
    if h.world.release_calls:
        return pack(h.world.release_calls[-1], kind="release")
    if h.world.set_hold_calls:
        return pack(h.world.set_hold_calls[-1], kind="set_hold")
    holds = ((facts or {}).get("DefaultHold") or {}).get("Holds") or []
    if holds:
        h0 = holds[-1]
        return {
            "Kind": "set_hold",
            "OpeNo": h0.get("OpeNo"),
            "OpeName": h0.get("OpeName") or ope_name,
            "RouteId": h0.get("RouteId"),
            "HoldCode": h0.get("HoldCode"),
            "HoldUser": h0.get("HoldUser"),
            "HoldMemo": h0.get("HoldMemo"),
        }
    return None


def collect_actual(h, case: ScenarioCase) -> dict[str, Any]:
    lot_id = case.expect.get("lot_id", "LOT1")
    ope = case.expect.get("ope", "OP100")
    rw = int(case.expect.get("rw") or 0)
    order = h.order(lot_id, ope, rw)
    facts = None
    missing_alarm = []
    judgment = None
    if order is not None:
        with h.app.uow_factory.new() as uow:
            snap = snapshot(h.app, uow, order)
            facts = observed_facts(snap, rec_time=h.clock.now())
            missing_alarm = [w.wafer_id for w in uow.wafers.list_by_order(order.order_id) if w.missing_alarm_type]
            from vai_hold.application.log import converted_state
            from vai_hold.domain.derive import derive_state

            judged = derive_state(snap)
            judgment = {
                "rule_id": judged.rule_id,
                "reason": judged.reason,
                "action": judged.business_action.value if judged.business_action else None,
                "work_state": judged.work_state.value if judged.work_state else None,
                "gates": converted_state(snap, judged),
            }
            uow.commit()
    hist = []
    if order is not None:
        hist = h.history(lot_id)
    return {
        "work_state": None if order is None else order.work_state.value,
        "lifecycle": None if order is None else order.lifecycle.value,
        "last_rule_id": None if order is None else order.last_rule_id,
        "state_reason": None if order is None else order.state_reason,
        "close_reason": None if order is None else order.close_reason,
        "data_error": None if order is None else order.data_error,
        "protection_state": None if order is None else order.protection_state.value,
        "ai_state": None if order is None else order.ai_state.value,
        "target_ope_no": None if order is None else order.target_hold_ope_no,
        "actions": {
            "set_hold": len(h.world.set_hold_calls),
            "release": len(h.world.release_calls),
        },
        "attempt_max": max((a.attempt_no for a in hist), default=0),
        "command_count": {
            "SET_HOLD": len([c for c in (h.commands(lot_id) if order else []) if c.action_type.value == "SET_HOLD"]),
            "SET_RELEASE": len([c for c in (h.commands(lot_id) if order else []) if c.action_type.value == "SET_RELEASE"]),
        },
        "incidents": sorted({i.incident_type for i in h.incidents()}),
        "incident_rows": [
            {
                "incident_id": i.incident_id,
                "incident_type": i.incident_type,
                "status": i.status,
                "severity": i.severity,
                "lot_id": i.lot_id,
                "order_id": i.order_id,
                "reason": i.reason,
                "first_seen_at": utc_now_iso(i.first_seen_at),
                "last_seen_at": utc_now_iso(i.last_seen_at),
                "occurrence_count": i.occurrence_count,
            }
            for i in h.incidents()
        ],
        "failed_attempts": [
            {
                "command_id": a.command_id,
                "hold_code": next(
                    (c.hold_code for c in (h.commands(lot_id) if order else []) if c.command_id == a.command_id),
                    None,
                ),
                "attempt_no": a.attempt_no,
                "receipt": a.receipt_outcome.value if a.receipt_outcome else None,
                "error": a.normalized_error,
                "retry_class": a.retry_class,
                "rule_id": a.rule_id,
                "finished_at": utc_now_iso(a.finished_at) if a.finished_at else None,
            }
            for a in hist
            if (a.receipt_outcome and a.receipt_outcome.value in {"REJECTED", "UNKNOWN"})
            or a.normalized_error
        ],
        "control_mode": h.control().mode.value,
        "emails": len(h.world.sent_emails),
        "open_count": h.open_count(),
        "smm_memo": next((x.memo for x in h.world.holds if x.hold_code == "SMMH"), None),
        "missing_alarm_wafers": missing_alarm,
        "facts": facts,
        "timeline": list(getattr(h, "scenario_timeline", [])),
        "action_detail": _action_detail(h, facts),
        "judgment": judgment,
    }


def compare(expect: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    diffs: list[str] = []
    for key in (
        "work_state",
        "lifecycle",
        "last_rule_id",
        "close_reason",
        "data_error",
        "protection_state",
        "ai_state",
        "target_ope_no",
        "control_mode",
        "emails",
        "open_count",
        "smm_memo",
        "attempt_max",
    ):
        if key in expect:
            diffs.extend(subset_diff(expect[key], actual.get(key), key))
    if "actions" in expect:
        diffs.extend(subset_diff(expect["actions"], actual.get("actions") or {}, "actions"))
    if "command_count" in expect:
        diffs.extend(subset_diff(expect["command_count"], actual.get("command_count") or {}, "command_count"))
    if "incidents" in expect:
        diffs.extend(subset_diff(expect["incidents"], actual.get("incidents") or [], "incidents"))
    if "incidents_absent" in expect:
        have = set(actual.get("incidents") or [])
        for name in expect["incidents_absent"]:
            if name in have:
                diffs.append(f"incidents: did not expect {name}")
    if "facts" in expect:
        diffs.extend(subset_diff(expect["facts"], actual.get("facts") or {}, "facts"))
    if "missing_alarm_wafers" in expect:
        diffs.extend(
            subset_diff(expect["missing_alarm_wafers"], actual.get("missing_alarm_wafers") or [], "missing_alarm_wafers")
        )
    return diffs


def run_case(case: ScenarioCase, *, tmp_path=None, backend="memory") -> ScenarioRunResult:
    import sys
    import tempfile
    from pathlib import Path

    tests = Path(__file__).resolve().parents[3] / "tests"
    if tests.exists() and str(tests) not in sys.path:
        sys.path.insert(0, str(tests))
    from harness import make_harness

    own_tmp = None
    if backend == "sqlite" and tmp_path is None:
        own_tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(own_tmp.name)
    try:
        h = make_harness(tmp_path=tmp_path, backend=backend, extra_overrides=case.settings or None)
        h.clock.set(SCENARIO_T0)
        h.scenario_timeline = []
        apply_given(h, case.given or {})
        run_script(h, case.script)
        actual = collect_actual(h, case)
        diffs = compare(case.expect, actual)
        return ScenarioRunResult(
            scenario_id=case.scenario_id,
            passed=not diffs,
            actual=actual,
            diffs=diffs,
            title=case.title,
        )
    finally:
        if own_tmp is not None:
            own_tmp.cleanup()


def run_catalog(catalog, *, tmp_path=None, backend="memory") -> list[ScenarioRunResult]:
    from pathlib import Path

    results = []
    for case in catalog.list_enabled():
        case_tmp = tmp_path
        if backend == "sqlite":
            base = Path(tmp_path) if tmp_path is not None else Path("var") / "scenario-sqlite"
            case_tmp = base / case.scenario_id
            case_tmp.mkdir(parents=True, exist_ok=True)
            stale = case_tmp / "order.db"
            if stale.exists():
                stale.unlink()
        result = run_case(case, tmp_path=case_tmp, backend=backend)
        catalog.record_run(result)
        results.append(result)
    return results
