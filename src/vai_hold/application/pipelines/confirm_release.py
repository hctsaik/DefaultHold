from __future__ import annotations

from typing import TYPE_CHECKING

from vai_hold.application.log import emit_decision
from vai_hold.application.services import claim_order, iter_scoped_open_orders, snapshot, touch_heartbeat
from vai_hold.application.usecases.verify_release import verify_release
from vai_hold.domain.derive import derive_state, plan_action
from vai_hold.domain.enums import ActionType, BusinessAction, FunctionCode, WorkState

if TYPE_CHECKING:
    from vai_hold.application.engine import App, RunResult

FN = FunctionCode.CONFIRM_RELEASE.value


def run(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    result = RunResult(FN)
    with app.uow_factory.new() as uow:
        touch_heartbeat(uow, app.clock.now())
        for order in iter_scoped_open_orders(app, uow, int(params.get("limit") or 500)):
            now = app.clock.now()
            snap = snapshot(app, uow, order)
            decision = plan_action(derive_state(snap), FN)
            in_scope = decision.work_state in {
                WorkState.RELEASE_SENT,
                WorkState.RELEASE_VERIFY_PENDING,
                WorkState.CLOSED,
                WorkState.RELEASE_FAILED,
                WorkState.HOLD_MISSING,
            } or decision.business_action in {
                BusinessAction.VERIFY_RELEASE,
                BusinessAction.NONE,
                BusinessAction.OPEN_INCIDENT,
            }
            has_release = order.work_state in {
                WorkState.RELEASE_SENT,
                WorkState.RELEASE_VERIFY_PENDING,
            } or any(
                c.action_type == ActionType.SET_RELEASE for c in snap.commands
            )
            if in_scope and has_release:
                claimed = claim_order(app, uow, order, now)
                if claimed is None:
                    continue
                order = claimed
                snap = snapshot(app, uow, order)
                verify_release(app, uow, order, snap, now)
                order = uow.orders.get(order.order_id) or order
                snap = snapshot(app, uow, order)
                result.processed += 1
                emit_decision(FN, snap, decision, order, rec_time=now)
        uow.commit()
    return result
