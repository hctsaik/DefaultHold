from __future__ import annotations

import re

from vai_hold.domain.models import WaferAiView

DEFAULT_TEMPLATE = "Please check {slots}"
_HASH_SLOT = re.compile(r"#(\d+)")
_WAFER_MEMO = re.compile(r"please check", re.IGNORECASE)


def format_smm_memo(template: str, slots: list[int]) -> str:
    joined = ",".join(f"#{s}" for s in slots)
    tmpl = template or DEFAULT_TEMPLATE
    if "{slots}" in tmpl:
        return tmpl.replace("{slots}", joined)
    return f"Please check {joined}"


def parse_smm_slots(memo: str | None) -> list[int]:
    if not memo:
        return []
    out: list[int] = []
    for n in _HASH_SLOT.findall(memo):
        v = int(n)
        if v not in out:
            out.append(v)
    return out


def mes_wafer_id(lot_id: str, slot: int) -> str:
    """現場 wafer id：A123456.01（lot + '.' + 兩位片號）。"""
    return f"{lot_id}.{int(slot):02d}"


def wafer_number(wafer_id: str) -> int | None:
    """從 MES wafer id 解出片號。A123456.01 → 1；後備 W03 → 3。"""
    text = (wafer_id or "").strip()
    m = re.search(r"\.(\d+)\s*$", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*$", text)
    return int(m.group(1)) if m else None


def defect_slots(
    expected_ids: list[str],
    views: list[WaferAiView],
    *,
    rework_count: int,
) -> list[int]:
    """Wafer numbers (#N) whose AI result is DEFECT."""
    by_id: dict[str, WaferAiView] = {}
    for v in views:
        if v.rework_count is not None and v.rework_count != rework_count:
            continue
        prev = by_id.get(v.wafer_id)
        if prev is None or (v.scan_completed_at and not prev.scan_completed_at):
            by_id[v.wafer_id] = v
    slots: list[int] = []
    for wid in expected_ids:
        v = by_id.get(wid)
        if v and v.scan_completed_at and v.result == "DEFECT":
            n = wafer_number(wid)
            if n is not None and n not in slots:
                slots.append(n)
    return sorted(slots)


def merged_slots(actual_memo: str | None, desired: list[int]) -> list[int]:
    return sorted(set(parse_smm_slots(actual_memo)) | set(desired))


def is_wafer_check_memo(memo: str | None) -> bool:
    if not memo:
        return False
    return bool(_WAFER_MEMO.search(memo)) or bool(_HASH_SLOT.search(memo) and "please check" in memo.lower())


def memo_needs_transfer(actual_memo: str | None, desired_slots: list[int]) -> bool:
    """True when known defect slots are not yet in the Lot-based SmmHold memo.

    Only wafer-based ``Please check #N`` memos are conciled. Other official
    SmmHold memos (handoff already present) are left alone.
    """
    if not desired_slots or not is_wafer_check_memo(actual_memo):
        return False
    actual = set(parse_smm_slots(actual_memo))
    return any(s not in actual for s in desired_slots)
