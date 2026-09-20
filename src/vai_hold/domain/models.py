from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from vai_hold.domain.enums import (
    ActionState,
    ActionType,
    AiState,
    BindingRole,
    BindingStatus,
    BusinessAction,
    ControlMode,
    HoldKind,
    Lifecycle,
    ManualControl,
    ProtectionState,
    ReceiptOutcome,
    SourceStatus,
    WorkState,
)


@dataclass(frozen=True)
class OrderKey:
    lot_id: str
    ope_no: str
    rework_count: int

    def as_tuple(self) -> tuple[str, str, int]:
        return (self.lot_id, self.ope_no, self.rework_count)


@dataclass
class HoldCommand:
    lot_id: str
    route_id: str
    ope_no: str
    memo: str
    hold_code: str
    hold_user: str
    kind: str | None = None  # FUTURE / CURRENT, optional MES hint
    tool_id: str | None = None
    hold_type: str | None = None
    idempotency_key: str | None = None
    new_memo: str | None = None


@dataclass
class TransportReceipt:
    outcome: ReceiptOutcome
    started_at: datetime
    finished_at: datetime
    provider_request_id: str | None = None
    raw_error_code: str | None = None
    normalized_error: str | None = None
    retry_class: str | None = None


@dataclass
class SourceResult:
    status: SourceStatus
    value: Any = None
    observed_at: datetime | None = None
    source_event_time: datetime | None = None
    source_watermark: str | None = None
    source_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    source_name: str = ""


@dataclass
class FlowStep:
    ope_no: str
    name: str
    process_type: str  # "METROLOGY" | "PROCESS_TOOL" | "OTHER"
    index: int
    tool_id: str | None = None


@dataclass
class FlowView:
    route_id: str
    version: str
    current_ope_no: str
    steps: list[FlowStep]
    current_tool_id: str | None = None


@dataclass
class HoldTarget:
    route_id: str  # MainPdId
    ope_no: str  # FutureHoldStep
    kind: HoldKind
    reason: str
    flow_version: str
    ope_name: str = ""  # FutureHoldOpeName


@dataclass
class WaferAiView:
    wafer_id: str
    scan_completed_at: datetime | None = None
    result: str | None = None  # OK / DEFECT / INVALID / None
    defect_types: list[str] = field(default_factory=list)
    result_version: str | None = None
    rework_count: int | None = None


@dataclass
class HoldOrder:
    order_id: str
    lot_id: str
    origin_ope_no: str
    rework_count: int
    policy_version: str
    lifecycle: Lifecycle = Lifecycle.OPEN
    protection_state: ProtectionState = ProtectionState.NONE
    ai_state: AiState = AiState.WAITING
    work_state: WorkState = WorkState.NEED_HOLD
    site_id: str | None = None
    visit_id: str | None = None
    current_ope_no: str | None = None
    target_hold_ope_no: str | None = None
    future_hold_ope_name: str | None = None
    hold_route_id: str | None = None
    target_occurrence: str | None = None
    target_reason: str | None = None
    tool_id: str | None = None
    flow_version: str | None = None
    config_version: str | None = None
    manifest_version: int | None = None
    last_rule_id: str | None = None
    state_reason: str | None = None
    close_reason: str | None = None
    data_error: str | None = None  # 事後可查：NO_SMM_HOLD_AFTER_SCAN 等
    last_snapshot_ref: str | None = None
    row_version: int = 1
    next_check_at: datetime | None = None
    manual_control: ManualControl = ManualControl.NONE
    claim_owner: str | None = None
    claim_until: datetime | None = None
    operation_start_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_evaluated_at: datetime | None = None

    @property
    def key(self) -> OrderKey:
        return OrderKey(self.lot_id, self.origin_ope_no, self.rework_count)


@dataclass
class OrderWafer:
    order_id: str
    wafer_id: str
    roster_version: int
    updated_at: datetime
    operation_start_at: datetime | None = None
    operation_complete_at: datetime | None = None
    scan_completed_at: datetime | None = None
    ai_result: str | None = None
    defect_types: str | None = None
    result_version: str | None = None
    required_tasks: str | None = None
    missing_alarm_type: bool = False  # 有 ScanCompletedTime 但沒有 Alarm Type


@dataclass
class HoldBinding:
    binding_id: str
    lot_id: str
    route_id: str
    ope_no: str
    hold_code: str
    hold_user: str
    hold_memo: str
    role: BindingRole
    status: BindingStatus
    created_at: datetime
    updated_at: datetime
    order_id: str | None = None
    generation: int = 1
    mes_hold_record_id: str | None = None
    hold_token: str | None = None
    target_step_occurrence: str | None = None
    hold_kind: HoldKind | None = None
    time_quality: str = "ESTIMATED"
    requested_at: datetime | None = None
    provider_created_at: datetime | None = None
    first_confirmed_at: datetime | None = None
    effective_at: datetime | None = None
    release_requested_at: datetime | None = None
    released_at: datetime | None = None
    release_verified_at: datetime | None = None


@dataclass
class ActionCommand:
    command_id: str
    order_id: str
    logical_action_key: str
    action_type: ActionType
    idempotency_key: str
    action_state: ActionState
    created_at: datetime
    updated_at: datetime
    generation: int | None = None
    hold_code: str | None = None
    target_occurrence: str | None = None
    payload_hash: str | None = None
    payload_json: str | None = None
    receipt_outcome: ReceiptOutcome | None = None
    current_attempt_id: str | None = None
    expected_postcondition: str | None = None
    evidence_ref: str | None = None


@dataclass
class ActionAttempt:
    attempt_id: str
    command_id: str
    order_id: str
    attempt_no: int
    started_at: datetime
    dispatched_at: datetime | None = None
    finished_at: datetime | None = None
    receipt_outcome: ReceiptOutcome | None = None
    provider_request_id: str | None = None
    raw_error_code: str | None = None
    normalized_error: str | None = None
    retry_class: str | None = None
    raw_response_masked: str | None = None
    actor: str | None = None
    rule_id: str | None = None
    program_version: str | None = None
    before_snapshot_ref: str | None = None
    after_snapshot_ref: str | None = None


@dataclass
class Incident:
    incident_id: str
    subject_kind: str
    subject_key: str
    incident_type: str
    episode_id: str
    severity: str
    status: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int = 1
    order_id: str | None = None
    source_event_id: str | None = None
    lot_id: str | None = None
    origin_ope_no: str | None = None
    rework_count: int | None = None
    reason: str | None = None
    error_detail: str | None = None
    evidence_ref: str | None = None
    acked_at: datetime | None = None
    acked_by: str | None = None
    resolved_at: datetime | None = None
    resolved_by: str | None = None


@dataclass
class OutboxRow:
    outbox_id: str
    incident_id: str
    channel: str
    payload: str
    delivery_status: str
    created_at: datetime
    attempt_count: int = 0
    last_error: str | None = None
    next_retry_at: datetime | None = None
    provider_msg_id: str | None = None
    sent_at: datetime | None = None
    acked_at: datetime | None = None


@dataclass
class SystemControl:
    scope: str
    mode: ControlMode
    control_version: int
    updated_at: datetime
    disable_reason: str | None = None
    disable_trigger: str | None = None
    disabled_at: datetime | None = None
    sponsor_id: str | None = None
    sponsor_approved_at: datetime | None = None
    resume_evidence_ref: str | None = None
    health_check_ref: str | None = None


@dataclass
class InboundEvent:
    source_event_id: str
    lot_id: str
    observed_at: datetime
    created_at: datetime
    site_id: str | None = None
    origin_ope_no: str | None = None
    rework_count: int | None = None
    event_time: datetime | None = None
    payload: str | None = None
    consumed: bool = False
    order_id: str | None = None


@dataclass
class DiscoveryCursor:
    cursor_name: str
    updated_at: datetime
    last_event_id: str | None = None
    last_event_time: datetime | None = None


@dataclass
class ObservationSnapshot:
    snapshot_id: str
    source_name: str
    outcome: SourceStatus
    observed_at: datetime
    created_at: datetime
    order_id: str | None = None
    source_event_time: datetime | None = None
    source_watermark: str | None = None
    source_version: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    payload_hash: str | None = None
    payload: str | None = None


@dataclass
class Decision:
    rule_id: str
    work_state: WorkState
    protection_state: ProtectionState
    ai_state: AiState
    business_action: BusinessAction
    reason: str
    hold_code: str | None = None
    target: HoldTarget | None = None
    missing_wafers: list[str] = field(default_factory=list)
    incidents: list[str] = field(default_factory=list)
    memo: str | None = None  # desired SmmHold memo for TRANSFER_HOLD


IN_FLIGHT_ACTION_STATES = frozenset(
    {
        ActionState.PREPARED,
        ActionState.DISPATCHED,
        ActionState.ACKNOWLEDGED,
        ActionState.UNKNOWN,
    }
)
