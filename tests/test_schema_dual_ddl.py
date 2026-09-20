from __future__ import annotations

import sqlite3

import pytest

from vai_hold.adapters.persistence.schema_sync import dual_ddl_diffs
from vai_hold.adapters.persistence.sqlite.uow import SqliteUowFactory
from vai_hold.domain.errors import SchemaError


def test_sqlite_and_oracle_ddl_have_the_same_tables_columns_indexes():
    diffs = dual_ddl_diffs()
    assert diffs == [], "SQLite is the Oracle rehearsal; fix both DDLs:\n" + "\n".join(diffs)


def test_sqlite_factory_refuses_stale_schema_instead_of_alter(tmp_path):
    path = tmp_path / "old.db"
    SqliteUowFactory(str(path))
    conn = sqlite3.connect(path)
    conn.execute("ALTER TABLE hold_order DROP COLUMN data_error")
    conn.commit()
    conn.close()
    with pytest.raises(SchemaError, match="data_error"):
        SqliteUowFactory(str(path))
