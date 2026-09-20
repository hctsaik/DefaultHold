from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Literal

from vai_hold.application.ports.clock import Clock
from vai_hold.domain.enums import ReceiptOutcome, SourceStatus
from vai_hold.domain.models import (
    FlowStep,
    FlowView,
    HoldCommand,
    InboundEvent,
    SourceResult,
    TransportReceipt,
    WaferAiView,
)

HoldEffect = Literal["create", "none"]
HoldResponse = Literal[
    "accepted", "rejected_conflict", "rejected_permission", "rejected_transient", "timeout"
]
ListStatus = Literal["ok", "unknown", "stale"]


@dataclass
class LotState:
    lot_id: str
    route_id: str
    rework_count: int
    current_ope_no: str
    flow_version: str
    steps: list[FlowStep]
    expected_wafers: list[str]
    origin_ope_no: str
    tool_id: str = "EQP01"


@dataclass
class FakeWorld:
    clock: Clock
    lots: dict[tuple[str, int], LotState] = field(default_factory=dict)
    holds: list[HoldCommand] = field(default_factory=list)
    events: list[InboundEvent] = field(default_factory=list)
    ai: dict[tuple[str, int, str], WaferAiView] = field(default_factory=dict)
    set_effect: dict[str, HoldEffect] = field(default_factory=dict)
    set_response: dict[str, HoldResponse] = field(default_factory=dict)
    release_response: dict[str, HoldResponse] = field(default_factory=dict)
    list_status: dict[str, ListStatus] = field(default_factory=dict)
    sent_emails: list[dict] = field(default_factory=list)
    notifier_fail: bool = False
    set_hold_calls: list[HoldCommand] = field(default_factory=list)
    release_calls: list[HoldCommand] = field(default_factory=list)
    transfer_calls: list[tuple[HoldCommand, str]] = field(default_factory=list)
    transfer_response: dict[str, HoldResponse] = field(default_factory=dict)
    network_calls: int = 0
    late_commit: dict[str, Callable[[], None]] = field(default_factory=dict)
    seen_idempotency: set[str] = field(default_factory=set)

    def add_lot(
        self,
        lot_id: str,
        *,
        origin_ope_no: str = "OP100",
        current_ope_no: str | None = None,
        rework_count: int = 0,
        route_id: str = "RT1",
        wafers: int | list[str] = 25,
        steps: list[FlowStep] | None = None,
        event_id: str | None = None,
        tool_id: str = "EQP01",
    ) -> LotState:
        current = current_ope_no or origin_ope_no
        if isinstance(wafers, int):
            wafer_ids = [f"W{i:02d}" for i in range(1, wafers + 1)]
        else:
            wafer_ids = list(wafers)
        if steps is None:
            steps = default_flow_steps()
        lot = LotState(
            lot_id=lot_id,
            route_id=route_id,
            rework_count=rework_count,
            current_ope_no=current,
            flow_version="fv1",
            steps=steps,
            expected_wafers=wafer_ids,
            origin_ope_no=origin_ope_no,
            tool_id=tool_id,
        )
        self.lots[(lot_id, rework_count)] = lot
        now = self.clock.now()
        self.events.append(
            InboundEvent(
                source_event_id=event_id or f"evt-{lot_id}-{rework_count}",
                lot_id=lot_id,
                observed_at=now,
                created_at=now,
                origin_ope_no=origin_ope_no,
                rework_count=rework_count,
                event_time=now,
                payload=",".join(wafer_ids),
            )
        )
        return lot

    def complete_ai(
        self,
        lot_id: str,
        *,
        rework_count: int = 0,
        result: str = "OK",
        skip: list[str] | None = None,
        extra_duplicate: str | None = None,
        missing_result: str | None = None,
    ) -> None:
        from datetime import timedelta

        lot = self.lots[(lot_id, rework_count)]
        skip_set = set(skip or [])
        now = self.clock.now()
        scanned = [wid for wid in lot.expected_wafers if wid not in skip_set]
        last_at = now
        for i, wid in enumerate(scanned):
            at = now + timedelta(seconds=12 * i)
            last_at = at
            view = WaferAiView(
                wafer_id=wid,
                scan_completed_at=at,
                result=None if wid == missing_result else result,
                defect_types=["D1"] if result == "DEFECT" else [],
                result_version="1",
                rework_count=rework_count,
            )
            self.ai[(lot_id, rework_count, wid)] = view
        if extra_duplicate:
            self.ai[(lot_id, rework_count, extra_duplicate + "#dup")] = WaferAiView(
                wafer_id=extra_duplicate,
                scan_completed_at=last_at,
                result=result,
                rework_count=rework_count,
            )
        elapsed = int((last_at - now).total_seconds())
        if elapsed > 0 and hasattr(self.clock, "advance"):
            self.clock.advance(seconds=elapsed)

    def add_foreign_hold(self, lot_id: str, **kwargs) -> None:
        lot = self.lots[(lot_id, kwargs.get("rework_count", 0))]
        self.holds.append(
            HoldCommand(
                lot_id=lot_id,
                route_id=kwargs.get("route_id", lot.route_id),
                ope_no=kwargs.get("ope_no", lot.current_ope_no),
                memo=kwargs.get("memo", "OTHER SYSTEM HOLD"),
                hold_code=kwargs.get("hold_code", "ENHL"),
                hold_user=kwargs.get("hold_user", "ABO"),
            )
        )

    def scan_wafer(
        self,
        lot_id: str,
        wafer_id: str,
        *,
        result: str = "DEFECT",
        rework_count: int = 0,
    ) -> None:
        now = self.clock.now()
        self.ai[(lot_id, rework_count, wafer_id)] = WaferAiView(
            wafer_id=wafer_id,
            scan_completed_at=now,
            result=result,
            defect_types=["D1"] if result == "DEFECT" else [],
            result_version="1",
            rework_count=rework_count,
        )

    def add_defect_hold(
        self,
        lot_id: str,
        rework_count: int = 0,
        ope_no: str | None = None,
        memo: str = "SMM AI DEFECT HOLD",
    ) -> None:
        lot = self.lots[(lot_id, rework_count)]
        self.holds.append(
            HoldCommand(
                lot_id=lot_id,
                route_id=lot.route_id,
                ope_no=ope_no or "OP200",
                memo=memo,
                hold_code="SMMH",
                hold_user="AOA",
                hold_type="SMMH",
            )
        )


def default_flow_steps() -> list[FlowStep]:
    return [
        FlowStep("OP100", "Process-A", "PROCESS_TOOL", 0),
        FlowStep("OP200", "August", "METROLOGY", 1),
        FlowStep("OP300", "Overlay", "METROLOGY", 2),
        FlowStep("OP400", "CDSEM", "METROLOGY", 3),
    ]


class FakeHoldPort:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world

    def set_hold(self, cmd: HoldCommand) -> TransportReceipt:
        self.world.network_calls += 1
        self.world.set_hold_calls.append(cmd)
        now = self.world.clock.now()
        if cmd.idempotency_key and cmd.idempotency_key in self.world.seen_idempotency:
            return TransportReceipt(outcome=ReceiptOutcome.ACCEPTED, started_at=now, finished_at=now)
        key = cmd.lot_id
        effect = self.world.set_effect.get(key, "create")
        response = self.world.set_response.get(key, "accepted")

        def _same_record(h: HoldCommand) -> bool:
            return (
                h.lot_id == cmd.lot_id
                and h.route_id == cmd.route_id
                and h.ope_no == cmd.ope_no
                and h.hold_code == cmd.hold_code
                and h.hold_user == cmd.hold_user
                and h.memo == cmd.memo
            )

        def _lot_smm_taken(h: HoldCommand) -> bool:
            return (
                cmd.hold_code == "SMMH"
                and h.lot_id == cmd.lot_id
                and h.route_id == cmd.route_id
                and h.ope_no == cmd.ope_no
                and h.hold_code == cmd.hold_code
                and h.hold_user == cmd.hold_user
            )

        def do_create() -> None:
            if any(_same_record(h) or _lot_smm_taken(h) for h in self.world.holds):
                return
            if not cmd.tool_id:
                lot = next((x for x in self.world.lots.values() if x.lot_id == cmd.lot_id), None)
                if lot:
                    cmd.tool_id = lot.tool_id
            self.world.holds.append(cmd)

        if any(_same_record(h) or _lot_smm_taken(h) for h in self.world.holds) and response == "accepted":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                raw_error_code="EXISTS",
                normalized_error="CODE_CONFLICT",
                retry_class="CODE_CONFLICT",
            )
        if response == "rejected_transient":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                raw_error_code="BUSY",
                normalized_error="TRANSIENT",
                retry_class="TRANSIENT",
            )
        if response == "rejected_conflict":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                raw_error_code="CONFLICT",
                normalized_error="CODE_CONFLICT",
                retry_class="CODE_CONFLICT",
            )
        if response == "rejected_permission":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                raw_error_code="PERM",
                normalized_error="PERMISSION",
                retry_class="PERMISSION",
            )
        if effect == "create":
            do_create()
        if response == "timeout":
            return TransportReceipt(outcome=ReceiptOutcome.UNKNOWN, started_at=now, finished_at=now)
        if cmd.idempotency_key:
            self.world.seen_idempotency.add(cmd.idempotency_key)
        return TransportReceipt(outcome=ReceiptOutcome.ACCEPTED, started_at=now, finished_at=now)

    def transfer_hold(self, cmd: HoldCommand, new_memo: str) -> TransportReceipt:
        self.world.network_calls += 1
        self.world.transfer_calls.append((cmd, new_memo))
        now = self.world.clock.now()
        response = self.world.transfer_response.get(cmd.lot_id, "accepted")
        if response == "rejected_permission":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                normalized_error="PERMISSION",
                retry_class="PERMISSION",
            )
        if response == "rejected_transient":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                normalized_error="TRANSIENT",
                retry_class="TRANSIENT",
            )
        idx = next(
            (
                i
                for i, h in enumerate(self.world.holds)
                if h.lot_id == cmd.lot_id
                and h.route_id == cmd.route_id
                and h.ope_no == cmd.ope_no
                and h.hold_code == cmd.hold_code
                and h.hold_user == cmd.hold_user
                and h.memo == cmd.memo
            ),
            None,
        )
        if idx is None:
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                normalized_error="NOT_FOUND",
                retry_class="PERMISSION",
            )
        if response == "timeout":
            if self.world.set_effect.get(f"transfer:{cmd.lot_id}", "create") == "create":
                self.world.holds[idx].memo = new_memo
            return TransportReceipt(outcome=ReceiptOutcome.UNKNOWN, started_at=now, finished_at=now)
        self.world.holds[idx].memo = new_memo
        return TransportReceipt(outcome=ReceiptOutcome.ACCEPTED, started_at=now, finished_at=now)

    def release_hold(self, cmd: HoldCommand) -> TransportReceipt:
        self.world.network_calls += 1
        self.world.release_calls.append(cmd)
        now = self.world.clock.now()
        if cmd.idempotency_key and cmd.idempotency_key in self.world.seen_idempotency:
            return TransportReceipt(outcome=ReceiptOutcome.ACCEPTED, started_at=now, finished_at=now)
        key = cmd.lot_id
        response = self.world.release_response.get(key, "accepted")
        if response == "rejected_permission":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                normalized_error="PERMISSION",
                retry_class="PERMISSION",
            )
        if response == "rejected_transient":
            return TransportReceipt(
                outcome=ReceiptOutcome.REJECTED,
                started_at=now,
                finished_at=now,
                normalized_error="TRANSIENT",
                retry_class="TRANSIENT",
            )
        if response == "timeout":
            # still apply effect unless configured none
            if self.world.set_effect.get(f"release:{key}", "create") == "create":
                self._remove(cmd)
            if cmd.idempotency_key:
                self.world.seen_idempotency.add(cmd.idempotency_key)
            return TransportReceipt(outcome=ReceiptOutcome.UNKNOWN, started_at=now, finished_at=now)
        self._remove(cmd)
        if cmd.idempotency_key:
            self.world.seen_idempotency.add(cmd.idempotency_key)
        return TransportReceipt(outcome=ReceiptOutcome.ACCEPTED, started_at=now, finished_at=now)

    def _remove(self, cmd: HoldCommand) -> None:
        self.world.holds = [
            h
            for h in self.world.holds
            if not (
                h.lot_id == cmd.lot_id
                and h.route_id == cmd.route_id
                and h.ope_no == cmd.ope_no
                and h.hold_code == cmd.hold_code
                and h.hold_user == cmd.hold_user
            )
        ]

    def list_holds(self, lot_id: str) -> SourceResult:
        self.world.network_calls += 1
        now = self.world.clock.now()
        st = self.world.list_status.get(lot_id, "ok")
        if st == "unknown":
            return SourceResult(status=SourceStatus.UNKNOWN, observed_at=now, source_name="fake_mes", error_code="TIMEOUT")
        if st == "stale":
            return SourceResult(status=SourceStatus.STALE, observed_at=now, source_name="fake_mes", value=[])
        holds = [h for h in self.world.holds if h.lot_id == lot_id]
        status = SourceStatus.FOUND if holds else SourceStatus.NOT_FOUND
        return SourceResult(status=status, value=holds, observed_at=now, source_name="fake_mes")


class FakeFlowPort:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world
        self.unknown_lots: set[str] = set()

    def get_flow(self, lot_id: str, rework_count: int) -> SourceResult:
        now = self.world.clock.now()
        if lot_id in self.unknown_lots:
            return SourceResult(status=SourceStatus.UNKNOWN, observed_at=now, source_name="fake_flow")
        lot = self.world.lots.get((lot_id, rework_count))
        if lot is None:
            return SourceResult(status=SourceStatus.NOT_FOUND, observed_at=now, source_name="fake_flow")
        view = FlowView(
            route_id=lot.route_id,
            version=lot.flow_version,
            current_ope_no=lot.current_ope_no,
            steps=lot.steps,
            current_tool_id=lot.tool_id,
        )
        return SourceResult(status=SourceStatus.FOUND, value=view, observed_at=now, source_name="fake_flow")


class FakeAiPort:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world
        self.unavailable_lots: set[str] = set()

    def read_results(self, lot_id: str, rework_count: int) -> SourceResult:
        now = self.world.clock.now()
        if lot_id in self.unavailable_lots:
            return SourceResult(status=SourceStatus.UNKNOWN, observed_at=now, source_name="fake_ai")
        views = [
            v
            for (lid, rw, _w), v in self.world.ai.items()
            if lid == lot_id and rw == rework_count
        ]
        return SourceResult(
            status=SourceStatus.FOUND if views else SourceStatus.NOT_FOUND,
            value=views,
            observed_at=now,
            source_name="fake_ai",
        )


class FakeSmmPort:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world

    def list_start_events(self, after_event_id: str | None) -> list[InboundEvent]:
        evs = list(self.world.events)
        if after_event_id:
            ids = [e.source_event_id for e in evs]
            if after_event_id in ids:
                evs = evs[ids.index(after_event_id) + 1 :]
        return evs

    def expected_keys(self) -> list[tuple[str, str, int]]:
        return [(lot.lot_id, lot.origin_ope_no, lot.rework_count) for lot in self.world.lots.values()]


class FakeNotifier:
    def __init__(self, world: FakeWorld) -> None:
        self.world = world

    def send(self, to_emails: list[str], subject: str, body: str) -> str:
        if self.world.notifier_fail:
            raise RuntimeError("notifier down")
        msg_id = f"mail-{len(self.world.sent_emails)+1}"
        self.world.sent_emails.append({"to": to_emails, "subject": subject, "body": body, "id": msg_id})
        return msg_id
