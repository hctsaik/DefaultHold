from __future__ import annotations

from copy import deepcopy
from datetime import datetime

from vai_hold.adapters.persistence.memory.store import MemoryStore
from vai_hold.domain.enums import ActionState
from vai_hold.domain.errors import ConcurrencyError, ConstraintError, DuplicateOrderError
from vai_hold.domain.models import (
    IN_FLIGHT_ACTION_STATES,
    ActionAttempt,
    ActionCommand,
    DiscoveryCursor,
    HoldBinding,
    HoldOrder,
    InboundEvent,
    Incident,
    ObservationSnapshot,
    OrderKey,
    OrderWafer,
    OutboxRow,
    SystemControl,
)


class _Orders:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get(self, order_id: str) -> HoldOrder | None:
        row = self._s.orders.get(order_id)
        return deepcopy(row) if row else None

    def get_by_key(self, key: OrderKey) -> HoldOrder | None:
        oid = self._s.orders_by_key.get(key.as_tuple())
        return self.get(oid) if oid else None

    def insert(self, order: HoldOrder) -> None:
        key = order.key.as_tuple()
        if key in self._s.orders_by_key:
            raise DuplicateOrderError(f"duplicate order key {key}")
        if order.order_id in self._s.orders:
            raise DuplicateOrderError(f"duplicate order_id {order.order_id}")
        self._s.orders[order.order_id] = deepcopy(order)
        self._s.orders_by_key[key] = order.order_id

    def update(self, order: HoldOrder, expected_version: int) -> None:
        cur = self._s.orders.get(order.order_id)
        if cur is None:
            raise ConcurrencyError("order missing")
        if cur.row_version != expected_version:
            raise ConcurrencyError("row_version mismatch")
        if cur.origin_ope_no != order.origin_ope_no:
            raise ConstraintError("origin_ope_no is immutable")
        order.row_version = expected_version + 1
        self._s.orders[order.order_id] = deepcopy(order)

    def list_open(self, limit: int = 500) -> list[HoldOrder]:
        rows = [deepcopy(o) for o in self._s.orders.values() if o.lifecycle.value == "OPEN"]
        rows.sort(key=lambda o: (o.created_at or datetime.min, o.order_id))
        return rows[:limit]

    def list_all(self, limit: int = 2000) -> list[HoldOrder]:
        rows = [deepcopy(o) for o in self._s.orders.values()]
        rows.sort(key=lambda o: (o.created_at or datetime.min, o.order_id))
        return rows[:limit]

    def try_claim(
        self,
        order_id: str,
        worker_id: str,
        until: datetime,
        expected_version: int,
        now: datetime | None = None,
    ) -> bool:
        cur = self._s.orders.get(order_id)
        if cur is None or cur.row_version != expected_version:
            return False
        clock = now if now is not None else until
        if (
            cur.claim_owner
            and cur.claim_owner != worker_id
            and cur.claim_until
            and cur.claim_until > clock
        ):
            return False
        cur.claim_owner = worker_id
        cur.claim_until = until
        cur.row_version = expected_version + 1
        return True

    def release_claim(self, order_id: str, worker_id: str) -> None:
        cur = self._s.orders.get(order_id)
        if cur and cur.claim_owner == worker_id:
            cur.claim_owner = None
            cur.claim_until = None


class _Wafers:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def replace_roster(self, order_id: str, roster_version: int, wafers: list[OrderWafer]) -> None:
        self._s.wafers[order_id] = [deepcopy(w) for w in wafers]

    def list_by_order(self, order_id: str) -> list[OrderWafer]:
        return [deepcopy(w) for w in self._s.wafers.get(order_id, [])]

    def upsert_ai_result(self, row: OrderWafer) -> None:
        items = self._s.wafers.setdefault(row.order_id, [])
        for i, w in enumerate(items):
            if w.wafer_id == row.wafer_id:
                items[i] = deepcopy(row)
                return
        items.append(deepcopy(row))


class _Bindings:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def add(self, binding: HoldBinding) -> None:
        if binding.hold_token:
            for b in self._s.bindings.values():
                if b.hold_token == binding.hold_token:
                    raise ConstraintError("duplicate hold_token")
        self._s.bindings[binding.binding_id] = deepcopy(binding)

    def update(self, binding: HoldBinding) -> None:
        if binding.binding_id not in self._s.bindings:
            raise ConstraintError("binding missing")
        self._s.bindings[binding.binding_id] = deepcopy(binding)

    def list_by_order(self, order_id: str) -> list[HoldBinding]:
        return [deepcopy(b) for b in self._s.bindings.values() if b.order_id == order_id]

    def find_by_mes_tuple(self, lot_id, route_id, ope_no, hold_code, hold_user) -> list[HoldBinding]:
        return [
            deepcopy(b)
            for b in self._s.bindings.values()
            if b.lot_id == lot_id
            and b.route_id == route_id
            and b.ope_no == ope_no
            and b.hold_code == hold_code
            and b.hold_user == hold_user
        ]

    def list_all(self) -> list[HoldBinding]:
        return [deepcopy(b) for b in self._s.bindings.values()]


class _Actions:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get_command(self, command_id: str) -> ActionCommand | None:
        row = self._s.commands.get(command_id)
        return deepcopy(row) if row else None

    def get_in_flight(self, order_id: str) -> ActionCommand | None:
        cands = [
            c
            for c in self._s.commands.values()
            if c.order_id == order_id and c.action_state in IN_FLIGHT_ACTION_STATES
        ]
        if not cands:
            return None
        cands.sort(key=lambda c: c.created_at)
        return deepcopy(cands[-1])

    def list_by_order(self, order_id: str) -> list[ActionCommand]:
        rows = [deepcopy(c) for c in self._s.commands.values() if c.order_id == order_id]
        rows.sort(key=lambda c: c.created_at)
        return rows

    def insert_prepared(self, command: ActionCommand) -> None:
        if any(c.idempotency_key == command.idempotency_key for c in self._s.commands.values()):
            raise ConstraintError("duplicate idempotency_key")
        if any(c.logical_action_key == command.logical_action_key for c in self._s.commands.values()):
            raise ConstraintError("duplicate logical_action_key")
        self._s.commands[command.command_id] = deepcopy(command)

    def save_command(self, command: ActionCommand) -> None:
        self._s.commands[command.command_id] = deepcopy(command)

    def add_attempt(self, attempt: ActionAttempt) -> None:
        self._s.history[attempt.attempt_id] = deepcopy(attempt)

    def list_history(self, order_id: str) -> list[ActionAttempt]:
        rows = [deepcopy(a) for a in self._s.history.values() if a.order_id == order_id]
        rows.sort(key=lambda a: (a.command_id, a.attempt_no))
        return rows


class _Incidents:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def open_or_touch(self, incident: Incident) -> Incident:
        for existing in self._s.incidents.values():
            if (
                existing.subject_key == incident.subject_key
                and existing.incident_type == incident.incident_type
                and existing.episode_id == incident.episode_id
            ):
                return deepcopy(existing)
        self._s.incidents[incident.incident_id] = deepcopy(incident)
        return deepcopy(incident)

    def get_open(self, subject_key: str, incident_type: str) -> Incident | None:
        for i in self._s.incidents.values():
            if i.subject_key == subject_key and i.incident_type == incident_type and i.status == "OPEN":
                return deepcopy(i)
        return None

    def list_open(self, limit: int = 500) -> list[Incident]:
        rows = [deepcopy(i) for i in self._s.incidents.values() if i.status == "OPEN"]
        return rows[:limit]

    def resolve(self, incident_id: str, actor: str, at: datetime) -> None:
        i = self._s.incidents[incident_id]
        i.status = "RESOLVED"
        i.resolved_by = actor
        i.resolved_at = at


class _Outbox:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def enqueue(self, row: OutboxRow) -> None:
        self._s.outbox[row.outbox_id] = deepcopy(row)

    def list_pending(self, now: datetime, limit: int = 100) -> list[OutboxRow]:
        rows = []
        for r in self._s.outbox.values():
            if r.delivery_status in {"PENDING", "FAILED"}:
                if r.next_retry_at is None or r.next_retry_at <= now:
                    rows.append(deepcopy(r))
        rows.sort(key=lambda r: r.created_at)
        return rows[:limit]

    def mark_sent(self, outbox_id: str, at: datetime, provider_msg_id: str | None) -> None:
        r = self._s.outbox[outbox_id]
        r.delivery_status = "SENT"
        r.sent_at = at
        r.provider_msg_id = provider_msg_id

    def mark_failed(self, outbox_id: str, at: datetime, error: str, next_retry_at: datetime) -> None:
        r = self._s.outbox[outbox_id]
        r.delivery_status = "FAILED"
        r.last_error = error
        r.next_retry_at = next_retry_at
        r.attempt_count += 1

    def mark_acked(self, outbox_id: str, at: datetime) -> None:
        r = self._s.outbox[outbox_id]
        r.delivery_status = "ACKED"
        r.acked_at = at

    def get(self, outbox_id: str) -> OutboxRow | None:
        r = self._s.outbox.get(outbox_id)
        return deepcopy(r) if r else None


class _Control:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get(self, scope: str) -> SystemControl:
        return deepcopy(self._s.control[scope])

    def save(self, control: SystemControl, expected_version: int) -> None:
        cur = self._s.control[control.scope]
        if cur.control_version != expected_version:
            raise ConcurrencyError("control version")
        control.control_version = expected_version + 1
        self._s.control[control.scope] = deepcopy(control)


class _Snaps:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def put(self, snap: ObservationSnapshot) -> None:
        self._s.snapshots[snap.snapshot_id] = deepcopy(snap)

    def get(self, snapshot_id: str) -> ObservationSnapshot | None:
        r = self._s.snapshots.get(snapshot_id)
        return deepcopy(r) if r else None


class _Cursors:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def get(self, name: str) -> DiscoveryCursor | None:
        r = self._s.cursors.get(name)
        return deepcopy(r) if r else None

    def advance(self, name: str, last_event_id: str, last_event_time: datetime, at: datetime) -> None:
        self._s.cursors[name] = DiscoveryCursor(
            cursor_name=name,
            last_event_id=last_event_id,
            last_event_time=last_event_time,
            updated_at=at,
        )


class _Inbound:
    def __init__(self, store: MemoryStore) -> None:
        self._s = store

    def try_record(self, event: InboundEvent) -> bool:
        if event.source_event_id in self._s.inbound:
            return False
        self._s.inbound[event.source_event_id] = deepcopy(event)
        return True

    def list_unconsumed(self, limit: int = 500) -> list[InboundEvent]:
        rows = [deepcopy(e) for e in self._s.inbound.values() if not e.consumed]
        rows.sort(key=lambda e: (e.event_time or e.created_at, e.source_event_id))
        return rows[:limit]

    def mark_consumed(self, source_event_id: str, order_id: str | None) -> None:
        e = self._s.inbound[source_event_id]
        e.consumed = True
        e.order_id = order_id

    def get(self, source_event_id: str) -> InboundEvent | None:
        r = self._s.inbound.get(source_event_id)
        return deepcopy(r) if r else None


class MemoryUnitOfWork:
    def __init__(self, live: MemoryStore) -> None:
        self._live = live
        self._working: MemoryStore | None = None
        self._committed = False
        self.orders = None  # type: ignore
        self.wafers = None
        self.holds = None
        self.actions = None
        self.incidents = None
        self.outbox = None
        self.control = None
        self.snapshots = None
        self.cursors = None
        self.inbound = None

    def __enter__(self) -> MemoryUnitOfWork:
        self._working = self._live.clone()
        self._bind(self._working)
        self._committed = False
        return self

    def _bind(self, store: MemoryStore) -> None:
        self.orders = _Orders(store)
        self.wafers = _Wafers(store)
        self.holds = _Bindings(store)
        self.actions = _Actions(store)
        self.incidents = _Incidents(store)
        self.outbox = _Outbox(store)
        self.control = _Control(store)
        self.snapshots = _Snaps(store)
        self.cursors = _Cursors(store)
        self.inbound = _Inbound(store)

    def commit(self) -> None:
        assert self._working is not None
        self._live.replace_from(self._working)
        self._committed = True

    def rollback(self) -> None:
        self._working = self._live.clone()
        self._bind(self._working)
        self._committed = False

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.rollback()
        elif not self._committed:
            self.rollback()


class MemoryUowFactory:
    def __init__(self) -> None:
        self.store = MemoryStore()

    def new(self) -> MemoryUnitOfWork:
        return MemoryUnitOfWork(self.store)

    def reset(self) -> None:
        self.store = MemoryStore()
