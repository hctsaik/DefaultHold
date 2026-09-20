from __future__ import annotations

from typing import TYPE_CHECKING

from vai_hold.application.log import emit, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import open_incident, refuse_unscoped_lot
from vai_hold.domain.enums import ControlMode, FunctionCode, Lifecycle, WorkState

if TYPE_CHECKING:
    from vai_hold.application.engine import App, RunResult


def run_resume(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    fn = FunctionCode.RESUME.value
    sponsor = params.get("sponsor")
    evidence = params.get("evidence")
    now = app.clock.now()
    with app.uow_factory.new() as uow:
        control = uow.control.get("DEFAULT")
        if not sponsor or not evidence:
            open_incident(
                app, uow, itype="RESUME_DENIED", order=None,
                reason="missing sponsor or evidence", now=now, function_code=fn, rule_id="A1-08",
            )
            emit(Event.CONTROL_RESUME_DENIED, function_code=fn)
            uow.commit()
            return RunResult(fn)
        control.mode = ControlMode.ENABLED
        control.sponsor_id = str(sponsor)
        control.sponsor_approved_at = now
        control.resume_evidence_ref = str(evidence)
        control.health_check_ref = str(params.get("health_check") or evidence)
        control.updated_at = now
        uow.control.save(control, control.control_version)
        emit(Event.CONTROL_RESUME, function_code=fn, sponsor=str(sponsor))
        uow.commit()
    return RunResult(fn, processed=1)


def run_manual_close(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    fn = FunctionCode.MANUAL_CLOSE.value
    order_id = params.get("order_id")
    actor = params.get("actor")
    approver = params.get("approver")
    now = app.clock.now()
    if not (order_id and actor and approver):
        return RunResult(fn)
    with app.uow_factory.new() as uow:
        order = uow.orders.get(str(order_id))
        if not order:
            return RunResult(fn)
        if refuse_unscoped_lot(app, order, function_code=fn):
            return RunResult(fn)
        order.lifecycle = Lifecycle.MANUAL_CLOSED
        order.work_state = WorkState.MANUAL_CLOSED
        order.close_reason = "MANUAL"
        order.state_reason = f"actor={actor};approver={approver}"
        order.last_rule_id = "A2-13"
        order.updated_at = now
        uow.orders.update(order, order.row_version)
        emit(Event.MANUAL_CLOSED, function_code=fn, rule_id="A2-13", actor=actor, extra=order_fields(order))
        uow.commit()
    return RunResult(fn, processed=1)
