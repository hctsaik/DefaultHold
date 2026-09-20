from __future__ import annotations

from vai_hold.domain.enums import Lifecycle

from harness import make_harness
from test_t01_t18 import _happy_until_hold


def test_t01_on_sqlite(tmp_path):
    h = make_harness(tmp_path=tmp_path, backend="sqlite")
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.check_ai()
    h.confirm_release()
    assert h.order().lifecycle == Lifecycle.CLOSED
