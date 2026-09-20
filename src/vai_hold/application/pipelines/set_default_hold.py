from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from vai_hold.application.ids import new_order_id
from vai_hold.application.log import emit, emit_decision, order_fields
from vai_hold.application.logevents import Event
from vai_hold.application.services import iter_scoped_open_orders, open_incident, persist_projection, snapshot, touch_heartbeat
from vai_hold.application.usecases.request_hold import request_hold
from vai_hold.domain.derive import derive_state, plan_action
from vai_hold.domain.enums import BusinessAction, FunctionCode, SourceStatus, WorkState
from vai_hold.domain.errors import DuplicateOrderError
from vai_hold.domain.models import HoldOrder, InboundEvent, OrderKey, OrderWafer

if TYPE_CHECKING:
    from vai_hold.application.engine import App, RunResult

FN = FunctionCode.SET_DEFAULT_HOLD.value
_SET_WORK = {
    WorkState.NEED_HOLD,
    WorkState.NEED_TARGET,
    WorkState.NEED_BACKUP_HOLD,
}


def run(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    result = RunResult(FN)
    now = app.clock.now()
    with app.uow_factory.new() as uow:
        touch_heartbeat(uow, now)
        events = app.smm.list_start_events(None)
        for ev in events:
            if not app.settings.allows_lot(ev.lot_id):
                continue
            if ev.rework_count is None or not ev.origin_ope_no:
                open_incident(
                    app, uow, itype="DISCOVERY_IDENTITY", order=None,
                    reason="missing rework or ope", now=now, function_code=FN,
                    lot_id=ev.lot_id, rule_id="A1-07",
                )
                emit(Event.DISCOVERY_IDENTITY, function_code=FN, lot_id=ev.lot_id, rule_id="A1-07")
                continue
            if not uow.inbound.try_record(ev):
                continue
            key = OrderKey(ev.lot_id, ev.origin_ope_no, ev.rework_count)
            existing = uow.orders.get_by_key(key)
            if existing is None:
                order = _new_order(app, ev, now)
                try:
                    uow.orders.insert(order)
                except DuplicateOrderError:
                    order = uow.orders.get_by_key(key)
                else:
                    result.created_orders += 1
                    emit(Event.ORDER_CREATED, function_code=FN, rule_id="A1-01", extra=order_fields(order))
                    wafer_ids = [w for w in (ev.payload or "").split(",") if w]
                    if wafer_ids:
                        uow.wafers.replace_roster(
                            order.order_id,
                            1,
                            [
                                OrderWafer(
                                    order_id=order.order_id, wafer_id=w, roster_version=1, updated_at=now
                                )
                                for w in wafer_ids
                            ],
                        )
                        order.manifest_version = 1
                        uow.orders.update(order, order.row_version)
            else:
                order = existing
                watermark = order.last_evaluated_at or order.updated_at
                if ev.event_time and watermark and ev.event_time < watermark:
                    emit(Event.STALE_EVENT, extra=order_fields(order), rule_id="A2-14")
                new_ids = [w for w in (ev.payload or "").split(",") if w]
                old_ids = [w.wafer_id for w in uow.wafers.list_by_order(order.order_id)]
                if old_ids and new_ids and set(old_ids) != set(new_ids):
                    emit(Event.ROSTER_CHANGED, extra=order_fields(order), rule_id="A2-05")
                    open_incident(
                        app, uow, itype="MANUAL_REVIEW", order=order,
                        reason="roster changed", now=now, function_code=FN, rule_id="A2-05",
                    )
                    order.work_state = WorkState.MANUAL_REVIEW
                    order.updated_at = now
                    uow.orders.update(order, order.row_version)
            uow.inbound.mark_consumed(ev.source_event_id, order.order_id if order else None)
        uow.commit()

    with app.uow_factory.new() as uow:
        orders = list(iter_scoped_open_orders(app, uow, int(params.get("limit") or 500)))
        if params.get("order_id"):
            orders = [o for o in orders if o.order_id == params["order_id"]]
        for order in orders:
            now = app.clock.now()
            if order.work_state not in _SET_WORK | {WorkState.HOLD_VERIFY_PENDING}:
                continue
            if order.work_state == WorkState.HOLD_VERIFY_PENDING:
                peek = plan_action(derive_state(snapshot(app, uow, order)), FN)
                # 已送出等 CONFIRM：不要 claim／重寫。RETRY 或清單用盡才由 SET 接著做。
                if peek.business_action == BusinessAction.VERIFY_HOLD:
                    continue
            if not uow.orders.try_claim(
                order.order_id, app.worker_id, now + timedelta(minutes=2), order.row_version, now=now
            ):
                emit(Event.ORDER_SKIP_CLAIM, function_code=FN, extra=order_fields(order))
                continue
            order = uow.orders.get(order.order_id)
            assert order
            snap = snapshot(app, uow, order)
            dirty = False
            if snap.flow_query.status == SourceStatus.FOUND and snap.flow_query.value:
                fv = snap.flow_query.value
                if order.current_ope_no != fv.current_ope_no:
                    order.current_ope_no = fv.current_ope_no
                    dirty = True
                if fv.current_tool_id and order.tool_id != fv.current_tool_id:
                    order.tool_id = fv.current_tool_id
                    dirty = True
            decision = plan_action(derive_state(snap), FN)
            if decision.business_action == BusinessAction.SELECT_TARGET and decision.target:
                order.target_hold_ope_no = decision.target.ope_no
                order.future_hold_ope_name = decision.target.ope_name
                order.hold_route_id = decision.target.route_id
                order.target_reason = decision.target.reason
                order.flow_version = decision.target.flow_version
                order.config_version = app.settings.config_version
                dirty = True
                snap = snapshot(app, uow, order)
                decision = plan_action(derive_state(snap), FN)
            if decision.business_action == BusinessAction.SET_HOLD:
                max_codes = max(1, len(app.settings.hold_codes))
                sent_any = False
                for _ in range(max_codes):
                    if decision.business_action != BusinessAction.SET_HOLD:
                        break
                    emit_decision(
                        FN, snap, decision, order, rec_time=now, observation_phase="before_action"
                    )
                    sent = request_hold(app, uow, order, decision, now)
                    if not sent:
                        break
                    sent_any = True
                    result.holds_sent += 1
                    order = uow.orders.get(order.order_id) or order
                    snap = snapshot(app, uow, order)
                    emit_decision(
                        FN,
                        snap,
                        decision,
                        order,
                        rec_time=now,
                        force=True,
                        observation_phase="after_write",
                    )
                    decision = plan_action(derive_state(snap), FN)
                    # 明確衝突：同一輪立刻改下一個 Code，不等下一分鐘。
                    if (
                        decision.business_action == BusinessAction.SET_HOLD
                        and decision.reason == "backup_hold_code"
                    ):
                        continue
                    break
                if decision.business_action == BusinessAction.OPEN_INCIDENT:
                    for t in decision.incidents:
                        open_incident(
                            app, uow, itype=t, order=order, reason=decision.reason,
                            now=now, function_code=FN, rule_id=decision.rule_id,
                        )
                    persist_projection(uow, order, decision, now)
                    if decision.work_state == WorkState.HOLD_FAILED:
                        emit(
                            Event.HOLD_FAILED,
                            function_code=FN,
                            rule_id=decision.rule_id,
                            extra=order_fields(order),
                        )
                result.processed += 1
                if sent_any:
                    continue
            emit_decision(FN, snap, decision, order, rec_time=now, observation_phase="before_action")
            if decision.business_action == BusinessAction.OPEN_INCIDENT:
                for t in decision.incidents:
                    open_incident(
                        app, uow, itype=t, order=order, reason=decision.reason,
                        now=now, function_code=FN, rule_id=decision.rule_id,
                    )
            projected = persist_projection(uow, order, decision, now)
            if not projected and dirty:
                order.updated_at = now
                uow.orders.update(order, order.row_version)
            result.processed += 1
        uow.commit()
    return result


def _new_order(app: App, ev: InboundEvent, now) -> HoldOrder:
    tool_id = None
    if ev.lot_id and ev.rework_count is not None:
        flow = app.flow.get_flow(ev.lot_id, ev.rework_count)
        if flow.value is not None:
            tool_id = flow.value.current_tool_id
    return HoldOrder(
        order_id=new_order_id(now, tool_id),
        lot_id=ev.lot_id,
        origin_ope_no=ev.origin_ope_no or "",
        rework_count=ev.rework_count or 0,
        policy_version=app.settings.policy_version,
        current_ope_no=ev.origin_ope_no,
        tool_id=tool_id,
        operation_start_at=ev.event_time,
        created_at=now,
        updated_at=now,
        work_state=WorkState.NEED_HOLD,
    )
