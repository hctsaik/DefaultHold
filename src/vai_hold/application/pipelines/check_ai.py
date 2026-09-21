from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

from vai_hold.application.log import emit_decision
from vai_hold.application.services import (
    claim_order,
    iter_scoped_open_orders,
    mark_preventive_released,
    maybe_resolve_order_incidents,
    open_incident,
    persist_projection,
    apply_projection,
    snapshot,
    touch_heartbeat,
)
from vai_hold.application.usecases.request_release import request_release
from vai_hold.domain.derive import derive_state, plan_action
from vai_hold.domain.enums import BusinessAction, FunctionCode, WorkState

if TYPE_CHECKING:
    from vai_hold.application.engine import App, RunResult

FN = FunctionCode.CHECK_AI.value


def run(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    result = RunResult(FN)
    with app.uow_factory.new() as uow:
        touch_heartbeat(uow, app.clock.now())
        for order in iter_scoped_open_orders(app, uow, int(params.get("limit") or 500)):
            now = app.clock.now()
            snap = snapshot(app, uow, order, persist_ai=True)
            decision = plan_action(derive_state(snap), FN)
            emit_decision(
                FN, snap, decision, order, rec_time=now, observation_phase="before_action"
            )
            if decision.business_action == BusinessAction.SET_RELEASE:
                claimed = claim_order(app, uow, order, now)
                if claimed is None:
                    continue
                order = claimed
                snap = snapshot(app, uow, order, persist_ai=True)
                decision = plan_action(derive_state(snap), FN)
            if decision.business_action == BusinessAction.SET_RELEASE:
                sent = request_release(app, uow, order, snap, decision, now)
                if sent:
                    snap = snapshot(app, uow, order, persist_ai=True)
                    result.releases_sent += 1
                    emit_decision(
                        FN, snap, decision, order, rec_time=now, force=True, observation_phase="after_write"
                    )
                maybe_resolve_order_incidents(app, uow, order, snap, now)
                result.processed += 1
                continue
            if decision.work_state in {
                WorkState.WAIT_AI,
                WorkState.AI_RESULT_INVALID,
                WorkState.DEFECT_HOLD_UNCONFIRMED,
                WorkState.PROTECTION_CONFIRMED,
                WorkState.HOLD_MISSING,
                WorkState.HOLD_FAILED,
                WorkState.CLOSED,
                WorkState.MANUAL_CLOSED,
            }:
                probe = deepcopy(order)
                if apply_projection(probe, decision, now):
                    claimed = claim_order(app, uow, order, now)
                    if claimed is None:
                        continue
                    order = claimed
                    if persist_projection(uow, order, decision, now):
                        if decision.reason == "line_released_after_confirmed":
                            mark_preventive_released(uow, order, now)
                        snap = snapshot(app, uow, order, persist_ai=False)
                        emit_decision(
                            FN, snap, decision, order, rec_time=now, force=True, observation_phase="after_write"
                        )
                        result.processed += 1
            if decision.business_action == BusinessAction.OPEN_INCIDENT:
                for t in decision.incidents:
                    open_incident(
                        app, uow, itype=t, order=order, reason=decision.reason,
                        now=now, function_code=FN, rule_id=decision.rule_id,
                    )
            maybe_resolve_order_incidents(app, uow, order, snap, now)
        uow.commit()
    return result
