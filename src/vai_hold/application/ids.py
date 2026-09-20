from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone


def new_id() -> str:
    return str(uuid.uuid4())


def new_order_id(now: datetime | None = None, tool_id: str | None = None) -> str:
    """yyyymmdd-hhmmss + 3 random digits + -ToolId  e.g. 20260919-064800123-EQP01"""
    now = now or datetime.now(timezone.utc)
    tool = (tool_id or "NA").replace(" ", "")
    return f"{now.strftime('%Y%m%d-%H%M%S')}{random.randint(0, 999):03d}-{tool}"
