from __future__ import annotations

from pathlib import Path

from vai_hold.tools.write_scenario_html import _business_result, write_all_scenario_html, write_scenario_html

ROOT = Path(__file__).resolve().parents[1]


def test_system_level_business_results_are_explicit():
    cases = [
        (
            {"incidents": ["COVERAGE_MISMATCH"], "control_mode": "ENABLED"},
            "覆蓋率不一致告警目前為 OPEN",
        ),
        (
            {"incidents": ["ORPHAN_HOLD"], "control_mode": "ENABLED"},
            "Orphan Hold 仍保留",
        ),
        (
            {"incidents": ["RESUME_DENIED"], "control_mode": "DISABLED_NEW_HOLD"},
            "目前仍禁止建立新 Default Hold",
        ),
        (
            {"incidents": [], "control_mode": "ENABLED", "last_function": "resume"},
            "目前允許建立新 Default Hold",
        ),
    ]
    for actual, expected in cases:
        _did, current = _business_result(actual)
        assert expected in current
        assert current != "目前停在 。"


def test_t19_html_shows_hold_missing_facts():
    out = write_scenario_html("C08")
    text = out.read_text(encoding="utf-8")
    assert "C08" in text
    assert "MANUAL" in text or "線上" in text
    assert "T19" in text
    assert "DefaultHold" in text
    assert "沒有重跑模擬" in text
    assert "scenario_run" in text
    assert 'href="index.html"' in text
    assert "Fake MES" not in text
    assert "set_default_hold.py" in text
    assert "Operation Start" in text


def test_scenario_index_links_every_catalog_case():
    index = write_all_scenario_html()
    text = index.read_text(encoding="utf-8")
    assert "情境庫總覽" in text
    assert "C01" in text and "C08" in text and "HOLD_RETRY3" in text
    assert "offline" in text or "D12" in text
    assert "generated/evidence/C08.html" in text
    assert "目前停在 。" not in text
    assert "覆蓋率不一致告警目前為 OPEN" in text
    assert "Orphan Hold 仍保留" in text
    assert "目前仍禁止建立新 Default Hold" in text
    assert "目前允許建立新 Default Hold" in text
    ev = ROOT / "Design" / "generated" / "evidence" / "index.html"
    assert ev.exists()
    body = ev.read_text(encoding="utf-8")
    assert "C08.html" in body
    t18 = (ROOT / "Design" / "generated" / "evidence" / "T18.html").read_text(encoding="utf-8")
    assert "實際系統會做" in t18 or "這輪要做" in t18
    assert "仍用自己的 Memo 送 ENHL" in t18
    assert "再試 OTHL" in t18
    assert "解別人的" in t18
    t03 = (ROOT / "Design" / "generated" / "evidence" / "T03.html").read_text(encoding="utf-8")
    assert "incident 表" in t03
    assert "HOLD_FAILED" in t03
    assert "失敗原因" in t03
    assert "CODE_CONFLICT" in t03 or "衝突" in t03
    t18b = (ROOT / "Design" / "generated" / "evidence" / "T18b.html").read_text(encoding="utf-8")
    assert "改送 OTHL" in t18b
    t02 = (ROOT / "Design" / "generated" / "evidence" / "T02.html").read_text(encoding="utf-8")
    assert "Fake MES" not in t02
    assert "Hold Code 衝突" in t02 or "CODE_衝突" in t02 or "衝突" in t02
    assert "set_default_hold.py" in t02
    t01 = (ROOT / "Design" / "generated" / "evidence" / "T01.html").read_text(encoding="utf-8")
    assert "狀態機" in t01
    assert "C01" in text
    assert "已送出" in text
    assert "HOLD_VERIFY_PENDING" in text
    assert "<br/>" in text
    assert "等掃片" in text or "未滿 2 分鐘" in text
    assert "RELEASE_SENT" in text
    assert "C10" in text
    assert "<details" in text
    stage = (ROOT / "Design" / "generated" / "evidence" / "C01.html").read_text(encoding="utf-8")
    assert "向 MES 設 Default Hold" in stage
    assert "不查 AI" in stage or "不准看 AI" in stage
    assert (ROOT / "Design" / "generated" / "evidence" / "T01.html").exists()
