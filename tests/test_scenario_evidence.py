from __future__ import annotations

from pathlib import Path

from vai_hold.investigate import parse_records
from vai_hold.tools.scenario_evidence import write_all

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "Design" / "generated" / "evidence"


def test_write_e2e_evidence_pack():
    write_all()
    index = EVIDENCE / "INDEX.md"
    assert index.exists()
    text = index.read_text(encoding="utf-8")
    for name in (
        "hold_retry_transient",
        "hold_retry_timeout",
        "hold_unknown_no_resend",
        "release_retry_transient",
        "release_retry_timeout",
        "transfer_memo_accumulate",
        "transfer_retry_transient",
        "t01_happy",
        "t14_defect_handoff",
    ):
        assert name in text
        md = EVIDENCE / f"{name}.md"
        log = EVIDENCE / f"{name}.log"
        assert md.exists(), name
        assert log.exists(), name
        body = md.read_text(encoding="utf-8")
        assert "OBSERVED" in body or "Action 時間序" in body
        recs = parse_records(log.read_text(encoding="utf-8"))
        assert recs, name


def test_evidence_hold_release_transfer_retry_counts():
    write_all()

    def events(name: str, ev: str) -> list[dict]:
        recs = parse_records((EVIDENCE / f"{name}.log").read_text(encoding="utf-8"))
        return [r for r in recs if r.get("event") == ev]

    hold_sent = events("hold_retry_transient", "hold.sent")
    assert len(hold_sent) == 3
    recs = events("hold_retry_transient", "hold.receipt")
    assert [r.get("attempt_no") for r in recs] == [1, 2, 3]

    assert len(events("hold_unknown_no_resend", "hold.sent")) == 1

    rel = events("release_retry_transient", "release.sent")
    assert len(rel) == 3
    rel_r = events("release_retry_transient", "release.receipt")
    assert [r.get("attempt_no") for r in rel_r] == [1, 2, 3]

    tr = events("transfer_retry_transient", "transfer.sent")
    assert len(tr) == 0

    acc = (EVIDENCE / "transfer_memo_accumulate.md").read_text(encoding="utf-8")
    assert "transfer.sent" not in acc
    assert "Please check #1,#2" not in acc
