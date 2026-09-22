from __future__ import annotations

from datetime import datetime, timezone

import pytest

from vai_hold.adapters.persistence.memory.uow import MemoryUowFactory
from vai_hold.adapters.persistence.oracle.factory import load_oracle_factory
from vai_hold.adapters.persistence.sqlite.uow import SqliteUowFactory
from vai_hold.application.settings import load_settings
from vai_hold.domain.enums import Lifecycle, WorkState
from vai_hold.domain.errors import ConcurrencyError, DuplicateOrderError, OracleNotImplemented
from vai_hold.domain.models import HoldOrder, OrderKey


def _order(oid="o1", lot="L1", ope="OP100", rw=0) -> HoldOrder:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return HoldOrder(
        order_id=oid,
        lot_id=lot,
        origin_ope_no=ope,
        rework_count=rw,
        policy_version="v1",
        created_at=now,
        updated_at=now,
        work_state=WorkState.NEED_HOLD,
        lifecycle=Lifecycle.OPEN,
    )


@pytest.fixture(params=["memory", "sqlite"])
def factory(request, tmp_path):
    if request.param == "memory":
        return MemoryUowFactory()
    return SqliteUowFactory(str(tmp_path / "c.db"))


def test_duplicate_order_key(factory):
    with factory.new() as uow:
        uow.orders.insert(_order())
        uow.commit()
    with factory.new() as uow:
        with pytest.raises(DuplicateOrderError):
            uow.orders.insert(_order(oid="o2"))


def test_data_error_roundtrip(factory):
    with factory.new() as uow:
        o = _order()
        o.data_error = "NO_SMM_HOLD_AFTER_SCAN"
        uow.orders.insert(o)
        uow.commit()
    with factory.new() as uow:
        got = uow.orders.get("o1")
        assert got is not None
        assert got.data_error == "NO_SMM_HOLD_AFTER_SCAN"
        got.data_error = None
        uow.orders.update(got, got.row_version)
        uow.commit()
    with factory.new() as uow:
        got = uow.orders.get("o1")
        assert got is not None
        assert got.data_error is None


def test_row_version_cas(factory):
    with factory.new() as uow:
        uow.orders.insert(_order())
        uow.commit()
    with factory.new() as uow:
        o = uow.orders.get_by_key(OrderKey("L1", "OP100", 0))
        assert o
        o.state_reason = "x"
        with pytest.raises(ConcurrencyError):
            uow.orders.update(o, expected_version=99)


def test_try_claim_rejects_other_worker_while_lease_live(factory):
    from datetime import timedelta

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with factory.new() as uow:
        uow.orders.insert(_order())
        uow.commit()
    with factory.new() as uow:
        o = uow.orders.get("o1")
        assert o is not None
        assert uow.orders.try_claim("o1", "w1", now + timedelta(minutes=2), o.row_version, now=now)
        uow.commit()
    with factory.new() as uow:
        o = uow.orders.get("o1")
        assert o is not None
        assert not uow.orders.try_claim("o1", "w2", now + timedelta(minutes=2), o.row_version, now=now)


def test_try_claim_one_winner(factory):
    with factory.new() as uow:
        uow.orders.insert(_order())
        uow.commit()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with factory.new() as uow:
        o = uow.orders.get("o1")
        assert uow.orders.try_claim("o1", "w1", now, o.row_version)
        uow.commit()
    with factory.new() as uow:
        o = uow.orders.get("o1")
        assert o.claim_owner == "w1"
        assert not uow.orders.try_claim("o1", "w2", now, 1)


def test_rollback_drops_incident_and_outbox(factory):
    from vai_hold.domain.models import Incident, OutboxRow

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with factory.new() as uow:
        uow.orders.insert(_order())
        uow.commit()
    try:
        with factory.new() as uow:
            inc = Incident(
                incident_id="i1",
                subject_kind="ORDER",
                subject_key="o1",
                incident_type="T",
                episode_id="1",
                severity="ERROR",
                status="OPEN",
                first_seen_at=now,
                last_seen_at=now,
                order_id="o1",
            )
            uow.incidents.open_or_touch(inc)
            uow.outbox.enqueue(
                OutboxRow(
                    outbox_id="x1",
                    incident_id="i1",
                    channel="email",
                    payload="{}",
                    delivery_status="PENDING",
                    created_at=now,
                )
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    with factory.new() as uow:
        assert uow.incidents.list_open() == []


def test_control_survives_new_uow(factory):
    from vai_hold.domain.enums import ControlMode

    with factory.new() as uow:
        c = uow.control.get("DEFAULT")
        assert c.mode == ControlMode.ENABLED
        c.mode = ControlMode.DISABLED_NEW_HOLD
        c.disable_reason = "test"
        c.resume_evidence_ref = "ticket-123"
        c.health_check_ref = "health-ok"
        uow.control.save(c, c.control_version)
        uow.commit()
    with factory.new() as uow:
        saved = uow.control.get("DEFAULT")
        assert saved.mode == ControlMode.DISABLED_NEW_HOLD
        assert saved.resume_evidence_ref == "ticket-123"
        assert saved.health_check_ref == "health-ok"


def test_oracle_stub_fail_fast():
    with pytest.raises(OracleNotImplemented):
        load_oracle_factory(None)


def test_prod_requires_oracle():
    with pytest.raises(Exception):
        load_settings(overrides={"runtime": {"mode": "PROD"}, "persistence": {"backend": "sqlite"}})
