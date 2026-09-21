from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from vai_hold.domain.enums import (
    ActionState,
    ActionType,
    AiState,
    BindingRole,
    BindingStatus,
    ControlMode,
    HoldKind,
    Lifecycle,
    ManualControl,
    ProtectionState,
    ReceiptOutcome,
    SourceStatus,
    WorkState,
)
from vai_hold.adapters.persistence.schema_sync import SQLITE_SCHEMA, require_sqlite_schema
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
from vai_hold.domain.timeutil import parse_iso, utc_now_iso

def _t(dt: datetime | None) -> str | None:
    return utc_now_iso(dt) if dt else None


def _e(v) -> str | None:
    return None if v is None else (v.value if hasattr(v, "value") else str(v))


class SqliteUnitOfWork:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: sqlite3.Connection | None = None
        self._bind()

    def _bind(self) -> None:
        self.orders = _Orders(self)
        self.wafers = _Wafers(self)
        self.holds = _Bindings(self)
        self.actions = _Actions(self)
        self.incidents = _Incidents(self)
        self.outbox = _Outbox(self)
        self.control = _Control(self)
        self.snapshots = _Snaps(self)
        self.cursors = _Cursors(self)
        self.inbound = _Inbound(self)

    @property
    def conn(self) -> sqlite3.Connection:
        assert self._conn is not None
        return self._conn

    def __enter__(self) -> SqliteUnitOfWork:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("BEGIN")
        return self

    def commit(self) -> None:
        assert self._conn is not None
        self._conn.commit()
        self._conn.execute("BEGIN")

    def rollback(self) -> None:
        assert self._conn is not None
        self._conn.rollback()
        self._conn.execute("BEGIN")

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._conn is None:
            return
        try:
            if exc_type is not None:
                self._conn.rollback()
            else:
                self._conn.commit()
        finally:
            self._conn.close()
            self._conn = None


class SqliteUowFactory:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.executescript(SQLITE_SCHEMA.read_text(encoding="utf-8"))
        require_sqlite_schema(conn)
        conn.commit()
        conn.close()

    def new(self) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(self.path)


def _order_from_row(r: sqlite3.Row) -> HoldOrder:
    return HoldOrder(
        order_id=r["order_id"],
        lot_id=r["lot_id"],
        origin_ope_no=r["origin_operation_id"],
        rework_count=r["rework_count"],
        policy_version=r["policy_version"],
        lifecycle=Lifecycle(r["lifecycle"]),
        protection_state=ProtectionState(r["protection_state"]),
        ai_state=AiState(r["ai_state"]),
        work_state=WorkState(r["work_state"]),
        site_id=r["site_id"],
        current_ope_no=r["current_operation_id"],
        target_hold_ope_no=r["target_hold_operation_id"],
        future_hold_ope_name=r["future_hold_ope_name"] if "future_hold_ope_name" in r.keys() else None,
        hold_route_id=r["hold_route_id"],
        target_reason=r["target_reason"],
        tool_id=r["tool_id"],
        flow_version=r["flow_version"],
        config_version=r["config_version"],
        last_rule_id=r["last_rule_id"],
        state_reason=r["state_reason"],
        close_reason=r["close_reason"],
        data_error=r["data_error"] if "data_error" in r.keys() else None,
        row_version=r["row_version"],
        next_check_at=parse_iso(r["next_check_at"]),
        manual_control=ManualControl(r["manual_control"] or "NONE"),
        claim_owner=r["claim_owner"],
        claim_until=parse_iso(r["claim_until"]),
        operation_start_at=parse_iso(r["operation_start_at"]) if "operation_start_at" in r.keys() else None,
        created_at=parse_iso(r["created_at"]),
        updated_at=parse_iso(r["updated_at"]),
        last_evaluated_at=parse_iso(r["last_evaluated_at"]),
    )


class _Orders:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def get(self, order_id: str) -> HoldOrder | None:
        r = self._u.conn.execute("SELECT * FROM hold_order WHERE order_id=?", (order_id,)).fetchone()
        return _order_from_row(r) if r else None

    def get_by_key(self, key: OrderKey) -> HoldOrder | None:
        r = self._u.conn.execute(
            "SELECT * FROM hold_order WHERE lot_id=? AND origin_operation_id=? AND rework_count=?",
            (key.lot_id, key.ope_no, key.rework_count),
        ).fetchone()
        return _order_from_row(r) if r else None

    def insert(self, o: HoldOrder) -> None:
        try:
            self._u.conn.execute(
                """INSERT INTO hold_order (
                    order_id, site_id, lot_id, origin_operation_id, rework_count,
                    current_operation_id, target_hold_operation_id, future_hold_ope_name, hold_route_id,
                    target_reason, tool_id, flow_version, config_version, policy_version,
                    lifecycle, protection_state, ai_state, work_state,
                    last_rule_id, state_reason, close_reason, data_error, row_version,
                    next_check_at, manual_control, claim_owner, claim_until, created_at, updated_at,
                    operation_start_at, last_evaluated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    o.order_id, o.site_id, o.lot_id, o.origin_ope_no, o.rework_count,
                    o.current_ope_no, o.target_hold_ope_no, o.future_hold_ope_name, o.hold_route_id,
                    o.target_reason, o.tool_id, o.flow_version, o.config_version, o.policy_version,
                    _e(o.lifecycle), _e(o.protection_state), _e(o.ai_state),
                    _e(o.work_state), o.last_rule_id, o.state_reason, o.close_reason, o.data_error,
                    o.row_version, _t(o.next_check_at), _e(o.manual_control),
                    o.claim_owner, _t(o.claim_until), _t(o.created_at), _t(o.updated_at),
                    _t(o.operation_start_at), _t(o.last_evaluated_at),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateOrderError(str(exc)) from exc

    def update(self, o: HoldOrder, expected_version: int) -> None:
        cur = self.get(o.order_id)
        if cur is None or cur.row_version != expected_version:
            raise ConcurrencyError("row_version mismatch")
        if cur.origin_ope_no != o.origin_ope_no:
            raise ConstraintError("origin immutable")
        o.row_version = expected_version + 1
        self._u.conn.execute(
            """UPDATE hold_order SET
                current_operation_id=?, target_hold_operation_id=?, future_hold_ope_name=?, hold_route_id=?,
                target_reason=?, tool_id=?, flow_version=?, config_version=?,
                policy_version=?, lifecycle=?, protection_state=?, ai_state=?,
                work_state=?, last_rule_id=?, state_reason=?, close_reason=?, data_error=?,
                row_version=?, next_check_at=?, manual_control=?, claim_owner=?, claim_until=?,
                updated_at=?, last_evaluated_at=?, operation_start_at=?
                WHERE order_id=? AND row_version=?""",
            (
                o.current_ope_no, o.target_hold_ope_no, o.future_hold_ope_name, o.hold_route_id,
                o.target_reason, o.tool_id, o.flow_version, o.config_version, o.policy_version,
                _e(o.lifecycle), _e(o.protection_state), _e(o.ai_state),
                _e(o.work_state), o.last_rule_id, o.state_reason, o.close_reason, o.data_error,
                o.row_version, _t(o.next_check_at), _e(o.manual_control),
                o.claim_owner, _t(o.claim_until), _t(o.updated_at), _t(o.last_evaluated_at),
                _t(o.operation_start_at),
                o.order_id, expected_version,
            ),
        )
        if self._u.conn.execute("SELECT changes()").fetchone()[0] != 1:
            raise ConcurrencyError("update lost")

    def list_open(self, limit: int = 500) -> list[HoldOrder]:
        rows = self._u.conn.execute(
            "SELECT * FROM hold_order WHERE lifecycle='OPEN' ORDER BY created_at, order_id LIMIT ?",
            (limit,),
        ).fetchall()
        return [_order_from_row(r) for r in rows]

    def list_all(self, limit: int = 2000) -> list[HoldOrder]:
        rows = self._u.conn.execute(
            "SELECT * FROM hold_order ORDER BY created_at, order_id LIMIT ?",
            (limit,),
        ).fetchall()
        return [_order_from_row(r) for r in rows]

    def try_claim(
        self,
        order_id: str,
        worker_id: str,
        until: datetime,
        expected_version: int,
        now: datetime | None = None,
    ) -> bool:
        cur = self.get(order_id)
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
        try:
            self.update(cur, expected_version)
            return True
        except ConcurrencyError:
            return False

    def release_claim(self, order_id: str, worker_id: str) -> None:
        self._u.conn.execute(
            "UPDATE hold_order SET claim_owner=NULL, claim_until=NULL WHERE order_id=? AND claim_owner=?",
            (order_id, worker_id),
        )


class _Wafers:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def replace_roster(self, order_id: str, roster_version: int, wafers: list[OrderWafer]) -> None:
        self._u.conn.execute("DELETE FROM order_wafer WHERE order_id=?", (order_id,))
        for w in wafers:
            self._insert(w)

    def _insert(self, w: OrderWafer) -> None:
        self._u.conn.execute(
            """INSERT INTO order_wafer (order_id, wafer_id, roster_version,
                scan_completed_at, ai_result, defect_types, result_version, updated_at)
                VALUES (?,?,?,?,?,?,?,?)""",
            (
                w.order_id, w.wafer_id, w.roster_version,
                _t(w.scan_completed_at), w.ai_result,
                w.defect_types, w.result_version, _t(w.updated_at),
            ),
        )

    def list_by_order(self, order_id: str) -> list[OrderWafer]:
        rows = self._u.conn.execute(
            "SELECT * FROM order_wafer WHERE order_id=?", (order_id,)
        ).fetchall()
        return [
            OrderWafer(
                order_id=r["order_id"],
                wafer_id=r["wafer_id"],
                roster_version=r["roster_version"],
                updated_at=parse_iso(r["updated_at"]) or datetime.min,
                scan_completed_at=parse_iso(r["scan_completed_at"]),
                ai_result=r["ai_result"],
                defect_types=r["defect_types"],
                result_version=r["result_version"],
            )
            for r in rows
        ]

    def upsert_ai_result(self, row: OrderWafer) -> None:
        existing = self._u.conn.execute(
            "SELECT 1 FROM order_wafer WHERE order_id=? AND wafer_id=?",
            (row.order_id, row.wafer_id),
        ).fetchone()
        if existing:
            self._u.conn.execute(
                """UPDATE order_wafer SET scan_completed_at=?, ai_result=?, defect_types=?,
                    result_version=?, roster_version=?, updated_at=?
                    WHERE order_id=? AND wafer_id=?""",
                (
                    _t(row.scan_completed_at), row.ai_result, row.defect_types, row.result_version,
                    row.roster_version, _t(row.updated_at),
                    row.order_id, row.wafer_id,
                ),
            )
        else:
            self._insert(row)


class _Bindings:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def _write(self, b: HoldBinding) -> None:
        if not b.order_id:
            return
        self._u.conn.execute(
            """UPDATE hold_order SET
                dh_binding_id=?, dh_code=?, dh_user=?, dh_memo=?, dh_status=?, dh_generation=?,
                dh_kind=?, dh_time_quality=?, dh_requested_at=?, dh_first_confirmed_at=?,
                dh_release_requested_at=?, dh_released_at=?,
                hold_route_id=COALESCE(?, hold_route_id),
                target_hold_operation_id=COALESCE(?, target_hold_operation_id)
                WHERE order_id=?""",
            (
                b.binding_id, b.hold_code, b.hold_user, b.hold_memo, _e(b.status), b.generation,
                _e(b.hold_kind), b.time_quality, _t(b.requested_at), _t(b.first_confirmed_at),
                _t(b.release_requested_at), _t(b.released_at),
                b.route_id, b.ope_no, b.order_id,
            ),
        )

    def add(self, b: HoldBinding) -> None:
        self._write(b)

    def update(self, b: HoldBinding) -> None:
        self._write(b)

    def _from(self, r) -> HoldBinding | None:
        if not r["dh_status"]:
            return None
        return HoldBinding(
            binding_id=r["dh_binding_id"] or r["order_id"],
            lot_id=r["lot_id"],
            route_id=r["hold_route_id"] or "",
            ope_no=r["target_hold_operation_id"] or "",
            hold_code=r["dh_code"] or "",
            hold_user=r["dh_user"] or "",
            hold_memo=r["dh_memo"] or "",
            role=BindingRole.PREVENTIVE,
            status=BindingStatus(r["dh_status"]),
            created_at=parse_iso(r["created_at"]) or datetime.min,
            updated_at=parse_iso(r["updated_at"]) or datetime.min,
            order_id=r["order_id"],
            generation=r["dh_generation"] or 1,
            hold_kind=HoldKind(r["dh_kind"]) if r["dh_kind"] else None,
            time_quality=r["dh_time_quality"] or "ESTIMATED",
            requested_at=parse_iso(r["dh_requested_at"]),
            first_confirmed_at=parse_iso(r["dh_first_confirmed_at"]),
            release_requested_at=parse_iso(r["dh_release_requested_at"]),
            released_at=parse_iso(r["dh_released_at"]),
        )

    def list_by_order(self, order_id: str) -> list[HoldBinding]:
        r = self._u.conn.execute("SELECT * FROM hold_order WHERE order_id=?", (order_id,)).fetchone()
        b = self._from(r) if r else None
        return [b] if b else []

    def find_by_mes_tuple(self, lot_id, route_id, ope_no, hold_code, hold_user) -> list[HoldBinding]:
        rows = self._u.conn.execute(
            """SELECT * FROM hold_order WHERE lot_id=? AND hold_route_id=? AND target_hold_operation_id=?
               AND dh_code=? AND dh_user=? AND dh_status IS NOT NULL""",
            (lot_id, route_id, ope_no, hold_code, hold_user),
        ).fetchall()
        return [b for b in (self._from(r) for r in rows) if b]

    def list_all(self) -> list[HoldBinding]:
        rows = self._u.conn.execute("SELECT * FROM hold_order WHERE dh_status IS NOT NULL").fetchall()
        return [b for b in (self._from(r) for r in rows) if b]


class _Actions:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def _latest(self, command_id: str):
        return self._u.conn.execute(
            "SELECT * FROM mes_action WHERE command_id=? ORDER BY attempt_no DESC LIMIT 1",
            (command_id,),
        ).fetchone()

    def _from_cmd(self, r) -> ActionCommand:
        return ActionCommand(
            command_id=r["command_id"],
            order_id=r["order_id"],
            logical_action_key=r["logical_action_key"],
            action_type=ActionType(r["action_type"]),
            idempotency_key=r["idempotency_key"],
            action_state=ActionState(r["action_state"]),
            created_at=parse_iso(r["created_at"]) or datetime.min,
            updated_at=parse_iso(r["updated_at"]) or datetime.min,
            generation=r["generation"],
            hold_code=r["hold_code"],
            target_occurrence=r["target_occurrence"],
            payload_hash=r["payload_hash"],
            payload_json=r["payload_json"],
            receipt_outcome=ReceiptOutcome(r["receipt_outcome"]) if r["receipt_outcome"] else None,
            current_attempt_id=r["attempt_id"],
            expected_postcondition=r["expected_postcondition"],
        )

    def get_command(self, command_id: str) -> ActionCommand | None:
        r = self._latest(command_id)
        return self._from_cmd(r) if r else None

    def get_in_flight(self, order_id: str) -> ActionCommand | None:
        for cmd in reversed(self.list_by_order(order_id)):
            if cmd.action_state in IN_FLIGHT_ACTION_STATES:
                return cmd
        return None

    def list_by_order(self, order_id: str) -> list[ActionCommand]:
        ids = [
            r[0]
            for r in self._u.conn.execute(
                """SELECT command_id FROM mes_action WHERE order_id=?
                   GROUP BY command_id ORDER BY MIN(created_at)""",
                (order_id,),
            ).fetchall()
        ]
        out = []
        for cid in ids:
            cmd = self.get_command(cid)
            if cmd:
                out.append(cmd)
        return out

    def insert_prepared(self, c: ActionCommand) -> None:
        aid = c.current_attempt_id or c.command_id
        try:
            self._u.conn.execute(
                """INSERT INTO mes_action (
                    attempt_id, command_id, order_id, logical_action_key, action_type, generation,
                    hold_code, target_occurrence, idempotency_key, payload_hash, payload_json,
                    action_state, receipt_outcome, expected_postcondition, attempt_no, started_at,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    aid, c.command_id, c.order_id, c.logical_action_key, _e(c.action_type), c.generation,
                    c.hold_code, c.target_occurrence, c.idempotency_key, c.payload_hash, c.payload_json,
                    _e(c.action_state), _e(c.receipt_outcome), c.expected_postcondition, 1,
                    _t(c.created_at), _t(c.created_at), _t(c.updated_at),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ConstraintError(str(exc)) from exc

    def save_command(self, c: ActionCommand) -> None:
        r = self._latest(c.command_id)
        if r is None:
            return
        self._u.conn.execute(
            """UPDATE mes_action SET action_state=?, receipt_outcome=?, expected_postcondition=?,
                updated_at=? WHERE attempt_id=?""",
            (
                _e(c.action_state), _e(c.receipt_outcome), c.expected_postcondition,
                _t(c.updated_at), r["attempt_id"],
            ),
        )

    def add_attempt(self, a: ActionAttempt) -> None:
        dup = self._u.conn.execute(
            "SELECT attempt_id FROM mes_action WHERE command_id=? AND attempt_no=?",
            (a.command_id, a.attempt_no),
        ).fetchone()
        if dup:
            self._u.conn.execute(
                """UPDATE mes_action SET receipt_outcome=?, finished_at=?, dispatched_at=?,
                    provider_request_id=?, raw_error_code=?, normalized_error=?, retry_class=?,
                    raw_response_masked=?, actor=?, rule_id=?, updated_at=? WHERE attempt_id=?""",
                (
                    _e(a.receipt_outcome), _t(a.finished_at), _t(a.dispatched_at),
                    a.provider_request_id, a.raw_error_code, a.normalized_error, a.retry_class,
                    a.raw_response_masked, a.actor, a.rule_id, _t(a.finished_at or a.started_at),
                    dup["attempt_id"],
                ),
            )
            return
        prev = self._latest(a.command_id)
        if prev is None:
            return
        self._u.conn.execute(
            """INSERT INTO mes_action (
                attempt_id, command_id, order_id, logical_action_key, action_type, generation,
                hold_code, target_occurrence, idempotency_key, payload_hash, payload_json,
                action_state, receipt_outcome, expected_postcondition, attempt_no, started_at,
                dispatched_at, finished_at, provider_request_id, raw_error_code, normalized_error,
                retry_class, raw_response_masked, actor, rule_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                a.attempt_id, a.command_id, a.order_id, prev["logical_action_key"], prev["action_type"],
                prev["generation"], prev["hold_code"], prev["target_occurrence"], prev["idempotency_key"],
                prev["payload_hash"], prev["payload_json"], prev["action_state"], _e(a.receipt_outcome),
                prev["expected_postcondition"], a.attempt_no, _t(a.started_at), _t(a.dispatched_at),
                _t(a.finished_at), a.provider_request_id, a.raw_error_code, a.normalized_error,
                a.retry_class, a.raw_response_masked, a.actor, a.rule_id,
                prev["created_at"], _t(a.finished_at or a.started_at),
            ),
        )

    def list_history(self, order_id: str) -> list[ActionAttempt]:
        rows = self._u.conn.execute(
            """SELECT * FROM mes_action WHERE order_id=?
               AND (receipt_outcome IS NOT NULL OR finished_at IS NOT NULL)
               ORDER BY command_id, attempt_no""",
            (order_id,),
        ).fetchall()
        return [
            ActionAttempt(
                attempt_id=r["attempt_id"],
                command_id=r["command_id"],
                order_id=r["order_id"],
                attempt_no=r["attempt_no"],
                started_at=parse_iso(r["started_at"]) or datetime.min,
                dispatched_at=parse_iso(r["dispatched_at"]),
                finished_at=parse_iso(r["finished_at"]),
                receipt_outcome=ReceiptOutcome(r["receipt_outcome"]) if r["receipt_outcome"] else None,
                provider_request_id=r["provider_request_id"],
                raw_error_code=r["raw_error_code"],
                normalized_error=r["normalized_error"],
                retry_class=r["retry_class"],
                raw_response_masked=r["raw_response_masked"],
                actor=r["actor"],
                rule_id=r["rule_id"],
            )
            for r in rows
        ]


class _Incidents:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def _from(self, r) -> Incident:
        return Incident(
            incident_id=r["incident_id"],
            subject_kind=r["subject_kind"],
            subject_key=r["subject_key"],
            incident_type=r["incident_type"],
            episode_id=r["episode_id"],
            severity=r["severity"],
            status=r["status"],
            first_seen_at=parse_iso(r["first_seen_at"]) or datetime.min,
            last_seen_at=parse_iso(r["last_seen_at"]) or datetime.min,
            occurrence_count=r["occurrence_count"],
            order_id=r["order_id"],
            source_event_id=r["source_event_id"],
            lot_id=r["lot_id"],
            origin_ope_no=r["origin_operation_id"],
            rework_count=r["rework_count"],
            reason=r["reason"],
            error_detail=r["error_detail"],
            acked_at=parse_iso(r["acked_at"]),
            acked_by=r["acked_by"],
            resolved_at=parse_iso(r["resolved_at"]),
            resolved_by=r["resolved_by"],
        )

    def open_or_touch(self, incident: Incident) -> Incident:
        r = self._u.conn.execute(
            """SELECT * FROM incident WHERE subject_key=? AND incident_type=? AND episode_id=?""",
            (incident.subject_key, incident.incident_type, incident.episode_id),
        ).fetchone()
        if r:
            # 已存在就不要每輪 Cron 改寫／累加。事後能查到第一筆即可。
            return self._from(r)
        self._u.conn.execute(
            """INSERT INTO incident (
                incident_id, subject_kind, subject_key, order_id, source_event_id, lot_id,
                origin_operation_id, rework_count, incident_type, episode_id, severity, status,
                reason, error_detail, first_seen_at, last_seen_at, occurrence_count
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                incident.incident_id, incident.subject_kind, incident.subject_key, incident.order_id,
                incident.source_event_id, incident.lot_id, incident.origin_ope_no, incident.rework_count,
                incident.incident_type, incident.episode_id, incident.severity, incident.status,
                incident.reason, incident.error_detail,
                _t(incident.first_seen_at), _t(incident.last_seen_at), incident.occurrence_count,
            ),
        )
        return incident

    def get_open(self, subject_key: str, incident_type: str) -> Incident | None:
        r = self._u.conn.execute(
            "SELECT * FROM incident WHERE subject_key=? AND incident_type=? AND status='OPEN'",
            (subject_key, incident_type),
        ).fetchone()
        return self._from(r) if r else None

    def list_open(self, limit: int = 500) -> list[Incident]:
        rows = self._u.conn.execute(
            "SELECT * FROM incident WHERE status='OPEN' LIMIT ?", (limit,)
        ).fetchall()
        return [self._from(r) for r in rows]

    def resolve(self, incident_id: str, actor: str, at: datetime) -> None:
        self._u.conn.execute(
            "UPDATE incident SET status='RESOLVED', resolved_by=?, resolved_at=? WHERE incident_id=?",
            (actor, _t(at), incident_id),
        )


class _Outbox:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def _from(self, r) -> OutboxRow:
        return OutboxRow(
            outbox_id=r["incident_id"],
            incident_id=r["incident_id"],
            channel=r["mail_channel"] or "email",
            payload=r["mail_payload"] or "",
            delivery_status=r["mail_status"] or "PENDING",
            created_at=parse_iso(r["first_seen_at"]) or datetime.min,
            attempt_count=r["mail_attempt_count"] or 0,
            last_error=r["mail_last_error"],
            next_retry_at=parse_iso(r["mail_next_retry_at"]),
            provider_msg_id=r["mail_provider_msg_id"],
            sent_at=parse_iso(r["mail_sent_at"]),
            acked_at=parse_iso(r["mail_acked_at"]),
        )

    def enqueue(self, row: OutboxRow) -> None:
        self._u.conn.execute(
            """UPDATE incident SET mail_channel=?, mail_payload=?, mail_status=?,
                mail_attempt_count=?, mail_next_retry_at=? WHERE incident_id=?""",
            (
                row.channel, row.payload, row.delivery_status,
                row.attempt_count, _t(row.next_retry_at), row.incident_id,
            ),
        )

    def list_pending(self, now: datetime, limit: int = 100) -> list[OutboxRow]:
        rows = self._u.conn.execute(
            """SELECT * FROM incident WHERE mail_status IN ('PENDING','FAILED')
               AND (mail_next_retry_at IS NULL OR mail_next_retry_at<=?)
               ORDER BY first_seen_at LIMIT ?""",
            (_t(now), limit),
        ).fetchall()
        return [self._from(r) for r in rows]

    def mark_sent(self, outbox_id: str, at: datetime, provider_msg_id: str | None) -> None:
        self._u.conn.execute(
            "UPDATE incident SET mail_status='SENT', mail_sent_at=?, mail_provider_msg_id=? WHERE incident_id=?",
            (_t(at), provider_msg_id, outbox_id),
        )

    def mark_failed(self, outbox_id: str, at: datetime, error: str, next_retry_at: datetime) -> None:
        self._u.conn.execute(
            """UPDATE incident SET mail_status='FAILED', mail_last_error=?, mail_next_retry_at=?,
               mail_attempt_count=mail_attempt_count+1 WHERE incident_id=?""",
            (error, _t(next_retry_at), outbox_id),
        )

    def mark_acked(self, outbox_id: str, at: datetime) -> None:
        self._u.conn.execute(
            "UPDATE incident SET mail_status='ACKED', mail_acked_at=? WHERE incident_id=?",
            (_t(at), outbox_id),
        )

    def get(self, outbox_id: str) -> OutboxRow | None:
        r = self._u.conn.execute("SELECT * FROM incident WHERE incident_id=?", (outbox_id,)).fetchone()
        return self._from(r) if r and r["mail_status"] else None


class _Control:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def get(self, scope: str) -> SystemControl:
        r = self._u.conn.execute("SELECT * FROM agent_control WHERE scope=?", (scope,)).fetchone()
        return SystemControl(
            scope=r["scope"],
            mode=ControlMode(r["mode"]),
            control_version=r["control_version"],
            updated_at=parse_iso(r["updated_at"]) or datetime.min,
            disable_reason=r["disable_reason"],
            disable_trigger=r["disable_trigger"],
            disabled_at=parse_iso(r["disabled_at"]),
            sponsor_id=r["sponsor_id"],
            sponsor_approved_at=parse_iso(r["sponsor_approved_at"]),
        )

    def save(self, control: SystemControl, expected_version: int) -> None:
        cur = self._u.conn.execute(
            "UPDATE agent_control SET mode=?, control_version=?, disable_reason=?, disable_trigger=?, "
            "disabled_at=?, sponsor_id=?, sponsor_approved_at=?, updated_at=? "
            "WHERE scope=? AND control_version=?",
            (
                _e(control.mode), expected_version + 1, control.disable_reason, control.disable_trigger,
                _t(control.disabled_at), control.sponsor_id, _t(control.sponsor_approved_at),
                _t(control.updated_at), control.scope, expected_version,
            ),
        )
        if cur.rowcount != 1:
            raise ConcurrencyError("control version")
        control.control_version = expected_version + 1


class _Snaps:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def put(self, s: ObservationSnapshot) -> None:
        return

    def get(self, snapshot_id: str) -> ObservationSnapshot | None:
        return None


class _Cursors:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def get(self, name: str) -> DiscoveryCursor | None:
        r = self._u.conn.execute("SELECT last_heartbeat_at, updated_at FROM agent_control WHERE scope='DEFAULT'").fetchone()
        if not r or not r["last_heartbeat_at"]:
            return None
        return DiscoveryCursor(
            cursor_name=name,
            updated_at=parse_iso(r["last_heartbeat_at"]) or datetime.min,
            last_event_id="ok",
            last_event_time=parse_iso(r["last_heartbeat_at"]),
        )

    def advance(self, name: str, last_event_id: str, last_event_time: datetime, at: datetime) -> None:
        self._u.conn.execute(
            "UPDATE agent_control SET last_heartbeat_at=?, updated_at=? WHERE scope='DEFAULT'",
            (_t(at), _t(at)),
        )


class _Inbound:
    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self._u = uow

    def try_record(self, e: InboundEvent) -> bool:
        try:
            self._u.conn.execute(
                """INSERT INTO inbound_event (
                    source_event_id, lot_id, origin_operation_id, rework_count, event_time,
                    observed_at, payload, consumed, order_id, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    e.source_event_id, e.lot_id, e.origin_ope_no, e.rework_count,
                    _t(e.event_time), _t(e.observed_at), e.payload, 1 if e.consumed else 0,
                    e.order_id, _t(e.created_at),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def list_unconsumed(self, limit: int = 500) -> list[InboundEvent]:
        rows = self._u.conn.execute(
            "SELECT * FROM inbound_event WHERE consumed=0 ORDER BY event_time, source_event_id LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._from(r) for r in rows]

    def _from(self, r) -> InboundEvent:
        return InboundEvent(
            source_event_id=r["source_event_id"],
            lot_id=r["lot_id"],
            observed_at=parse_iso(r["observed_at"]) or datetime.min,
            created_at=parse_iso(r["created_at"]) or datetime.min,
            origin_ope_no=r["origin_operation_id"],
            rework_count=r["rework_count"],
            event_time=parse_iso(r["event_time"]),
            payload=r["payload"],
            consumed=bool(r["consumed"]),
            order_id=r["order_id"],
        )

    def mark_consumed(self, source_event_id: str, order_id: str | None) -> None:
        self._u.conn.execute(
            "UPDATE inbound_event SET consumed=1, order_id=? WHERE source_event_id=?",
            (order_id, source_event_id),
        )

    def get(self, source_event_id: str) -> InboundEvent | None:
        r = self._u.conn.execute(
            "SELECT * FROM inbound_event WHERE source_event_id=?", (source_event_id,)
        ).fetchone()
        return self._from(r) if r else None
