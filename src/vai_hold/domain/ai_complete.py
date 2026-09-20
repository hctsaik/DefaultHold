from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vai_hold.domain.models import WaferAiView

SCAN_SETTLE = timedelta(minutes=2)


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


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def max_scan_completed_at(
    expected_ids: list[str],
    views: list[WaferAiView],
    *,
    rework_count: int,
) -> datetime | None:
    status, _ = expected_complete(expected_ids, views, rework_count=rework_count)
    if status not in {"COMPLETE_OK", "COMPLETE_DEFECT"}:
        return None
    by_id: dict[str, WaferAiView] = {}
    for v in views:
        if v.rework_count is not None and v.rework_count != rework_count:
            continue
        if v.wafer_id in expected_ids and v.scan_completed_at:
            prev = by_id.get(v.wafer_id)
            if prev is None or (v.scan_completed_at and prev.scan_completed_at and v.scan_completed_at >= prev.scan_completed_at):
                by_id[v.wafer_id] = v
    times = [_aware(by_id[w].scan_completed_at) for w in expected_ids if w in by_id and by_id[w].scan_completed_at]
    return max(times) if times else None


def scan_settle_ready(
    expected_ids: list[str],
    views: list[WaferAiView],
    *,
    rework_count: int,
    now: datetime,
) -> bool:
    mx = max_scan_completed_at(expected_ids, views, rework_count=rework_count)
    if mx is None:
        return False
    return _aware(now) >= mx + SCAN_SETTLE
