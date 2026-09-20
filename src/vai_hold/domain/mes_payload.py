"""Freeze the MES request body so retries send the same pack, not current YAML."""

from __future__ import annotations

import hashlib
import json

from vai_hold.domain.models import HoldCommand


def freeze_hold_command(cmd: HoldCommand) -> tuple[str, str]:
    data = {
        "lot_id": cmd.lot_id,
        "route_id": cmd.route_id,
        "ope_no": cmd.ope_no,
        "memo": cmd.memo,
        "hold_code": cmd.hold_code,
        "hold_user": cmd.hold_user,
        "tool_id": cmd.tool_id,
        "idempotency_key": cmd.idempotency_key,
        "new_memo": cmd.new_memo,
    }
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest


def thaw_hold_command(raw: str) -> HoldCommand:
    data = json.loads(raw)
    return HoldCommand(
        lot_id=data["lot_id"],
        route_id=data.get("route_id") or "",
        ope_no=data.get("ope_no") or "",
        memo=data.get("memo") or "",
        hold_code=data.get("hold_code") or "",
        hold_user=data.get("hold_user") or "",
        tool_id=data.get("tool_id"),
        idempotency_key=data.get("idempotency_key"),
        new_memo=data.get("new_memo"),
    )
