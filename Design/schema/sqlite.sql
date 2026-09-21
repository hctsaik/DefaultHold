-- Vision AI Preventive Hold — SQLite（Oracle 彩排，6 張表）
-- 加欄必須同時改 oracle.sql。禁止 Python ALTER。

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. 訂單 + 目前這一筆 Default Hold
CREATE TABLE IF NOT EXISTS hold_order (
    order_id                 TEXT    NOT NULL PRIMARY KEY,
    site_id                  TEXT,
    lot_id                   TEXT    NOT NULL,
    origin_operation_id      TEXT    NOT NULL,
    rework_count             INTEGER NOT NULL,
    current_operation_id     TEXT,
    target_hold_operation_id TEXT,
    future_hold_ope_name     TEXT,
    hold_route_id            TEXT,
    target_reason            TEXT,
    tool_id                  TEXT,
    flow_version             TEXT,
    config_version           TEXT,
    policy_version           TEXT    NOT NULL,
    lifecycle                TEXT    NOT NULL,
    protection_state         TEXT    NOT NULL,
    ai_state                 TEXT    NOT NULL,
    work_state               TEXT    NOT NULL,
    last_rule_id             TEXT,
    state_reason             TEXT,
    close_reason             TEXT,
    data_error               TEXT,
    row_version              INTEGER NOT NULL DEFAULT 1,
    next_check_at            TEXT,
    manual_control           TEXT    NOT NULL DEFAULT 'NONE',
    claim_owner              TEXT,
    claim_until              TEXT,
    operation_start_at       TEXT,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    last_evaluated_at        TEXT,
    dh_binding_id            TEXT,
    dh_code                  TEXT,
    dh_user                  TEXT,
    dh_memo                  TEXT,
    dh_status                TEXT,
    dh_generation            INTEGER,
    dh_kind                  TEXT,
    dh_time_quality          TEXT    NOT NULL DEFAULT 'ESTIMATED',
    dh_requested_at          TEXT,
    dh_first_confirmed_at    TEXT,
    dh_release_requested_at  TEXT,
    dh_released_at           TEXT,
    CHECK (rework_count >= 0),
    CHECK (row_version >= 1),
    CHECK (lifecycle IN ('OPEN', 'CLOSED', 'MANUAL_CLOSED')),
    CHECK (protection_state IN (
        'NONE', 'SET_PENDING', 'CONFIRMED', 'UNKNOWN',
        'FAILED', 'LOST', 'RELEASE_PENDING', 'RELEASED'
    )),
    CHECK (ai_state IN (
        'UNKNOWN', 'WAITING', 'COMPLETE_OK', 'COMPLETE_DEFECT', 'INVALID'
    )),
    CHECK (manual_control IN ('NONE', 'TAKEOVER', 'BLOCKED')),
    CHECK (dh_status IS NULL OR dh_status IN (
        'PENDING', 'CONFIRMED', 'ACTIVE',
        'RELEASE_PENDING', 'RELEASED', 'LOST', 'FAILED'
    )),
    UNIQUE (lot_id, origin_operation_id, rework_count)
);

CREATE INDEX IF NOT EXISTS idx_hold_order_due
    ON hold_order (lifecycle, next_check_at);
CREATE INDEX IF NOT EXISTS idx_hold_order_lot
    ON hold_order (lot_id);
CREATE INDEX IF NOT EXISTS idx_hold_order_work
    ON hold_order (lifecycle, work_state);

-- 2. 片與 ScanCompletedTime（解 Hold 的依據）
CREATE TABLE IF NOT EXISTS order_wafer (
    order_id              TEXT    NOT NULL,
    wafer_id              TEXT    NOT NULL,
    roster_version        INTEGER NOT NULL,
    scan_completed_at     TEXT,
    ai_result             TEXT,
    defect_types          TEXT,
    result_version        TEXT,
    updated_at            TEXT    NOT NULL,
    PRIMARY KEY (order_id, wafer_id),
    CHECK (roster_version >= 1),
    CHECK (ai_result IS NULL OR ai_result IN ('OK', 'DEFECT', 'INVALID')),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

-- 3. 每次送 MES 一列（含 retry）
CREATE TABLE IF NOT EXISTS mes_action (
    attempt_id             TEXT    NOT NULL PRIMARY KEY,
    command_id             TEXT    NOT NULL,
    order_id               TEXT    NOT NULL,
    logical_action_key     TEXT    NOT NULL,
    action_type            TEXT    NOT NULL,
    generation             INTEGER,
    hold_code              TEXT,
    target_occurrence      TEXT,
    idempotency_key        TEXT    NOT NULL,
    payload_hash           TEXT,
    payload_json           TEXT,
    action_state           TEXT    NOT NULL,
    receipt_outcome        TEXT,
    expected_postcondition TEXT,
    attempt_no             INTEGER NOT NULL,
    started_at             TEXT    NOT NULL,
    dispatched_at          TEXT,
    finished_at            TEXT,
    provider_request_id    TEXT,
    raw_error_code         TEXT,
    normalized_error       TEXT,
    retry_class            TEXT,
    raw_response_masked    TEXT,
    actor                  TEXT,
    rule_id                TEXT,
    created_at             TEXT    NOT NULL,
    updated_at             TEXT    NOT NULL,
    CHECK (attempt_no >= 1),
    CHECK (action_type IN ('SET_HOLD', 'SET_RELEASE')),
    CHECK (action_state IN (
        'PREPARED', 'DISPATCHED', 'ACKNOWLEDGED',
        'REJECTED', 'UNKNOWN', 'CONFIRMED', 'CANCELLED', 'RETRY_WAIT'
    )),
    CHECK (receipt_outcome IS NULL OR receipt_outcome IN (
        'NOT_SENT', 'ACCEPTED', 'REJECTED', 'UNKNOWN'
    )),
    UNIQUE (command_id, attempt_no),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_mes_action_order
    ON mes_action (order_id, action_state);
CREATE INDEX IF NOT EXISTS idx_mes_action_cmd
    ON mes_action (command_id, attempt_no);

-- 4. 告警 + 寄信（一告警一封信）
CREATE TABLE IF NOT EXISTS incident (
    incident_id         TEXT    NOT NULL PRIMARY KEY,
    subject_kind        TEXT    NOT NULL,
    subject_key         TEXT    NOT NULL,
    order_id            TEXT,
    source_event_id     TEXT,
    lot_id              TEXT,
    origin_operation_id TEXT,
    rework_count        INTEGER,
    incident_type       TEXT    NOT NULL,
    episode_id          TEXT    NOT NULL,
    severity            TEXT    NOT NULL,
    status              TEXT    NOT NULL,
    reason              TEXT,
    error_detail        TEXT,
    first_seen_at       TEXT    NOT NULL,
    last_seen_at        TEXT    NOT NULL,
    occurrence_count    INTEGER NOT NULL DEFAULT 1,
    acked_at            TEXT,
    acked_by            TEXT,
    resolved_at         TEXT,
    resolved_by         TEXT,
    mail_channel        TEXT,
    mail_payload        TEXT,
    mail_status         TEXT,
    mail_attempt_count  INTEGER NOT NULL DEFAULT 0,
    mail_last_error     TEXT,
    mail_next_retry_at  TEXT,
    mail_provider_msg_id TEXT,
    mail_sent_at        TEXT,
    mail_acked_at       TEXT,
    CHECK (subject_kind IN ('ORDER', 'DISCOVERY', 'SYSTEM')),
    CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    CHECK (status IN ('OPEN', 'ACKED', 'RESOLVED')),
    CHECK (occurrence_count >= 1),
    CHECK (mail_status IS NULL OR mail_status IN ('PENDING', 'SENT', 'FAILED', 'ACKED')),
    UNIQUE (subject_key, incident_type, episode_id),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_open
    ON incident (status, last_seen_at);
CREATE INDEX IF NOT EXISTS idx_incident_lot
    ON incident (lot_id, status);
CREATE INDEX IF NOT EXISTS idx_incident_mail
    ON incident (mail_status, mail_next_retry_at);

-- 5. DEV 彩排：正式 Oracle 不建這張，改寫現場 MV_NXT_PARAM_BT（key-value）。
-- 一列對應正式環境一組 PARAM key（見 Design/ORACLE_TABLES_AND_DAO.html）。
CREATE TABLE IF NOT EXISTS agent_control (
    scope               TEXT    NOT NULL PRIMARY KEY,
    mode                TEXT    NOT NULL,
    control_version     INTEGER NOT NULL DEFAULT 1,
    disable_reason      TEXT,
    disable_trigger     TEXT,
    disabled_at         TEXT,
    sponsor_id          TEXT,
    sponsor_approved_at TEXT,
    last_heartbeat_at   TEXT,
    updated_at          TEXT    NOT NULL,
    CHECK (mode IN ('ENABLED', 'DISABLED_NEW_HOLD', 'RECOVERY_PENDING')),
    CHECK (control_version >= 1)
);

INSERT OR IGNORE INTO agent_control (scope, mode, control_version, updated_at)
VALUES ('DEFAULT', 'ENABLED', 1, '1970-01-01T00:00:00Z');

-- 6. 進站事件去重
CREATE TABLE IF NOT EXISTS inbound_event (
    source_event_id      TEXT    NOT NULL PRIMARY KEY,
    lot_id               TEXT    NOT NULL,
    origin_operation_id  TEXT,
    rework_count         INTEGER,
    event_time           TEXT,
    observed_at          TEXT    NOT NULL,
    payload              TEXT,
    consumed             INTEGER NOT NULL DEFAULT 0,
    order_id             TEXT,
    created_at           TEXT    NOT NULL,
    CHECK (consumed IN (0, 1)),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_inbound_unconsumed
    ON inbound_event (consumed, event_time);
