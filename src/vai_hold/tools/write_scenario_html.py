"""Present catalog scenarios from SQLite runs as HTML. Do not re-execute."""

from __future__ import annotations

import html
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DB = ROOT / "Design" / "generated" / "scenario_catalog.sqlite"
OUT_DIR = ROOT / "Design" / "generated" / "evidence"
ORDERS_ROOT = ROOT / "Design" / "generated" / "scenario_orders"

# 尚未定案、總覽必須看得到。詳見 Design/SCENARIO_DISCUSSION.md
OPEN_ISSUES: list[tuple[str, str]] = []

GROUP_INTRO = {
    "stage": "狀態機單格：Given → 一支 Cron → Then。這才是驗收單位。",
    "v1": "V1 編號對照（長串走完，不是驗收單位）。",
    "happy": "串接走完（不是單格）。",
    "hold": "Default Hold 的設、查驗、衝突、消失、權限失敗。",
    "ai": "Wafer 掃片未齊、結果無效、AI 查詢 UNKNOWN。",
    "smm": "進站時現場已有 SMM Hold 則不設 Default Hold。本 Agent 不解、不改 SMM Hold。",
    "release": "申請解除 Default Hold：成功、被拒、timeout。",
    "target": "選防守站：目前站／未來量測站。",
    "control": "停用新 Hold、Resume、人工結案。",
    "defense": "Watchdog、覆蓋率、Orphan、結案後殘留。",
    "order": "Rework 隔離、Roster 變更、過期進站事件。",
    "retry": "同一 logical action 含第 1 次最多送 3 次。",
}

CSS = """
    body { font-family: "Segoe UI","Noto Sans TC",sans-serif; margin:0; background:#f4f1ea; color:#1c1917; }
    header, main { max-width: 1100px; margin: 0 auto; padding: 24px; }
    h1 { font-size: 1.45rem; margin-bottom: 8px; }
    h2 { font-size: 1.08rem; color: #0f766e; }
    .muted { color:#57534e; }
    .card { background:#fff; border-radius:12px; padding:18px 20px; margin:16px 0; border:1px solid #e7e5e4; }
    .card.focus { border-color:#b45309; box-shadow: 0 0 0 3px #fed7aa; }
    table { width:100%; border-collapse:collapse; font-size:0.9rem; }
    td, th { border-bottom:1px solid #e7e5e4; padding:8px 6px; text-align:left; vertical-align:top; }
    pre { background:#1c1917; color:#fafaf9; padding:12px; border-radius:10px; overflow:auto; font-size:0.78rem; }
    .mermaid { background:#fafaf9; border-radius:8px; padding:8px; overflow:auto; }
    .badge { display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.82rem; }
    .badge.pass { background:#d1fae5; color:#065f46; }
    .badge.fail { background:#fee2e2; color:#991b1b; }
    .badge.none { background:#e7e5e4; color:#44403c; }
    .badge.skip { background:#fef3c7; color:#92400e; }
    a { color:#0f766e; }
    tr.row:hover { background:#fafaf9; }
    tr.env td:first-child { color:#78716c; }
    tr.act td:first-child { color:#0f766e; font-weight:600; }
    .err { color:#9a3412; font-weight:600; }
    table.kv th { width:28%; color:#57534e; font-weight:500; }
    .story { font-size:1.02rem; line-height:1.55; }
    .times { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
    .times .box { background:#fafaf9; border-radius:8px; padding:10px 12px; }
    .spec { border-color:#0f766e; }
    .spec h2 { margin-top:0; }
    .spec ul { margin:6px 0 12px 1.2em; }
    .spec .must { color:#065f46; }
    .spec .not { color:#9a3412; }
    .spec .passwhen { background:#ecfdf5; padding:8px 10px; border-radius:8px; }
    .spec .open { background:#fff7ed; padding:8px 10px; border-radius:8px; color:#9a3412; }
    tr.when { background:#ccfbf1; }
    tr.given { color:#78716c; }
    .verdict { padding:16px 18px; border-radius:12px; margin:16px 0; font-size:1.15rem; font-weight:700; }
    .verdict.pass { background:#d1fae5; color:#065f46; border:1px solid #6ee7b7; }
    .verdict.fail { background:#fee2e2; color:#991b1b; border:1px solid #fca5a5; }
    .verdict .sub { font-size:0.92rem; font-weight:500; margin-top:8px; color:inherit; opacity:0.9; }
    .facts-grid { display:grid; gap:12px; }
    .facts-grid h3 { margin:0 0 6px; font-size:0.95rem; color:#0f766e; }
    .milestones { table-layout:fixed; }
    .milestones th, .milestones td { text-align:center; font-size:0.82rem; }
    .milestones td.hit { background:#ccfbf1; font-weight:600; }
    .milestones td.here { background:#fde68a; font-weight:700; }
    .milestones td.err { background:#ffedd5; color:#9a3412; font-weight:700; }
    .milestones td.skip { color:#a8a29e; }
    .milestones td.then { background:#d1fae5; font-weight:700; color:#065f46; }
    tr.drive td { background:#fef3c7; }
    .yes { color:#065f46; font-weight:600; }
    .no { color:#9a3412; }
    .bridge-out { background:#ecfdf5; padding:12px 14px; border-radius:8px; margin-top:10px; }
"""


def _safe_mm(text: str) -> str:
    return (
        (text or "")
        .replace('"', "'")
        .replace("[", "(")
        .replace("]", ")")
        .replace("(", "（")
        .replace(")", "）")
    )


def _failure_tables(actual: dict) -> str:
    rows = actual.get("incident_rows") or []
    fails = actual.get("failed_attempts") or []
    if not rows and not fails:
        return ""
    inc_trs = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(r.get('incident_id') or ''))}</code></td>"
        f"<td><code>{html.escape(str(r.get('incident_type') or ''))}</code></td>"
        f"<td>{html.escape(str(r.get('status') or ''))}</td>"
        f"<td>{html.escape(str(r.get('lot_id') or ''))}</td>"
        f"<td><code>{html.escape(str(r.get('order_id') or ''))}</code></td>"
        f"<td>{html.escape(str(r.get('reason') or ''))}</td>"
        f"<td>{html.escape(str(r.get('first_seen_at') or ''))}</td>"
        f"<td>{html.escape(str(r.get('occurrence_count') or 1))}</td>"
        "</tr>"
        for r in rows
    )
    att_trs = "".join(
        "<tr>"
        f"<td><code>{html.escape(str(a.get('hold_code') or ''))}</code></td>"
        f"<td>{html.escape(str(a.get('attempt_no') or ''))}</td>"
        f"<td>{html.escape(str(a.get('receipt') or ''))}</td>"
        f"<td>{html.escape(str(a.get('error') or ''))}</td>"
        f"<td>{html.escape(str(a.get('retry_class') or ''))}</td>"
        f"<td>{html.escape(_fmt_time(str(a.get('finished_at') or '')) or str(a.get('finished_at') or ''))}</td>"
        "</tr>"
        for a in fails
    )
    why_bits = []
    for a in fails:
        code = a.get("hold_code") or "（無 Code）"
        err = a.get("error") or a.get("receipt") or "失敗"
        why_bits.append(f"{code} 被 MES {err}")
    if rows:
        for r in rows:
            why_bits.append(
                f"incident {r.get('incident_type')}：{r.get('reason') or r.get('status')}"
            )
    why = "；".join(why_bits) if why_bits else "見下表。"
    inc_tbl = (
        "<h2>incident 表（之後用 DB 查這筆失敗）</h2>"
        "<p class='muted'><code>SELECT * FROM incident WHERE lot_id='LOT1' AND status='OPEN'</code></p>"
        "<table><thead><tr><th>incident_id</th><th>type</th><th>status</th><th>lot_id</th>"
        "<th>order_id</th><th>reason</th><th>first_seen_at</th><th>count</th></tr></thead>"
        f"<tbody>{inc_trs}</tbody></table>"
        if rows
        else "<p class='muted'>沒有寫入 incident 列。</p>"
    )
    att_tbl = (
        "<h2>action_history 每一筆失敗</h2>"
        "<table><thead><tr><th>Hold Code</th><th>attempt</th><th>receipt</th><th>error</th>"
        "<th>retry_class</th><th>時間</th></tr></thead>"
        f"<tbody>{att_trs}</tbody></table>"
        if fails
        else ""
    )
    return (
        f"<div class='card spec'><h2>失敗原因</h2>"
        f"<p class='story'>{html.escape(why)}</p>"
        f"{inc_tbl}{att_tbl}</div>"
    )


def _cell(value) -> str:
    if value is None:
        return "<span class='muted'>—</span>"
    if isinstance(value, (dict, list)):
        return f"<pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2, default=str))}</pre>"
    return f"<code>{html.escape(str(value))}</code>"


RULE_WHY = {
    "A1-01": "還沒有訂單，先建單",
    "A1-02": "訂單有了，先選要設 Default Hold 的站",
    "A1-03": "MES 上還沒有本系統 Default Hold，向 MES 設一筆",
    "A1-04": "這個 Hold Code 設不上，改用清單下一個",
    "A1-08": "已停用新 Hold，不再設",
    "A2-01": "Default Hold 已送出，向 MES 確認它是否真的在",
    "A2-02": "MES 上已看到本系統 Default Hold，當成已設上，等掃片",
    "A2-03": "設 Default Hold 失敗",
    "A2-04": "曾確認的 Default Hold 不見了，當線上代解並結案",
    "A2-05": "Default Hold 還在，片還沒掃完，不解",
    "A2-06": "掃片結果無效，不解 Default Hold",
    "A2-07": "（已併入 A2-21）掃完且滿 settle，申請解除 Default Hold",
    "A2-08": "（已併入 A2-21）掃完且滿 settle，申請解除 Default Hold",
    "A2-09": "已全部掃完，還沒滿 config 的 settle 分鐘，暫不解",
    "A2-21": "已全部掃完且滿 settle 分鐘，申請解除 Default Hold",
    "A2-20": "現場已有 SMM Hold，不設 Default Hold",
    "A2-10": "已申請解除，向 MES 確認自己的 Default Hold 還在不在",
    "A2-11": "自己的 Default Hold 已沒有，結案",
    "A2-12": "解除失敗，Default Hold 留著",
    "A2-16": "SMM Hold 要補片號，請 MES 改 Memo",
}

RULE_TO_ACTION = {
    "A1-03": "SET_HOLD",
    "A1-04": "SET_HOLD",
    "A2-01": "VERIFY_HOLD",
    "A2-02": "VERIFY_HOLD",
    "A2-03": "OPEN_INCIDENT",
    "A2-04": "NONE",
    "A2-05": "NONE",
    "A2-06": "NONE",
    "A2-07": "SET_RELEASE",
    "A2-08": "SET_RELEASE",
    "A2-09": "NONE",
    "A2-21": "SET_RELEASE",
    "A2-20": "NONE",
    "A2-10": "VERIFY_RELEASE",
    "A2-11": "NONE",
    "A2-12": "OPEN_INCIDENT",
    "A2-16": "TRANSFER_HOLD",
}

ACTION_WHY = {
    "SET_HOLD": "向 MES 設 Default Hold",
    "SET_RELEASE": "向 MES 申請解除 Default Hold",
    "VERIFY_HOLD": "向 MES 確認 Default Hold 是否存在",
    "VERIFY_RELEASE": "向 MES 確認 Default Hold 是否已解除",
    "TRANSFER_HOLD": "請 MES 更新 SMM Hold 的說明",
    "OPEN_INCIDENT": "留下告警／錯誤紀錄",
    "NONE": "這一輪不向 MES 送新動作",
}


def _facts_decision_bridge(actual: dict) -> str:
    """跟 Order Summary 同一套：一列欄位看完。左＝判斷用到的現場，右＝因此做了什麼。"""
    facts = actual.get("facts") or {}
    ch = _observed_channels(actual)
    dh_holds = (facts.get("DefaultHold") or {}).get("Holds") if ch["default"] else None
    if not isinstance(dh_holds, list):
        dh_holds = []
    smm = _smm_facts(facts.get("SmmHold")) or {}
    smm_holds = smm.get("Holds") if ch["smm"] and isinstance(smm.get("Holds"), list) else []
    ai = facts.get("AiScan") or {}
    scanned, expected = ai.get("ScannedCount"), ai.get("ExpectedCount")
    inflight = (facts.get("OrderDb") or {}).get("ActionInFlight")
    err = (facts.get("OrderDb") or {}).get("DataError") or actual.get("data_error")
    rule = (actual.get("judgment") or {}).get("rule_id") or actual.get("last_rule_id") or ""
    action = (actual.get("judgment") or {}).get("action") or ""
    why = RULE_WHY.get(str(rule), "")
    act_key = str(action) or RULE_TO_ACTION.get(str(rule), "")
    if str(rule) in {"A1-04", "A2-04", "A2-05", "A2-09", "A2-11", "A2-20", "A2-21"}:
        act_biz = RULE_WHY.get(str(rule), "")
    else:
        act_biz = ACTION_WHY.get(act_key, "") or why or "見各欄"

    def cell(text: str, *, skip=False, drive=False, then=False) -> str:
        cls = []
        if skip:
            cls.append("skip")
        if drive:
            cls.append("here")
        if then:
            cls.append("then")
        return f"<td class='{' '.join(cls)}'>{html.escape(text)}</td>"

    if ch["default"] and dh_holds:
        code = dh_holds[0].get("HoldCode") or ""
        hold_txt, hold_skip = ("有" + (f"（{code}）" if code else "")), False
    elif ch["default"]:
        hold_txt, hold_skip = "沒有", False
    elif str(rule) in {"A1-03", "A1-04"}:
        # 這一格的工作是「去設」，輸入是「當時還沒有」，不是「設完還沒去查」。
        hold_txt, hold_skip = "下決定時：沒有", False
    else:
        hold_txt, hold_skip = "—", True

    if not ch["smm"]:
        smm_txt, smm_skip = "—", True
    elif smm_holds:
        smm_txt, smm_skip = "有", False
    else:
        smm_txt, smm_skip = "沒有", False

    if not ch["ai"]:
        ai_txt, ai_skip = "—", True
    else:
        result_hint = ""
        views_ok = expected not in (None, 0) and scanned == expected
        if views_ok:
            ai_txt = f"掃完 {scanned}/{expected}"
        else:
            ai_txt = f"{scanned}/{expected} 未齊"
        ai_skip = False

    if inflight:
        inflight_txt = {
            "SET_HOLD": "剛設 Default Hold，還沒查完",
            "SET_RELEASE": "剛解除 Default Hold，還沒查完",
            "TRANSFER_HOLD": "剛改 SMM Hold Memo，還沒查完",
        }.get(str(inflight.get("ActionType") or ""), "有，還沒查完")
    else:
        inflight_txt = "沒有"

    if err and str(err) != "NO_SMM_HOLD_AFTER_SCAN":
        err_txt = str(err)
    else:
        err_txt = "沒有"
        err = None

    drive_hold = str(rule) in {"A1-03", "A2-02", "A2-04", "A2-11"}
    drive_smm = str(rule) in {"A2-20"}
    drive_ai = str(rule) in {"A2-05", "A2-06", "A2-09", "A2-21"}
    drive_inf = str(rule) in {"A2-01", "A2-10"}
    drive_err = bool(err)

    cols: list[tuple[str, str, bool, bool]] = []
    if ch["default"] or drive_hold:
        cols.append(("本系統 Default Hold", hold_txt if not hold_skip else "—", False, drive_hold))
    if ch["smm"]:
        cols.append(("SMM Hold", smm_txt, False, drive_smm))
    if ch["ai"]:
        cols.append(("掃片", ai_txt, False, drive_ai))
    if drive_inf:
        cols.append(("剛送出還沒查完", inflight_txt, False, True))
    if err or drive_err:
        cols.append(("訂單錯誤", err_txt, False, drive_err))
    cols.append(("因此做了", act_biz, True, False))

    th = "".join(f"<th>{html.escape(n)}</th>" for n, _t, _then, _d in cols)
    tds = "".join(cell(t, then=then, drive=drive) for _n, t, then, drive in cols)
    return f"""
  <div class="card focus">
    <h2>為什麼做這一步</h2>
    <p class="muted">這是<strong>原因</strong>，不是時間軸。黃底＝做決定時看到的條件。綠底＝因此去做的事。送出的內容在「待查驗」，不在這裡。</p>
    <table class="milestones"><thead><tr>{th}</tr></thead>
    <tbody><tr>{tds}</tr></tbody></table>
  </div>
"""


def _script_fns(actual: dict) -> set[str]:
    return {str(x.get("fn") or "") for x in (actual.get("timeline") or []) if x.get("fn")}


def _observed_channels(actual: dict) -> dict[str, bool]:
    """哪一種現場資料這格業務上有查過。snapshot 順便撈到的不算 Facts。"""
    fns = _script_fns(actual)
    ws = actual.get("work_state") or ""
    prot = actual.get("protection_state") or ""
    lot = bool((actual.get("facts") or {}).get("Lot")) or bool(ws)
    default = "confirm" in fns or "release" in fns
    if "check" in fns and prot not in {"SET_PENDING", "NONE", ""}:
        default = True
    if ws in {"NEED_HOLD", "NEED_TARGET", "NEED_BACKUP_HOLD", "HOLD_VERIFY_PENDING"}:
        default = False
    if prot == "SET_PENDING":
        default = False
    rule = str((actual.get("judgment") or {}).get("rule_id") or actual.get("last_rule_id") or "")
    return {
        "lot": lot,
        "default": default,
        # 解 Hold 不看 SMMH。只有 D04（進站已有 → 不設 Default Hold）才當 Facts。
        "smm": rule == "A2-20",
        "ai": "check" in fns,
    }


def _json_block(value) -> str:
    if value is None:
        return "<span class='muted'>—</span>"
    return f"<pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2, default=str))}</pre>"


def _public_actions(actions: dict | None) -> dict:
    """查案頁不列 transfer：本 Agent 不再改現場其他 Hold 的 Memo。"""
    out = dict(actions or {})
    out.pop("transfer", None)
    return out


def _smm_facts(smm: dict | None) -> dict | None:
    if not smm:
        return smm
    ope = smm.get("OpeNo") or smm.get("StepOpeNo")
    return {
        "StepMode": smm.get("StepMode"),
        "OpeNo": ope,
        "QueryStatus": smm.get("QueryStatus"),
        "Holds": smm.get("Holds"),
    }


def _hold_place(actual: dict) -> str:
    d = actual.get("action_detail") or {}
    if not d.get("HoldCode") and not d.get("OpeNo"):
        holds = ((actual.get("facts") or {}).get("DefaultHold") or {}).get("Holds") or []
        if holds:
            d = holds[-1]
    code = d.get("HoldCode") or ""
    ope = d.get("OpeNo") or ""
    name = d.get("OpeName") or ""
    bits = [x for x in (code, f"{ope} {name}".strip()) if x]
    return "、".join(bits)


def _this_cell_did(actual: dict) -> str:
    """這一格做的事，不是劇本前面累積的 set_hold 次數。"""
    rule = str(actual.get("last_rule_id") or "")
    action = str((actual.get("judgment") or {}).get("action") or RULE_TO_ACTION.get(rule) or "")
    if rule in {"A1-04", "A2-04", "A2-05", "A2-09", "A2-11", "A2-20", "A2-21"}:
        return RULE_WHY[rule]
    biz = ACTION_WHY.get(action) or RULE_WHY.get(rule) or "見本頁「為什麼做這一步」"
    place = _hold_place(actual)
    if action == "SET_HOLD" and place:
        return f"{biz}（{place}）"
    return biz


def _business_result(actual: dict) -> tuple[str, str]:
    """人話：這一格對現場做了什麼、現在停在哪。"""
    ws = actual.get("work_state") or ""
    did = _this_cell_did(actual)
    now = {
        "NEED_HOLD": "還沒向 MES 設 Default Hold。",
        "HOLD_VERIFY_PENDING": "Default Hold 已送出，還沒確認它真的在 MES 上。還沒掃片、還沒解除。",
        "WAIT_AI": "Default Hold 已確認存在。正在等掃完，或掃完未滿 2 分鐘。",
        "PROTECTION_CONFIRMED": "Default Hold 已確認存在。",
        "RELEASE_SENT": "已向 MES 申請解除 Default Hold，還沒確認解除成功，這張單尚未結案。",
        "RELEASE_VERIFY_PENDING": "解除已送出，MES 上可能還沒跟上；不重送、不結案。",
        "CLOSED": "Default Hold 已確認解除，這張單結案。",
        "MANUAL_CLOSED": "MES 上 Default Hold 已不在（線上代解），這張單結案。",
        "HOLD_FAILED": "設 Default Hold 失敗，這張單沒有防守。",
        "RELEASE_FAILED": "解除 Default Hold 失敗，Hold 還在。",
        "NEED_BACKUP_HOLD": "這個 Hold Code 設不上，會改用下一個 Code。",
    }.get(str(ws), f"目前停在 {ws}。")
    return (did if did.endswith("。") else did + "。"), now


def _clock(value) -> str:
    return _fmt_time(str(value) if value else "") or (str(value) if value else "—")


def _order_summary_section(scenario_id: str, actual: dict) -> str:
    """狀態機里程碑：一列欄位、各記時間。現況停在哪一格用黃底。"""
    path = ORDERS_ROOT / scenario_id / "order.db"
    marks: dict[str, str] = {}
    here = actual.get("work_state") or ""
    data_error = actual.get("data_error")
    if data_error == "NO_SMM_HOLD_AFTER_SCAN":
        data_error = None
    close_reason = actual.get("close_reason")
    if path.is_file():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            o = conn.execute("SELECT * FROM hold_order LIMIT 1").fetchone()
            if o:
                keys = o.keys()
                if "operation_start_at" in keys:
                    marks["進站"] = o["operation_start_at"]
                data_error = data_error or (o["data_error"] if "data_error" in keys else None)
                if data_error == "NO_SMM_HOLD_AFTER_SCAN":
                    data_error = None
                close_reason = close_reason or (o["close_reason"] if "close_reason" in keys else None)
                here = here or (o["work_state"] if "work_state" in keys else "")
            row = conn.execute(
                """SELECT json_extract(j.value, '$.created_at') FROM hold_order o, json_each(o.actions_json) j
                   WHERE json_extract(j.value, '$.action_type')='SET_HOLD'
                   ORDER BY 1 LIMIT 1"""
            ).fetchone()
            if row:
                marks["送出 Default Hold"] = row[0]
            row = conn.execute(
                "SELECT dh_first_confirmed_at FROM hold_order WHERE dh_first_confirmed_at IS NOT NULL ORDER BY dh_first_confirmed_at LIMIT 1"
            ).fetchone()
            if row:
                marks["確認 Default Hold 存在"] = row[0]
            row = conn.execute(
                """SELECT json_extract(j.value, '$.created_at') FROM hold_order o, json_each(o.actions_json) j
                   WHERE json_extract(j.value, '$.action_type')='SET_RELEASE'
                   ORDER BY 1 LIMIT 1"""
            ).fetchone()
            if row:
                marks["解除 Default Hold"] = row[0]
            row = conn.execute(
                "SELECT dh_released_at FROM hold_order WHERE dh_released_at IS NOT NULL ORDER BY dh_released_at LIMIT 1"
            ).fetchone()
            if row:
                marks["確認解除 Default Hold"] = row[0]
            if o and o["lifecycle"] in {"CLOSED", "MANUAL_CLOSED"}:
                marks["結案"] = o["updated_at"] if "updated_at" in o.keys() else o["last_evaluated_at"]
        except sqlite3.Error:
            pass
        conn.close()

    cols = [
        "進站",
        "送出 Default Hold",
        "確認 Default Hold 存在",
        "解除 Default Hold",
        "確認解除 Default Hold",
        "結案",
    ]
    here_col = {
        "NEED_HOLD": "進站",
        "HOLD_VERIFY_PENDING": "送出 Default Hold",
        "WAIT_AI": "確認 Default Hold 存在",
        "PROTECTION_CONFIRMED": "確認 Default Hold 存在",
        "RELEASE_SENT": "解除 Default Hold",
        "RELEASE_VERIFY_PENDING": "解除 Default Hold",
        "RELEASE_FAILED": "解除 Default Hold",
        "CLOSED": "結案",
        "MANUAL_CLOSED": "結案",
        "HOLD_FAILED": "送出 Default Hold",
    }.get(here, "")
    th = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    tds = []
    for c in cols:
        raw = marks.get(c)
        text = _clock(raw) if raw else "—"
        cls = []
        if raw:
            cls.append("hit")
        if c == here_col:
            cls.append("here")
        tds.append(f"<td class='{' '.join(cls)}'>{html.escape(text)}</td>")
    err = (
        f"<p class='err'>data_error：{html.escape(str(data_error))}</p>"
        if data_error
        else ""
    )
    close = (
        f"<p class='muted'>結案原因 <code>{html.escape(str(close_reason))}</code></p>"
        if close_reason
        else ""
    )
    return f"""
  <div class="card">
    <h2>這張單走到哪裡</h2>
    <p class="muted">時間軸，不是「Hold 已經在現場」。有時間＝這一步做過；—＝還沒做。「送出」不是「已確認存在」。黃底＝這題停在這裡。</p>
    {err}{close}
    <table class="milestones"><thead><tr>{th}</tr></thead>
    <tbody><tr>{''.join(tds)}</tr></tbody></table>
  </div>
"""


def _story_title(it: dict) -> str:
    title = it.get("title") or ""
    kind = it.get("kind") or "env"
    if kind == "env":
        return "現場已經：" + title
    if kind == "given":
        return "上一格已經：" + title
    return title


def _fmt_time(value: str | None) -> str:
    if not value:
        return ""
    from vai_hold.domain.timeutil import parse_iso

    dt = parse_iso(value)
    if dt is None:
        return value
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _delta(start: str | None, rec: str | None) -> str:
    from vai_hold.domain.timeutil import parse_iso

    a, b = parse_iso(start), parse_iso(rec)
    if not a or not b:
        return ""
    sec = int((b - a).total_seconds())
    if sec == 0:
        return "同時刻 · 順序看步驟編號"
    sign = "+" if sec >= 0 else "-"
    sec = abs(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"Δ {sign}{h}時{m}分{s}秒（本機 Clock，非 MES Created）"
    return f"Δ {sign}{m}分{s}秒（本機 Clock，非 MES Created）"


def _timeline_items(script: list[dict], actual: dict) -> list[dict]:
    from vai_hold.application.scenario_present import describe_step, flatten_script

    stored = actual.get("timeline") or []
    items = []
    for i, step in enumerate(flatten_script(script)):
        info = dict(describe_step(step))
        if step.get("_repeat"):
            info["title"] = f"{info['title']}（第 {step['_repeat']} 次）"
        prev = stored[i] if i < len(stored) else {}
        if prev.get("at"):
            info["at"] = prev["at"]
        if prev.get("when") is not None:
            info["when"] = prev["when"]
        if prev.get("kind") == "given":
            info["kind"] = "given"
        if prev.get("fn"):
            info["fn"] = prev["fn"]
        if prev.get("work_state"):
            info["work_state"] = prev["work_state"]
        items.append(info)
    return items or stored


def _mm_label(i: int, item: dict) -> str:
    title = html.escape(_safe_mm(f"{i}. {item.get('title') or ''}"))
    meta = []
    if item.get("at"):
        meta.append(_fmt_time(str(item["at"])) or str(item["at"]))
    if item.get("loc"):
        meta.append(item["loc"])
    if item.get("via"):
        meta.append(item["via"])
    if item.get("mes"):
        meta.append(item["mes"])
    meta_html = "<br/>".join(html.escape(_safe_mm(x)) for x in meta)
    return (
        f"<span style='color:#0f766e;font-weight:700'>{title}</span>"
        f"<br/><span style='color:#57534e;font-size:11px'>{meta_html}</span>"
    )


# 狀態機節點：英文 id 底下的中文目的（也當 tooltip）
STATE_PURPOSE = {
    "NEED_HOLD": "起點，沒有 Cron／沒有編號。要做事走箭頭 C01（送 Hold）",
    "NEED_TARGET": "訂單有了，還沒選防守站",
    "NEED_BACKUP_HOLD": "這個 Code 沒設上，改試清單下一個",
    "HOLD_VERIFY_PENDING": "已送出、這格不查它在不在；下一格才查 MES",
    "PROTECTION_CONFIRMED": "已確認 MES 上有本系統 Default Hold",
    "WAIT_AI": "已設 Default Hold，等掃片或掃完未滿 2 分鐘",
    "AI_RESULT_INVALID": "結果明確 INVALID；Default Hold 不解",
    "READY_RELEASE_OK": "可以申請解除 Default Hold",
    "READY_RELEASE_HANDOFF": "已掃完且滿 settle，可解 Default Hold",
    "RELEASE_SENT": "已申請解除 Default Hold；MES／DB 可能還沒跟上",
    "RELEASE_VERIFY_PENDING": "正在查自己的 Hold 是否已沒有；還看得到先當 Delay，不重送、不失敗",
    "RELEASE_FAILED": "解除失敗，Hold 還在",
    "HOLD_FAILED": "設 Hold 失敗，沒有防守",
    "HOLD_MISSING": "曾確認的 Hold 不見了（舊規則）",
    "CLOSED": "本系統 Hold 已解除，訂單結束",
    "MANUAL_CLOSED": "Default Hold 已不見，訂單記 Manual 結案",
    "MANUAL_CLOSED": "有人核過的人工結案",
    "OBSERVATION_UNKNOWN": "Hold 查詢不明，不准當成沒有",
    "MANUAL_REVIEW": "名單／資料變了，停自動",
    "STATE_CONFLICT": "已結案卻又出現本系統 Hold",
    "BLOCKED_BY_CONTROL": "停用新 Hold，這張單不能再設",
}


def _state_notes(ids: list[str]) -> str:
    """第一行英文狀態名，第二行中文目的。"""
    lines = []
    seen = set()
    for sid in ids:
        if sid in seen or sid not in STATE_PURPOSE:
            continue
        seen.add(sid)
        purpose = STATE_PURPOSE[sid].replace('"', "'")
        lines.append(f'  state "{sid}<br/>{purpose}" as {sid}')
    return "\n".join(lines)


def _state_machine_mermaid(actual: dict) -> str:
    """只把有跑 function code 的步驟畫成狀態機。"""
    items = [x for x in (actual.get("timeline") or []) if x.get("work_state")]
    if not items:
        return ""
    fn_name = {
        "set": "SET Hold",
        "confirm": "CONFIRM 存在",
        "check": "CHECK AI／申請解除",
        "release": "CONFIRM 已解除",
        "defense": "DEFENSE",
        "close": "人工結案",
        "resume": "Resume",
    }
    lines = [
        "stateDiagram-v2",
        "  [*] --> NEED_HOLD",
    ]
    prev = "NEED_HOLD"
    used = ["NEED_HOLD"]
    for i, item in enumerate(items, 1):
        st = item.get("work_state") or "UNKNOWN"
        nid = st if st.isidentifier() else f"S{i}"
        if nid not in used:
            used.append(nid)
        label = fn_name.get(item.get("fn") or "", item.get("title") or f"步驟{i}")
        lines.append(f"  {prev} --> {nid}: {i}. {_safe_mm(label)}")
        prev = nid
    if actual.get("lifecycle") == "CLOSED":
        lines.append(f"  {prev} --> [*]")
    notes = _state_notes(used)
    if notes:
        lines.append(notes)
    return "\n".join(lines) + "\n"


def _script_mermaid(script: list[dict], actual: dict) -> str:
    items = _timeline_items(script, actual)
    lines = [
        "flowchart TB",
        "  classDef env fill:#e7e5e4,stroke:#78716c,color:#44403c",
        "  classDef act fill:#ccfbf1,stroke:#0f766e,color:#134e4a",
        "  classDef endn fill:#fde68a,stroke:#b45309",
    ]
    prev = None
    env_ids: list[str] = []
    act_ids: list[str] = []
    for i, item in enumerate(items, 1):
        nid = f"n{i}"
        label = _mm_label(i, item)
        kind = item.get("kind") or "env"
        if kind == "act":
            lines.append(f'  {nid}["{label}"]')
            act_ids.append(nid)
        else:
            lines.append(f'  {nid}(["{label}"])')
            env_ids.append(nid)
        if prev:
            lines.append(f"  {prev} --> {nid}")
        prev = nid
    end = "e0"
    ws = actual.get("work_state") or "?"
    rule = actual.get("last_rule_id") or "?"
    lines.append(f'  {end}["結果 {ws} / {rule}"]')
    if prev:
        lines.append(f"  {prev} --> {end}")
    if env_ids:
        lines.append("  class " + ",".join(env_ids) + " env")
    if act_ids:
        lines.append("  class " + ",".join(act_ids) + " act")
    lines.append("  class e0 endn")
    return "\n".join(lines) + "\n"


def render_case_html(
    case, ran_at: str, passed: bool, actual: dict, *, index_href: str, diffs: list | None = None
) -> str:
    facts = actual.get("facts") or {}
    dh = facts.get("DefaultHold") or {}
    lot = facts.get("Lot") or {}
    items = _timeline_items(case.script, actual)
    script_rows = "".join(
        f"<tr class='{html.escape(it.get('kind') or 'env')}{' when' if it.get('when') else ''}'>"
        f"<td>{i}</td><td><code>{html.escape(_fmt_time(str(it.get('at') or '')) or str(it.get('at') or ''))}</code></td>"
        f"<td>{html.escape(it.get('title') or '')}</td>"
        f"<td><code>{html.escape(it.get('loc') or '')}</code>"
        f"{('<br/><code>' + html.escape(it['via']) + '</code>') if it.get('via') else ''}</td>"
        f"<td>{html.escape(it.get('mes') or '')}</td></tr>"
        for i, it in enumerate(items, 1)
    )
    story_rows = "".join(
        f"<tr class='{html.escape(it.get('kind') or 'env')}{' when' if it.get('when') else ''}'>"
        f"<td>{i}</td><td><code>{html.escape(_fmt_time(str(it.get('at') or '')) or str(it.get('at') or ''))}</code></td>"
        f"<td>{html.escape(_story_title(it))}</td></tr>"
        for i, it in enumerate(items, 1)
    )
    expect_rows = "".join(
        f"<tr><td><code>{html.escape(k)}</code></td><td>{_cell(_public_actions(v) if k == 'actions' else v)}</td>"
        f"<td>{_cell(_public_actions(actual.get(k)) if k == 'actions' else (actual.get('facts') if k == 'facts' else actual.get(k)))}</td></tr>"
        for k, v in case.expect.items()
        if k not in {"lot_id", "ope", "rw"}
    )
    fact_rows = "".join(
        f"<tr><td><code>{html.escape(str(k))}</code></td><td>{_cell(v)}</td></tr>"
        for k, v in facts.items()
    )
    seq = _script_mermaid(case.script, actual)
    sm = _state_machine_mermaid(actual)
    sm_card = ""
    if sm:
        sm_card = f"""<div class="card spec">
    <h2>狀態機</h2>
    <p class="muted">每一格＝一支 Cron。狀態寫在 Order DB，下一分鐘再推下一格。</p>
    <pre class="mermaid">
{sm}
    </pre>
  </div>"""
    intro = GROUP_INTRO.get(case.group_name, "")
    spec = case.spec or {}
    spec_card = ""
    if spec.get("situation") or spec.get("do"):
        open_q = spec.get("open") or ""
        open_html = (
            f"<p class='open'><strong>未決，先問再改測試：</strong> {html.escape(open_q)}</p>"
            if open_q
            else ""
        )
        spec_card = f"""<div class="card spec">
    <h2>這題要做什麼</h2>
    <table>
      <tr><th>現場已經</th><td>{html.escape(spec.get("given") or "")}</td></tr>
      <tr><th>實際系統會做</th><td><strong>{html.escape(spec.get("do") or "")}</strong></td></tr>
      <tr><th>做完現場應看到</th><td>{html.escape(spec.get("then") or "")}</td></tr>
      <tr><th>禁止</th><td>{html.escape(spec.get("dont") or spec.get("forbidden") or "")}</td></tr>
    </table>
    {open_html}
    {"" if not (spec.get("situation") or spec.get("expected")) else (
        "<p class='muted'>規格原文：情境「" + html.escape(spec.get("situation") or "") + "」／預期「"
        + html.escape(spec.get("expected") or "") + "」／禁止「"
        + html.escape(spec.get("forbidden") or "") + "」。</p>"
    )}
  </div>"""
    then = spec.get("then") or spec.get("expected") or ""
    did, now_txt = _business_result(actual)
    if passed:
        verdict = f"""<div class="verdict pass">結論：與預期相符
    <div class="sub"><strong>實際系統做了：</strong>{html.escape(did)}</div>
    <div class="sub"><strong>現在：</strong>{html.escape(now_txt)}</div>
  </div>"""
    else:
        diff_html = ""
        if diffs:
            diff_html = "<ul>" + "".join(f"<li>{html.escape(str(d))}</li>" for d in diffs) + "</ul>"
        verdict = f"""<div class="verdict fail">結論：與預期不符
    <div class="sub"><strong>預期現場應看到：</strong>{html.escape(then or "見對照明細")}</div>
    <div class="sub"><strong>實際系統做了：</strong>{html.escape(did)}</div>
    <div class="sub"><strong>現在：</strong>{html.escape(now_txt)}</div>
    {diff_html}
  </div>"""
    compare_block = ""
    if expect_rows:
        compare_block = f"""<details class="card"><summary>對照明細（可略過；結論已寫在上面）</summary>
    <p class="muted">題目規定要對上的欄位，對這次跑完的結果。通過時不必逐列看。</p>
    <table><thead><tr><th>檢查什麼</th><th>題目規定</th><th>這次跑完</th></tr></thead><tbody>{expect_rows}</tbody></table>
  </details>"""
    action_detail = actual.get("action_detail")
    if not action_detail and (dh.get("Holds") or []):
        action_detail = dh["Holds"][-1]
    ch = _observed_channels(actual)
    pending_card = ""
    if not ch["default"] and (actual.get("actions") or {}).get("set_hold"):
        pending_card = f"""<div class="card">
    <h2>待查驗（現場現在還不能當這筆 Hold 存在）</h2>
    <p class="muted">下面是<strong>已送到 MES 的內容</strong>。這一格沒有去對過 MES，所以還不是 Facts。下一格才確認它在不在。</p>
    {_json_block(action_detail)}
  </div>"""
    fact_bits = []
    if ch["lot"]:
        lot_show = {k: v for k, v in lot.items() if k != "RecTime"}
        fact_bits.append(
            "<div><h3>Lot</h3>"
            "<p class='muted'>進站時間是 Operation Start。不是 Hold 時間。</p>"
            f"{_json_block(lot_show)}</div>"
        )
    if ch["default"]:
        fact_bits.append(
            "<div><h3>DefaultHold</h3>"
            "<p class='muted'>已向 MES 查驗、確認是本系統 Default Hold 的那一筆（或確認已經沒有）。</p>"
            f"{_json_block(dh)}</div>"
        )
    if ch["smm"]:
        fact_bits.append(
            "<div><h3>SmmHold</h3>"
            "<p class='muted'>已查過的現場正式 Defect Hold（SMMH／AOA）。空陣列＝查過、現場沒有。</p>"
            f"{_json_block(_smm_facts(facts.get('SmmHold')))}</div>"
        )
    if ch["ai"]:
        fact_bits.append(
            "<div><h3>AiScan</h3>"
            "<p class='muted'>已查過的掃片結果。</p>"
            f"{_json_block(facts.get('AiScan'))}</div>"
        )
    facts_card = f"""<div class="card">
    <h2>已觀察到的現場（Facts）</h2>
    <p class="muted">只放這一格有查過、並且採信的東西。沒查過的不列。</p>
    <div class="facts-grid">{''.join(fact_bits) or '<p class="muted">這格還沒有已觀察的現場資料。</p>'}</div>
  </div>"""
    order_card = _order_summary_section(case.scenario_id, actual)
    page_title = (spec.get("do") or case.title).split("。")[0]
    why_card = _facts_decision_bridge(actual)
    dev_block = f"""<details class="card"><summary>給對程式的人（狀態機、路徑、檔名、對照明細）</summary>
    {sm_card}
    <h3>路徑</h3>
    <pre class="mermaid">
{seq}
    </pre>
    <h3>劇本（含 file:function）</h3>
    <table><thead><tr><th>#</th><th>時間</th><th>發生什麼</th><th>file:function</th><th>Port</th></tr></thead>
    <tbody>{script_rows}</tbody></table>
    {compare_block}
    <h3>actions</h3>
    {_json_block(_public_actions(actual.get("actions")))}
    <p class="muted">scenario_run {html.escape(ran_at)}</p>
  </details>"""
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <title>{html.escape(case.scenario_id)} — {html.escape(page_title)}</title>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "neutral", securityLevel: "loose", flowchart: {{ htmlLabels: true }} }});
    document.addEventListener("DOMContentLoaded", () => {{
      const purpose = {json.dumps(STATE_PURPOSE, ensure_ascii=False)};
      const applyTips = () => {{
        document.querySelectorAll("svg .stateLabel, svg .nodeLabel, svg text").forEach((el) => {{
          const t = (el.textContent || "").trim().split(/\\s|\\n/)[0];
          if (purpose[t] && !el.querySelector("title")) {{
            const n = document.createElementNS("http://www.w3.org/2000/svg", "title");
            n.textContent = t + " — " + purpose[t];
            el.appendChild(n);
          }}
        }});
      }};
      setTimeout(applyTips, 800);
    }});
  </script>
  <style>{CSS}</style>
</head>
<body>
<header>
  <p><a href="{html.escape(index_href)}">← 全部情境</a></p>
  <h1>{html.escape(case.scenario_id)}　{html.escape(page_title)}</h1>
  <p class="muted">{html.escape(case.title)} · <strong>沒有重跑模擬</strong></p>
  {"" if case.enabled else "<p><span class='badge none'>現場不適用，不列入驗收</span></p>"}
</header>
<main>
  {spec_card}
  {verdict}
  {order_card}
  {why_card}
  {pending_card}
  {facts_card}
  <div class="card">
    <h2>發生了什麼</h2>
    <p class="muted">灰＝現場進站；青＝本系統對 MES 做的事。這不是「Hold 已在現場」。</p>
    <table><thead><tr><th>#</th><th>時間</th><th>發生什麼</th></tr></thead>
    <tbody>{story_rows}</tbody></table>
  </div>
  {dev_block}
  {_failure_tables(actual)}
</main>
</body>
</html>
"""


def _index_machine(link_prefix: str) -> str:
    """總覽用狀態機；邊上的字連到單格驗收頁。"""
    def href(sid: str) -> str:
        return html.escape(link_prefix + sid + ".html")

    notes = _state_notes(
        [
            "NEED_HOLD",
            "HOLD_VERIFY_PENDING",
            "WAIT_AI",
            "RELEASE_SENT",
            "RELEASE_VERIFY_PENDING",
            "CLOSED",
            "DEFECT_HOLD_UNCONFIRMED",
        ]
    )
    return f"""stateDiagram-v2
  [*] --> NEED_HOLD
  NEED_HOLD --> HOLD_VERIFY_PENDING: C01 送出 Default Hold
  HOLD_VERIFY_PENDING --> WAIT_AI: C02 確認存在
  WAIT_AI --> WAIT_AI: C03 等掃片
  WAIT_AI --> RELEASE_SENT: C04 掃完+settle 申請解除
  RELEASE_SENT --> RELEASE_VERIFY_PENDING: C05 查驗解除
  RELEASE_VERIFY_PENDING --> CLOSED: C06 確認已解除
  CLOSED --> [*]
  NEED_HOLD --> HOLD_VERIFY_PENDING: C07 改用下一個 Hold Code
  WAIT_AI --> CLOSED: C08 線上代解
  WAIT_AI --> RELEASE_SENT: C09 NG 同樣 settle 後解
  WAIT_AI --> RELEASE_SENT: C10 Defect 同樣 settle 後解
  RELEASE_VERIFY_PENDING --> CLOSED: C11 確認已解除
{notes}
"""


def render_index_html(rows: list[dict], *, link_prefix: str) -> str:
    total = len(rows)
    passed = sum(1 for r in rows if r["passed"] is True)
    failed = sum(1 for r in rows if r["passed"] is False)
    skipped = sum(1 for r in rows if r.get("badge") == "skip")
    missing = sum(1 for r in rows if r["passed"] is None and r.get("badge") != "skip")
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["group"], []).append(r)
    blocks = []
    order = ["stage"] + [g for g in GROUP_INTRO if g not in {"stage", "v1"} and g in groups] + (["v1"] if "v1" in groups else [])
    for group in order:
        if group not in groups:
            continue
        items = groups[group]
        intro = GROUP_INTRO.get(group, "")
        trs = "".join(
            f"<tr class='row'><td>{html.escape(str(it['n']))}</td>"
            f"<td><a href='{html.escape(link_prefix + it['id'] + '.html')}'><code>{html.escape(it['id'])}</code></a></td>"
            f"<td><a href='{html.escape(link_prefix + it['id'] + '.html')}'>{html.escape(it['do'])}</a></td>"
            f"<td><span class='badge {it['badge']}'>{html.escape(it['badge_text'])}</span></td>"
            f"<td>{html.escape(it['now'])}</td></tr>"
            for it in items
        )
        inner = (
            f"<table><thead><tr><th>#</th><th>ID</th><th>這一格做什麼</th><th>結論</th>"
            f"<th>現在</th></tr></thead><tbody>{trs}</tbody></table>"
        )
        if group == "v1":
            blocks.append(
                f"<details class='card'><summary><h2 style='display:inline'>{html.escape(group)}</h2> "
                f"<span class='muted'>{html.escape(intro)}</span></summary>{inner}</details>"
            )
        else:
            blocks.append(
                f"<div class='card'><h2>{html.escape(group)}</h2>"
                f"<p class='muted'>{html.escape(intro)}</p>{inner}</div>"
            )
    discuss = "SCENARIO_DISCUSSION.md" if link_prefix else "../../SCENARIO_DISCUSSION.md"
    issue_trs = "".join(
        f"<tr><td><code>{html.escape(k)}</code></td><td>{html.escape(v)}</td></tr>"
        for k, v in OPEN_ISSUES
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <title>情境庫總覽</title>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "neutral", securityLevel: "loose", htmlLabels: true, flowchart: {{ htmlLabels: true }} }});
    const purpose = {json.dumps(STATE_PURPOSE, ensure_ascii=False)};
    setTimeout(() => {{
      document.querySelectorAll("svg .stateLabel, svg text").forEach((el) => {{
        const t = (el.textContent || "").trim().split(/\\n/)[0].trim();
        if (purpose[t]) {{
          el.setAttribute("title", purpose[t]);
          const n = document.createElementNS("http://www.w3.org/2000/svg", "title");
          n.textContent = purpose[t];
          el.appendChild(n);
        }}
      }});
    }}, 800);
  </script>
  <style>{CSS}</style>
</head>
<body>
<header>
  <h1>Vision AI Hold — 情境庫總覽</h1>
  <p class="story">每一頁同一格式：<strong>這題要做什麼 → 結論 → 單子走到哪 → 為什麼做這一步</strong>。
  點 <code>C01</code>…<code>C11</code>。結論先看過／不過，不必對表。</p>
  <div class="card spec">
    <h2>主路徑狀態機</h2>
    <pre class="mermaid">
{_index_machine(link_prefix)}
    </pre>
    <p class="muted">方塊＝訂單現在停在哪（狀態）。<strong>編號在箭頭上</strong>＝這一格要跑的驗收／Cron（C01、C02…）。
    像 NEED_HOLD 沒有編號，是因為它只是起點，還沒動作。</p>
  </div>
  {f'''<div class="card spec">
    <h2>還值得討論（尚未定案，沒有對應通過標章）</h2>
    <p class="muted">全文：<a href="{html.escape(discuss)}">SCENARIO_DISCUSSION.md</a></p>
    <table><thead><tr><th>議題</th><th>卡在哪</th></tr></thead><tbody>{issue_trs}</tbody></table>
  </div>''' if OPEN_ISSUES else ""}
  <p><span class="badge pass">通過 {passed}</span>
     <span class="badge fail">失敗 {failed}</span>
     {f'<span class="badge skip">現場不適用，不跑 {skipped}</span>' if skipped else ""}
     {f'<span class="badge none">尚無 run {missing}</span>' if missing else ""}
     共 {total} 筆</p>
  <p class="muted">資料庫 <code>Design/generated/scenario_catalog.sqlite</code>。
    本頁通過＝offline 邏輯（D12）；上線再用程式對 MES 確認。</p>
</header>
<main>
{''.join(blocks)}
</main>
</body>
</html>
"""


def render_skipped_html(case, *, index_href: str) -> str:
    """題庫關掉的題：不是漏跑，是現場不適用所以故意不跑。"""
    spec = case.spec or {}
    why = spec.get("given") or spec.get("do") or case.title
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <title>{html.escape(case.scenario_id)} — 現場不適用，不跑</title>
  <style>{CSS}</style>
</head>
<body>
<header>
  <p><a href="{html.escape(index_href)}">← 全部情境</a></p>
  <h1>{html.escape(case.scenario_id)}　{html.escape(case.title)}</h1>
  <p><span class="badge skip">現場不適用，不跑</span></p>
</header>
<main>
  <div class="verdict" style="background:#fef3c7;color:#92400e;border:1px solid #fcd34d;">
    結論：這題<strong>故意不跑</strong>，不是漏測。
    <div class="sub">現場 MES 一定能回答這批有沒有 Hold。list_holds 只會是「有」或「沒有」，不會是 UNKNOWN。所以不當驗收、也不進每日回歸。</div>
  </div>
  <div class="card spec">
    <h2>為什麼在清單裡還看得到</h2>
    <p>V1 編號還在，避免以為題號斷了。點進來是為了說明「為什麼不跑」，不是等補跑。</p>
    <table>
      <tr><th>現場已經</th><td>{html.escape(spec.get("given") or why)}</td></tr>
      <tr><th>實際系統會做</th><td><strong>{html.escape(spec.get("do") or "")}</strong></td></tr>
      <tr><th>做完應看到</th><td>{html.escape(spec.get("then") or "不列入驗收。")}</td></tr>
      <tr><th>禁止</th><td>{html.escape(spec.get("dont") or spec.get("forbidden") or "")}</td></tr>
    </table>
  </div>
</main>
</body>
</html>
"""


def write_scenario_html(scenario_id: str = "T19") -> Path:
    write_all_scenario_html()
    return OUT_DIR / f"{scenario_id}.html"


def write_all_scenario_html() -> Path:
    from vai_hold.adapters.persistence.sqlite.scenario_catalog import SqliteScenarioCatalog

    if not DB.exists():
        raise FileNotFoundError(f"沒有已跑過的情境庫：{DB}。請先 python -m vai_hold run-scenarios")
    cat = SqliteScenarioCatalog(DB)
    from vai_hold.tools.seed_scenario_catalog import seed_catalog

    seed_catalog(cat)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cat.list_all():
        stored = cat.latest_run(case.scenario_id)
        if not case.enabled:
            (OUT_DIR / f"{case.scenario_id}.html").write_text(
                render_skipped_html(case, index_href="index.html"),
                encoding="utf-8",
            )
            rows.append(
                {
                    "n": case.sort_order,
                    "id": case.scenario_id,
                    "title": case.title,
                    "do": ((case.spec or {}).get("do") or case.title).split("。")[0],
                    "group": case.group_name,
                    "passed": None,
                    "badge": "skip",
                    "badge_text": "現場不適用，不跑",
                    "now": "MES 一定能回答有沒有 Hold；這題不當驗收",
                }
            )
            continue
        if stored is None:
            rows.append(
                {
                    "n": case.sort_order,
                    "id": case.scenario_id,
                    "title": case.title,
                    "do": ((case.spec or {}).get("do") or case.title).split("。")[0],
                    "group": case.group_name,
                    "passed": None,
                    "badge": "none",
                    "badge_text": "尚無 run",
                    "now": "—",
                }
            )
            continue
        ran_at, passed, actual, diffs = stored
        (OUT_DIR / f"{case.scenario_id}.html").write_text(
            render_case_html(case, ran_at, passed, actual, index_href="index.html", diffs=diffs),
            encoding="utf-8",
        )
        _did, now_txt = _business_result(actual)
        rows.append(
            {
                "n": case.sort_order,
                "id": case.scenario_id,
                "title": case.title,
                "do": ((case.spec or {}).get("do") or case.title).split("。")[0],
                "group": case.group_name,
                "passed": passed,
                "badge": "pass" if passed else "fail",
                "badge_text": "與預期相符" if passed else "與預期不符",
                "now": now_txt,
            }
        )
    index_in_evidence = render_index_html(rows, link_prefix="")
    (OUT_DIR / "index.html").write_text(index_in_evidence, encoding="utf-8")
    index_in_design = render_index_html(rows, link_prefix="generated/evidence/")
    (ROOT / "Design" / "scenarios.html").write_text(index_in_design, encoding="utf-8")
    return ROOT / "Design" / "scenarios.html"


if __name__ == "__main__":
    print(write_all_scenario_html())
