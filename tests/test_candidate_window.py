from __future__ import annotations

import pytest

from vai_hold.domain.enums import FunctionCode, WorkState

from harness import make_harness


def test_operation_start_older_than_twelve_hours_is_not_read():
    h = make_harness()
    h.world.add_lot("OLD_LOT")
    h.clock.advance(hours=13)

    h.set_hold()

    assert h.order("OLD_LOT") is None
    assert h.world.set_hold_calls == []


def test_recent_open_orders_are_paged_past_first_five_hundred():
    h = make_harness()
    for i in range(501):
        h.world.add_lot(f"LOT{i:03d}", tool_id=f"EQP{i:03d}")

    h.app.run(FunctionCode.SET_DEFAULT_HOLD.value, {"limit": 50})

    assert len(h.world.set_hold_calls) == 501
    assert {c.lot_id for c in h.world.set_hold_calls} == {f"LOT{i:03d}" for i in range(501)}


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_recent_db_touch_does_not_reenter_old_operation_start(tmp_path, backend):
    h = make_harness(tmp_path=tmp_path, backend=backend)
    h.world.add_lot("OLD_OPEN")
    h.set_hold()
    h.confirm_hold()
    h.clock.advance(hours=13)

    # 模擬其他維護工作剛更新過資料列；候選窗仍必須看 OperationStartTime，
    # 不能因 updated_at 很新就把 13 小時前的單撈回來。
    order = h.order("OLD_OPEN")
    assert order is not None
    with h.app.uow_factory.new() as uow:
        stored = uow.orders.get(order.order_id)
        assert stored is not None
        stored.updated_at = h.clock.now()
        uow.orders.update(stored, stored.row_version)
        uow.commit()

    h.world.complete_ai("OLD_OPEN")
    h.clock.advance(minutes=2)
    h.check_ai()

    assert h.order("OLD_OPEN").work_state == WorkState.WAIT_AI
    assert h.world.release_calls == []
