"""Parse vai_hold logs and classify Facts vs Decision vs Action for case work."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_JSON = re.compile(r"\{.*\}\s*$")


@dataclass
class ParseReport:
    records: list[dict[str, Any]] = field(default_factory=list)
    lines: int = 0
    parsed: int = 0
    skipped_plain: int = 0
    skipped_bad_json: int = 0
    skipped_no_event: int = 0

    def summary_lines(self) -> list[str]:
        return [
            f"- 總行數 {self.lines}；有效事件 {self.parsed}；略過普通文字 {self.skipped_plain}；",
            f"- 損壞 JSON {self.skipped_bad_json}；無 event 欄 {self.skipped_no_event}",
        ]


def parse_log(text: str) -> ParseReport:
    report = ParseReport()
    for line in text.splitlines():
        report.lines += 1
        m = _JSON.search(line)
        if not m:
            report.skipped_plain += 1
            continue
        try:
            rec = json.loads(m.group(0))
        except json.JSONDecodeError:
            report.skipped_bad_json += 1
            continue
        if isinstance(rec, dict) and rec.get("event"):
            report.records.append(rec)
            report.parsed += 1
        else:
            report.skipped_no_event += 1
    return report


def parse_records(text: str) -> list[dict[str, Any]]:
    return parse_log(text).records


def _record_lot(rec: dict[str, Any]) -> str | None:
    if rec.get("lot_id"):
        return str(rec.get("lot_id"))
    extra = rec.get("extra") or {}
    if isinstance(extra, dict) and extra.get("lot_id"):
        return str(extra.get("lot_id"))
    obs = rec.get("observed") or {}
    if isinstance(obs, dict):
        lot = obs.get("Lot") or {}
        if isinstance(lot, dict) and lot.get("LotId"):
            return str(lot.get("LotId"))
    return None


def for_lot(records: list[dict[str, Any]], lot_id: str) -> list[dict[str, Any]]:
    return [r for r in records if _record_lot(r) == lot_id]


def for_order(records: list[dict[str, Any]], order_id: str) -> list[dict[str, Any]]:
    def oid(r: dict[str, Any]) -> str | None:
        if r.get("order_id"):
            return str(r.get("order_id"))
        obs = r.get("observed") or {}
        if isinstance(obs, dict):
            db = obs.get("OrderDb") or {}
            if isinstance(db, dict) and db.get("OrderId"):
                return str(db.get("OrderId"))
        return None

    return [r for r in records if oid(r) == order_id]


def decisions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in records if r.get("event") == "decision.applied"]


def classify_layer(decision: dict[str, Any]) -> str:
    """Which layer to open first when this decision looks wrong."""
    facts = decision.get("facts") or {}
    if facts.get("hold_query") in {"UNKNOWN", "STALE"}:
        return "facts"
    if facts.get("flow_query") == "UNKNOWN":
        return "facts"
    if facts.get("data_error") or decision.get("rule_id") == "A2-09":
        return "decision"
    action = decision.get("action")
    if action in {"SET_HOLD", "SET_RELEASE", "VERIFY_HOLD", "VERIFY_RELEASE", "CHECK_AI"}:
        return "action_or_decision"
    return "decision"


def required_fields_ok(rec: dict[str, Any]) -> list[str]:
    missing = []
    if not rec.get("event"):
        missing.append("event")
    if rec.get("event") in {"pipeline.start", "pipeline.end", "decision.applied"} and not rec.get("run_id"):
        missing.append("run_id")
    if rec.get("event") == "eval.cycle":
        for k in ("observed", "state", "decision", "function_code"):
            if k not in rec:
                missing.append(k)
    if rec.get("event") == "decision.applied":
        for k in ("rule_id", "reason", "action", "facts", "function_code"):
            if k not in rec:
                missing.append(k)
        facts = rec.get("facts") or {}
        for k in ("hold_query", "own_hold_count", "in_flight", "ai_status"):
            if k not in facts:
                missing.append(f"facts.{k}")
    return missing


def playbook_path() -> Path:
    return Path(__file__).resolve().parents[2] / "Design" / "LOG_CODE_MAP.md"


LAYER_FILES = {
    "facts": "src/vai_hold/application/services.py snapshot + domain/ownership.py",
    "decision": "src/vai_hold/domain/derive.py",
    "action": "src/vai_hold/application/usecases/",
    "action_or_decision": "derive.py then matching usecases/*.py",
}


_CONSEQ = {
    "hold.intent",
    "hold.sent",
    "hold.receipt",
    "hold.confirmed",
    "hold.failed",
    "hold.verify_unknown",
    "release.intent",
    "release.sent",
    "release.receipt",
    "release.confirmed",
    "release.failed",
    "transfer.intent",
    "transfer.sent",
    "transfer.receipt",
    "transfer.confirmed",
    "incident.opened",
    "order.created",
    "decision.applied",
    "pipeline.start",
    "pipeline.end",
    "control.disabled",
    "hold.orphan",
    "agent.stall",
}


_STEP_TITLE = {
    ("order.created", "A1-01"): "建單 A1-01",
    ("decision.applied", "A1-02"): "選站 A1-02",
    ("decision.applied", "A1-03"): "送 Hold A1-03",
    ("decision.applied", "A1-04"): "備援 Hold A1-04",
    ("hold.intent", None): "Hold Intent",
    ("hold.sent", None): "Hold 送出",
    ("hold.receipt", None): "Hold Receipt",
    ("decision.applied", "A2-01"): "查驗 A2-01",
    ("hold.confirmed", "A2-02"): "Hold 已確認 A2-02",
    ("decision.applied", "A2-04"): "線上代解，視為解除成功 A2-04",
    ("decision.applied", "A2-05"): "等 AI A2-05",
    ("decision.applied", "A2-07"): "AI OK A2-07",
    ("decision.applied", "A2-08"): "Defect 交接 A2-08",
    ("decision.applied", "A2-16"): "SmmHold transfer A2-16",
    ("transfer.sent", None): "transferHold 送出",
    ("transfer.confirmed", "A2-16"): "memo 已累積",
    ("decision.applied", "A1-09"): "同一命令重試 A1-09",
    ("decision.applied", "A2-09"): "Defect 未交接 A2-09",
    ("release.intent", None): "Release Intent",
    ("release.sent", None): "送 Release",
    ("release.receipt", None): "Release Receipt",
    ("decision.applied", "A2-10"): "查驗解除 A2-10",
    ("release.confirmed", "A2-11"): "已解除 A2-11",
}

_SKIP_SEQ = {"pipeline.start", "pipeline.end"}


def _short_path(loc: str) -> str:
    return loc.replace("vai_hold/", "").replace("application/", "").replace("src/", "")


def _title(ev: str, rule: str) -> str:
    return _STEP_TITLE.get((ev, rule)) or _STEP_TITLE.get((ev, None)) or (f"{ev} {rule}".strip())


def loc_for_record(r: dict[str, Any], locator: dict | None = None) -> dict[str, str]:
    """判斷位置 vs 執行位置。"""
    from vai_hold.locator import build_locator, first_loc

    locator = locator or build_locator()
    ev = r.get("event") or ""
    rule = r.get("rule_id") or ""
    action = r.get("action") or ""
    attr = ev.replace(".", "_").upper()
    decide = first_loc(locator, rule, prefer="domain/derive") if rule else ""
    run = ""
    if ev == "decision.applied":
        if action == "VERIFY_HOLD" or rule == "A2-01":
            run = first_loc(locator, "A2-02", "event:HOLD_CONFIRMED", prefer="usecases/verify_hold")
        elif action == "VERIFY_RELEASE" or rule == "A2-10":
            run = first_loc(locator, "A2-11", "event:RELEASE_CONFIRMED", prefer="usecases/verify_release")
        elif action == "SET_HOLD" or rule in {"A1-03", "A1-04"}:
            run = first_loc(locator, "event:HOLD_INTENT", prefer="usecases/request_hold")
        elif action == "SET_RELEASE" or rule in {"A2-07", "A2-08", "A2-21"}:
            run = first_loc(locator, "event:RELEASE_INTENT", prefer="usecases/request_release")
        elif rule == "A2-09":
            run = first_loc(locator, "A2-09", prefer="pipelines/check_ai")
        elif action == "SELECT_TARGET" or rule == "A1-02":
            run = first_loc(locator, "A1-02", prefer="pipelines/set_default_hold")
        else:
            run = first_loc(locator, rule, prefer="pipelines")
    elif ev in {"hold.intent", "hold.sent", "hold.receipt"}:
        run = first_loc(locator, f"event:{attr}", prefer="usecases/request_hold") or first_loc(
            locator, f"event:{attr}", prefer="services"
        )
        decide = first_loc(locator, rule or "A1-03", prefer="domain/derive")
    elif ev == "hold.confirmed":
        run = first_loc(locator, "A2-02", prefer="usecases/verify_hold")
        decide = first_loc(locator, "A2-01", prefer="domain/derive")
    elif ev.startswith("release."):
        run = first_loc(locator, f"event:{attr}", "A2-11", prefer="usecases")
        decide = first_loc(locator, rule or "A2-21", prefer="domain/derive")
    elif ev == "order.created":
        run = first_loc(locator, "event:ORDER_CREATED", prefer="pipelines/set_default_hold")
        decide = first_loc(locator, "A1-01", prefer="domain/derive")
    else:
        run = first_loc(locator, rule, f"event:{attr}")
    return {"decide": decide, "run": run}


def mermaid_sequence(records: list[dict[str, Any]], lot_id: str | None = None) -> str:
    from vai_hold.locator import build_locator

    locator = build_locator()
    recs = for_lot(records, lot_id) if lot_id else records
    recs = [r for r in recs if r.get("event") in _CONSEQ and r.get("event") not in _SKIP_SEQ]
    omitted = 0
    if len(recs) > 40:
        omitted = len(recs) - 40
        recs = recs[-40:]
    lines = ["flowchart TB"]
    if omitted:
        lines.append(f'  skip["省略較早 {omitted} 筆；完整 JSONL 請看原 log"]')
    prev = "skip" if omitted else None
    for i, r in enumerate(recs):
        nid = f"n{i}"
        ev = r.get("event") or ""
        rule = r.get("rule_id") or ""
        title = _title(ev, rule)
        locs = loc_for_record(r, locator)
        loc_l = _short_path(locs["run"] or locs["decide"] or "")
        decide_l = _short_path(locs["decide"] or "")
        parts = [title]
        if loc_l:
            parts.append(f"執行 {loc_l}")
        if decide_l and decide_l != loc_l:
            parts.append(f"判斷 {decide_l}")
        label = "\\n".join(parts).replace('"', "'")
        lines.append(f'  {nid}["{label}"]')
        if prev:
            lines.append(f"  {prev} --> {nid}")
        prev = nid
    return "\n".join(lines) + "\n"


def facts_state_rule(decision: dict[str, Any]) -> dict[str, Any]:
    facts = dict(decision.get("facts") or {})
    work = facts.get("work_state") or decision.get("work_state")
    inflight = facts.get("in_flight")
    states = []
    if facts.get("hold_query"):
        states.append(("Hold 觀察", str(facts["hold_query"]), "FOUND=查到列；NOT_FOUND=確定沒有；UNKNOWN=不能當沒有"))
    states.append(("本系統 Hold 筆數", str(facts.get("own_hold_count")), "≥1 已有防守，不再 A1-03 新設"))
    states.append(("未完成命令", str(inflight), "SET_HOLD:* → 只能查驗 A2-01；SET_RELEASE:* → A2-10"))
    states.append(("AI", str(facts.get("ai_status")), "WAITING→A2-05；掃完未滿 settle→A2-09；滿 settle→A2-21"))
    states.append(("工作狀態", str(work), "HOLD_VERIFY_PENDING / WAIT_AI / READY_RELEASE_OK …"))
    states.append(("控制開關", str(facts.get("control")), "非 ENABLED → A1-08 不新設 Hold"))
    return {
        "facts": facts,
        "states": states,
        "rule_id": decision.get("rule_id"),
        "reason": decision.get("reason"),
        "action": decision.get("action"),
        "function_code": decision.get("function_code"),
    }


def mermaid_derive_path(decision: dict[str, Any]) -> str:
    from vai_hold.decision_tree import nid, path_spine

    if decision.get("event") == "eval.cycle":
        dec = decision.get("decision") or {}
        rule = dec.get("rule_id") or ""
        reason = dec.get("reason") or ""
        facts = {**(decision.get("observed") or {}), **(decision.get("state") or {})}
    else:
        rule = decision.get("rule_id") or ""
        reason = decision.get("reason") or ""
        facts = decision.get("facts") or {}
    spine = path_spine(rule, reason, facts)
    if not spine:
        return f'flowchart TD\n  X["未知葉 {rule} {reason}"]\n'
    lines = ["flowchart TD"]
    prev = None
    for i, (r, s, cap) in enumerate(spine):
        node = nid(r, s) + str(i)
        safe = str(cap).replace('"', "'")[:80]
        lines.append(f'  {node}["{r} {s}\\n{safe}"]')
        if prev:
            lines.append(f"  {prev} --> {node}")
        prev = node
    if prev:
        lines.append(f"  style {prev} fill:#f96,stroke:#333")
    return "\n".join(lines) + "\n"


def business_stack(records: list[dict[str, Any]], lot_id: str | None = None) -> list[str]:
    from vai_hold.locator import build_locator

    locator = build_locator()
    recs = for_lot(records, lot_id) if lot_id else records
    lines: list[str] = []
    for r in recs:
        ev = r.get("event")
        if ev not in _CONSEQ or ev in _SKIP_SEQ:
            continue
        rule = r.get("rule_id") or ""
        locs = loc_for_record(r, locator)
        bit = f"{_title(ev, rule)}"
        if r.get("reason"):
            bit += f" ({r['reason']})"
        if locs.get("run"):
            bit += f"  執行 `{_short_path(locs['run'])}`"
        if locs.get("decide") and locs["decide"] != locs.get("run"):
            bit += f"  判斷 `{_short_path(locs['decide'])}`"
        lines.append(bit)
    return lines


def render_case(text: str, lot_id: str, *, order_id: str | None = None) -> str:
    report = parse_log(text)
    recs = report.records
    focused = for_lot(recs, lot_id)
    if order_id:
        focused = for_order(focused, order_id)
    evals = [r for r in focused if r.get("event") == "eval.cycle"]
    decs = decisions(focused)
    befores = [e for e in evals if e.get("observation_phase") == "before_action"]
    afters = [e for e in evals if e.get("observation_phase") == "after_write"]
    focus = befores[-1] if befores else (evals[-1] if evals else (decs[-1] if decs else None))
    parts = [f"# Case lot_id={lot_id}", ""]
    parts += ["## 解析摘要（不是結論）", ""] + report.summary_lines() + [""]
    if afters and focus and focus.get("observation_phase") == "before_action":
        after = afters[-1]
        holds = ((after.get("observed") or {}).get("DefaultHold") or {}).get("Holds")
        n = len(holds) if isinstance(holds, list) else "未知"
        after_err = ((after.get("observed") or {}).get("OrderDb") or {}).get("DataError")
        extra = f"；data_error `{after_err}`" if after_err else ""
        parts += [
            f"- 決策用 **before_action**；寫入後觀察 **after_write** DefaultHold 筆數 `{n}`{extra}（不是決策輸入）",
            "",
        ]
    if focus and focus.get("event") == "eval.cycle":
        obs = focus.get("observed") or {}
        st = focus.get("state") or {}
        dec = focus.get("decision") or {}
        parts += [f"## 1. 程式印出的 OBSERVED（原始 Facts） `{focus.get('function_code')}`", ""]
        for k, v in obs.items():
            parts.append(f"- `{k}` = `{v!s}`")
        parts += ["", "## 2. 程式印出的 STATE（轉換後）", ""]
        for k, v in st.items():
            parts.append(f"- `{k}` = `{v!s}`")
        parts += [
            "",
            "## 3. 程式印出的 DECISION",
            "",
            f"- **rule_id** `{dec.get('rule_id')}` / `{dec.get('reason')}`",
            f"- **action** `{dec.get('action')}`",
            f"- **判斷** `{_short_path(str(dec.get('judge_loc') or ''))}`",
            f"- **執行** `{_short_path(str(dec.get('run_loc') or ''))}`",
            "",
        ]
        odb = obs.get("OrderDb") or {}
        if odb.get("DataError"):
            parts += [
                "## Order DB 錯誤旗標（本系統表，不是 MES）",
                "",
                f"- **data_error** `{odb.get('DataError')}`",
                f"- work_state `{odb.get('WorkState')}`",
                "",
            ]
    elif focus:
        pack = facts_state_rule(focus)
        locs = loc_for_record(focus)
        parts += [f"## 1. 撈到的資料（{focus.get('function_code')} / {pack['rule_id']}）", ""]
        facts = pack["facts"]
        for k in (
            "hold_query",
            "own_hold_count",
            "in_flight",
            "ai_status",
            "expected_wafers",
            "missing_wafers",
            "binding_status",
            "lifecycle",
            "work_state",
            "control",
            "has_target",
            "has_defect_hold",
        ):
            if k in facts:
                parts.append(f"- `{k}` = `{facts[k]!s}`")
        parts += ["", "## 2. 這些資料對到哪些狀態", ""]
        for name, val, meaning in pack["states"]:
            parts.append(f"- **{name}** = `{val}` — {meaning}")
        parts += [
            "",
            "## 3. 狀態對到哪個 rule_id、哪段程式",
            "",
            f"- **rule_id** `{pack['rule_id']}` / `{pack['reason']}`",
            f"- **action** `{pack['action']}`",
            f"- **執行** `{_short_path(locs.get('run') or '')}`",
            f"- **判斷** `{_short_path(locs.get('decide') or '')}`",
            "",
        ]
    parts += ["## 4. 業務路徑（每一步含檔名:函式:行號）", "", "```mermaid", mermaid_sequence(focused, lot_id), "```"]
    if focus:
        parts += [
            "",
            f"## 5. 決策脊柱 `{(focus.get('decision') or focus).get('rule_id') if isinstance(focus.get('decision'), dict) else focus.get('rule_id')}`",
            "",
            "```mermaid",
            mermaid_derive_path(focus),
            "```",
        ]
    parts += ["", "## 6. Call stack", ""]
    for line in business_stack(focused, lot_id):
        parts.append(f"- {line}")
    return "\n".join(parts) + "\n"
