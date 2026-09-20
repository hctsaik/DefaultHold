-- Vision AI Preventive Hold Agent — Oracle schema (PROD)
-- 與 schema/sqlite.sql 同一組表／欄／索引名稱；差異只在型別與 DDL 方言。
-- 加欄位必須兩份一起改。SQLite 是接 Oracle 前的彩排，不是另一套業務庫。
-- 目標版本：Oracle 19c+（不使用 23c 的 CREATE TABLE IF NOT EXISTS / BOOLEAN）。
-- 遷移程式依 schema_migration 決定是否執行，勿手動重跑整份。

-- 連線後建議：ALTER SESSION SET TIME_ZONE = 'UTC';

CREATE TABLE schema_migration (
    version     NUMBER(10)     NOT NULL,
    name        VARCHAR2(128)  NOT NULL,
    applied_at  TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_schema_migration PRIMARY KEY (version)
);

CREATE TABLE hold_order (
    order_id                 VARCHAR2(36)   NOT NULL,
    site_id                  VARCHAR2(32),
    lot_id                   VARCHAR2(128)  NOT NULL,
    origin_operation_id      VARCHAR2(128)  NOT NULL,
    rework_count             NUMBER(10)     NOT NULL,
    visit_id                 VARCHAR2(128),
    current_operation_id     VARCHAR2(128),
    target_hold_operation_id VARCHAR2(128),
    future_hold_ope_name     VARCHAR2(128),
    hold_route_id            VARCHAR2(128),
    target_occurrence        VARCHAR2(128),
    target_reason            VARCHAR2(4000),
    tool_id                  VARCHAR2(128),
    flow_version             VARCHAR2(64),
    config_version           VARCHAR2(64),
    policy_version           VARCHAR2(64)   NOT NULL,
    manifest_version         NUMBER(10),
    lifecycle                VARCHAR2(32)   NOT NULL,
    protection_state         VARCHAR2(32)   NOT NULL,
    ai_state                 VARCHAR2(32)   NOT NULL,
    work_state               VARCHAR2(64)   NOT NULL,
    last_rule_id             VARCHAR2(32),
    state_reason             VARCHAR2(4000),
    close_reason             VARCHAR2(64),
    data_error               VARCHAR2(64),
    last_snapshot_ref        VARCHAR2(36),
    row_version              NUMBER(10)     DEFAULT 1 NOT NULL,
    next_check_at            TIMESTAMP(6) WITH TIME ZONE,
    manual_control           VARCHAR2(32)   DEFAULT 'NONE' NOT NULL,
    claim_owner              VARCHAR2(128),
    claim_until              TIMESTAMP(6) WITH TIME ZONE,
    operation_start_at       TIMESTAMP(6) WITH TIME ZONE,
    created_at               TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    updated_at               TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    last_evaluated_at        TIMESTAMP(6) WITH TIME ZONE,
    CONSTRAINT pk_hold_order PRIMARY KEY (order_id),
    CONSTRAINT ck_hold_order_rw CHECK (rework_count >= 0),
    CONSTRAINT ck_hold_order_ver CHECK (row_version >= 1),
    CONSTRAINT ck_hold_order_life CHECK (lifecycle IN ('OPEN', 'CLOSED', 'MANUAL_CLOSED')),
    CONSTRAINT ck_hold_order_prot CHECK (protection_state IN (
        'NONE', 'SET_PENDING', 'CONFIRMED', 'UNKNOWN',
        'FAILED', 'LOST', 'RELEASE_PENDING', 'RELEASED'
    )),
    CONSTRAINT ck_hold_order_ai CHECK (ai_state IN (
        'UNKNOWN', 'WAITING', 'COMPLETE_OK', 'COMPLETE_DEFECT', 'INVALID'
    )),
    CONSTRAINT ck_hold_order_man CHECK (manual_control IN ('NONE', 'TAKEOVER', 'BLOCKED')),
    CONSTRAINT uq_hold_order_key UNIQUE (lot_id, origin_operation_id, rework_count)
);

CREATE INDEX idx_hold_order_due ON hold_order (lifecycle, next_check_at);
CREATE INDEX idx_hold_order_lot ON hold_order (lot_id);
CREATE INDEX idx_hold_order_work ON hold_order (lifecycle, work_state);

CREATE TABLE order_wafer (
    order_id              VARCHAR2(36)  NOT NULL,
    wafer_id              VARCHAR2(64)  NOT NULL,
    roster_version        NUMBER(10)    NOT NULL,
    operation_start_at    TIMESTAMP(6) WITH TIME ZONE,
    operation_complete_at TIMESTAMP(6) WITH TIME ZONE,
    scan_completed_at     TIMESTAMP(6) WITH TIME ZONE,
    ai_result             VARCHAR2(16),
    defect_types          CLOB,
    result_version        VARCHAR2(64),
    required_tasks        CLOB,
    missing_alarm_type    NUMBER(1) DEFAULT 0 NOT NULL,
    updated_at            TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_order_wafer PRIMARY KEY (order_id, wafer_id),
    CONSTRAINT ck_order_wafer_rv CHECK (roster_version >= 1),
    CONSTRAINT ck_order_wafer_ai CHECK (ai_result IS NULL OR ai_result IN ('OK', 'DEFECT', 'INVALID')),
    CONSTRAINT fk_order_wafer_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE TABLE hold_binding (
    binding_id             VARCHAR2(36)   NOT NULL,
    order_id               VARCHAR2(36),
    role                   VARCHAR2(32)   NOT NULL,
    generation             NUMBER(10)     DEFAULT 1 NOT NULL,
    mes_hold_record_id     VARCHAR2(128),
    lot_id                 VARCHAR2(128)  NOT NULL,
    route_id               VARCHAR2(128)  NOT NULL,
    ope_no                 VARCHAR2(128)  NOT NULL,
    hold_code              VARCHAR2(32)   NOT NULL,
    hold_user              VARCHAR2(32)   NOT NULL,
    hold_memo              VARCHAR2(4000) NOT NULL,
    hold_token             VARCHAR2(128),
    target_step_occurrence VARCHAR2(128),
    hold_kind              VARCHAR2(16),
    status                 VARCHAR2(32)   NOT NULL,
    time_quality           VARCHAR2(16)   DEFAULT 'ESTIMATED' NOT NULL,
    requested_at           TIMESTAMP(6) WITH TIME ZONE,
    provider_created_at    TIMESTAMP(6) WITH TIME ZONE,
    first_confirmed_at     TIMESTAMP(6) WITH TIME ZONE,
    effective_at           TIMESTAMP(6) WITH TIME ZONE,
    release_requested_at   TIMESTAMP(6) WITH TIME ZONE,
    released_at            TIMESTAMP(6) WITH TIME ZONE,
    release_verified_at    TIMESTAMP(6) WITH TIME ZONE,
    created_at             TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    updated_at             TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_hold_binding PRIMARY KEY (binding_id),
    CONSTRAINT ck_hold_bind_gen CHECK (generation >= 1),
    CONSTRAINT ck_hold_bind_role CHECK (role IN ('PREVENTIVE', 'DEFECT_REFERENCE')),
    CONSTRAINT ck_hold_bind_kind CHECK (hold_kind IS NULL OR hold_kind IN ('FUTURE', 'CURRENT')),
    CONSTRAINT ck_hold_bind_st CHECK (status IN (
        'PENDING', 'CONFIRMED', 'ACTIVE',
        'RELEASE_PENDING', 'RELEASED', 'LOST', 'FAILED'
    )),
    CONSTRAINT ck_hold_bind_tq CHECK (time_quality IN ('EXACT', 'ESTIMATED')),
    CONSTRAINT fk_hold_bind_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX idx_hold_binding_order ON hold_binding (order_id, role, status);
-- Oracle UNIQUE 允許多個 NULL；非 NULL 值必須唯一（與 SQLite 對齊）
CREATE UNIQUE INDEX idx_hold_binding_token ON hold_binding (hold_token);
CREATE UNIQUE INDEX idx_hold_binding_mes ON hold_binding (mes_hold_record_id);
CREATE INDEX idx_hold_binding_lot_ope ON hold_binding (lot_id, route_id, ope_no, hold_code);

CREATE TABLE action_command (
    command_id             VARCHAR2(36)   NOT NULL,
    order_id               VARCHAR2(36)   NOT NULL,
    logical_action_key     VARCHAR2(256)  NOT NULL,
    action_type            VARCHAR2(32)   NOT NULL,
    generation             NUMBER(10),
    hold_code              VARCHAR2(32),
    target_occurrence      VARCHAR2(128),
    idempotency_key        VARCHAR2(128)  NOT NULL,
    payload_hash           VARCHAR2(64),
    payload_json           CLOB,
    action_state           VARCHAR2(32)   NOT NULL,
    receipt_outcome        VARCHAR2(16),
    current_attempt_id     VARCHAR2(36),
    expected_postcondition VARCHAR2(4000),
    evidence_ref           VARCHAR2(36),
    created_at             TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    updated_at             TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_action_command PRIMARY KEY (command_id),
    CONSTRAINT ck_act_cmd_type CHECK (action_type IN (
        'CREATE_ORDER', 'SET_HOLD', 'VERIFY_HOLD',
        'SET_RELEASE', 'VERIFY_RELEASE', 'TRANSFER_HOLD', 'RAISE_ALARM',
        'DISABLE_NEW_HOLDS', 'APPROVE_RESUME'
    )),
    CONSTRAINT ck_act_cmd_st CHECK (action_state IN (
        'PREPARED', 'DISPATCHED', 'ACKNOWLEDGED',
        'REJECTED', 'UNKNOWN', 'CONFIRMED', 'CANCELLED', 'RETRY_WAIT'
    )),
    CONSTRAINT ck_act_cmd_rc CHECK (receipt_outcome IS NULL OR receipt_outcome IN (
        'NOT_SENT', 'ACCEPTED', 'REJECTED', 'UNKNOWN'
    )),
    CONSTRAINT uq_act_cmd_idem UNIQUE (idempotency_key),
    CONSTRAINT uq_act_cmd_log UNIQUE (logical_action_key),
    CONSTRAINT fk_act_cmd_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX idx_action_command_order ON action_command (order_id, action_state);

CREATE TABLE action_history (
    attempt_id          VARCHAR2(36)  NOT NULL,
    command_id          VARCHAR2(36)  NOT NULL,
    order_id            VARCHAR2(36)  NOT NULL,
    attempt_no          NUMBER(10)    NOT NULL,
    started_at          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    dispatched_at       TIMESTAMP(6) WITH TIME ZONE,
    finished_at         TIMESTAMP(6) WITH TIME ZONE,
    receipt_outcome     VARCHAR2(16),
    provider_request_id VARCHAR2(128),
    raw_error_code      VARCHAR2(64),
    normalized_error    VARCHAR2(64),
    retry_class         VARCHAR2(32),
    raw_response_masked CLOB,
    actor               VARCHAR2(64),
    rule_id             VARCHAR2(32),
    program_version     VARCHAR2(64),
    before_snapshot_ref VARCHAR2(36),
    after_snapshot_ref  VARCHAR2(36),
    CONSTRAINT pk_action_history PRIMARY KEY (attempt_id),
    CONSTRAINT ck_act_hist_no CHECK (attempt_no >= 1),
    CONSTRAINT fk_act_hist_cmd FOREIGN KEY (command_id) REFERENCES action_command (command_id),
    CONSTRAINT fk_act_hist_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX idx_action_history_cmd ON action_history (command_id, attempt_no);

CREATE TABLE incident (
    incident_id         VARCHAR2(36)   NOT NULL,
    subject_kind        VARCHAR2(16)   NOT NULL,
    subject_key         VARCHAR2(128)  NOT NULL,
    order_id            VARCHAR2(36),
    source_event_id     VARCHAR2(128),
    lot_id              VARCHAR2(128),
    origin_operation_id VARCHAR2(128),
    rework_count        NUMBER(10),
    incident_type       VARCHAR2(64)   NOT NULL,
    episode_id          VARCHAR2(64)   NOT NULL,
    severity            VARCHAR2(16)   NOT NULL,
    status              VARCHAR2(16)   NOT NULL,
    reason              VARCHAR2(4000),
    error_detail        CLOB,
    evidence_ref        VARCHAR2(36),
    first_seen_at       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    last_seen_at        TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    occurrence_count    NUMBER(10)     DEFAULT 1 NOT NULL,
    acked_at            TIMESTAMP(6) WITH TIME ZONE,
    acked_by            VARCHAR2(64),
    resolved_at         TIMESTAMP(6) WITH TIME ZONE,
    resolved_by         VARCHAR2(64),
    CONSTRAINT pk_incident PRIMARY KEY (incident_id),
    CONSTRAINT ck_inc_kind CHECK (subject_kind IN ('ORDER', 'DISCOVERY', 'SYSTEM')),
    CONSTRAINT ck_inc_sev CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    CONSTRAINT ck_inc_st CHECK (status IN ('OPEN', 'ACKED', 'RESOLVED')),
    CONSTRAINT ck_inc_cnt CHECK (occurrence_count >= 1),
    CONSTRAINT uq_inc_episode UNIQUE (subject_key, incident_type, episode_id),
    CONSTRAINT fk_inc_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX idx_incident_open ON incident (status, last_seen_at);

CREATE TABLE alarm_outbox (
    outbox_id       VARCHAR2(36)  NOT NULL,
    incident_id     VARCHAR2(36)  NOT NULL,
    channel         VARCHAR2(32)  NOT NULL,
    payload         CLOB          NOT NULL,
    delivery_status VARCHAR2(16)  NOT NULL,
    attempt_count   NUMBER(10)    DEFAULT 0 NOT NULL,
    last_error      VARCHAR2(4000),
    next_retry_at   TIMESTAMP(6) WITH TIME ZONE,
    provider_msg_id VARCHAR2(128),
    created_at      TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    sent_at         TIMESTAMP(6) WITH TIME ZONE,
    acked_at        TIMESTAMP(6) WITH TIME ZONE,
    CONSTRAINT pk_alarm_outbox PRIMARY KEY (outbox_id),
    CONSTRAINT ck_outbox_st CHECK (delivery_status IN ('PENDING', 'SENT', 'FAILED', 'ACKED')),
    CONSTRAINT ck_outbox_cnt CHECK (attempt_count >= 0),
    CONSTRAINT fk_outbox_inc FOREIGN KEY (incident_id) REFERENCES incident (incident_id)
);

CREATE INDEX idx_outbox_pending ON alarm_outbox (delivery_status, next_retry_at);

CREATE TABLE system_control (
    scope               VARCHAR2(64)  NOT NULL,
    mode                VARCHAR2(32)  NOT NULL,
    control_version     NUMBER(10)    DEFAULT 1 NOT NULL,
    disable_reason      VARCHAR2(4000),
    disable_trigger     VARCHAR2(64),
    disabled_at         TIMESTAMP(6) WITH TIME ZONE,
    sponsor_id          VARCHAR2(64),
    sponsor_approved_at TIMESTAMP(6) WITH TIME ZONE,
    resume_evidence_ref VARCHAR2(36),
    health_check_ref    VARCHAR2(36),
    updated_at          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_system_control PRIMARY KEY (scope),
    CONSTRAINT ck_sysctl_mode CHECK (mode IN ('ENABLED', 'DISABLED_NEW_HOLD', 'RECOVERY_PENDING')),
    CONSTRAINT ck_sysctl_ver CHECK (control_version >= 1)
);

INSERT INTO system_control (scope, mode, control_version, updated_at)
SELECT 'DEFAULT', 'ENABLED', 1, TIMESTAMP '1970-01-01 00:00:00 UTC'
FROM dual
WHERE NOT EXISTS (SELECT 1 FROM system_control WHERE scope = 'DEFAULT');

CREATE TABLE observation_snapshot (
    snapshot_id       VARCHAR2(36)  NOT NULL,
    order_id          VARCHAR2(36),
    source_name       VARCHAR2(64)  NOT NULL,
    outcome           VARCHAR2(16)  NOT NULL,
    observed_at       TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    source_event_time TIMESTAMP(6) WITH TIME ZONE,
    source_watermark  VARCHAR2(128),
    source_version    VARCHAR2(64),
    error_code        VARCHAR2(64),
    error_message     VARCHAR2(4000),
    payload_hash      VARCHAR2(64),
    payload           CLOB,
    created_at        TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_obs_snapshot PRIMARY KEY (snapshot_id),
    CONSTRAINT ck_obs_outcome CHECK (outcome IN ('FOUND', 'NOT_FOUND', 'UNKNOWN', 'STALE')),
    CONSTRAINT fk_obs_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX idx_snapshot_order ON observation_snapshot (order_id, observed_at);

CREATE TABLE discovery_cursor (
    cursor_name     VARCHAR2(64) NOT NULL,
    last_event_id   VARCHAR2(128),
    last_event_time TIMESTAMP(6) WITH TIME ZONE,
    updated_at      TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_discovery_cursor PRIMARY KEY (cursor_name)
);

CREATE TABLE inbound_event (
    source_event_id     VARCHAR2(128) NOT NULL,
    site_id             VARCHAR2(32),
    lot_id              VARCHAR2(128) NOT NULL,
    origin_operation_id VARCHAR2(128),
    rework_count        NUMBER(10),
    event_time          TIMESTAMP(6) WITH TIME ZONE,
    observed_at         TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    payload             CLOB,
    consumed            NUMBER(1)     DEFAULT 0 NOT NULL,
    order_id            VARCHAR2(36),
    created_at          TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_inbound_event PRIMARY KEY (source_event_id),
    CONSTRAINT ck_inbound_cons CHECK (consumed IN (0, 1)),
    CONSTRAINT fk_inbound_ord FOREIGN KEY (order_id) REFERENCES hold_order (order_id)
);

CREATE INDEX idx_inbound_unconsumed ON inbound_event (consumed, event_time);

INSERT INTO schema_migration (version, name, applied_at)
SELECT 1, 'init', TIMESTAMP '1970-01-01 00:00:00 UTC'
FROM dual
WHERE NOT EXISTS (SELECT 1 FROM schema_migration WHERE version = 1);
