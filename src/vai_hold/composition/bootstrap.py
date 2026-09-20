from __future__ import annotations

from pathlib import Path

from vai_hold.adapters.fake_world.world import (
    FakeAiPort,
    FakeFlowPort,
    FakeHoldPort,
    FakeNotifier,
    FakeSmmPort,
    FakeWorld,
)
from vai_hold.adapters.persistence.memory.uow import MemoryUowFactory
from vai_hold.adapters.persistence.oracle.factory import load_oracle_factory
from vai_hold.adapters.persistence.sqlite.uow import SqliteUowFactory
from vai_hold.application.engine import App
from vai_hold.application.ports.clock import ManualClock, SystemClock
from vai_hold.application.settings import Settings, load_settings
from vai_hold.domain.errors import ConfigError, UnknownPersistenceBackend


class RealAdapterForbidden(ConfigError):
    pass


def build_uow_factory(settings: Settings):
    b = settings.persistence_backend
    if b == "memory":
        return MemoryUowFactory()
    if b == "sqlite":
        return SqliteUowFactory(settings.sqlite_path)
    if b == "oracle":
        return load_oracle_factory(settings)
    raise UnknownPersistenceBackend(b)


def build_app(
    *,
    settings: Settings | None = None,
    config_path: str | Path | None = None,
    overrides: dict | None = None,
    world: FakeWorld | None = None,
    uow_factory=None,
    clock=None,
    worker_id: str = "worker-1",
) -> App:
    if settings is None:
        settings = load_settings(config_path, overrides)
    if clock is None:
        clock = ManualClock() if settings.runtime_mode == "DEV" else SystemClock()
    if uow_factory is None:
        uow_factory = build_uow_factory(settings)
    if settings.runtime_mode == "PROD" and world is not None:
        raise RealAdapterForbidden("PROD cannot use FakeWorld")
    if world is None:
        if settings.runtime_mode == "PROD":
            raise RealAdapterForbidden("PROD real MES adapter is not wired in this build")
        world = FakeWorld(clock=clock)
    return App(
        settings=settings,
        uow_factory=uow_factory,
        clock=clock,
        hold=FakeHoldPort(world),
        flow=FakeFlowPort(world),
        ai=FakeAiPort(world),
        smm=FakeSmmPort(world),
        notifier=FakeNotifier(world),
        worker_id=worker_id,
    )
