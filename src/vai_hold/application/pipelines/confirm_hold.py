from __future__ import annotations

from typing import TYPE_CHECKING

from vai_hold.application.log import emit, emit_decision, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import (
    claim_order,
    iter_scoped_open_orders,
    mark_preventive_released,
    open_incident,
    persist_projection,
    snapshot,
    touch_heartbeat,
)
from vai_hold.application.usecases.verify_hold import verify_hold
from vai_hold.domain.derive import derive_state, plan_action
from vai_hold.domain.enums import BusinessAction, FunctionCode, WorkState

if TYPE_CHECKING:
    from vai_hold.application.engine import App, RunResult

FN = FunctionCode.CONFIRM_HOLD.value


def run(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    result = RunResult(FN)
    with app.uow_factory.new() as uow:
        touch_heartbeat(uow, app.clock.now())
        for order in iter_scoped_open_orders(app, uow, int(params.get("limit") or 500)):
            now = app.clock.now()
            snap = snapshot(app, uow, order)
            decision = plan_action(derive_state(snap), FN)
            if decision.business_action == BusinessAction.VERIFY_HOLD or order.work_state == WorkState.HOLD_VERIFY_PENDING:
                claimed = claim_order(app, uow, order, now)
                if claimed is None:
                    continue
                order = claimed
                snap = snapshot(app, uow, order)
                verify_hold(app, uow, order, snap, now)
                snap = snapshot(app, uow, order)
                emit_decision(FN, snap, decision, order, rec_time=now)
                result.processed += 1
                continue
            if decision.work_state in {
                WorkState.HOLD_FAILED,
                WorkState.OBSERVATION_UNKNOWN,
                WorkState.NEED_BACKUP_HOLD,
                WorkState.CLOSED,
                WorkState.MANUAL_CLOSED,
            }:
                claimed = claim_order(app, uow, order, now)
                if claimed is None:
                    continue
                order = claimed
                emit_decision(FN, snap, decision, order, rec_time=now)
                if decision.business_action == BusinessAction.OPEN_INCIDENT:
                    for t in decision.incidents:
                        open_incident(
                            app, uow, itype=t, order=order, reason=decision.reason,
                            now=now, function_code=FN, rule_id=decision.rule_id,
                        )
                if persist_projection(uow, order, decision, now):
                    if decision.work_state == WorkState.OBSERVATION_UNKNOWN:
                        emit(Event.HOLD_VERIFY_UNKNOWN, extra=order_fields(order), rule_id=decision.rule_id)
                    if decision.reason == "line_released_after_confirmed":
                        mark_preventive_released(uow, order, now)
                    result.processed += 1
        uow.commit()
    return result
