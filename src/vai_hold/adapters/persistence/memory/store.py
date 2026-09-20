from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from vai_hold.domain.enums import ControlMode
from vai_hold.domain.models import (
    ActionAttempt,
    ActionCommand,
    DiscoveryCursor,
    HoldBinding,
    HoldOrder,
    InboundEvent,
    Incident,
    ObservationSnapshot,
    OrderWafer,
    OutboxRow,
    SystemControl,
)


def _now() -> datetime:
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass
class MemoryStore:
    orders: dict[str, HoldOrder] = field(default_factory=dict)
    orders_by_key: dict[tuple, str] = field(default_factory=dict)
    wafers: dict[str, list[OrderWafer]] = field(default_factory=dict)
    bindings: dict[str, HoldBinding] = field(default_factory=dict)
    commands: dict[str, ActionCommand] = field(default_factory=dict)
    history: dict[str, ActionAttempt] = field(default_factory=dict)
    incidents: dict[str, Incident] = field(default_factory=dict)
    outbox: dict[str, OutboxRow] = field(default_factory=dict)
    control: dict[str, SystemControl] = field(default_factory=dict)
    snapshots: dict[str, ObservationSnapshot] = field(default_factory=dict)
    cursors: dict[str, DiscoveryCursor] = field(default_factory=dict)
    inbound: dict[str, InboundEvent] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if "DEFAULT" not in self.control:
            self.control["DEFAULT"] = SystemControl(
                scope="DEFAULT",
                mode=ControlMode.ENABLED,
                control_version=1,
                updated_at=_now(),
            )

    def clone(self) -> MemoryStore:
        return deepcopy(self)

    def replace_from(self, other: MemoryStore) -> None:
        self.orders = other.orders
        self.orders_by_key = other.orders_by_key
        self.wafers = other.wafers
        self.bindings = other.bindings
        self.commands = other.commands
        self.history = other.history
        self.incidents = other.incidents
        self.outbox = other.outbox
        self.control = other.control
        self.snapshots = other.snapshots
        self.cursors = other.cursors
        self.inbound = other.inbound
