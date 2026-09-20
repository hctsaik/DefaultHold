from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from vai_hold.application.ids import new_id
from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import open_incident, record_receipt, refuse_unscoped_lot
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
from vai_hold.domain.mes_payload import freeze_hold_command, thaw_hold_command
from vai_hold.domain.models import ActionCommand, Decision, HoldCommand, HoldOrder
from vai_hold.domain.ownership import match_by_binding
from vai_hold.domain.retry import attempts_for

if TYPE_CHECKING:
    from vai_hold.application.engine import App
    from vai_hold.application.ports.persistence import UnitOfWork
    from vai_hold.domain.derive import Snapshot

FN = FunctionCode.CHECK_AI.value


def request_release(
    app: App, uow: UnitOfWork, order: HoldOrder, snap: Snapshot, decision: Decision, now: datetime
) -> bool:
    if refuse_unscoped_lot(app, order, function_code=FN):
        return False
    history = uow.actions.list_history(order.order_id)
    retry_cmds = [
        c
        for c in uow.actions.list_by_order(order.order_id)
        if c.action_type == ActionType.SET_RELEASE and c.action_state == ActionState.RETRY_WAIT
    ]
    if retry_cmds:
        cmd = retry_cmds[-1]
        if attempts_for(cmd.command_id, history) >= app.settings.max_action_attempts:
            return False
        cmd.action_state = ActionState.PREPARED
        cmd.updated_at = now
        uow.actions.save_command(cmd)
        bindings = [
            b
            for b in snap.bindings
            if b.role == BindingRole.PREVENTIVE
            and b.status in {BindingStatus.CONFIRMED, BindingStatus.ACTIVE, BindingStatus.RELEASE_PENDING}
        ]
        if not bindings:
            return False
        b = bindings[-1]
        b.status = BindingStatus.RELEASE_PENDING
        b.updated_at = now
        uow.holds.update(b)
        order.work_state = WorkState.RELEASE_SENT
        order.updated_at = now
        uow.orders.update(order, order.row_version)
        uow.commit()
        emit(Event.RELEASE_SENT, function_code=FN, rule_id=decision.rule_id, extra=order_fields(order))
        hold_cmd = thaw_hold_command(cmd.payload_json) if cmd.payload_json else HoldCommand(
            lot_id=b.lot_id,
            route_id=b.route_id,
            ope_no=b.ope_no,
            memo=app.settings.release_memo,
            hold_code=b.hold_code,
            hold_user=b.hold_user,
            idempotency_key=cmd.idempotency_key,
        )
        receipt = app.hold.release_hold(hold_cmd)
        record_receipt(
            app, uow, cmd, receipt, now, decision.rule_id,
            function_code=FN, event=Event.RELEASE_RECEIPT, order=order,
        )
        uow.commit()
        return True
    if uow.actions.get_in_flight(order.order_id):
        return False
    bindings = [
        b
        for b in snap.bindings
        if b.role == BindingRole.PREVENTIVE
        and b.status in {BindingStatus.CONFIRMED, BindingStatus.ACTIVE}
    ]
    if not bindings:
        return False
    mes = list(snap.hold_query.value or [])
    if snap.hold_query.status not in (SourceStatus.FOUND, SourceStatus.NOT_FOUND):
        return False
    b = bindings[-1]
    matched = match_by_binding(
        mes, b, standard_memo=app.settings.hold_memo, hold_user=app.settings.hold_user
    )
    if len(matched) != 1:
        open_incident(
            app, uow, itype="RELEASE_NOT_UNIQUE", order=order,
            reason=f"expected 1 hold matched, got {len(matched)}",
            now=now, function_code=FN, rule_id=decision.rule_id,
        )
        emit(Event.RELEASE_NOT_UNIQUE, function_code=FN, matched=len(matched), extra=order_fields(order))
        return False
    logical = f"{order.order_id}|RELEASE|{b.route_id}|{b.ope_no}|{b.hold_code}"
    hold_cmd = HoldCommand(
        lot_id=b.lot_id,
        route_id=b.route_id,
        ope_no=b.ope_no,
        memo=app.settings.release_memo,
        hold_code=b.hold_code,
        hold_user=b.hold_user,
        idempotency_key=logical,
    )
    payload, payload_hash = freeze_hold_command(hold_cmd)
    cmd = ActionCommand(
        command_id=new_id(),
        order_id=order.order_id,
        logical_action_key=logical,
        action_type=ActionType.SET_RELEASE,
        idempotency_key=logical,
        action_state=ActionState.PREPARED,
        created_at=now,
        updated_at=now,
        hold_code=b.hold_code,
        target_occurrence=b.ope_no,
        payload_json=payload,
        payload_hash=payload_hash,
    )
    emit(
        Event.RELEASE_INTENT,
        function_code=FN,
        rule_id=decision.rule_id,
        hold_code=b.hold_code,
        command_id=cmd.command_id,
        extra=order_fields(order),
    )
    uow.actions.insert_prepared(cmd)
    b.status = BindingStatus.RELEASE_PENDING
    b.release_requested_at = now
    b.updated_at = now
    uow.holds.update(b)
    order.work_state = WorkState.RELEASE_SENT
    order.protection_state = ProtectionState.RELEASE_PENDING
    order.last_rule_id = decision.rule_id
    order.ai_state = decision.ai_state
    order.updated_at = now
    uow.orders.update(order, order.row_version)
    uow.commit()
    emit(Event.RELEASE_SENT, function_code=FN, rule_id=decision.rule_id, extra=order_fields(order))
    receipt = app.hold.release_hold(hold_cmd)
    record_receipt(
        app, uow, cmd, receipt, now, decision.rule_id,
        function_code=FN, event=Event.RELEASE_RECEIPT, order=order,
    )
    uow.commit()
    return True
