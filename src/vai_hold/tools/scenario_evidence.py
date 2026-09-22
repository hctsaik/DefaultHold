"""Run mock E2E scenarios and write Facts/Action evidence under Design/generated/evidence/."""

from __future__ import annotations

import io
import json
import logging
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "Design" / "generated" / "evidence"


def _harness():
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "src"))
    from harness import make_harness
    from test_t01_t18 import _happy_until_hold

    return make_harness, _happy_until_hold


def _capture(run: Callable) -> tuple[object, str]:
    make_harness, _happy = _harness()
    buf = io.StringIO()
    log = logging.getLogger("vai_hold")
    handler = logging.StreamHandler(buf)
    old_handlers = list(log.handlers)
    old_prop = log.propagate
    old_level = log.level
    log.handlers[:] = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False
    try:
        h = run(make_harness, _happy)
        return h, buf.getvalue()
    finally:
        log.handlers[:] = old_handlers
        log.propagate = old_prop
        log.setLevel(old_level)


def run_t01(make_harness, happy):
    h = make_harness()
    happy(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.check_ai()
    h.confirm_release()
    return h


def run_hold_retry_transient(make_harness, _happy):
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "rejected_transient"
    for _ in range(5):
        h.set_hold()
    return h


def run_hold_retry_timeout(make_harness, _happy):
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    for _ in range(4):
        h.set_hold()
        h.confirm_hold()
    return h


def run_hold_unknown_does_not_resend(make_harness, _happy):
    h = make_harness()
    h.world.add_lot("LOT1")
    h.world.set_response["LOT1"] = "timeout"
    h.world.set_effect["LOT1"] = "none"
    h.set_hold()
    h.world.list_status["LOT1"] = "unknown"
    h.confirm_hold()
    h.set_hold()
    return h


def run_release_retry_transient(make_harness, happy):
    h = make_harness()
    happy(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.world.release_response["LOT1"] = "rejected_transient"
    for _ in range(5):
        h.check_ai()
        h.confirm_release()
    return h


def run_release_retry_timeout(make_harness, happy):
    h = make_harness()
    happy(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.world.release_response["LOT1"] = "timeout"
    h.world.set_effect["release:LOT1"] = "none"
    for _ in range(4):
        h.check_ai()
        h.confirm_release()
    return h


def run_transfer_success(make_harness, happy):
    h = make_harness()
    happy(h)
    h.world.scan_wafer("LOT1", "W01", result="DEFECT")
    h.world.add_defect_hold("LOT1", memo="Please check #1")
    h.check_ai()
    h.world.scan_wafer("LOT1", "W02", result="DEFECT")
    h.check_ai()
    h.check_ai()
    return h


def run_transfer_retry_transient(make_harness, happy):
    h = make_harness()
    happy(h)
    h.world.scan_wafer("LOT1", "W01", result="DEFECT")
    h.world.add_defect_hold("LOT1", memo="Please check #1")
    h.check_ai()
    h.world.scan_wafer("LOT1", "W02", result="DEFECT")
    for _ in range(5):
        h.check_ai()
    return h


def run_t14_handoff(make_harness, happy):
    h = make_harness()
    happy(h)
    h.world.complete_ai("LOT1", result="DEFECT")
    h.settle()
    h.world.add_defect_hold("LOT1")
    h.check_ai()
    h.confirm_release()
    return h


SCENARIOS: list[tuple[str, str, Callable]] = [
    ("t01_happy", "進站 → Default Hold → AI OK → 解除", run_t01),
    ("hold_retry_transient", "SET_HOLD 暫時拒絕：同一命令最多 3 次", run_hold_retry_transient),
    ("hold_retry_timeout", "SET_HOLD timeout：先查驗再重送，最多 3 次", run_hold_retry_timeout),
    ("hold_unknown_no_resend", "Hold 查詢仍 UNKNOWN：不准重送", run_hold_unknown_does_not_resend),
    ("release_retry_transient", "SET_RELEASE 暫時拒絕：同一命令最多 3 次", run_release_retry_transient),
    ("release_retry_timeout", "SET_RELEASE timeout：先查驗再重送，最多 3 次", run_release_retry_timeout),
    ("transfer_memo_accumulate", "未掃完：本 Agent 不改 SMM Memo", run_transfer_success),
    ("transfer_retry_transient", "本 Agent 不送 transferHold", run_transfer_retry_transient),
    ("t14_defect_handoff", "Defect + 現場 SMM Hold → 只解 Default Hold", run_t14_handoff),
]


def _actions(recs: list[dict]) -> list[dict]:
    keep = {
        "hold.intent",
        "hold.sent",
        "hold.receipt",
        "hold.confirmed",
        "hold.failed",
        "release.intent",
        "release.sent",
        "release.receipt",
        "release.confirmed",
        "release.failed",
        "transfer.intent",
        "transfer.sent",
        "transfer.receipt",
        "transfer.confirmed",
        "transfer.failed",
        "incident.opened",
    }
    return [r for r in recs if r.get("event") in keep]


def render_markdown(name: str, title: str, text: str, extra: dict) -> str:
    from vai_hold.investigate import parse_records

    recs = parse_records(text)
    evals = [r for r in recs if r.get("event") == "eval.cycle"]
    actions = _actions(recs)
    lines = [
        f"# Evidence：`{name}`",
        "",
        f"**情境：** {title}",
        "",
        "這份是程式自己印的 log 切片，不是事後摘要。",
        "",
        "## MES / Action 次數",
        "",
        f"- set_hold calls: `{extra.get('set_hold')}`",
        f"- release calls: `{extra.get('release')}`",
        f"- transfer calls: `{extra.get('transfer')}`",
        f"- work_state: `{extra.get('work_state')}`",
        f"- lifecycle: `{extra.get('lifecycle')}`",
        "",
        "## Action 時間序",
        "",
    ]
    if not actions:
        lines.append("_（這輪沒有對外 Hold/Release/Transfer）_")
    for a in actions:
        att = a.get("attempt_no")
        att_s = f" attempt_no={att}" if att is not None else ""
        lines.append(
            f"- `{a.get('event')}` `{a.get('function_code')}` "
            f"rule=`{a.get('rule_id')}` receipt=`{a.get('receipt')}`{att_s}"
        )
    lines += ["", "## 每一輪 EVAL（Facts → State → Decision）", ""]
    if not evals:
        lines.append("_沒有 eval.cycle_")
    for i, ev in enumerate(evals, 1):
        obs = ev.get("observed") or {}
        st = ev.get("state") or {}
        dec = ev.get("decision") or {}
        lines += [
            f"### EVAL {i} `{ev.get('function_code')}`",
            "",
            f"- **DECISION** `{dec.get('rule_id')}` / `{dec.get('reason')}` action=`{dec.get('action')}`",
            "",
            "<details><summary>OBSERVED（原始 Facts）</summary>",
            "",
            "```json",
            json.dumps(obs, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "</details>",
            "",
            "<details><summary>STATE</summary>",
            "",
            "```json",
            json.dumps(st, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "</details>",
            "",
        ]
    return "\n".join(lines) + "\n"


def write_all() -> Path:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    index = [
        "# E2E Evidence 索引",
        "",
        "每個情境都是 Fake World 跑出來的真實 log。打開 `.md` 看 Facts／Action；`.log` 是完整原始輸出。",
        "",
        "| 情境 | 說明 |",
        "|---|---|",
    ]
    for name, title, fn in SCENARIOS:
        h, text = _capture(fn)
        order = h.order()
        extra = {
            "set_hold": len(h.world.set_hold_calls),
            "release": len(h.world.release_calls),
            "work_state": getattr(order, "work_state", None),
            "lifecycle": getattr(order, "lifecycle", None),
        }
        md = render_markdown(name, title, text, extra)
        (EVIDENCE / f"{name}.md").write_text(md, encoding="utf-8")
        (EVIDENCE / f"{name}.log").write_text(text, encoding="utf-8")
        index.append(f"| [`{name}.md`]({name}.md) | {title} |")
    (EVIDENCE / "INDEX.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    return EVIDENCE


if __name__ == "__main__":
    print(write_all())
