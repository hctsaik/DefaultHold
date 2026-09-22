-- Vision AI Preventive Hold — Oracle DDL（DBA 只建這兩張）
--   MV_NXT_DEF_HOLD_ORDER_BT
--   MV_NXT_DEF_HOLD_INCIDENT_BT
-- 整廠開關：重用 MV_NXT_PARAM_BT（不建新表；key = DEFAULT_HOLD_*）
-- 欄位與 sqlite.sql 的 hold_order／incident 對齊。加欄必須兩份一起改。
-- 目標：Oracle 19c+。連線後建議：ALTER SESSION SET TIME_ZONE = 'UTC';

CREATE TABLE MV_NXT_DEF_HOLD_ORDER_BT (
    order_id                 VARCHAR2(36)   NOT NULL,
    site_id                  VARCHAR2(32),
    lot_id                   VARCHAR2(128)  NOT NULL,
    origin_operation_id      VARCHAR2(128)  NOT NULL,
    rework_count             NUMBER(10)     NOT NULL,
    current_operation_id     VARCHAR2(128),
    target_hold_operation_id VARCHAR2(128),
    future_hold_ope_name     VARCHAR2(128),
    hold_route_id            VARCHAR2(128),
    target_reason            VARCHAR2(4000),
    tool_id                  VARCHAR2(128),
    flow_version             VARCHAR2(64),
    config_version           VARCHAR2(64),
    policy_version           VARCHAR2(64)   NOT NULL,
    lifecycle                VARCHAR2(32)   NOT NULL,
    protection_state         VARCHAR2(32)   NOT NULL,
    ai_state                 VARCHAR2(32)   NOT NULL,
    work_state               VARCHAR2(64)   NOT NULL,
    last_rule_id             VARCHAR2(32),
    state_reason             VARCHAR2(4000),
    close_reason             VARCHAR2(64),
    data_error               VARCHAR2(64),
    row_version              NUMBER(10)     DEFAULT 1 NOT NULL,
    next_check_at            TIMESTAMP(6) WITH TIME ZONE,
    manual_control           VARCHAR2(32)   DEFAULT 'NONE' NOT NULL,
    claim_owner              VARCHAR2(128),
    claim_until              TIMESTAMP(6) WITH TIME ZONE,
    operation_start_at       TIMESTAMP(6) WITH TIME ZONE,
    created_at               TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    updated_at               TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    last_evaluated_at        TIMESTAMP(6) WITH TIME ZONE,
    dh_binding_id            VARCHAR2(36),
    dh_code                  VARCHAR2(32),
    dh_user                  VARCHAR2(32),
    dh_memo                  VARCHAR2(4000),
    dh_status                VARCHAR2(32),
    dh_generation            NUMBER(10),
    dh_kind                  VARCHAR2(16),
    dh_time_quality          VARCHAR2(16)   DEFAULT 'ESTIMATED' NOT NULL,
    dh_requested_at          TIMESTAMP(6) WITH TIME ZONE,
    dh_first_confirmed_at    TIMESTAMP(6) WITH TIME ZONE,
    dh_release_requested_at  TIMESTAMP(6) WITH TIME ZONE,
    dh_released_at           TIMESTAMP(6) WITH TIME ZONE,
    wafers_json              CLOB DEFAULT '[]' NOT NULL,
    actions_json             CLOB DEFAULT '[]' NOT NULL,
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
    CONSTRAINT ck_hold_order_dh CHECK (dh_status IS NULL OR dh_status IN (
        'PENDING', 'CONFIRMED', 'ACTIVE',
        'RELEASE_PENDING', 'RELEASED', 'LOST', 'FAILED'
    )),
    CONSTRAINT uq_hold_order_key UNIQUE (lot_id, origin_operation_id, rework_count)
);

CREATE INDEX idx_hold_order_due ON MV_NXT_DEF_HOLD_ORDER_BT (lifecycle, next_check_at);
CREATE INDEX idx_hold_order_lot ON MV_NXT_DEF_HOLD_ORDER_BT (lot_id);
CREATE INDEX idx_hold_order_work ON MV_NXT_DEF_HOLD_ORDER_BT (lifecycle, work_state);
CREATE INDEX idx_hold_order_recent ON MV_NXT_DEF_HOLD_ORDER_BT (lifecycle, operation_start_at, created_at, order_id);

-- 片／MES retry 在 wafers_json、actions_json。進站去重正式走 PARAM；SQLite 在 agent_control.inbound_json。

CREATE TABLE MV_NXT_DEF_HOLD_INCIDENT_BT (
    incident_id          VARCHAR2(36)   NOT NULL,
    subject_kind         VARCHAR2(16)   NOT NULL,
    subject_key          VARCHAR2(128)  NOT NULL,
    order_id             VARCHAR2(36),
    source_event_id      VARCHAR2(128),
    lot_id               VARCHAR2(128),
    origin_operation_id  VARCHAR2(128),
    rework_count         NUMBER(10),
    incident_type        VARCHAR2(64)   NOT NULL,
    episode_id           VARCHAR2(64)   NOT NULL,
    severity             VARCHAR2(16)   NOT NULL,
    status               VARCHAR2(16)   NOT NULL,
    reason               VARCHAR2(4000),
    error_detail         CLOB,
    first_seen_at        TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    last_seen_at         TIMESTAMP(6) WITH TIME ZONE NOT NULL,
    occurrence_count     NUMBER(10)     DEFAULT 1 NOT NULL,
    acked_at             TIMESTAMP(6) WITH TIME ZONE,
    acked_by             VARCHAR2(64),
    resolved_at          TIMESTAMP(6) WITH TIME ZONE,
    resolved_by          VARCHAR2(64),
    mail_channel         VARCHAR2(32),
    mail_payload         CLOB,
    mail_status          VARCHAR2(16),
    mail_attempt_count   NUMBER(10)     DEFAULT 0 NOT NULL,
    mail_last_error      VARCHAR2(4000),
    mail_next_retry_at   TIMESTAMP(6) WITH TIME ZONE,
    mail_provider_msg_id VARCHAR2(128),
    mail_sent_at         TIMESTAMP(6) WITH TIME ZONE,
    mail_acked_at        TIMESTAMP(6) WITH TIME ZONE,
    CONSTRAINT pk_incident PRIMARY KEY (incident_id),
    CONSTRAINT ck_inc_kind CHECK (subject_kind IN ('ORDER', 'DISCOVERY', 'SYSTEM')),
    CONSTRAINT ck_inc_sev CHECK (severity IN ('INFO', 'WARN', 'ERROR', 'CRITICAL')),
    CONSTRAINT ck_inc_st CHECK (status IN ('OPEN', 'ACKED', 'RESOLVED')),
    CONSTRAINT ck_inc_cnt CHECK (occurrence_count >= 1),
    CONSTRAINT ck_inc_mail CHECK (mail_status IS NULL OR mail_status IN ('PENDING', 'SENT', 'FAILED', 'ACKED')),
    CONSTRAINT uq_inc_episode UNIQUE (subject_key, incident_type, episode_id),
    CONSTRAINT fk_inc_ord FOREIGN KEY (order_id) REFERENCES MV_NXT_DEF_HOLD_ORDER_BT (order_id)
);

CREATE INDEX idx_incident_open ON MV_NXT_DEF_HOLD_INCIDENT_BT (status, last_seen_at);
CREATE INDEX idx_incident_lot ON MV_NXT_DEF_HOLD_INCIDENT_BT (lot_id, status);
CREATE INDEX idx_incident_mail ON MV_NXT_DEF_HOLD_INCIDENT_BT (mail_status, mail_next_retry_at);

-- 不要建 agent_control。整廠開關／恢復／心跳重用現場 MV_NXT_PARAM_BT。
-- Key：DEFAULT_HOLD_MODE 等，見 Design/ORACLE_TABLES_AND_DAO.html。adapter 依現場欄位另實作。
