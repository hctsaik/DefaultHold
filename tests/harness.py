from __future__ import annotations

from dataclasses import dataclass

from vai_hold.adapters.fake_world.world import FakeWorld
from vai_hold.application.engine import App
from vai_hold.application.ports.clock import ManualClock
from vai_hold.application.settings import load_settings
from vai_hold.composition.bootstrap import build_app
from vai_hold.domain.enums import FunctionCode
from vai_hold.domain.models import OrderKey


@dataclass
class Harness:
    app: App
    world: FakeWorld
    clock: ManualClock
    settings: object

    def set_hold(self):
        return self.app.run(FunctionCode.SET_DEFAULT_HOLD.value)

    def confirm_hold(self):
        return self.app.run(FunctionCode.CONFIRM_HOLD.value)

    def check_ai(self):
        return self.app.run(FunctionCode.CHECK_AI.value)

    def confirm_release(self):
        return self.app.run(FunctionCode.CONFIRM_RELEASE.value)

    def defense(self):
        return self.app.run(FunctionCode.DEFENSE.value)

    def order(self, lot_id="LOT1", ope="OP100", rw=0):
        with self.app.uow_factory.new() as uow:
            return uow.orders.get_by_key(OrderKey(lot_id, ope, rw))

    def incidents(self):
        with self.app.uow_factory.new() as uow:
            return uow.incidents.list_open()

    def history(self, lot_id="LOT1"):
        order = self.order(lot_id)
        assert order
        with self.app.uow_factory.new() as uow:
            return uow.actions.list_history(order.order_id)

    def commands(self, lot_id="LOT1"):
        order = self.order(lot_id)
        assert order
        with self.app.uow_factory.new() as uow:
            return uow.actions.list_by_order(order.order_id)

    def control(self):
        with self.app.uow_factory.new() as uow:
            return uow.control.get("DEFAULT")

    def open_count(self) -> int:
        with self.app.uow_factory.new() as uow:
            return len(uow.orders.list_open(5000))

    def journal_codes(self, lot_id="LOT1") -> list[str]:
        return [a.hold_code or "" for a in self.history(lot_id)]

    def incident_types(self) -> set[str]:
        return {i.incident_type for i in self.incidents()}


def make_harness(tmp_path=None, backend="memory", extra_overrides=None) -> Harness:
    clock = ManualClock()
    sqlite_path = str(tmp_path / "order.db") if tmp_path is not None else "var/dev.db"
    overrides = {
        "runtime": {"mode": "DEV"},
        "persistence": {"backend": backend, "sqlite_path": sqlite_path},
        "smm_exception_defense": {"notify": {"emails": ["lit.onduty@example.com"]}},
    }
    if extra_overrides:
        from vai_hold.application.settings import _deep_merge

        overrides = _deep_merge(overrides, extra_overrides)
    settings = load_settings(overrides=overrides)
    world = FakeWorld(clock=clock)
    app = build_app(settings=settings, world=world, clock=clock)
    return Harness(app=app, world=world, clock=clock, settings=settings)
