"""Living decision cascade: one node per path-changing leaf. Generated mermaid must match this list."""

from __future__ import annotations

# Order matches derive_state early-returns. Guards skipped are implied.
DERIVE_LEAVES: list[tuple[str, str, str]] = [
    # rule_id, reason, human label
    ("A1-01", "no_order", "沒有訂單 → 建單"),
    ("A1-07", "manual_review_locked", "已鎖定人工審查"),
    ("A2-13", "authorized_manual_close", "已授權人工結案"),
    ("D-05", "closed_with_own_hold", "已結案仍有本系統 Hold"),
    ("A1-06", "already_closed", "已結案"),
    ("A2-01", "set_hold_in_flight", "設 Hold 命令未查驗完"),
    ("A2-10", "release_sent", "已送解除，MES 可能還沒跟上"),
    ("A2-10", "release_verifying", "查驗是否已解除（允許 Delay）"),
    ("A2-10", "release_in_flight", "解除命令未查驗完"),
    ("A2-14", "hold_query_unknown", "Hold 查詢 UNKNOWN/STALE"),
    ("A1-09", "retry_same_action", "同一命令重試（最多 3 次）"),
    ("A2-11", "release_verified", "解除已在 MES 證實"),
    ("A2-12", "release_rejected_hold_remains", "解除失敗且 Hold 仍在"),
    ("A2-20", "skip_default_hold_smm_present", "現場已有 SMM Hold，不設 Default Hold"),
    ("A2-05", "ai_incomplete", "有防守但 AI 未齊"),
    ("A2-06", "ai_result_invalid", "AI 結果無效"),
    ("A2-09", "scan_dwell", "已掃完，等 settle 分鐘"),
    ("A2-21", "scan_completed", "已掃完且滿 settle，申請解除"),
    ("A2-04", "line_released_after_confirmed", "曾確認的 Hold 被線上解掉，視為解除成功"),
    ("A2-18", "retry_exhausted", "同一命令已送滿 3 次"),
    ("A1-04", "backup_hold_code", "換備援 Hold Code"),
    ("A2-03", "all_hold_codes_failed", "所有 Code 失敗"),
    ("A1-08", "new_holds_disabled", "停用新 Default Hold"),
    ("A1-07", "flow_unknown", "Flow 讀不到"),
    ("A1-07", "cannot_select_target", "選不到防守站"),
    ("A1-02", "select_hold_target", "尚未選站"),
    ("A1-02", "flow_changed_reselect", "Flow 變了重選站"),
    ("A1-03", "need_preventive_hold", "送出 Default Hold"),
]

# Fact shown on the taken edge for each leaf
LEAF_FACT: dict[tuple[str, str], str] = {
    ("A1-01", "no_order"): "無 order",
    ("A1-07", "manual_review_locked"): "work_state=MANUAL_REVIEW",
    ("A2-13", "authorized_manual_close"): "authorized_manual_close",
    ("D-05", "closed_with_own_hold"): "lifecycle=CLOSED 且 own_hold_count>0",
    ("A1-06", "already_closed"): "lifecycle=CLOSED",
    ("A2-01", "set_hold_in_flight"): "in_flight=SET_HOLD:*",
    ("A2-10", "release_sent"): "in_flight=SET_RELEASE 且尚未 ACK",
    ("A2-10", "release_verifying"): "in_flight=SET_RELEASE ACK，Hold 可能因 Delay 還看得到",
    ("A2-10", "release_in_flight"): "in_flight=SET_RELEASE:*",
    ("A1-09", "retry_same_action"): "action_state=RETRY_WAIT",
    ("A2-18", "retry_exhausted"): "attempts>=max_action_attempts",
    ("A2-14", "hold_query_unknown"): "hold_query=UNKNOWN|STALE",
    ("A2-11", "release_verified"): "release_cmd_state=CONFIRMED 且 own_hold_count=0",
    ("A2-12", "release_rejected_hold_remains"): "release 失敗且 Hold 仍在",
    ("A2-20", "skip_default_hold_smm_present"): "現場已有 SMMH/AOA，不設 Default Hold",
    ("A2-05", "ai_incomplete"): "own_hold_count>0 且 ai_status=WAITING|EMPTY",
    ("A2-06", "ai_result_invalid"): "ai_status=INVALID",
    ("A2-09", "scan_dwell"): "已掃完，未滿 scan_settle_minutes",
    ("A2-21", "scan_completed"): "已掃完且 now >= Max(ScanCompletedTime)+settle",
    ("A2-04", "line_released_after_confirmed"): "binding 曾 CONFIRMED，MES 上已沒有本系統 Hold",
    ("A1-04", "backup_hold_code"): "remaining_codes 非空",
    ("A2-03", "all_hold_codes_failed"): "remaining_codes 空",
    ("A1-08", "new_holds_disabled"): "control≠ENABLED",
    ("A1-07", "flow_unknown"): "flow_query=UNKNOWN|STALE",
    ("A1-07", "cannot_select_target"): "選站失敗",
    ("A1-02", "select_hold_target"): "has_target=false",
    ("A1-02", "flow_changed_reselect"): "flow_version_match=false",
    ("A1-03", "need_preventive_hold"): "has_target=true",
}

OUTCOME_LEAVES: list[tuple[str, str, str]] = [
    ("A2-02", "hold.confirmed", "MES 對上本系統 Hold"),
    ("A2-11", "release.confirmed", "MES 已無本系統 Hold → CLOSED"),
    ("A2-12", "release.failed", "解除被拒"),
    ("D-01", "HOLD_OVERDUE", "Hold > 30 分"),
    ("D-02", "control.disabled", "第 3 批超時停用"),
    ("D-03", "COVERAGE_MISMATCH", "應守 vs 實守不一致"),
    ("D-04", "hold.orphan", "有 Default Hold 無訂單"),
    ("D-05", "STATE_CONFLICT", "結案仍有 Hold"),
    ("D-06", "agent.stall", "主路徑心跳過期"),
]


def nid(rule_id: str, reason: str) -> str:
    raw = f"{rule_id}_{reason}".replace("-", "_").replace(".", "_")
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in raw)


def mermaid_full_tree() -> str:
    lines = [
        "flowchart TB",
        "  S[觀察 Snapshot]",
    ]
    prev = "S"
    for i, (rule, reason, label) in enumerate(DERIVE_LEAVES):
        node = nid(rule, reason)
        lines.append(f'  {node}["{rule} {label}"]')
        if i == 0:
            lines.append(f"  {prev} --> {node}")
        else:
            lines.append(f"  {prev} -->|否| {node}")
        prev = node
    lines.append("  subgraph OUTCOME[查驗與 Defense 結果]")
    for rule, reason, label in OUTCOME_LEAVES:
        node = nid(rule, reason)
        lines.append(f'    {node}["{rule} {label}"]')
    lines.append("  end")
    lines.append("  A2_01_set_hold_in_flight --> A2_02_hold_confirmed")
    lines.append("  A2_10_release_in_flight --> A2_11_release_confirmed")
    lines.append("  A2_07_ai_ok --> A2_11_release_confirmed")
    return "\n".join(lines) + "\n"


def leaf_index(rule_id: str, reason: str | None) -> int | None:
    if reason:
        for i, (r, s, _) in enumerate(DERIVE_LEAVES):
            if r == rule_id and s == reason:
                return i
    for i, (r, s, _) in enumerate(DERIVE_LEAVES):
        if r == rule_id:
            return i
    return None


def path_spine(rule_id: str, reason: str | None, facts: dict | None) -> list[tuple[str, str, str]]:
    """Taken cascade nodes up to the leaf, with fact captions."""
    idx = leaf_index(rule_id, reason)
    if idx is None:
        return []
    facts = facts or {}
    out: list[tuple[str, str, str]] = []
    for i, (r, s, label) in enumerate(DERIVE_LEAVES[: idx + 1]):
        cap = LEAF_FACT.get((r, s), "")
        if i < idx:
            out.append((r, s, f"不是：{label}"))
        else:
            extra = _fact_caption(r, s, facts)
            out.append((r, s, extra or cap or label))
    # keep diagram small: only last 6 skipped + leaf
    if len(out) > 7:
        out = out[-7:]
    return out


def _fact_caption(rule_id: str, reason: str, facts: dict) -> str:
    mapping = {
        ("A2-01", "set_hold_in_flight"): f"in_flight={facts.get('in_flight')}",
        ("A2-05", "ai_incomplete"): f"ai_status={facts.get('ai_status')} missing={facts.get('missing_wafers')}",
        ("A2-09", "scan_dwell"): f"ai_status={facts.get('ai_status')}",
        ("A2-21", "scan_completed"): f"ai_status={facts.get('ai_status')}",
        ("A2-20", "skip_default_hold_smm_present"): "smm_hold_present",
        ("A2-14", "hold_query_unknown"): f"hold_query={facts.get('hold_query')}",
        ("A1-03", "need_preventive_hold"): f"has_target={facts.get('has_target')}",
        ("A1-02", "select_hold_target"): f"has_target={facts.get('has_target')}",
        ("A1-08", "new_holds_disabled"): f"control={facts.get('control')}",
        ("A1-04", "backup_hold_code"): f"remaining={facts.get('remaining_codes')}",
        ("A2-03", "all_hold_codes_failed"): f"attempted={facts.get('codes_attempted')}",
    }
    return mapping.get((rule_id, reason), "")
