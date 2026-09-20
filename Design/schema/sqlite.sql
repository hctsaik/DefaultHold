-- Vision AI Preventive Hold Agent — SQLite schema
-- 這是 Oracle 彩排：欄位／UNIQUE／INDEX 名稱必須與 oracle.sql 對齊。
-- 加欄位同時改兩份 DDL，重建 DB；禁止在 Python ALTER。
-- Apply with: sqlite3 var/dev.db < Design/schema/sqlite.sql

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migration (
    version     INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL
);

-- ---------------------------------------------------------------------------
-- hold_order : 訂單主檔與狀態投影
-- 唯一鍵：lot_id + origin_operation_id（觸發 OpeNo）+ rework_count
-- origin_operation_id 寫入後不可改（DAO 強制）；未知 Rework 不准建單
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hold_order (
    order_id                 TEXT    NOT NULL PRIMARY KEY,
    site_id                  TEXT,
    lot_id                   TEXT    NOT NULL,
    origin_operation_id      TEXT    NOT NULL,
    rework_count             INTEGER NOT NULL,
    visit_id                 TEXT,
    current_operation_id     TEXT,
    target_hold_operation_id TEXT,
    future_hold_ope_name     TEXT,
    hold_route_id            TEXT,
    target_occurrence        TEXT,
    target_reason            TEXT,
    tool_id                  TEXT,
    flow_version             TEXT,
    config_version           TEXT,
    policy_version           TEXT    NOT NULL,
    manifest_version         INTEGER,
    lifecycle                TEXT    NOT NULL,
    protection_state         TEXT    NOT NULL,
    ai_state                 TEXT    NOT NULL,
    work_state               TEXT    NOT NULL,
    last_rule_id             TEXT,
    state_reason             TEXT,
    close_reason             TEXT,
    data_error               TEXT, -- C09：NO_SMM_HOLD_AFTER_SCAN；事後可查，不是 MES 欄位
    last_snapshot_ref        TEXT,
    row_version              INTEGER NOT NULL DEFAULT 1,
    next_check_at            TEXT,
    manual_control           TEXT    NOT NULL DEFAULT 'NONE',
    claim_owner              TEXT,
    claim_until              TEXT,
    operation_start_at       TEXT,
    created_at               TEXT    NOT NULL,
    updated_at               TEXT    NOT NULL,
    last_evaluated_at        TEXT,
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
    UNIQUE (lot_id, origin_operation_id, rework_count)
);

CREATE INDEX IF NOT EXISTS idx_hold_order_due
    ON hold_order (lifecycle, next_check_at);
CREATE INDEX IF NOT EXISTS idx_hold_order_lot
    ON hold_order (lot_id);
CREATE INDEX IF NOT EXISTS idx_hold_order_work
    ON hold_order (lifecycle, work_state);

-- ---------------------------------------------------------------------------
-- order_wafer : 本輪 expected roster + AI 結果
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS order_wafer (
    order_id              TEXT    NOT NULL,
    wafer_id              TEXT    NOT NULL,
    roster_version        INTEGER NOT NULL,
    operation_start_at    TEXT,
    operation_complete_at TEXT,
    scan_completed_at     TEXT,
    ai_result             TEXT,
    defect_types          TEXT,
    result_version        TEXT,
    required_tasks        TEXT,
    missing_alarm_type    INTEGER NOT NULL DEFAULT 0,
    updated_at            TEXT    NOT NULL,
    PRIMARY KEY (order_id, wafer_id),
    CHECK (roster_version >= 1),
    CHECK (ai_result IS NULL OR ai_result IN ('OK', 'DEFECT', 'INVALID')),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

-- ---------------------------------------------------------------------------
-- hold_binding : 預防性 Hold 與正式異常 Hold 證據
-- order_id 可為 NULL：發現本系統 token 但尚無訂單（ORPHAN_HOLD）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hold_binding (
    binding_id             TEXT NOT NULL PRIMARY KEY,
    order_id               TEXT,
    role                   TEXT NOT NULL,
    generation             INTEGER NOT NULL DEFAULT 1,
    mes_hold_record_id     TEXT,
    lot_id                 TEXT    NOT NULL,
    route_id               TEXT    NOT NULL,
    ope_no                 TEXT    NOT NULL,
    hold_code              TEXT    NOT NULL,
    hold_user              TEXT    NOT NULL,
    hold_memo              TEXT    NOT NULL,
    hold_token             TEXT,
    target_step_occurrence TEXT,
    hold_kind              TEXT,
    status                 TEXT NOT NULL,
    time_quality           TEXT NOT NULL DEFAULT 'ESTIMATED',
    requested_at           TEXT,
    provider_created_at    TEXT,
    first_confirmed_at     TEXT,
    effective_at           TEXT,
    release_requested_at   TEXT,
    released_at            TEXT,
    release_verified_at    TEXT,
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL,
    CHECK (generation >= 1),
    CHECK (role IN ('PREVENTIVE', 'DEFECT_REFERENCE')),
    CHECK (hold_kind IS NULL OR hold_kind IN ('FUTURE', 'CURRENT')),
    CHECK (status IN (
        'PENDING', 'CONFIRMED', 'ACTIVE',
        'RELEASE_PENDING', 'RELEASED', 'LOST', 'FAILED'
    )),
    CHECK (time_quality IN ('EXACT', 'ESTIMATED')),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_hold_binding_order
    ON hold_binding (order_id, role, status);
-- 多個 NULL 在 SQLite／Oracle UNIQUE 都允許；非 NULL 必須唯一（與 Oracle 對齊，不用 partial index）
CREATE UNIQUE INDEX IF NOT EXISTS idx_hold_binding_token
    ON hold_binding (hold_token);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hold_binding_mes
    ON hold_binding (mes_hold_record_id);
CREATE INDEX IF NOT EXISTS idx_hold_binding_lot_ope
    ON hold_binding (lot_id, route_id, ope_no, hold_code);

-- ---------------------------------------------------------------------------
-- action_command : 目前邏輯命令（摘要）
-- action_history : 每次 attempt 只追加
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS action_command (
    command_id              TEXT NOT NULL PRIMARY KEY,
    order_id                TEXT NOT NULL,
    logical_action_key      TEXT NOT NULL,
    action_type             TEXT NOT NULL,
    generation              INTEGER,
    hold_code               TEXT,
    target_occurrence       TEXT,
    idempotency_key         TEXT NOT NULL,
    payload_hash            TEXT,
    payload_json            TEXT,
    action_state            TEXT NOT NULL,
    receipt_outcome         TEXT,
    current_attempt_id      TEXT,
    expected_postcondition  TEXT,
    evidence_ref            TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    CHECK (action_type IN (
        'CREATE_ORDER', 'SET_HOLD', 'VERIFY_HOLD',
        'SET_RELEASE', 'VERIFY_RELEASE', 'TRANSFER_HOLD', 'RAISE_ALARM',
        'DISABLE_NEW_HOLDS', 'APPROVE_RESUME'
    )),
    CHECK (action_state IN (
        'PREPARED', 'DISPATCHED', 'ACKNOWLEDGED',
        'REJECTED', 'UNKNOWN', 'CONFIRMED', 'CANCELLED', 'RETRY_WAIT'
    )),
    CHECK (receipt_outcome IS NULL OR receipt_outcome IN (
        'NOT_SENT', 'ACCEPTED', 'REJECTED', 'UNKNOWN'
    )),
    UNIQUE (idempotency_key),
    UNIQUE (logical_action_key),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_action_command_order
    ON action_command (order_id, action_state);

CREATE TABLE IF NOT EXISTS action_history (
    attempt_id           TEXT    NOT NULL PRIMARY KEY,
    command_id           TEXT    NOT NULL,
    order_id             TEXT    NOT NULL,
    attempt_no           INTEGER NOT NULL,
    started_at           TEXT    NOT NULL,
    dispatched_at        TEXT,
    finished_at          TEXT,
    receipt_outcome      TEXT,
    provider_request_id  TEXT,
    raw_error_code       TEXT,
    normalized_error     TEXT,
    retry_class          TEXT,
    raw_response_masked  TEXT,
    actor                TEXT,
    rule_id              TEXT,
    program_version      TEXT,
    before_snapshot_ref  TEXT,
    after_snapshot_ref   TEXT,
    CHECK (attempt_no >= 1),
    FOREIGN KEY (command_id) REFERENCES action_command (command_id),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_action_history_cmd
    ON action_history (command_id, attempt_no);

-- ---------------------------------------------------------------------------
-- incident + alarm_outbox
-- 尚無訂單時 subject_kind = DISCOVERY，subject_key = source_event_id
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS incident (
    incident_id          TEXT    NOT NULL PRIMARY KEY,
    subject_kind         TEXT    NOT NULL,
    subject_key          TEXT    NOT NULL,
    order_id             TEXT,
    source_event_id      TEXT,
    lot_id               TEXT,
    origin_operation_id  TEXT,
    rework_count         INTEGER,
    incident_type        TEXT    NOT NULL,
    episode_id           TEXT    NOT NULL,
    severity             TEXT    NOT NULL,
    status               TEXT    NOT NULL,
    reason               TEXT,
    error_detail         TEXT,
    evidence_ref         TEXT,
    first_seen_at        TEXT    NOT NULL,
    last_seen_at         TEXT    NOT NULL,
    occurrence_count     INTEGER NOT NULL DEFAULT 1,
    acked_at             TEXT,
    acked_by             TEXT,
    resolved_at          TEXT,
    resolved_by          TEXT,
    CHECK (subject_kind IN ('ORDER', 'DISCOVERY', 'SYSTEM')),
    CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    CHECK (status IN ('OPEN', 'ACKED', 'RESOLVED')),
    CHECK (occurrence_count >= 1),
    UNIQUE (subject_key, incident_type, episode_id),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_incident_open
    ON incident (status, last_seen_at);

CREATE TABLE IF NOT EXISTS alarm_outbox (
    outbox_id         TEXT    NOT NULL PRIMARY KEY,
    incident_id       TEXT    NOT NULL,
    channel           TEXT    NOT NULL,
    payload           TEXT    NOT NULL,
    delivery_status   TEXT    NOT NULL,
    attempt_count     INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    next_retry_at     TEXT,
    provider_msg_id   TEXT,
    created_at        TEXT    NOT NULL,
    sent_at           TEXT,
    acked_at          TEXT,
    CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'ACKED')),
    CHECK (attempt_count >= 0),
    FOREIGN KEY (incident_id) REFERENCES incident (incident_id)
);

CREATE INDEX IF NOT EXISTS idx_outbox_pending
    ON alarm_outbox (delivery_status, next_retry_at);

-- ---------------------------------------------------------------------------
-- system_control : 重啟後必須仍讀到停用狀態
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_control (
    scope               TEXT    NOT NULL PRIMARY KEY,
    mode                TEXT    NOT NULL,
    control_version     INTEGER NOT NULL DEFAULT 1,
    disable_reason      TEXT,
    disable_trigger     TEXT,
    disabled_at         TEXT,
    sponsor_id          TEXT,
    sponsor_approved_at TEXT,
    resume_evidence_ref TEXT,
    health_check_ref    TEXT,
    updated_at          TEXT    NOT NULL,
    CHECK (mode IN ('ENABLED', 'DISABLED_NEW_HOLD', 'RECOVERY_PENDING')),
    CHECK (control_version >= 1)
);

INSERT OR IGNORE INTO system_control (scope, mode, control_version, updated_at)
VALUES ('DEFAULT', 'ENABLED', 1, '1970-01-01T00:00:00Z');

-- ---------------------------------------------------------------------------
-- observation_snapshot : 決策證據摘要
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS observation_snapshot (
    snapshot_id        TEXT NOT NULL PRIMARY KEY,
    order_id           TEXT,
    source_name        TEXT NOT NULL,
    outcome            TEXT NOT NULL,
    observed_at        TEXT NOT NULL,
    source_event_time  TEXT,
    source_watermark   TEXT,
    source_version     TEXT,
    error_code         TEXT,
    error_message      TEXT,
    payload_hash       TEXT,
    payload            TEXT,
    created_at         TEXT NOT NULL,
    CHECK (outcome IN ('FOUND', 'NOT_FOUND', 'UNKNOWN', 'STALE')),
    FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX IF NOT EXISTS idx_snapshot_order
    ON observation_snapshot (order_id, observed_at);

-- ---------------------------------------------------------------------------
-- discovery_cursor + inbound_event
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discovery_cursor (
    cursor_name      TEXT NOT NULL PRIMARY KEY,
    last_event_id    TEXT,
    last_event_time  TEXT,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inbound_event (
    source_event_id      TEXT    NOT NULL PRIMARY KEY,
    site_id              TEXT,
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

INSERT OR IGNORE INTO schema_migration (version, name, applied_at)
VALUES (1, 'init', '1970-01-01T00:00:00Z');
