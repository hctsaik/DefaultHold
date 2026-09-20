"""Build Design/case_example.html from a real T01 mock log."""

from __future__ import annotations

import html
import io
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _capture_t01_log() -> str:
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "src"))
    from harness import make_harness
    from test_t01_t18 import _happy_until_hold

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
        h = make_harness()
        _happy_until_hold(h)
        h.world.complete_ai("LOT1")
        h.check_ai()
        h.confirm_release()
        return buf.getvalue()
    finally:
        log.handlers[:] = old_handlers
        log.propagate = old_prop
        log.setLevel(old_level)


def write_html() -> Path:
    from vai_hold.investigate import business_stack, for_lot, mermaid_sequence, parse_records, _short_path

    text = _capture_t01_log()
    recs = parse_records(text)
    focused = for_lot(recs, "LOT1")
    evals = [r for r in focused if r.get("event") == "eval.cycle"]
    a201 = next(d for d in evals if (d.get("decision") or {}).get("rule_id") == "A2-01")
    obs = a201.get("observed") or {}
    st = a201.get("state") or {}
    dec = a201.get("decision") or {}
    seq = mermaid_sequence(focused, "LOT1")
    vai_lines = [ln for ln in text.splitlines() if ln.startswith("[VAI_EVAL]") or ln.strip().startswith("OBSERVED") or ln.strip().startswith("STATE") or ln.strip().startswith("DECISION") or ln.strip().startswith("JUDGE") or ln.strip().startswith("RUN")]
    vai_block = "\n".join(vai_lines[:12])
    if not vai_block:
        vai_block = json.dumps(
            {"event": "eval.cycle", "observed": obs, "state": st, "decision": dec},
            ensure_ascii=False,
            indent=2,
        )
    fact_rows = "".join(
        f"<tr><td><code>{html.escape(str(k))}</code></td><td><code>{html.escape(str(v))}</code></td></tr>"
        for k, v in obs.items()
    )
    state_rows = "".join(
        f"<tr><td><code>{html.escape(str(k))}</code></td><td><code>{html.escape(str(v))}</code></td></tr>"
        for k, v in st.items()
    )
    stack_rows = "".join(f"<tr><td>{html.escape(line)}</td></tr>" for line in business_stack(focused, "LOT1"))
    page = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <title>查案 Example：程式印出的 EVAL log</title>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true, theme: "neutral", securityLevel: "loose" }});
  </script>
  <style>
    body {{ font-family: "Segoe UI","Noto Sans TC",sans-serif; margin:0; background:#f4f1ea; color:#1c1917; }}
    header, main {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 1.4rem; }}
    h2 {{ font-size: 1.08rem; color: #0f766e; }}
    .muted {{ color:#57534e; }}
    .card {{ background:#fff; border-radius:12px; padding:18px 20px; margin:16px 0; border:1px solid #e7e5e4; }}
    table {{ width:100%; border-collapse:collapse; font-size:0.9rem; }}
    td, th {{ border-bottom:1px solid #e7e5e4; padding:8px 6px; text-align:left; vertical-align:top; }}
    pre {{ background:#1c1917; color:#fafaf9; padding:12px; border-radius:10px; overflow:auto; font-size:0.78rem; }}
    .mermaid {{ background:#fafaf9; border-radius:8px; padding:8px; overflow:auto; }}
    .need {{ border-color:#93c5fd; }}
  </style>
</head>
<body>
<header>
  <h1>查案 Example：你貼給我的是「程式印出來的 EVAL」</h1>
  <p class="muted">不是事後摘要。Pipeline 每次判斷都會印 <code>eval.cycle</code> / <code>[VAI_EVAL]</code>，裡面已含 OBSERVED（原始 Facts）、STATE（轉換後）、DECISION（規則＋檔名行號）。你把這段貼回來即可。</p>
</header>
<main>
  <div class="card need">
    <h2>輸入 = 程式自己印的 Log（請貼這個，不是精簡 JSON）</h2>
    <pre>{html.escape(vai_block)}</pre>
    <p class="muted">對應 JSON 事件名 <code>eval.cycle</code>，同一輪還有 <code>run_id</code>、<code>lot_id</code>。</p>
  </div>
  <div class="card">
    <h2>1. OBSERVED — 原始 Facts（程式撈到的）</h2>
    <table><thead><tr><th>欄位</th><th>值</th></tr></thead><tbody>{fact_rows}</tbody></table>
  </div>
  <div class="card">
    <h2>2. STATE — 轉換後的狀態（程式算完印出，不是查案時才猜）</h2>
    <table><thead><tr><th>狀態</th><th>值</th></tr></thead><tbody>{state_rows}</tbody></table>
  </div>
  <div class="card">
    <h2>3. DECISION — 規則與程式位置</h2>
    <ul>
      <li><strong>rule_id</strong> <code>{html.escape(str(dec.get("rule_id")))}</code> / <code>{html.escape(str(dec.get("reason")))}</code></li>
      <li><strong>action</strong> <code>{html.escape(str(dec.get("action")))}</code></li>
      <li><strong>判斷</strong> <code>{html.escape(_short_path(str(dec.get("judge_loc") or "")))}</code></li>
      <li><strong>執行</strong> <code>{html.escape(_short_path(str(dec.get("run_loc") or "")))}</code></li>
    </ul>
  </div>
  <div class="card">
    <h2>4. 業務路徑（每一步含檔名:函式:行號）</h2>
    <pre class="mermaid">
{seq}
    </pre>
  </div>
  <div class="card">
    <h2>5. Call stack</h2>
    <table><tbody>{stack_rows}</tbody></table>
  </div>
</main>
</body>
</html>
"""
    out = ROOT / "Design" / "case_example.html"
    out.write_text(page, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(write_html())
