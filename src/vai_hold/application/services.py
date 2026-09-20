from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from vai_hold.application.ids import new_id
from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.domain.derive import Snapshot
from vai_hold.domain.enums import (
    ActionState,
    AiState,
    BindingRole,
    BindingStatus,
    Lifecycle,
    ManualControl,
    ReceiptOutcome,
    SourceStatus,
    WorkState,
)
from vai_hold.domain.ai_complete import expected_complete
from vai_hold.domain.ownership import is_smm_hold
from vai_hold.domain.retry import next_attempt_no, state_after_receipt

_RESOLVE_SKIP = frozenset(
    {
        "STATE_CONFLICT",
        "AGENT_STALL",
        "CONTROL_DISABLED",
        "ORPHAN_HOLD",
        "DEFECT_HOLD_UNCONFIRMED",  # 掃完無 SMM Hold：告警留著當 Order 錯誤紀錄
    }
)
from vai_hold.domain.models import (
    ActionAttempt,
    ActionCommand,
    Decision,
    HoldOrder,
    Incident,
    OutboxRow,
    TransportReceipt,
    WaferAiView,
)

if TYPE_CHECKING:
    from vai_hold.application.engine import App
    from vai_hold.application.ports.persistence import UnitOfWork


def claim_order(app: App, uow: UnitOfWork, order: HoldOrder, now: datetime) -> HoldOrder | None:
    """多台同時跑時，沒搶到租約就不要改這張單、不要送 MES。"""
    from datetime import timedelta

    until = now + timedelta(minutes=2)
    if not uow.orders.try_claim(
        order.order_id, app.worker_id, until, order.row_version, now=now
    ):
        emit(Event.ORDER_SKIP_CLAIM, extra=order_fields(order), lot_id=order.lot_id)
        return None
    return uow.orders.get(order.order_id) or order


def iter_scoped_open_orders(app: App, uow: UnitOfWork, limit: int = 500):
    """Candidate loop：OPEN 且通過 scope.lot_ids。

    有名單時多掃一些 OPEN 列，避免 limit 被範圍外訂單占滿、合法 Lot 永遠輪不到。
    Filter 留在 Application，不推進 DAO。
    """
    want = int(limit or 500)
    scan = 5000 if app.settings.scope_lot_ids else want
    taken = 0
    for order in uow.orders.list_open(scan):
        if not app.settings.allows_lot(order.lot_id):
            continue
        yield order
        taken += 1
        if taken >= want:
            return


def refuse_unscoped_lot(app: App, order: HoldOrder, *, function_code: str) -> bool:
    """True = Lot 不在 scope.lot_ids，不准寫 MES／結案。"""
    if app.settings.allows_lot(order.lot_id):
        return False
    emit(Event.SCOPE_SKIP_LOT, function_code=function_code, extra=order_fields(order), lot_id=order.lot_id)
    return True


def touch_heartbeat(uow: UnitOfWork, now: datetime) -> None:
    uow.cursors.advance("agent_heartbeat", "ok", now, now)


def snapshot(app: App, uow: UnitOfWork, order: HoldOrder, *, persist_ai: bool = False) -> Snapshot:
    hold_q = app.hold.list_holds(order.lot_id)
    flow_q = app.flow.get_flow(order.lot_id, order.rework_count)
    ai_q = app.ai.read_results(order.lot_id, order.rework_count)
    wafers = uow.wafers.list_by_order(order.order_id)
    expected = [w.wafer_id for w in wafers]
    views: list[WaferAiView] = []
    if ai_q.status == SourceStatus.FOUND and ai_q.value:
        views = list(ai_q.value)
    elif ai_q.status == SourceStatus.NOT_FOUND:
        views = []
    # UNKNOWN/STALE: do not pretend local wafers are a successful AI read
    if persist_ai and views:
        now = app.clock.now()
        by_w = {w.wafer_id: w for w in wafers}
        for v in views:
            row = by_w.get(v.wafer_id)
            if row is None:
                continue
            result = (v.result or "").strip() or None
            missing = bool(v.scan_completed_at and not result)
            if missing:
                result = "OK"
            changed = False
            if v.scan_completed_at and row.scan_completed_at != v.scan_completed_at:
                row.scan_completed_at = v.scan_completed_at
                changed = True
            if result and row.ai_result != result:
                row.ai_result = result
                changed = True
            if missing and not row.missing_alarm_type:
                row.missing_alarm_type = True
                changed = True
            if changed:
                row.updated_at = now
                uow.wafers.upsert_ai_result(row)
        wafers = uow.wafers.list_by_order(order.order_id)
    return Snapshot(
        order=order,
        control=uow.control.get("DEFAULT"),
        hold_query=hold_q,
        flow_query=flow_q,
        expected_wafer_ids=expected,
        ai_views=views,
        bindings=uow.holds.list_by_order(order.order_id),
        in_flight=uow.actions.get_in_flight(order.order_id),
        commands=uow.actions.list_by_order(order.order_id),
        standard_memo=app.settings.hold_memo,
        hold_user=app.settings.hold_user,
        hold_codes=list(app.settings.hold_codes),
        station_priority=list(app.settings.station_priority),
        policy_version=app.settings.policy_version,
        ai_query=ai_q,
        smm_hold_code=app.settings.smm_hold_code,
        smm_hold_user=app.settings.smm_hold_user,
        smm_hold_step=app.settings.smm_hold_step,
        smm_memo_template=app.settings.smm_memo_template,
        max_action_attempts=app.settings.max_action_attempts,
    )


def apply_projection(order: HoldOrder, decision: Decision, now: datetime) -> bool:
    """Return False if nothing material changed（避免每分鐘重寫 Order DB／Log）。"""
    data_error = order.data_error
    if decision.work_state == WorkState.DEFECT_HOLD_UNCONFIRMED:
        data_error = "NO_SMM_HOLD_AFTER_SCAN"
    elif order.data_error == "NO_SMM_HOLD_AFTER_SCAN":
        data_error = None
    if (
        order.work_state == decision.work_state
        and order.protection_state == decision.protection_state
        and order.ai_state == decision.ai_state
        and order.last_rule_id == decision.rule_id
        and order.state_reason == decision.reason
        and order.data_error == data_error
        and order.close_reason
        == (
            "AI_OK"
            if decision.work_state == WorkState.CLOSED and decision.ai_state == AiState.COMPLETE_OK
            else "TRANSFERRED"
            if decision.work_state == WorkState.CLOSED
            else "MANUAL"
            if decision.work_state == WorkState.MANUAL_CLOSED
            else order.close_reason
        )
    ):
        return False
    order.work_state = decision.work_state
    order.protection_state = decision.protection_state
    order.ai_state = decision.ai_state
    order.last_rule_id = decision.rule_id
    order.state_reason = decision.reason
    order.data_error = data_error
    order.last_evaluated_at = now
    order.updated_at = now
    if decision.work_state == WorkState.CLOSED:
        order.lifecycle = Lifecycle.CLOSED
        if decision.ai_state == AiState.COMPLETE_OK:
            order.close_reason = "AI_OK"
        else:
            order.close_reason = "TRANSFERRED"
    if decision.work_state == WorkState.MANUAL_CLOSED:
        order.lifecycle = Lifecycle.MANUAL_CLOSED
        order.close_reason = "MANUAL"
    if decision.work_state == WorkState.BLOCKED_BY_CONTROL:
        order.manual_control = ManualControl.BLOCKED
    return True


def persist_projection(uow: UnitOfWork, order: HoldOrder, decision: Decision, now: datetime) -> bool:
    if apply_projection(order, decision, now):
        uow.orders.update(order, order.row_version)
        return True
    return False


def assign_order(order: HoldOrder, now: datetime, **fields) -> bool:
    """只在欄位真的變了才 bump updated_at。"""
    changed = False
    for key, value in fields.items():
        if getattr(order, key) != value:
            setattr(order, key, value)
            changed = True
    if changed:
        order.updated_at = now
    return changed


def maybe_resolve_order_incidents(app, uow, order: HoldOrder, snap, now: datetime) -> None:
    """SMM Hold 在 Default Hold 站，或所有 wafer 已掃完 → 結案該訂單 OPEN 告警。寄信成功即通知結束。"""
    mes = (
        list(snap.hold_query.value or [])
        if snap.hold_query.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND)
        else []
    )
    smm = [
        h
        for h in mes
        if order.target_hold_ope_no
        and is_smm_hold(
            h,
            lot_id=order.lot_id,
            hold_code=app.settings.smm_hold_code,
            hold_user=app.settings.smm_hold_user,
            ope_no=order.target_hold_ope_no,
        )
    ]
    ai_status, _ = expected_complete(snap.expected_wafer_ids, snap.ai_views, rework_count=order.rework_count)
    if not smm and ai_status not in {"COMPLETE_OK", "COMPLETE_DEFECT"}:
        return
    for inc in uow.incidents.list_open(500):
        if inc.incident_type in _RESOLVE_SKIP:
            continue
        if inc.order_id == order.order_id or inc.subject_key == order.order_id:
            uow.incidents.resolve(inc.incident_id, "vai_hold", now)


def mark_preventive_released(uow, order: HoldOrder, now: datetime) -> None:
    for b in uow.holds.list_by_order(order.order_id):
        if b.role == BindingRole.PREVENTIVE and b.status in {
            BindingStatus.PENDING,
            BindingStatus.CONFIRMED,
            BindingStatus.ACTIVE,
            BindingStatus.RELEASE_PENDING,
        }:
            b.status = BindingStatus.RELEASED
            b.released_at = now
            b.updated_at = now
            uow.holds.update(b)


def open_incident(
    app: App,
    uow: UnitOfWork,
    *,
    itype: str,
    order: HoldOrder | None,
    reason: str,
    now: datetime,
    function_code: str,
    episode: str = "1",
    lot_id: str | None = None,
    extra: str | None = None,
    rule_id: str | None = None,
) -> Incident:
    subject = order.order_id if order else (lot_id or "system")
    inc = Incident(
        incident_id=new_id(),
        subject_kind="ORDER" if order else "SYSTEM",
        subject_key=subject,
        incident_type=itype,
        episode_id=episode,
        severity="ERROR",
        status="OPEN",
        first_seen_at=now,
        last_seen_at=now,
        order_id=order.order_id if order else None,
        lot_id=order.lot_id if order else lot_id,
        origin_ope_no=order.origin_ope_no if order else None,
        rework_count=order.rework_count if order else None,
        reason=reason,
        error_detail=extra,
    )
    saved = uow.incidents.open_or_touch(inc)
    created = saved.incident_id == inc.incident_id
    if not created:
        return saved
    emit(
        Event.INCIDENT_OPENED,
        function_code=function_code,
        incident_type=itype,
        incident_id=saved.incident_id,
        reason=reason,
        rule_id=rule_id,
        extra=order_fields(order),
        lot_id=inc.lot_id,
    )
    payload = json.dumps(
        {
            "incident_type": itype,
            "reason": reason,
            "lot_id": inc.lot_id,
            "order_id": inc.order_id,
            "emails": app.settings.notify_emails,
        }
    )
    uow.outbox.enqueue(
        OutboxRow(
            outbox_id=new_id(),
            incident_id=saved.incident_id,
            channel="email",
            payload=payload,
            delivery_status="PENDING",
            created_at=now,
        )
    )
    return saved


def record_receipt(
    app: App,
    uow: UnitOfWork,
    cmd: ActionCommand,
    receipt: TransportReceipt,
    now: datetime,
    rule_id: str,
    *,
    function_code: str,
    event: str,
    order: HoldOrder | None = None,
) -> None:
    history = uow.actions.list_history(cmd.order_id)
    attempt_no = next_attempt_no(cmd.command_id, history)
    attempt = ActionAttempt(
        attempt_id=new_id(),
        command_id=cmd.command_id,
        order_id=cmd.order_id,
        attempt_no=attempt_no,
        started_at=receipt.started_at,
        dispatched_at=receipt.started_at,
        finished_at=receipt.finished_at,
        receipt_outcome=receipt.outcome,
        provider_request_id=receipt.provider_request_id,
        raw_error_code=receipt.raw_error_code,
        normalized_error=receipt.normalized_error,
        retry_class=receipt.retry_class,
        rule_id=rule_id,
        actor=app.worker_id,
    )
    uow.actions.add_attempt(attempt)
    cmd.current_attempt_id = attempt.attempt_id
    cmd.receipt_outcome = receipt.outcome
    cmd.updated_at = now
    cmd.action_state = state_after_receipt(
        receipt,
        attempt_no=attempt_no,
        max_attempts=app.settings.max_action_attempts,
    )
    uow.actions.save_command(cmd)
    emit(
        event,
        function_code=function_code,
        rule_id=rule_id,
        command_id=cmd.command_id,
        attempt_id=attempt.attempt_id,
        attempt_no=attempt_no,
        receipt=receipt.outcome.value,
        hold_code=cmd.hold_code,
        provider_request_id=receipt.provider_request_id,
        normalized_error=receipt.normalized_error,
        raw_error_code=receipt.raw_error_code,
        extra=order_fields(order),
    )
