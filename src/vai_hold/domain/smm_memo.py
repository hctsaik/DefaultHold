from __future__ import annotations

import re

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
