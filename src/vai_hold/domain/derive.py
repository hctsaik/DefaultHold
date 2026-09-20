from __future__ import annotations

from dataclasses import dataclass

from vai_hold.domain.ai_complete import expected_complete
from vai_hold.domain.enums import (
    ActionState,
    ActionType,
    AiState,
    BindingRole,
    BindingStatus,
    BusinessAction,
    ControlMode,
    Lifecycle,
    ProtectionState,
    ReceiptOutcome,
    SourceStatus,
    WorkState,
)
from vai_hold.domain.models import (
    ActionCommand,
    Decision,
    FlowView,
    HoldBinding,
    HoldCommand,
    HoldOrder,
    HoldTarget,
    IN_FLIGHT_ACTION_STATES,
    SourceResult,
    SystemControl,
    WaferAiView,
)
from vai_hold.domain.ownership import is_smm_hold, match_our_holds
from vai_hold.domain.retry import retry_wait_commands
from vai_hold.domain.smm_memo import (
    DEFAULT_TEMPLATE,
    defect_slots,
    format_smm_memo,
    memo_needs_transfer,
    merged_slots,
)
from vai_hold.domain.target import choose_hold_target, smm_hold_ope_no


@dataclass
class Snapshot:
    order: HoldOrder | None
    control: SystemControl
    hold_query: SourceResult  # list[HoldCommand] | None
    flow_query: SourceResult  # FlowView | None
    expected_wafer_ids: list[str]
    ai_views: list[WaferAiView]
    bindings: list[HoldBinding]
    in_flight: ActionCommand | None
    commands: list[ActionCommand]
    standard_memo: str
    hold_user: str
    hold_codes: list[str]
    station_priority: list[str]
    policy_version: str
    authorized_manual_close: bool = False
    ai_query: SourceResult | None = None
    smm_hold_code: str = "SMMH"
    smm_hold_user: str = "AOA"
    smm_hold_step: str = "DefaultHoldStep"
    smm_memo_template: str = "Please check {slots}"
    max_action_attempts: int = 3


def _codes_attempted(commands: list[ActionCommand]) -> list[str]:
    out: list[str] = []
    for c in commands:
        if c.action_type == ActionType.SET_HOLD and c.hold_code:
            if c.hold_code not in out:
                out.append(c.hold_code)
    return out


def derive_state(snap: Snapshot) -> Decision:
    order = snap.order
    if order is None:
        return Decision(
            rule_id="A1-01",
            work_state=WorkState.NEED_ORDER,
            protection_state=ProtectionState.NONE,
            ai_state=AiState.WAITING,
            business_action=BusinessAction.CREATE_ORDER,
            reason="no_order",
        )

    if order.work_state == WorkState.MANUAL_REVIEW:
        return Decision(
            rule_id="A1-07",
            work_state=WorkState.MANUAL_REVIEW,
            protection_state=order.protection_state,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="manual_review_locked",
        )

    if snap.authorized_manual_close:
        return Decision(
            rule_id="A2-13",
            work_state=WorkState.MANUAL_CLOSED,
            protection_state=order.protection_state,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="authorized_manual_close",
        )

    if order.lifecycle in (Lifecycle.CLOSED, Lifecycle.MANUAL_CLOSED):
        own = []
        if snap.hold_query.status == SourceStatus.FOUND and snap.hold_query.value:
            own = match_our_holds(
                snap.hold_query.value,
                order,
                snap.bindings,
                standard_memo=snap.standard_memo,
                hold_user=snap.hold_user,
            )
        if own:
            return Decision(
                rule_id="D-05",
                work_state=WorkState.STATE_CONFLICT,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=order.ai_state,
                business_action=BusinessAction.OPEN_INCIDENT,
                reason="closed_with_own_hold",
                incidents=["STATE_CONFLICT"],
            )
        return Decision(
            rule_id="A1-06",
            work_state=WorkState.CLOSED
            if order.lifecycle == Lifecycle.CLOSED
            else WorkState.MANUAL_CLOSED,
            protection_state=ProtectionState.RELEASED,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="already_closed",
        )

    inflight = snap.in_flight
    if inflight and inflight.action_state in IN_FLIGHT_ACTION_STATES:
        if inflight.action_type == ActionType.SET_HOLD:
            return Decision(
                rule_id="A2-01",
                work_state=WorkState.HOLD_VERIFY_PENDING,
                protection_state=ProtectionState.SET_PENDING,
                ai_state=order.ai_state,
                business_action=BusinessAction.VERIFY_HOLD,
                reason="set_hold_in_flight",
                hold_code=inflight.hold_code,
            )
        if inflight.action_type == ActionType.SET_RELEASE:
            # 已送出 ≠ 已查到。MES／DB Delay 時 Hold 可能還看得到，不能當失敗或重送。
            still_querying = inflight.action_state == ActionState.ACKNOWLEDGED
            return Decision(
                rule_id="A2-10",
                work_state=WorkState.RELEASE_VERIFY_PENDING if still_querying else WorkState.RELEASE_SENT,
                protection_state=ProtectionState.RELEASE_PENDING,
                ai_state=order.ai_state,
                business_action=BusinessAction.VERIFY_RELEASE,
                reason="release_verifying" if still_querying else "release_sent",
                hold_code=inflight.hold_code,
            )
        if inflight.action_type == ActionType.TRANSFER_HOLD:
            return Decision(
                rule_id="A2-16",
                work_state=order.work_state if order.work_state != WorkState.NEED_HOLD else WorkState.WAIT_AI,
                protection_state=order.protection_state,
                ai_state=order.ai_state,
                business_action=BusinessAction.NONE,
                reason="transfer_in_flight",
                hold_code=inflight.hold_code,
                memo=inflight.expected_postcondition,
            )

    if snap.hold_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
        return Decision(
            rule_id="A2-14",
            work_state=WorkState.OBSERVATION_UNKNOWN,
            protection_state=ProtectionState.UNKNOWN,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="hold_query_unknown",
            incidents=["DATA_STALE"] if snap.hold_query.status == SourceStatus.STALE else ["HOLD_QUERY_UNKNOWN"],
        )

    retrying = retry_wait_commands(snap.commands)
    if retrying:
        cmd = retrying[-1]
        if cmd.action_type == ActionType.SET_HOLD:
            return Decision(
                rule_id="A1-09",
                work_state=WorkState.NEED_HOLD,
                protection_state=ProtectionState.FAILED,
                ai_state=order.ai_state,
                business_action=BusinessAction.SET_HOLD,
                reason="retry_same_action",
                hold_code=cmd.hold_code,
            )
        if cmd.action_type == ActionType.SET_RELEASE:
            return Decision(
                rule_id="A1-09",
                work_state=WorkState.READY_RELEASE_OK,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=order.ai_state,
                business_action=BusinessAction.SET_RELEASE,
                reason="retry_same_action",
                hold_code=cmd.hold_code,
            )
        if cmd.action_type == ActionType.TRANSFER_HOLD:
            return Decision(
                rule_id="A1-09",
                work_state=WorkState.WAIT_AI,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=order.ai_state,
                business_action=BusinessAction.TRANSFER_HOLD,
                reason="retry_same_action",
                hold_code=cmd.hold_code,
                memo=cmd.expected_postcondition,
            )

    mes_holds: list[HoldCommand] = []
    if snap.hold_query.status == SourceStatus.FOUND and snap.hold_query.value:
        mes_holds = list(snap.hold_query.value)

    own_holds = match_our_holds(
        mes_holds,
        order,
        [b for b in snap.bindings if b.role == BindingRole.PREVENTIVE],
        standard_memo=snap.standard_memo,
        hold_user=snap.hold_user,
    )

    confirmed_binding = next(
        (
            b
            for b in snap.bindings
            if b.role == BindingRole.PREVENTIVE
            and b.status in {BindingStatus.CONFIRMED, BindingStatus.ACTIVE, BindingStatus.RELEASE_PENDING}
        ),
        None,
    )

    release_cmd = next(
        (c for c in snap.commands if c.action_type == ActionType.SET_RELEASE),
        None,
    )

    if release_cmd and release_cmd.action_state == ActionState.CONFIRMED and not own_holds:
        return Decision(
            rule_id="A2-11",
            work_state=WorkState.CLOSED,
            protection_state=ProtectionState.RELEASED,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="release_verified",
        )

    if release_cmd and release_cmd.action_state == ActionState.REJECTED and own_holds:
        return Decision(
            rule_id="A2-12",
            work_state=WorkState.RELEASE_FAILED,
            protection_state=ProtectionState.CONFIRMED,
            ai_state=order.ai_state,
            business_action=BusinessAction.OPEN_INCIDENT,
            reason="release_rejected_hold_remains",
            incidents=["RELEASE_FAILED"],
        )

    smm_at_dh = [
        h
        for h in mes_holds
        if order.target_hold_ope_no
        and is_smm_hold(
            h,
            lot_id=order.lot_id,
            hold_code=snap.smm_hold_code,
            hold_user=snap.smm_hold_user,
            ope_no=order.target_hold_ope_no,
        )
    ]
    if smm_at_dh and not own_holds:
        ai_status, missing = expected_complete(
            snap.expected_wafer_ids, snap.ai_views, rework_count=order.rework_count
        )
        if ai_status in {"WAITING", "EMPTY"} or (
            snap.ai_query is not None and snap.ai_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE)
        ):
            return Decision(
                rule_id="A2-20",
                work_state=WorkState.WAIT_AI,
                protection_state=ProtectionState.NONE,
                ai_state=AiState.UNKNOWN
                if snap.ai_query is not None and snap.ai_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE)
                else AiState.WAITING,
                business_action=BusinessAction.CHECK_AI,
                reason="skip_default_hold_smm_present",
                missing_wafers=missing,
            )
        if ai_status == "COMPLETE_OK":
            return Decision(
                rule_id="A2-20",
                work_state=WorkState.CLOSED,
                protection_state=ProtectionState.NONE,
                ai_state=AiState.COMPLETE_OK,
                business_action=BusinessAction.NONE,
                reason="skip_default_hold_smm_present_ai_ok",
            )
        if ai_status == "INVALID":
            return Decision(
                rule_id="A2-06",
                work_state=WorkState.AI_RESULT_INVALID,
                protection_state=ProtectionState.NONE,
                ai_state=AiState.INVALID,
                business_action=BusinessAction.OPEN_INCIDENT,
                reason="ai_result_invalid",
                incidents=["AI_RESULT_INVALID"],
            )
        return Decision(
            rule_id="A2-08",
            work_state=WorkState.CLOSED,
            protection_state=ProtectionState.NONE,
            ai_state=AiState.COMPLETE_DEFECT,
            business_action=BusinessAction.NONE,
            reason="skip_default_hold_smm_handoff",
        )

    if own_holds:
        if snap.ai_query is not None and snap.ai_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
            return Decision(
                rule_id="A2-05",
                work_state=WorkState.WAIT_AI,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=AiState.UNKNOWN,
                business_action=BusinessAction.CHECK_AI,
                reason="ai_query_unknown",
            )
        ai_status, missing = expected_complete(
            snap.expected_wafer_ids, snap.ai_views, rework_count=order.rework_count
        )
        fv = snap.flow_query.value if snap.flow_query.status == SourceStatus.FOUND else None
        # 接手：Default Hold 站上有 SMM Hold 即可（D04）
        smm_ope = order.target_hold_ope_no
        defect_holds = [
            h
            for h in mes_holds
            if is_smm_hold(
                h,
                lot_id=order.lot_id,
                hold_code=snap.smm_hold_code,
                hold_user=snap.smm_hold_user,
                ope_no=smm_ope,
            )
        ]
        desired_slots = defect_slots(
            snap.expected_wafer_ids, snap.ai_views, rework_count=order.rework_count
        )
        transfer = _smm_transfer_decision(snap, order, defect_holds, desired_slots)
        if transfer is not None:
            return transfer
        if ai_status in {"WAITING", "EMPTY"}:
            return Decision(
                rule_id="A2-05",
                work_state=WorkState.WAIT_AI,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=AiState.WAITING,
                business_action=BusinessAction.CHECK_AI,
                reason="ai_incomplete",
                missing_wafers=missing,
            )
        if ai_status == "INVALID":
            return Decision(
                rule_id="A2-06",
                work_state=WorkState.AI_RESULT_INVALID,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=AiState.INVALID,
                business_action=BusinessAction.OPEN_INCIDENT,
                reason="ai_result_invalid",
                missing_wafers=missing,
                incidents=["AI_RESULT_INVALID"],
            )
        if ai_status == "COMPLETE_OK":
            return Decision(
                rule_id="A2-07",
                work_state=WorkState.READY_RELEASE_OK,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=AiState.COMPLETE_OK,
                business_action=BusinessAction.SET_RELEASE,
                reason="ai_ok",
            )
        if defect_holds:
            return Decision(
                rule_id="A2-08",
                work_state=WorkState.READY_RELEASE_HANDOFF,
                protection_state=ProtectionState.CONFIRMED,
                ai_state=AiState.COMPLETE_DEFECT,
                business_action=BusinessAction.SET_RELEASE,
                reason="defect_hold_handoff",
            )
        return Decision(
            rule_id="A2-09",
            work_state=WorkState.DEFECT_HOLD_UNCONFIRMED,
            protection_state=ProtectionState.CONFIRMED,
            ai_state=AiState.COMPLETE_DEFECT,
            business_action=BusinessAction.OPEN_INCIDENT,
            reason="defect_without_formal_hold",
            incidents=["DEFECT_HOLD_UNCONFIRMED"],
        )

    if confirmed_binding and not own_holds and not (
        release_cmd and release_cmd.action_state in IN_FLIGHT_ACTION_STATES | {ActionState.CONFIRMED}
    ):
        # 現場：曾經確認設上，後來被線上解掉（含我們 Release 失敗請線上代解）→ 當成解除成功
        return Decision(
            rule_id="A2-04",
            work_state=WorkState.MANUAL_CLOSED,
            protection_state=ProtectionState.RELEASED,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="line_released_after_confirmed",
        )

    last_set = next((c for c in reversed(snap.commands) if c.action_type == ActionType.SET_HOLD), None)
    if last_set and last_set.action_state == ActionState.REJECTED:
        post = (last_set.expected_postcondition or "").upper()
        if post in {"TRANSIENT", "RATE_LIMIT", "TIMEOUT", "RETRY_EXHAUSTED"}:
            return Decision(
                rule_id="A2-18",
                work_state=WorkState.HOLD_FAILED,
                protection_state=ProtectionState.FAILED,
                ai_state=order.ai_state,
                business_action=BusinessAction.OPEN_INCIDENT,
                reason="retry_exhausted",
                incidents=["HOLD_FAILED"],
            )

    attempted = _codes_attempted(snap.commands)
    rejected_terminal = [
        c
        for c in snap.commands
        if c.action_type == ActionType.SET_HOLD
        and c.action_state == ActionState.REJECTED
        and c.receipt_outcome == ReceiptOutcome.REJECTED
    ]
    permission_fail = any(
        (c.expected_postcondition or "") == "PERMISSION" for c in rejected_terminal
    )
    remaining = [c for c in snap.hold_codes if c not in attempted]
    if permission_fail:
        remaining = []
    conflict_ok = all(
        (c.expected_postcondition or "CODE_CONFLICT") in {"CODE_CONFLICT", "CONFLICT", ""}
        for c in rejected_terminal
    )

    if rejected_terminal and remaining and conflict_ok and not permission_fail:
        return Decision(
            rule_id="A1-04",
            work_state=WorkState.NEED_BACKUP_HOLD,
            protection_state=ProtectionState.FAILED,
            ai_state=order.ai_state,
            business_action=BusinessAction.SET_HOLD,
            reason="backup_hold_code",
            hold_code=remaining[0],
        )

    if rejected_terminal and not remaining:
        return Decision(
            rule_id="A2-03",
            work_state=WorkState.HOLD_FAILED,
            protection_state=ProtectionState.FAILED,
            ai_state=order.ai_state,
            business_action=BusinessAction.OPEN_INCIDENT,
            reason="all_hold_codes_failed",
            incidents=["HOLD_FAILED"],
        )

    if snap.control.mode != ControlMode.ENABLED:
        return Decision(
            rule_id="A1-08",
            work_state=WorkState.BLOCKED_BY_CONTROL,
            protection_state=ProtectionState.NONE,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="new_holds_disabled",
            incidents=["BLOCKED_BY_CONTROL"],
        )

    if snap.flow_query.status in (SourceStatus.UNKNOWN, SourceStatus.STALE):
        return Decision(
            rule_id="A1-07",
            work_state=WorkState.OBSERVATION_UNKNOWN,
            protection_state=ProtectionState.NONE,
            ai_state=order.ai_state,
            business_action=BusinessAction.NONE,
            reason="flow_unknown",
        )

    target = choose_hold_target(snap.flow_query, station_priority=snap.station_priority)
    if target is None:
        return Decision(
            rule_id="A1-07",
            work_state=WorkState.MANUAL_REVIEW,
            protection_state=ProtectionState.NONE,
            ai_state=order.ai_state,
            business_action=BusinessAction.OPEN_INCIDENT,
            reason="cannot_select_target",
            incidents=["MANUAL_REVIEW"],
        )

    if not order.target_hold_ope_no:
        return Decision(
            rule_id="A1-02",
            work_state=WorkState.NEED_TARGET,
            protection_state=ProtectionState.NONE,
            ai_state=order.ai_state,
            business_action=BusinessAction.SELECT_TARGET,
            reason="select_hold_target",
            target=target,
            hold_code=snap.hold_codes[0] if snap.hold_codes else None,
        )

    # re-select if flow moved
    if (
        order.flow_version
        and isinstance(snap.flow_query.value, FlowView)
        and order.flow_version != snap.flow_query.value.version
    ):
        return Decision(
            rule_id="A1-02",
            work_state=WorkState.NEED_TARGET,
            protection_state=ProtectionState.NONE,
            ai_state=order.ai_state,
            business_action=BusinessAction.SELECT_TARGET,
            reason="flow_changed_reselect",
            target=target,
            hold_code=snap.hold_codes[0] if snap.hold_codes else None,
        )

    return Decision(
        rule_id="A1-03",
        work_state=WorkState.NEED_HOLD,
        protection_state=ProtectionState.NONE,
        ai_state=order.ai_state,
        business_action=BusinessAction.SET_HOLD,
        reason="need_preventive_hold",
        target=HoldTarget(
            route_id=order.hold_route_id or target.route_id,
            ope_no=order.target_hold_ope_no or target.ope_no,
            ope_name=order.future_hold_ope_name or target.ope_name,
            kind=target.kind,
            reason=order.target_reason or target.reason,
            flow_version=order.flow_version or target.flow_version,
        ),
        hold_code=snap.hold_codes[0] if snap.hold_codes else None,
    )


def _smm_transfer_decision(snap: Snapshot, order, defect_holds: list, desired_slots: list[int]) -> Decision | None:
    if not defect_holds or not desired_slots:
        return None
    current = defect_holds[0]
    if not memo_needs_transfer(current.memo, desired_slots):
        return None
    slots = merged_slots(current.memo, desired_slots)
    memo = format_smm_memo(snap.smm_memo_template or DEFAULT_TEMPLATE, slots)
    prior = [
        c
        for c in snap.commands
        if c.action_type == ActionType.TRANSFER_HOLD and c.expected_postcondition == memo
    ]
    if any(c.action_state == ActionState.REJECTED for c in prior):
        return Decision(
            rule_id="A2-18",
            work_state=WorkState.WAIT_AI,
            protection_state=ProtectionState.CONFIRMED,
            ai_state=order.ai_state,
            business_action=BusinessAction.OPEN_INCIDENT,
            reason="retry_exhausted",
            incidents=["TRANSFER_FAILED"],
            memo=memo,
        )
    return Decision(
        rule_id="A2-16",
        work_state=WorkState.WAIT_AI,
        protection_state=ProtectionState.CONFIRMED,
        ai_state=order.ai_state,
        business_action=BusinessAction.TRANSFER_HOLD,
        reason="smm_memo_transfer",
        hold_code=current.hold_code,
        memo=memo,
    )


def plan_action(decision: Decision, function_code: str) -> Decision:
    """Restrict action to what this pipeline is allowed to execute."""
    from vai_hold.domain.enums import FunctionCode

    allowed = {
        FunctionCode.SET_DEFAULT_HOLD: {
            BusinessAction.CREATE_ORDER,
            BusinessAction.SELECT_TARGET,
            BusinessAction.SET_HOLD,
            BusinessAction.NONE,
            BusinessAction.OPEN_INCIDENT,
        },
        FunctionCode.CONFIRM_HOLD: {
            BusinessAction.VERIFY_HOLD,
            BusinessAction.OPEN_INCIDENT,
            BusinessAction.NONE,
        },
        FunctionCode.CHECK_AI: {
            BusinessAction.CHECK_AI,
            BusinessAction.SET_RELEASE,
            BusinessAction.TRANSFER_HOLD,
            BusinessAction.OPEN_INCIDENT,
            BusinessAction.NONE,
        },
        FunctionCode.CONFIRM_RELEASE: {
            BusinessAction.VERIFY_RELEASE,
            BusinessAction.OPEN_INCIDENT,
            BusinessAction.NONE,
        },
        FunctionCode.DEFENSE: {
            BusinessAction.OPEN_INCIDENT,
            BusinessAction.NONE,
        },
        FunctionCode.RESUME: {BusinessAction.NONE},
        FunctionCode.MANUAL_CLOSE: {BusinessAction.NONE},
    }.get(FunctionCode(function_code), {BusinessAction.NONE})

    if decision.business_action not in allowed:
        decision.business_action = BusinessAction.NONE
    return decision
