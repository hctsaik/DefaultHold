from __future__ import annotations

from vai_hold.domain.models import WaferAiView


def expected_complete(
    expected_ids: list[str],
    views: list[WaferAiView],
    *,
    rework_count: int,
) -> tuple[str, list[str]]:
    """
    Returns (status, missing_or_invalid).
    status: WAITING | COMPLETE_OK | COMPLETE_DEFECT | INVALID | EMPTY
    """
    if not expected_ids:
        return "EMPTY", []

    by_id: dict[str, WaferAiView] = {}
    for v in views:
        if v.rework_count is not None and v.rework_count != rework_count:
            continue
        prev = by_id.get(v.wafer_id)
        if prev is None:
            by_id[v.wafer_id] = v
            continue
        # de-dupe by result_version then prefer completed
        if (v.scan_completed_at and not prev.scan_completed_at) or (
            v.result_version or ""
        ) > (prev.result_version or ""):
            by_id[v.wafer_id] = v

    missing = [w for w in expected_ids if w not in by_id or by_id[w].scan_completed_at is None]
    if missing:
        return "WAITING", missing

    # 有 ScanCompletedTime、沒有 Alarm Type → 先當完成（不當 DEFECT）。INVALID 仍算無效。
    invalid = [w for w in expected_ids if (by_id[w].result or "").upper() == "INVALID"]
    if invalid:
        return "INVALID", invalid

    defects = [w for w in expected_ids if (by_id[w].result or "").upper() == "DEFECT"]
    if defects:
        return "COMPLETE_DEFECT", defects
    return "COMPLETE_OK", []
