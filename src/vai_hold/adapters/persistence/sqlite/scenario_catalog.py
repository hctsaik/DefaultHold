from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from vai_hold.application.ids import new_id
from vai_hold.domain.errors import SchemaError
from vai_hold.domain.scenario import ScenarioCase, ScenarioRunResult

def _schema_path() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "Design" / "schema" / "scenario_catalog.sql"
        if cand.exists():
            return cand
    raise FileNotFoundError("Design/schema/scenario_catalog.sql")


SCHEMA = _schema_path()


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _load(text: str | None, default):
    if not text:
        return default
    return json.loads(text)


class SqliteScenarioCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(scenario)").fetchall()}
        if "spec_json" not in cols:
            raise SchemaError(
                f"{self.path} is an old scenario catalog missing spec_json. "
                "Delete the file and re-seed; do not ALTER TABLE."
            )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _row(self, r: sqlite3.Row) -> ScenarioCase:
        return ScenarioCase(
            scenario_id=r["scenario_id"],
            group_name=r["group_name"],
            title=r["title"],
            enabled=bool(r["enabled"]),
            sort_order=int(r["sort_order"]),
            settings=_load(r["settings_json"], {}),
            given=_load(r["given_json"], {}),
            script=_load(r["script_json"], []),
            expect=_load(r["expect_json"], {}),
            spec=_load(r["spec_json"] if "spec_json" in r.keys() else None, {}),
        )

    def list_enabled(self) -> list[ScenarioCase]:
        rows = self.conn.execute(
            "SELECT * FROM scenario WHERE enabled=1 ORDER BY sort_order, scenario_id"
        ).fetchall()
        return [self._row(r) for r in rows]

    def list_all(self) -> list[ScenarioCase]:
        rows = self.conn.execute("SELECT * FROM scenario ORDER BY sort_order, scenario_id").fetchall()
        return [self._row(r) for r in rows]

    def get(self, scenario_id: str) -> ScenarioCase | None:
        r = self.conn.execute("SELECT * FROM scenario WHERE scenario_id=?", (scenario_id,)).fetchone()
        return self._row(r) if r else None

    def upsert(self, case: ScenarioCase) -> None:
        self.conn.execute(
            """INSERT INTO scenario (
                scenario_id, group_name, title, enabled, sort_order,
                settings_json, given_json, script_json, expect_json, spec_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(scenario_id) DO UPDATE SET
                group_name=excluded.group_name,
                title=excluded.title,
                enabled=excluded.enabled,
                sort_order=excluded.sort_order,
                settings_json=excluded.settings_json,
                given_json=excluded.given_json,
                script_json=excluded.script_json,
                expect_json=excluded.expect_json,
                spec_json=excluded.spec_json
            """,
            (
                case.scenario_id,
                case.group_name,
                case.title,
                1 if case.enabled else 0,
                case.sort_order,
                _json(case.settings or {}),
                _json(case.given or {}),
                _json(case.script),
                _json(case.expect),
                _json(case.spec or {}),
            ),
        )
        self.conn.commit()

    def record_run(self, result: ScenarioRunResult) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.conn.execute(
            """INSERT INTO scenario_run (run_id, scenario_id, ran_at, passed, actual_json, diff_json)
               VALUES (?,?,?,?,?,?)""",
            (
                new_id(),
                result.scenario_id,
                now,
                1 if result.passed else 0,
                _json(result.actual),
                _json(result.diffs),
            ),
        )
        self.conn.commit()

    def delete(self, scenario_id: str) -> None:
        self.conn.execute("DELETE FROM scenario_run WHERE scenario_id=?", (scenario_id,))
        self.conn.execute("DELETE FROM scenario WHERE scenario_id=?", (scenario_id,))
        self.conn.commit()

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM scenario").fetchone()[0])

    def latest_run(self, scenario_id: str) -> tuple[str, bool, dict, list] | None:
        r = self.conn.execute(
            """SELECT ran_at, passed, actual_json, diff_json
               FROM scenario_run WHERE scenario_id=?
               ORDER BY ran_at DESC LIMIT 1""",
            (scenario_id,),
        ).fetchone()
        if r is None:
            return None
        return r["ran_at"], bool(r["passed"]), _load(r["actual_json"], {}), _load(r["diff_json"], [])
