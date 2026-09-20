from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator

from vai_hold.application.ids import new_id
from vai_hold.application.logevents import Event
from vai_hold.domain.ai_complete import expected_complete
from vai_hold.domain.derive import Snapshot
from vai_hold.domain.enums import ActionType, BindingRole, SourceStatus
from vai_hold.domain.models import Decision, HoldOrder
from vai_hold.domain.ownership import is_smm_hold, match_our_holds
from vai_hold.domain.target import smm_hold_ope_no

logger = logging.getLogger("vai_hold")
_LOCATOR = None


def _locator_cache():
    global _LOCATOR
    if _LOCATOR is None:
        from vai_hold.locator import build_locator

        _LOCATOR = build_locator()
    return _LOCATOR
_run_id: ContextVar[str | None] = ContextVar("vai_hold_run_id", default=None)
_function_code: ContextVar[str | None] = ContextVar("vai_hold_fn", default=None)


def order_fields(order: HoldOrder | None) -> dict[str, Any]:
    if order is None:
        return {}
    return {
        "order_id": order.order_id,
        "lot_id": order.lot_id,
        "ope_no": order.origin_ope_no,
        "rework_count": order.rework_count,
    }


def _val(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def current_run_id() -> str | None:
    return _run_id.get()


@contextmanager
def pipeline_run(function_code: str) -> Iterator[str]:
    rid = new_id()
    t1 = _run_id.set(rid)
    t2 = _function_code.set(function_code)
    emit(Event.PIPELINE_START, function_code=function_code)
    try:
        yield rid
    finally:
        _function_code.reset(t2)
        _run_id.reset(t1)


def emit(event: str, extra: dict[str, Any] | None = None, **fields: Any) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "event_id": new_id(),
        "recorded_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    rid = _run_id.get()
    if rid:
        payload["run_id"] = rid
    fn = fields.get("function_code") or _function_code.get()
    if fn:
        payload["function_code"] = fn
    for src in (extra or {}, fields):
        for key, value in src.items():
            if value is None:
                continue
            payload[key] = _val(value)
    logger.info("%s %s", event, json.dumps(payload, default=str, ensure_ascii=False))


def facts_digest(snap: Snapshot) -> dict[str, Any]:
    """Compact inputs to derive_state — enough to tell Facts vs Decision vs Action."""
    mes = list(snap.hold_query.value or []) if snap.hold_query.status in {
        SourceStatus.FOUND,
        SourceStatus.NOT_FOUND,
    } else []
    own = []
    if snap.order is not None:
        own = match_our_holds(
            mes,
            snap.order,
            snap.bindings,
            standard_memo=snap.standard_memo,
            hold_user=snap.hold_user,
        )
    ai_status, missing = expected_complete(
        snap.expected_wafer_ids,
        snap.ai_views,
        rework_count=snap.order.rework_count if snap.order else 0,
    )
    inflight = snap.in_flight
    preventive = [b for b in snap.bindings if b.role == BindingRole.PREVENTIVE]
    attempted = [
        c.hold_code
        for c in snap.commands
        if c.action_type == ActionType.SET_HOLD and c.hold_code
    ]
    flow = snap.flow_query
    return {
        "hold_query": _val(snap.hold_query.status),
        "mes_hold_count": len(mes),
        "own_hold_count": len(own),
        "in_flight": (
            f"{_val(inflight.action_type)}:{_val(inflight.action_state)}:{inflight.hold_code}"
            if inflight
            else None
        ),
        "control": _val(snap.control.mode),
        "flow_query": _val(flow.status),
        "ai_status": ai_status,
        "expected_wafers": len(snap.expected_wafer_ids),
        "ai_views": len(snap.ai_views),
        "missing_count": len(missing),
        "missing_wafers": missing[:10],
        "binding_status": [_val(b.status) for b in preventive],
        "codes_attempted": attempted,
        "lifecycle": _val(snap.order.lifecycle) if snap.order else None,
        "work_state": _val(snap.order.work_state) if snap.order else None,
        "has_target": bool(snap.order and snap.order.target_hold_ope_no),
        "flow_version_match": (
            bool(snap.order and snap.order.flow_version and getattr(flow.value, "version", None) == snap.order.flow_version)
            if flow.value is not None
            else None
        ),
        "remaining_codes": [c for c in snap.hold_codes if c not in attempted],
        "has_defect_hold": bool(
            snap.order
            and any(
                is_smm_hold(
                    h,
                    lot_id=snap.order.lot_id,
                    hold_code=snap.smm_hold_code,
                    hold_user=snap.smm_hold_user,
                    ope_no=smm_hold_ope_no(
                        snap.flow_query.value if snap.flow_query.status == SourceStatus.FOUND else None,
                        snap.order.target_hold_ope_no,
                        snap.smm_hold_step,
                    ),
                )
                for h in mes
            )
        ),
        "release_cmd_state": (
            _val(next((c.action_state for c in reversed(snap.commands) if c.action_type == ActionType.SET_RELEASE), None))
        ),
        "data_error": snap.order.data_error if snap.order else None,
    }


def observed_facts(
    snap: Snapshot,
    *,
    rec_time=None,
    include_flow_steps: bool = False,
) -> dict[str, Any]:
    """必要且不重覆的原始觀察。Lot 身分只出現一次。

    RecTime 必須是注入 Clock，不可用主機牆鐘。
    OperationStartTime 只寫訂單上的進站時間，不用 created_at 假裝。
    UNKNOWN 查詢不得改寫成空集合。沒 FETCH 到的 MES 欄位不要出現。
    """
    from vai_hold.domain.timeutil import utc_now_iso

    order = snap.order
    op_start = order.operation_start_at if order else None
    fv = snap.flow_query.value if snap.flow_query.status == SourceStatus.FOUND else None
    hold_query = _val(snap.hold_query.status)
    holds: list[dict[str, Any]] = []
    if snap.hold_query.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND):
        for h in snap.hold_query.value or []:
            holds.append(
                {
                    "OpeNo": h.ope_no,
                    "OpeName": None,
                    "RouteId": h.route_id,
                    "HoldCode": h.hold_code,
                    "HoldUser": h.hold_user,
                    "HoldMemo": h.memo,
                }
            )
    inflight = snap.in_flight
    future_step = order.target_hold_ope_no if order else None
    future_name = order.future_hold_ope_name if order else None
    if not future_name and future_step and fv is not None:
        future_name = next((s.name for s in fv.steps if s.ope_no == future_step), None)
    future_holds = [
        h
        for h in holds
        if (not future_step or h.get("OpeNo") == future_step)
        and h.get("HoldCode") in snap.hold_codes
        and h.get("HoldUser") == snap.hold_user
    ]
    for h in future_holds:
        h["OpeName"] = future_name
    smm_ope = smm_hold_ope_no(fv, future_step, snap.smm_hold_step)
    smm_holds = []
    if snap.hold_query.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND) and order:
        for h in snap.hold_query.value or []:
            if is_smm_hold(
                h,
                lot_id=order.lot_id,
                hold_code=snap.smm_hold_code,
                hold_user=snap.smm_hold_user,
                ope_no=smm_ope,
            ):
                smm_holds.append(
                    {
                        "RouteId": h.route_id,
                        "OpeNo": h.ope_no,
                        "OpeName": next((s.name for s in (fv.steps if fv else []) if s.ope_no == h.ope_no), None),
                        "HoldCode": h.hold_code,
                        "HoldUser": h.hold_user,
                        "HoldType": h.hold_type or h.hold_code,
                        "HoldMemo": h.memo,
                    }
                )
    flow_block: dict[str, Any] = {
        "MainPdId": (order.hold_route_id if order else None) or (fv.route_id if fv is not None else None),
        "FutureHoldStep": future_step,
        "FutureHoldOpeName": future_name,
    }
    expected_n = len(snap.expected_wafer_ids)
    ai_q = snap.ai_query
    ai_status = _val(ai_q.status) if ai_q is not None else "UNKNOWN"
    ai_readable = ai_q is not None and ai_q.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND)
    scanned = 0
    latest_scan = None
    if ai_readable:
        for v in snap.ai_views:
            if v.scan_completed_at or v.result:
                scanned += 1
                if v.scan_completed_at and (latest_scan is None or v.scan_completed_at > latest_scan):
                    latest_scan = v.scan_completed_at
    return {
        "Lot": {
            "LotId": order.lot_id if order else None,
            "OpeNo": order.origin_ope_no if order else None,
            "ReworkCount": order.rework_count if order else None,
            "ToolId": order.tool_id if order else None,
            "RouteId": (fv.route_id if fv is not None else None) or (order.hold_route_id if order else None),
            "OperationStartTime": utc_now_iso(op_start) if op_start else None,
            "RecTime": utc_now_iso(rec_time) if rec_time else None,
        },
        "DefaultHold": {
            "QueryStatus": hold_query,
            "Holds": future_holds if snap.hold_query.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND) else None,
        },
        "SmmHold": {
            "StepMode": snap.smm_hold_step,
            "OpeNo": smm_ope,
            "QueryStatus": hold_query,
            "Holds": smm_holds if snap.hold_query.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND) else None,
        },
        "AiScan": {
            "QueryStatus": ai_status,
            "ExpectedCount": expected_n,
            "ScannedCount": scanned if ai_readable else None,
            "LatestScanTime": utc_now_iso(latest_scan) if latest_scan else None,
            "RecTime": utc_now_iso(rec_time) if rec_time else None,
        },
        "Flow": flow_block,
        "OrderDb": {
            "OrderId": order.order_id if order else None,
            "Lifecycle": _val(order.lifecycle) if order else None,
            "WorkState": _val(order.work_state) if order else None,
            "ProtectionState": _val(order.protection_state) if order else None,
            "AiState": _val(order.ai_state) if order else None,
            "LastRuleId": order.last_rule_id if order else None,
            "StateReason": order.state_reason if order else None,
            "CloseReason": order.close_reason if order else None,
            "DataError": order.data_error if order else None,
            "TargetOpeNo": order.target_hold_ope_no if order else None,
            "OperationStartAt": utc_now_iso(order.operation_start_at) if order and order.operation_start_at else None,
            "Bindings": [
                {
                    "Status": _val(b.status),
                    "Role": _val(b.role),
                    "RouteId": b.route_id,
                    "OpeNo": b.ope_no,
                    "HoldCode": b.hold_code,
                    "HoldUser": b.hold_user,
                    "HoldMemo": b.hold_memo,
                    "BackupHoldOrder": b.generation,
                    "TimeQuality": b.time_quality or "ESTIMATED",
                    "RequestedAt": utc_now_iso(b.requested_at) if b.requested_at else None,
                    "FirstConfirmedAt": utc_now_iso(b.first_confirmed_at) if b.first_confirmed_at else None,
                }
                for b in snap.bindings
            ],
            "ActionInFlight": (
                {
                    "ActionType": _val(inflight.action_type),
                    "ActionState": _val(inflight.action_state),
                    "HoldCode": inflight.hold_code,
                }
                if inflight
                else None
            ),
        },
    }


def converted_state(snap: Snapshot, decision: Decision) -> dict[str, Any]:
    """Facts 轉成的狀態：查案第二步。"""
    d = facts_digest(snap)
    own = int(d.get("own_hold_count") or 0)
    inflight = d.get("in_flight") or ""
    return {
        "lifecycle": d.get("lifecycle"),
        "work_state": _val(decision.work_state),
        "protection_state": _val(decision.protection_state),
        "ai_state": _val(decision.ai_state),
        "hold_present": own > 0,
        "ours_hold_count": own,
        "hold_query": d.get("hold_query"),
        "hold_query_ok": d.get("hold_query") in {"FOUND", "NOT_FOUND"},
        "unverified_set_hold": bool(inflight.startswith("SET_HOLD")),
        "unverified_release": bool(inflight.startswith("SET_RELEASE")),
        "ai_gate": d.get("ai_status"),
        "expected_count": d.get("expected_wafers"),
        "missing_count": d.get("missing_count"),
        "new_hold_allowed": d.get("control") == "ENABLED",
        "defect_handoff_ready": bool(d.get("has_defect_hold")),
    }


def emit_decision(
    function_code: str,
    snap: Snapshot,
    decision: Decision,
    order: HoldOrder | None,
    rec_time=None,
    *,
    force: bool = False,
    observation_phase: str = "before_action",
) -> None:
    rec_time = rec_time or (order.last_evaluated_at if order else None)
    if (
        not force
        and order
        and order.last_rule_id == decision.rule_id
        and order.work_state == decision.work_state
        and order.state_reason == decision.reason
    ):
        return
    observed = observed_facts(
        snap,
        rec_time=rec_time,
        include_flow_steps=_val(decision.business_action) == "SELECT_TARGET",
    )
    if function_code == "SET_DEFAULT_HOLD_BY_Operation_Start":
        observed.pop("AiScan", None)
    state = converted_state(snap, decision)
    if function_code == "SET_DEFAULT_HOLD_BY_Operation_Start":
        for k in ("ai_gate", "expected_count", "missing_count"):
            state.pop(k, None)
    decide_loc = ""
    run_loc = ""
    try:
        from vai_hold.locator import first_loc

        loc = _locator_cache()
        decide_loc = first_loc(loc, decision.rule_id, prefer="domain/derive")
        action = _val(decision.business_action)
        if action == "VERIFY_HOLD":
            run_loc = first_loc(loc, "A2-02", prefer="usecases/verify_hold")
        elif action == "VERIFY_RELEASE":
            run_loc = first_loc(loc, "A2-11", prefer="usecases/verify_release")
        elif action == "SET_HOLD":
            run_loc = first_loc(loc, "event:HOLD_INTENT", prefer="usecases/request_hold")
        elif action == "SET_RELEASE":
            run_loc = first_loc(loc, "event:RELEASE_INTENT", prefer="usecases/request_release")
        elif action == "TRANSFER_HOLD":
            run_loc = first_loc(loc, "event:TRANSFER_INTENT", prefer="usecases/request_transfer")
        elif action == "SELECT_TARGET":
            run_loc = first_loc(loc, "A1-02", prefer="set_default_hold")
            if not run_loc or "derive" in run_loc:
                run_loc = "vai_hold/application/pipelines/set_default_hold.py:run"
        else:
            run_loc = first_loc(loc, decision.rule_id, prefer="pipelines")
    except Exception:
        pass
    decision_block = {
        "rule_id": decision.rule_id,
        "reason": decision.reason,
        "action": _val(decision.business_action),
        "judge_loc": decide_loc,
        "run_loc": run_loc,
    }
    extra = order_fields(order)
    if order is not None:
        extra["order_row_version"] = order.row_version
    emit(
        Event.EVAL,
        extra=extra,
        function_code=function_code,
        observation_phase=observation_phase,
        observed=observed,
        state=state,
        decision=decision_block,
    )
    emit(
        Event.DECISION,
        extra=extra,
        function_code=function_code,
        observation_phase=observation_phase,
        rule_id=decision.rule_id,
        work_state=decision.work_state,
        action=decision.business_action,
        reason=decision.reason,
        facts=facts_digest(snap),
        judge_loc=decide_loc,
        run_loc=run_loc,
    )
    lot = extra.get("lot_id") or ""
    logger.info(
        "[VAI_EVAL] %s lot=%s\n  OBSERVED %s\n  STATE %s\n  DECISION %s %s action=%s\n  JUDGE %s\n  RUN %s",
        function_code,
        lot,
        json.dumps(observed, ensure_ascii=False, default=str),
        json.dumps(state, ensure_ascii=False, default=str),
        decision.rule_id,
        decision.reason,
        _val(decision.business_action),
        decide_loc,
        run_loc,
    )
