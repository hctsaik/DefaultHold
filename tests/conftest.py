from __future__ import annotations

import pytest

from harness import Harness, make_harness


@pytest.fixture
def h() -> Harness:
    return make_harness()
