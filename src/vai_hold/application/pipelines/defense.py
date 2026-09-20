from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING

from vai_hold.application.log import emit
from vai_hold.application.logevents import Event
from vai_hold.application.services import (
    iter_scoped_open_orders,
    maybe_resolve_order_incidents,
    open_incident,
    snapshot,
)
from vai_hold.domain.enums import BindingRole, BindingStatus, ControlMode, FunctionCode, Lifecycle, SourceStatus
from vai_hold.domain.ownership import match_our_holds

if TYPE_CHECKING:
    from vai_hold.application.engine import App, RunResult

FN = FunctionCode.DEFENSE.value


def run(app: App, params: dict) -> RunResult:
    from vai_hold.application.engine import RunResult

    result = RunResult(FN)
    now = app.clock.now()
    with app.uow_factory.new() as uow:
        control = uow.control.get("DEFAULT")
        hb = uow.cursors.get("agent_heartbeat")
        if hb and hb.updated_at and now - hb.updated_at > timedelta(minutes=5):
            emit(Event.AGENT_STALL, function_code=FN, rule_id="D-06")
            open_incident(
                app, uow, itype="AGENT_STALL", order=None,
                reason="agent heartbeat stale", now=now, function_code=FN, rule_id="D-06",
            )
        overdue_lots: set[str] = set()
        owned: set[tuple] = set()
        for order in uow.orders.list_all(2000):
            if not app.settings.allows_lot(order.lot_id):
                continue
            for b in uow.holds.list_by_order(order.order_id):
                if b.role == BindingRole.PREVENTIVE:
                    owned.add((b.lot_id, b.route_id, b.ope_no, b.hold_code, b.hold_user))
            snap = snapshot(app, uow, order)
            if order.lifecycle == Lifecycle.CLOSED:
                mes = list(snap.hold_query.value or []) if snap.hold_query.value else []
                own = match_our_holds(
                    mes, order, snap.bindings,
                    standard_memo=app.settings.hold_memo, hold_user=app.settings.hold_user,
                )
                if own:
                    open_incident(
                        app, uow, itype="STATE_CONFLICT", order=order, reason="closed with hold",
                        now=now, function_code=FN, rule_id="D-05",
                    )
                continue
            bindings = uow.holds.list_by_order(order.order_id)
            prev = [
                b
                for b in bindings
                if b.role == BindingRole.PREVENTIVE
                and b.status in {BindingStatus.CONFIRMED, BindingStatus.ACTIVE, BindingStatus.PENDING}
            ]
            for b in prev:
                start = b.first_confirmed_at or b.requested_at
                if start and now - start > timedelta(minutes=app.settings.watchdog_minutes):
                    overdue_lots.add(order.lot_id)
                    open_incident(
                        app, uow, itype="HOLD_OVERDUE", order=order,
                        reason=(
                        f"hold older than {app.settings.watchdog_minutes} min "
                        f"(time_quality={b.time_quality or 'ESTIMATED'}; not MES Created)"
                    ),
                        now=now, function_code=FN, rule_id="D-01",
                    )
            if snap.hold_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
                open_incident(
                    app, uow, itype="DATA_UNAVAILABLE", order=order, reason="hold query unknown",
                    now=now, function_code=FN, rule_id="A2-14",
                )
            maybe_resolve_order_incidents(app, uow, order, snap, now)
        lot_ids = {
            k[0] for k in app.smm.expected_keys() if app.settings.allows_lot(k[0])
        } | {o.lot_id for o in uow.orders.list_all(2000) if app.settings.allows_lot(o.lot_id)}
        for lot_id in lot_ids:
            q = app.hold.list_holds(lot_id)
            if q.status not in (SourceStatus.FOUND, SourceStatus.NOT_FOUND):
                continue
            for h in q.value or []:
                if h.memo != app.settings.hold_memo or h.hold_user != app.settings.hold_user:
                    continue
                key = (h.lot_id, h.route_id, h.ope_no, h.hold_code, h.hold_user)
                if key not in owned:
                    emit(Event.ORPHAN_HOLD, function_code=FN, rule_id="D-04", lot_id=lot_id, hold_code=h.hold_code)
                    open_incident(
                        app, uow, itype="ORPHAN_HOLD", order=None, lot_id=lot_id,
                        reason="default hold without order", now=now, function_code=FN, rule_id="D-04",
                    )

        expected = {k for k in app.smm.expected_keys() if app.settings.allows_lot(k[0])}
        actual_keys = {order.key.as_tuple() for order in iter_scoped_open_orders(app, uow, 1000)}
        missing = expected - actual_keys
        extra = actual_keys - expected
        if missing or extra:
            open_incident(
                app, uow, itype="COVERAGE_MISMATCH", order=None,
                reason=f"missing={sorted(missing)} extra={sorted(extra)}",
                now=now, function_code=FN, rule_id="D-03",
                extra=json.dumps({"missing": [list(x) for x in missing], "extra": [list(x) for x in extra]}),
            )

        if len(overdue_lots) >= app.settings.disable_after_overdue_lots and control.mode == ControlMode.ENABLED:
            control.mode = ControlMode.DISABLED_NEW_HOLD
            control.disable_reason = f"overdue_lots={len(overdue_lots)}"
            control.disable_trigger = "WATCHDOG"
            control.disabled_at = now
            control.updated_at = now
            uow.control.save(control, control.control_version)
            emit(Event.CONTROL_DISABLED, function_code=FN, rule_id="D-02", overdue_lots=len(overdue_lots))
            open_incident(
                app, uow, itype="CONTROL_DISABLED", order=None, reason=control.disable_reason,
                now=now, function_code=FN, rule_id="D-02",
            )

        for row in uow.outbox.list_pending(now, 100):
            if row.attempt_count >= app.settings.max_action_attempts:
                continue
            try:
                payload = json.loads(row.payload)
                emails = payload.get("emails") or app.settings.notify_emails
                msg = app.notifier.send(
                    emails,
                    subject=f"[SMM] {payload.get('incident_type')}",
                    body=row.payload,
                )
                uow.outbox.mark_sent(row.outbox_id, now, msg)
                result.emails_sent += 1
                emit(
                    Event.NOTIFY_SENT, function_code=FN, outbox_id=row.outbox_id,
                    incident_type=payload.get("incident_type"),
                )
            except Exception as exc:  # noqa: BLE001
                uow.outbox.mark_failed(row.outbox_id, now, str(exc), now + timedelta(minutes=1))
                emit(Event.NOTIFY_FAILED, function_code=FN, outbox_id=row.outbox_id, error=str(exc))
        uow.commit()
    return result
