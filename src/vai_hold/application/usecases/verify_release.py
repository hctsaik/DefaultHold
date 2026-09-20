from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import assign_order, open_incident
from vai_hold.domain.enums import (
    ActionState,
    ActionType,
    BindingRole,
    BindingStatus,
    FunctionCode,
    Lifecycle,
    ProtectionState,
    ReceiptOutcome,
    SourceStatus,
    WorkState,
)
from vai_hold.domain.models import HoldOrder
from vai_hold.domain.ownership import is_smm_hold, match_our_holds
from vai_hold.domain.retry import attempts_for

if TYPE_CHECKING:
    from vai_hold.application.engine import App
    from vai_hold.application.ports.persistence import UnitOfWork
    from vai_hold.domain.derive import Snapshot

FN = FunctionCode.CONFIRM_RELEASE.value


def verify_release(app: App, uow: UnitOfWork, order: HoldOrder, snap: Snapshot, now: datetime) -> None:
    if snap.hold_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
        if assign_order(order, now, work_state=WorkState.OBSERVATION_UNKNOWN):
            uow.orders.update(order, order.row_version)
        return
    mes = list(snap.hold_query.value or [])
    own = match_our_holds(
        mes, order, snap.bindings,
        standard_memo=app.settings.hold_memo, hold_user=app.settings.hold_user,
    )
    release_cmds = [c for c in snap.commands if c.action_type == ActionType.SET_RELEASE]
    latest = release_cmds[-1] if release_cmds else None
    if not own:
        if latest and latest.action_state in {
            ActionState.ACKNOWLEDGED,
            ActionState.UNKNOWN,
            ActionState.CONFIRMED,
            ActionState.PREPARED,
            ActionState.DISPATCHED,
        }:
            if latest.action_state == ActionState.UNKNOWN and snap.hold_query.status != SourceStatus.NOT_FOUND:
                return
            latest.action_state = ActionState.CONFIRMED
            latest.updated_at = now
            uow.actions.save_command(latest)
            for b in snap.bindings:
                if b.role == BindingRole.PREVENTIVE:
                    b.status = BindingStatus.RELEASED
                    b.released_at = now
                    b.release_verified_at = now
                    b.updated_at = now
                    uow.holds.update(b)
            if order.ai_state.value == "COMPLETE_DEFECT":
                smm = [
                    h
                    for h in mes
                    if is_smm_hold(
                        h,
                        lot_id=order.lot_id,
                        hold_code=app.settings.smm_hold_code,
                        hold_user=app.settings.smm_hold_user,
                        ope_no=order.target_hold_ope_no,
                    )
                ]
                if not smm and order.close_reason != "SCAN_COMPLETED":
                    order.work_state = WorkState.DEFECT_HOLD_UNCONFIRMED
                    order.updated_at = now
                    uow.orders.update(order, order.row_version)
                    return
            order.lifecycle = Lifecycle.CLOSED
            order.work_state = WorkState.CLOSED
            order.protection_state = ProtectionState.RELEASED
            if order.close_reason == "SCAN_COMPLETED":
                pass
            elif order.ai_state.value == "COMPLETE_OK":
                order.close_reason = "AI_OK"
            else:
                order.close_reason = "TRANSFERRED"
            order.last_rule_id = "A2-11"
            order.updated_at = now
            emit(Event.RELEASE_CONFIRMED, function_code=FN, rule_id="A2-11", extra=order_fields(order))
            uow.orders.update(order, order.row_version)
            return
    if latest and latest.action_state == ActionState.REJECTED:
        open_incident(
            app, uow, itype="RELEASE_FAILED", order=order, reason="rejected",
            now=now, function_code=FN, rule_id="A2-12",
        )
        emit(Event.RELEASE_FAILED, function_code=FN, rule_id="A2-12", extra=order_fields(order))
        order.work_state = WorkState.RELEASE_FAILED
        order.updated_at = now
        uow.orders.update(order, order.row_version)
        return
    if latest and latest.action_state == ActionState.UNKNOWN:
        # Delay：還看得到自己的 Hold ≠ 沒解成功，不准重送
        if own:
            if assign_order(order, now, work_state=WorkState.RELEASE_VERIFY_PENDING):
                uow.orders.update(order, order.row_version)
            return
            latest.action_state = ActionState.REJECTED
            latest.expected_postcondition = "RETRY_EXHAUSTED"
            latest.updated_at = now
            uow.actions.save_command(latest)
            order.work_state = WorkState.RELEASE_FAILED
            open_incident(
                app, uow, itype="RELEASE_FAILED", order=order, reason="retry exhausted",
                now=now, function_code=FN, rule_id="A2-18",
            )
            emit(Event.RELEASE_FAILED, function_code=FN, rule_id="A2-18", extra=order_fields(order))
            order.updated_at = now
            uow.orders.update(order, order.row_version)
            return
        if assign_order(order, now, work_state=WorkState.RELEASE_VERIFY_PENDING):
            uow.orders.update(order, order.row_version)
        return
    if latest and latest.action_state == ActionState.RETRY_WAIT:
        return
    if own and latest and latest.action_state == ActionState.ACKNOWLEDGED:
        # 已送出且 MES 仍看得到：當 DB Delay，停在查驗格，不重送、不失敗
        if assign_order(order, now, work_state=WorkState.RELEASE_VERIFY_PENDING):
            uow.orders.update(order, order.row_version)
        return
    if own and latest and latest.receipt_outcome == ReceiptOutcome.REJECTED:
        order.work_state = WorkState.RELEASE_FAILED
        open_incident(
            app, uow, itype="RELEASE_FAILED", order=order, reason="hold remains",
            now=now, function_code=FN, rule_id="A2-12",
        )
        emit(Event.RELEASE_FAILED, function_code=FN, rule_id="A2-12", extra=order_fields(order))
        order.updated_at = now
        uow.orders.update(order, order.row_version)
