from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from vai_hold.application.ids import new_id
from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import record_receipt, refuse_unscoped_lot
from vai_hold.domain.enums import ActionState, ActionType, FunctionCode, ReceiptOutcome
from vai_hold.domain.mes_payload import freeze_hold_command, thaw_hold_command
from vai_hold.domain.models import ActionCommand, Decision, HoldCommand, HoldOrder
from vai_hold.domain.ownership import is_smm_hold
from vai_hold.domain.retry import attempts_for
from vai_hold.domain.target import smm_hold_ope_no

if TYPE_CHECKING:
    from vai_hold.application.engine import App
    from vai_hold.application.ports.persistence import UnitOfWork
    from vai_hold.domain.derive import Snapshot

FN = FunctionCode.CHECK_AI.value


def request_transfer(
    app: App, uow: UnitOfWork, order: HoldOrder, snap: Snapshot, decision: Decision, now: datetime
) -> bool:
    """Update SmmHold memo in place (same Code/User). New memo = new logical action."""
    if refuse_unscoped_lot(app, order, function_code=FN):
        return False
    new_memo = decision.memo
    if not new_memo:
        return False
    history = uow.actions.list_history(order.order_id)
    retry_cmds = [
        c
        for c in uow.actions.list_by_order(order.order_id)
        if c.action_type == ActionType.TRANSFER_HOLD
        and c.action_state == ActionState.RETRY_WAIT
        and c.expected_postcondition == new_memo
    ]
    current = _current_smm(app, snap, order)
    if current is None:
        return False

    if retry_cmds:
        cmd = retry_cmds[-1]
        if attempts_for(cmd.command_id, history) >= app.settings.max_action_attempts:
            return False
        cmd.action_state = ActionState.PREPARED
        cmd.updated_at = now
        uow.actions.save_command(cmd)
        uow.commit()
        frozen = thaw_hold_command(cmd.payload_json) if cmd.payload_json else current
        memo = frozen.new_memo or cmd.expected_postcondition or new_memo
        return _send(app, uow, order, cmd, frozen, memo, decision, now)

    if uow.actions.get_in_flight(order.order_id):
        return False
    logical = f"{order.order_id}|TRANSFER|{current.ope_no}|{current.hold_code}|{new_memo}"
    packed = HoldCommand(
        lot_id=current.lot_id,
        route_id=current.route_id,
        ope_no=current.ope_no,
        memo=current.memo,
        hold_code=current.hold_code,
        hold_user=current.hold_user,
        idempotency_key=logical,
        new_memo=new_memo,
    )
    payload, payload_hash = freeze_hold_command(packed)
    cmd = ActionCommand(
        command_id=new_id(),
        order_id=order.order_id,
        logical_action_key=logical,
        action_type=ActionType.TRANSFER_HOLD,
        idempotency_key=logical,
        action_state=ActionState.PREPARED,
        created_at=now,
        updated_at=now,
        hold_code=current.hold_code,
        target_occurrence=current.ope_no,
        expected_postcondition=new_memo,
        payload_json=payload,
        payload_hash=payload_hash,
    )
    emit(
        Event.TRANSFER_INTENT,
        function_code=FN,
        rule_id=decision.rule_id,
        hold_code=current.hold_code,
        command_id=cmd.command_id,
        extra=order_fields(order),
    )
    uow.actions.insert_prepared(cmd)
    uow.commit()
    return _send(app, uow, order, cmd, packed, new_memo, decision, now)


def verify_transfer(app: App, uow: UnitOfWork, order: HoldOrder, snap: Snapshot, now: datetime) -> None:
    inflight = snap.in_flight
    if inflight is None or inflight.action_type != ActionType.TRANSFER_HOLD:
        return
    desired = inflight.expected_postcondition
    current = _current_smm(app, snap, order)
    if current is not None and desired and current.memo == desired:
        inflight.action_state = ActionState.CONFIRMED
        inflight.updated_at = now
        uow.actions.save_command(inflight)
        emit(Event.TRANSFER_CONFIRMED, function_code=FN, rule_id="A2-16", extra=order_fields(order))
        return
    from vai_hold.domain.enums import SourceStatus

    if inflight.action_state == ActionState.UNKNOWN and snap.hold_query.status in (
        SourceStatus.FOUND,
        SourceStatus.NOT_FOUND,
    ):
        n = attempts_for(inflight.command_id, uow.actions.list_history(order.order_id))
        if n < app.settings.max_action_attempts:
            inflight.action_state = ActionState.RETRY_WAIT
            inflight.updated_at = now
            uow.actions.save_command(inflight)
            return
        inflight.action_state = ActionState.REJECTED
        inflight.expected_postcondition = desired or "RETRY_EXHAUSTED"
        inflight.updated_at = now
        uow.actions.save_command(inflight)
        emit(Event.TRANSFER_FAILED, function_code=FN, rule_id="A2-18", extra=order_fields(order))


def _current_smm(app: App, snap: Snapshot, order: HoldOrder) -> HoldCommand | None:
    from vai_hold.domain.enums import SourceStatus

    if snap.hold_query.status not in (SourceStatus.FOUND, SourceStatus.NOT_FOUND):
        return None
    fv = snap.flow_query.value if snap.flow_query.status == SourceStatus.FOUND else None
    ope = smm_hold_ope_no(fv, order.target_hold_ope_no, snap.smm_hold_step)
    for h in snap.hold_query.value or []:
        if is_smm_hold(
            h,
            lot_id=order.lot_id,
            hold_code=snap.smm_hold_code,
            hold_user=snap.smm_hold_user,
            ope_no=ope,
        ):
            return h
    return None


def _send(app, uow, order, cmd, current: HoldCommand, new_memo: str, decision: Decision, now: datetime) -> bool:
    emit(Event.TRANSFER_SENT, function_code=FN, rule_id=decision.rule_id, extra=order_fields(order))
    receipt = app.hold.transfer_hold(current, current.new_memo or new_memo)
    record_receipt(
        app, uow, cmd, receipt, now, decision.rule_id,
        function_code=FN, event=Event.TRANSFER_RECEIPT, order=order,
    )
    if receipt.outcome == ReceiptOutcome.REJECTED and cmd.action_state != ActionState.RETRY_WAIT:
        cmd.expected_postcondition = new_memo
        uow.actions.save_command(cmd)
    uow.commit()
    return True
