from __future__ import annotations

from vai_hold.application.settings import load_settings
from vai_hold.domain.enums import WorkState

from harness import make_harness


def test_empty_scope_processes_all_lots():
    h = make_harness()
    h.world.add_lot("LOT_A")
    h.world.add_lot("LOT_B")
    h.set_hold()
    assert h.order("LOT_A") is not None
    assert h.order("LOT_B") is not None
    assert {c.lot_id for c in h.world.set_hold_calls} == {"LOT_A", "LOT_B"}


def test_scope_lot_ids_skips_other_lots_and_does_not_hold_them():
    h = make_harness(extra_overrides={"scope": {"lot_ids": ["KEEP1"]}})
    h.world.add_lot("SKIP1")
    h.world.add_lot("KEEP1")
    h.set_hold()
    h.confirm_hold()
    assert h.order("KEEP1") is not None
    assert h.order("KEEP1").work_state == WorkState.WAIT_AI
    assert h.order("SKIP1") is None
    assert {c.lot_id for c in h.world.set_hold_calls} == {"KEEP1"}
    with h.app.uow_factory.new() as uow:
        assert uow.inbound.get("evt-SKIP1-0") is None
        keep = uow.inbound.get("evt-KEEP1-0")
        assert keep is not None and keep.consumed


def test_scope_defense_does_not_coverage_mismatch_unscoped_lots():
    h = make_harness(extra_overrides={"scope": {"lot_ids": ["KEEP1"]}})
    h.world.add_lot("SKIP1")
    h.world.add_lot("KEEP1")
    h.set_hold()
    h.confirm_hold()
    h.defense()
    assert "COVERAGE_MISMATCH" not in {i.incident_type for i in h.incidents()}
    assert "ORPHAN_HOLD" not in {i.incident_type for i in h.incidents()}


def test_scope_not_starved_when_open_list_limit_is_small():
    from vai_hold.domain.enums import FunctionCode

    h = make_harness(extra_overrides={"scope": {"lot_ids": ["KEEP1"]}})
    h.world.add_lot("SKIP1")
    h.world.add_lot("KEEP1")
    h.app.run(FunctionCode.SET_DEFAULT_HOLD.value, {"limit": 1})
    assert h.order("KEEP1") is not None
    assert h.order("SKIP1") is None


def test_allows_lot_from_yaml():
    s = load_settings(
        overrides={
            "runtime": {"mode": "DEV"},
            "persistence": {"backend": "memory"},
            "scope": {"lot_ids": ["A123456", ""]},
        }
    )
    assert s.scope_lot_ids == frozenset({"A123456"})
    assert s.allows_lot("A123456")
    assert not s.allows_lot("OTHER")
    open_all = load_settings(
        overrides={"runtime": {"mode": "DEV"}, "persistence": {"backend": "memory"}, "scope": {"lot_ids": []}}
    )
    assert open_all.allows_lot("ANY")
