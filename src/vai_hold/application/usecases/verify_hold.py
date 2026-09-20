from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import assign_order, open_incident, persist_projection, snapshot
from vai_hold.domain.derive import derive_state
from vai_hold.domain.enums import (
    ActionState,
    ActionType,
    BindingRole,
    BindingStatus,
    FunctionCode,
    ProtectionState,
    SourceStatus,
    WorkState,
)
from vai_hold.domain.models import HoldOrder
from vai_hold.domain.ownership import match_by_binding
from vai_hold.domain.retry import attempts_for

if TYPE_CHECKING:
    from vai_hold.application.engine import App
    from vai_hold.application.ports.persistence import UnitOfWork
    from vai_hold.domain.derive import Snapshot

FN = FunctionCode.CONFIRM_HOLD.value


def verify_hold(app: App, uow: UnitOfWork, order: HoldOrder, snap: Snapshot, now: datetime) -> None:
    if snap.hold_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
        decision = derive_state(snap)
        if persist_projection(uow, order, decision, now):
            open_incident(
                app, uow, itype="HOLD_QUERY_UNKNOWN", order=order, reason="query unknown",
                now=now, function_code=FN, rule_id="A2-14",
            )
            emit(Event.HOLD_VERIFY_UNKNOWN, function_code=FN, rule_id="A2-14", extra=order_fields(order))
        return
    mes = list(snap.hold_query.value or [])
    pending = [
        b for b in snap.bindings
        if b.role == BindingRole.PREVENTIVE and b.status == BindingStatus.PENDING
    ]
    matched = []
    for b in pending or snap.bindings:
        matched.extend(match_by_binding(mes, b, standard_memo=app.settings.hold_memo, hold_user=app.settings.hold_user))
    inflight = snap.in_flight
    if matched:
        for b in snap.bindings:
            if b.role == BindingRole.PREVENTIVE and b.status == BindingStatus.PENDING:
                hits = match_by_binding(mes, b, standard_memo=app.settings.hold_memo, hold_user=app.settings.hold_user)
                if hits:
                    b.status = BindingStatus.CONFIRMED
                    b.first_confirmed_at = now
                    b.updated_at = now
                    uow.holds.update(b)
        if inflight and inflight.action_type == ActionType.SET_HOLD:
            inflight.action_state = ActionState.CONFIRMED
            inflight.updated_at = now
            uow.actions.save_command(inflight)
        order.protection_state = ProtectionState.CONFIRMED
        order.work_state = WorkState.WAIT_AI
        order.last_rule_id = "A2-02"
        order.updated_at = now
        emit(Event.HOLD_CONFIRMED, function_code=FN, rule_id="A2-02", extra=order_fields(order))
        uow.orders.update(order, order.row_version)
        return

    if inflight and inflight.action_state == ActionState.UNKNOWN:
        if snap.hold_query.status in (SourceStatus.FOUND, SourceStatus.NOT_FOUND) and not matched:
            n = attempts_for(inflight.command_id, uow.actions.list_history(order.order_id))
            if n < app.settings.max_action_attempts:
                inflight.action_state = ActionState.RETRY_WAIT
                inflight.updated_at = now
                uow.actions.save_command(inflight)
                order.work_state = WorkState.NEED_HOLD
                order.protection_state = ProtectionState.FAILED
                order.last_rule_id = "A1-09"
                order.updated_at = now
                uow.orders.update(order, order.row_version)
                emit(Event.HOLD_VERIFY_UNKNOWN, function_code=FN, rule_id="A1-09", extra=order_fields(order))
                return
            inflight.action_state = ActionState.REJECTED
            inflight.expected_postcondition = "RETRY_EXHAUSTED"
            inflight.updated_at = now
            uow.actions.save_command(inflight)
            order.work_state = WorkState.HOLD_FAILED
            order.protection_state = ProtectionState.FAILED
            order.last_rule_id = "A2-18"
            order.updated_at = now
            uow.orders.update(order, order.row_version)
            open_incident(
                app, uow, itype="HOLD_FAILED", order=order, reason="retry exhausted",
                now=now, function_code=FN, rule_id="A2-18",
            )
            emit(Event.HOLD_FAILED, function_code=FN, rule_id="A2-18", extra=order_fields(order))
            return
        order.work_state = WorkState.HOLD_VERIFY_PENDING
        order.protection_state = ProtectionState.UNKNOWN
        order.last_rule_id = "A2-01"
        order.updated_at = now
        uow.orders.update(order, order.row_version)
        open_incident(
            app, uow, itype="HOLD_VERIFY_UNKNOWN", order=order, reason="timeout still unknown",
            now=now, function_code=FN, rule_id="A2-01",
        )
        emit(Event.HOLD_VERIFY_UNKNOWN, function_code=FN, rule_id="A2-01", extra=order_fields(order))
        return
    if inflight and inflight.action_state == ActionState.ACKNOWLEDGED:
        if assign_order(order, now, work_state=WorkState.HOLD_VERIFY_PENDING):
            uow.orders.update(order, order.row_version)
        return
    snap2 = snapshot(app, uow, order)
    decision = derive_state(snap2)
    if persist_projection(uow, order, decision, now):
        if decision.work_state == WorkState.HOLD_FAILED:
            open_incident(
                app, uow, itype="HOLD_FAILED", order=order, reason=decision.reason,
                now=now, function_code=FN, rule_id=decision.rule_id,
            )
            emit(Event.HOLD_FAILED, function_code=FN, rule_id=decision.rule_id, extra=order_fields(order))
