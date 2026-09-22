from __future__ import annotations

from datetime import datetime
from typing import Protocol

from vai_hold.domain.models import (
    FlowView,
    HoldCommand,
    InboundEvent,
    SourceResult,
    TransportReceipt,
    WaferAiView,
)


class HoldPort(Protocol):
    def set_hold(self, cmd: HoldCommand) -> TransportReceipt: ...
    def release_hold(self, cmd: HoldCommand) -> TransportReceipt: ...
    def list_holds(self, lot_id: str) -> SourceResult: ...


class FlowPort(Protocol):
    def get_flow(self, lot_id: str, rework_count: int) -> SourceResult: ...


class AiPort(Protocol):
    def read_results(self, lot_id: str, rework_count: int) -> SourceResult: ...


class SmmPort(Protocol):
    def list_start_events(
        self, after_event_id: str | None, *, since: datetime | None = None
    ) -> list[InboundEvent]: ...
    def expected_keys(self, *, since: datetime | None = None) -> list[tuple[str, str, int]]: ...


class NotifierPort(Protocol):
    def send(self, to_emails: list[str], subject: str, body: str) -> str: ...
