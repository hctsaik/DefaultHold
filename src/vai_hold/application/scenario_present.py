"""查案用語：MES／本系統發生了什麼，對回 file:function。不出現 Fake。"""

from __future__ import annotations

from typing import Any

RUN = {
    "set": {
        "title": "設 Default Hold",
        "loc": "pipelines/set_default_hold.py:run",
        "via": "usecases/request_hold.py:request_hold",
        "mes": "HoldPort.set_hold",
        "kind": "act",
    },
    "confirm": {
        "title": "查驗 Default Hold 是否還在",
        "loc": "pipelines/confirm_hold.py:run",
        "via": "usecases/verify_hold.py:verify_hold",
        "mes": "HoldPort.list_holds",
        "kind": "act",
    },
    "check": {
        "title": "查 AI 是否掃完",
        "loc": "pipelines/check_ai.py:run",
        "via": "domain/derive.py:derive_state",
        "mes": "AiPort.read_results / HoldPort",
        "kind": "act",
    },
    "release": {
        "title": "查驗 Default Hold 是否已解除",
        "loc": "pipelines/confirm_release.py:run",
        "via": "usecases/verify_release.py:verify_release",
        "mes": "HoldPort.list_holds",
        "kind": "act",
    },
    "defense": {
        "title": "對帳：超時、覆蓋、殘留、心跳",
        "loc": "pipelines/defense.py:run",
        "via": "application/services.py:snapshot",
        "mes": "HoldPort.list_holds（Watchdog 時間＝本機估計）",
        "kind": "act",
    },
    "close": {
        "title": "人工結案",
        "loc": "pipelines/control.py:run_manual_close",
        "via": "",
        "mes": "",
        "kind": "act",
    },
    "resume": {
        "title": "申請恢復新 Hold",
        "loc": "pipelines/control.py:run_resume",
        "via": "",
        "mes": "",
        "kind": "act",
    },
}

HOLD_RECEIPT = {
    "accepted": "MES 接受 Hold",
    "rejected_conflict": "MES 拒絕：Hold Code 衝突",
    "rejected_permission": "MES 拒絕：權限不足",
    "rejected_transient": "MES 暫時拒絕",
    "timeout": "MES 無回覆（Receipt UNKNOWN）",
}

RELEASE_RECEIPT = {
    "accepted": "MES 接受解除",
    "rejected_permission": "MES 拒絕解除：權限不足",
    "rejected_transient": "MES 暫時拒絕解除",
    "timeout": "MES 解除無回覆（Receipt UNKNOWN）",
}

def describe_step(step: dict[str, Any]) -> dict[str, str]:
    op = step.get("op")
    if op == "run":
        meta = dict(RUN.get(step.get("fn") or "", {
            "title": f"跑 {step.get('fn') or step.get('code')}",
            "loc": "",
            "via": "",
            "mes": "",
            "kind": "act",
        }))
        return meta
    if op == "add_lot":
        lot = step.get("lot_id") or ""
        ope = step.get("origin_ope_no") or step.get("current_ope_no") or "OP100"
        return {
            "title": f"Lot 進站 {lot} {ope}（Operation Start）",
            "loc": "pipelines/set_default_hold.py:run",
            "via": "SmmPort.list_start_events",
            "mes": "",
            "kind": "env",
        }
    if op == "append_event":
        extra = "；過期進站不重建" if step.get("stale_hours") else ""
        return {
            "title": f"又來一筆進站事件{extra}",
            "loc": "pipelines/set_default_hold.py:run",
            "via": "SmmPort.list_start_events",
            "mes": "",
            "kind": "env",
        }
    if op == "remove_event":
        return {
            "title": f"SMM 目前應防守名單移除 {step.get('lot_id') or step.get('event_id') or '指定事件'}",
            "loc": "SmmPort.expected_keys",
            "via": "pipelines/defense.py:run",
            "mes": "只改對帳輸入，不刪既有 Order",
            "kind": "env",
        }
    if op == "set_world":
        return _describe_world(step)
    if op == "clear_holds":
        return {
            "title": "MES 上的 Hold 被清掉",
            "loc": "HoldPort.list_holds",
            "via": "application/services.py:snapshot",
            "mes": "下一次 list_holds → NOT_FOUND",
            "kind": "env",
        }
    if op == "add_defect_hold":
        return {
            "title": "MES 上另有一筆 Hold（不是本系統 Default Hold）",
            "loc": "HoldPort.list_holds",
            "via": "application/services.py:snapshot",
            "mes": "",
            "kind": "env",
        }
    if op == "add_foreign_hold":
        return {
            "title": "MES 已有別人的 Hold（Memo 不是本系統）",
            "loc": "domain/ownership.py:match_our_holds",
            "via": "HoldPort.list_holds",
            "mes": step.get("memo") or "",
            "kind": "env",
        }
    if op == "add_standard_hold":
        return {
            "title": "MES 出現本系統 Memo 的 Hold",
            "loc": "HoldPort.list_holds",
            "via": "domain/ownership.py:match_our_holds",
            "mes": "",
            "kind": "env",
        }
    if op == "complete_ai":
        bits = ["AI 掃片結果到齊"]
        if step.get("skip"):
            bits = [f"AI 結果未齊（缺 {','.join(step['skip'])}）"]
        if step.get("missing_result"):
            bits = [f"AI 完成但無結果（{step['missing_result']}）"]
        if step.get("result") == "DEFECT":
            bits.append("有 Defect")
        return {
            "title": "；".join(bits),
            "loc": "application/services.py:snapshot",
            "via": "AiPort.read_results",
            "mes": "",
            "kind": "env",
        }
    if op == "scan_wafer":
        return {
            "title": f"一片掃完 {step.get('wafer_id')}＝{step.get('result', 'DEFECT')}",
            "loc": "AiPort.read_results",
            "via": "application/services.py:snapshot",
            "mes": "",
            "kind": "env",
        }
    if op == "ai_unavailable":
        return {
            "title": "AI 查詢 UNKNOWN（不是空、不是掃完）",
            "loc": "application/services.py:snapshot",
            "via": "AiPort.read_results",
            "mes": "QueryStatus=UNKNOWN 不准當空",
            "kind": "env",
        }
    if op == "advance":
        parts = [f"{k}={v}" for k, v in step.items() if k != "op"]
        return {
            "title": f"本機 Clock 往前（{', '.join(parts)}）",
            "loc": "application/ports/clock.py:ManualClock.advance",
            "via": "",
            "mes": "不是 MES 時間；Watchdog 用本機估計",
            "kind": "env",
        }
    if op == "disable_control":
        return {
            "title": "停用新 Hold",
            "loc": "domain/derive.py:derive_state",
            "via": "",
            "mes": "",
            "kind": "env",
        }
    if op == "repeat":
        return {
            "title": f"同一邏輯再跑 {step.get('times')} 次",
            "loc": "",
            "via": "",
            "mes": "",
            "kind": "act",
        }
    return {
        "title": op or "?",
        "loc": "",
        "via": "",
        "mes": "",
        "kind": "env",
    }


def _describe_world(step: dict[str, Any]) -> dict[str, str]:
    bits: list[str] = []
    loc = "HoldPort.set_hold"
    for _lot, resp in (step.get("set_response") or {}).items():
        bits.append(HOLD_RECEIPT.get(str(resp), str(resp)))
    if (step.get("set_effect") or {}) and any(v == "none" for v in (step.get("set_effect") or {}).values()):
        bits.append("送出後 MES 沒有落地 Hold")
        loc = "HoldPort.set_hold"
    for _lot, st in (step.get("list_status") or {}).items():
        if st == "unknown":
            bits.append("list_holds 回 UNKNOWN（不准當沒有 Hold）")
            loc = "HoldPort.list_holds"
    for _lot, resp in (step.get("release_response") or {}).items():
        bits.append(RELEASE_RECEIPT.get(str(resp), str(resp)))
        loc = "HoldPort.release_hold"
    if step.get("notifier_fail"):
        bits.append("通知通道失敗")
        loc = "NotifierPort.send"
    return {
        "title": "；".join(bits) or "MES 條件變更",
        "loc": loc,
        "via": "",
        "mes": "",
        "kind": "env",
    }


def flatten_script(script: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for step in script:
        if step.get("op") == "repeat":
            times = int(step.get("times") or 1)
            inner = step.get("steps") or []
            for k in range(1, times + 1):
                for inner_step in flatten_script(inner):
                    cloned = dict(inner_step)
                    cloned["_repeat"] = f"{k}/{times}"
                    out.append(cloned)
        else:
            out.append(step)
    return out
