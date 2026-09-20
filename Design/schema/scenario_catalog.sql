-- Scenario catalog (test fixture DB, not production hold_order)
-- DAO loads rows as Given Facts, runner acts, then diffs actual Facts vs Expect.

CREATE TABLE IF NOT EXISTS scenario (
    scenario_id   TEXT    NOT NULL PRIMARY KEY,
    group_name    TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    enabled       INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    settings_json TEXT,
    given_json    TEXT    NOT NULL DEFAULT '{}',
    script_json   TEXT    NOT NULL,
    expect_json   TEXT    NOT NULL,
    spec_json     TEXT,
    CHECK (enabled IN (0, 1))
);

CREATE TABLE IF NOT EXISTS scenario_run (
    run_id        TEXT    NOT NULL PRIMARY KEY,
    scenario_id   TEXT    NOT NULL,
    ran_at        TEXT    NOT NULL,
    passed        INTEGER NOT NULL,
    actual_json   TEXT    NOT NULL,
    diff_json     TEXT,
    FOREIGN KEY (scenario_id) REFERENCES scenario (scenario_id)
);

CREATE INDEX IF NOT EXISTS idx_scenario_group ON scenario (group_name, sort_order);
CREATE INDEX IF NOT EXISTS idx_scenario_run_case ON scenario_run (scenario_id, ran_at);
