from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from vai_hold.application.ids import new_id
from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import record_receipt, refuse_unscoped_lot
from vai_hold.domain.enums import (
    ActionState,
    ActionType,
    BindingRole,
    BindingStatus,
    FunctionCode,
    HoldKind,
    ProtectionState,
    ReceiptOutcome,
    WorkState,
)
from vai_hold.domain.mes_payload import freeze_hold_command, thaw_hold_command
from vai_hold.domain.models import ActionCommand, Decision, HoldBinding, HoldCommand, HoldOrder, HoldTarget
from vai_hold.domain.retry import attempts_for

if TYPE_CHECKING:
    from vai_hold.application.engine import App
    from vai_hold.application.ports.persistence import UnitOfWork

FN = FunctionCode.SET_DEFAULT_HOLD.value


def request_hold(app: App, uow: UnitOfWork, order: HoldOrder, decision: Decision, now: datetime) -> bool:
    """Atomic: persist intent, commit, call MES, record receipt.

    Same logical action reuses command_id / idempotency_key; attempt_no increments up to max_attempts.
    """
    if refuse_unscoped_lot(app, order, function_code=FN):
        return False
    code = decision.hold_code or app.settings.hold_codes[0]
    history = uow.actions.list_history(order.order_id)
    existing = [
        c
        for c in uow.actions.list_by_order(order.order_id)
        if c.action_type == ActionType.SET_HOLD
        and c.hold_code == code
        and c.action_state == ActionState.RETRY_WAIT
    ]
    if existing:
        cmd = existing[-1]
        if attempts_for(cmd.command_id, history) >= app.settings.max_action_attempts:
            return False
        cmd.action_state = ActionState.PREPARED
        cmd.updated_at = now
        uow.actions.save_command(cmd)
        for b in uow.holds.list_by_order(order.order_id):
            if b.role == BindingRole.PREVENTIVE and b.hold_code == code:
                b.status = BindingStatus.PENDING
                b.updated_at = now
                uow.holds.update(b)
        order.work_state = WorkState.HOLD_VERIFY_PENDING
        order.protection_state = ProtectionState.SET_PENDING
        order.updated_at = now
        uow.orders.update(order, order.row_version)
        uow.commit()
        hold_cmd = (
            thaw_hold_command(cmd.payload_json)
            if cmd.payload_json
            else HoldCommand(
                lot_id=order.lot_id,
                route_id=order.hold_route_id or "",
                ope_no=order.target_hold_ope_no or cmd.target_occurrence or "",
                memo=app.settings.hold_memo,
                hold_code=code,
                hold_user=app.settings.hold_user,
                tool_id=order.tool_id,
                idempotency_key=cmd.idempotency_key,
            )
        )
        emit(Event.HOLD_SENT, function_code=FN, rule_id=decision.rule_id, hold_code=code, extra=order_fields(order))
        receipt = app.hold.set_hold(hold_cmd)
        record_receipt(
            app, uow, cmd, receipt, now, decision.rule_id,
            function_code=FN, event=Event.HOLD_RECEIPT, order=order,
        )
        if receipt.outcome == ReceiptOutcome.REJECTED and cmd.action_state != ActionState.RETRY_WAIT:
            for b in uow.holds.list_by_order(order.order_id):
                if b.role == BindingRole.PREVENTIVE and b.hold_code == code:
                    b.status = BindingStatus.FAILED
                    b.updated_at = now
                    uow.holds.update(b)
            cmd.expected_postcondition = receipt.normalized_error or "CODE_CONFLICT"
            uow.actions.save_command(cmd)
        uow.commit()
        return True
    if uow.actions.get_in_flight(order.order_id):
        return False
    target = decision.target
    if target is None and order.target_hold_ope_no and order.hold_route_id:
        target = HoldTarget(
            route_id=order.hold_route_id,
            ope_no=order.target_hold_ope_no,
            ope_name=order.future_hold_ope_name or "",
            kind=HoldKind.FUTURE,
            reason=order.target_reason or "",
            flow_version=order.flow_version or "",
        )
    if target is None:
        return False
    gen = 1 + sum(1 for c in uow.actions.list_by_order(order.order_id) if c.action_type == ActionType.SET_HOLD)
    logical = f"{order.order_id}|SET|{gen}|{target.ope_no}|{code}"
    hold_cmd = HoldCommand(
        lot_id=order.lot_id,
        route_id=target.route_id,
        ope_no=target.ope_no,
        memo=app.settings.hold_memo,
        hold_code=code,
        hold_user=app.settings.hold_user,
        tool_id=order.tool_id,
        idempotency_key=logical,
    )
    payload, payload_hash = freeze_hold_command(hold_cmd)
    cmd = ActionCommand(
        command_id=new_id(),
        order_id=order.order_id,
        logical_action_key=logical,
        action_type=ActionType.SET_HOLD,
        idempotency_key=logical,
        action_state=ActionState.PREPARED,
        created_at=now,
        updated_at=now,
        generation=gen,
        hold_code=code,
        target_occurrence=target.ope_no,
        payload_json=payload,
        payload_hash=payload_hash,
    )
    binding = HoldBinding(
        binding_id=new_id(),
        lot_id=order.lot_id,
        route_id=target.route_id,
        ope_no=target.ope_no,
        hold_code=code,
        hold_user=app.settings.hold_user,
        hold_memo=app.settings.hold_memo,
        role=BindingRole.PREVENTIVE,
        status=BindingStatus.PENDING,
        created_at=now,
        updated_at=now,
        order_id=order.order_id,
        generation=gen,
        hold_kind=target.kind,
        time_quality="ESTIMATED",
        requested_at=now,
    )
    emit(
        Event.HOLD_INTENT,
        function_code=FN,
        rule_id=decision.rule_id,
        hold_code=code,
        route_id=target.route_id,
        hold_ope_no=target.ope_no,
        command_id=cmd.command_id,
        extra=order_fields(order),
    )
    uow.actions.insert_prepared(cmd)
    uow.holds.add(binding)
    order.hold_route_id = target.route_id
    order.target_hold_ope_no = target.ope_no
    order.protection_state = ProtectionState.SET_PENDING
    order.work_state = WorkState.HOLD_VERIFY_PENDING
    order.last_rule_id = decision.rule_id
    order.updated_at = now
    uow.orders.update(order, order.row_version)
    uow.commit()

    emit(Event.HOLD_SENT, function_code=FN, rule_id=decision.rule_id, hold_code=code, extra=order_fields(order))
    receipt = app.hold.set_hold(hold_cmd)
    record_receipt(
        app, uow, cmd, receipt, now, decision.rule_id,
        function_code=FN, event=Event.HOLD_RECEIPT, order=order,
    )
    if receipt.outcome == ReceiptOutcome.REJECTED and cmd.action_state != ActionState.RETRY_WAIT:
        binding.status = BindingStatus.FAILED
        binding.updated_at = now
        uow.holds.update(binding)
        cmd.expected_postcondition = receipt.normalized_error or "CODE_CONFLICT"
        uow.actions.save_command(cmd)
    uow.commit()
    return True
