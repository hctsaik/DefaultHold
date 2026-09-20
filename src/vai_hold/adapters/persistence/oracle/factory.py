from __future__ import annotations

from vai_hold.domain.errors import OracleNotImplemented


def load_oracle_factory(settings) -> None:
    raise OracleNotImplemented(
        "persistence.backend=oracle 但 Oracle adapter 尚未實作。"
        "請實作 adapters.persistence.oracle 的 UnitOfWorkFactory。"
    )
