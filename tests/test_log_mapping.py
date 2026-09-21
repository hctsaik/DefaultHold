from __future__ import annotations

import logging

from vai_hold.application.logevents import Event

from harness import make_harness
from test_t01_t18 import _happy_until_hold


def test_set_eval_printed_after_hold_receipt(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    h.world.add_lot("LOT1")
    h.set_hold()
    from vai_hold.investigate import parse_records

    recs = [
        r
        for r in parse_records(caplog.text)
        if r.get("function_code") == "SET_DEFAULT_HOLD_BY_Operation_Start"
        and r.get("event") in {"hold.sent", "hold.receipt", "eval.cycle"}
    ]
    events = [r["event"] for r in recs]
    assert "hold.sent" in events
    assert "hold.receipt" in events
    assert "eval.cycle" in events
    assert events[::-1].index("eval.cycle") < events[::-1].index("hold.receipt")
    ev = next(r for r in reversed(recs) if r["event"] == "eval.cycle")
    holds = ((ev.get("observed") or {}).get("DefaultHold") or {}).get("Holds") or []
    assert any(row.get("HoldCode") == "ENHL" for row in holds)
    assert ev.get("observation_phase") == "after_write"
    before = next(r for r in recs if r["event"] == "eval.cycle" and r.get("observation_phase") == "before_action")
    before_holds = ((before.get("observed") or {}).get("DefaultHold") or {}).get("Holds") or []
    assert not any(row.get("HoldCode") == "ENHL" for row in before_holds)
    receipt = next(r for r in recs if r["event"] == "hold.receipt")
    assert receipt.get("attempt_id")
    assert receipt.get("attempt_no") == 1


def test_happy_path_emits_mappable_events(caplog):
    caplog.set_level(logging.INFO, logger="vai_hold")
    h = make_harness()
    _happy_until_hold(h)
    h.world.complete_ai("LOT1")
    h.settle()
    h.check_ai()
    h.confirm_release()
    text = caplog.text
    for event in (
        Event.PIPELINE_START,
        Event.ORDER_CREATED,
        Event.HOLD_INTENT,
        Event.HOLD_SENT,
        Event.HOLD_RECEIPT,
        Event.HOLD_CONFIRMED,
        Event.RELEASE_INTENT,
        Event.RELEASE_SENT,
        Event.RELEASE_RECEIPT,
        Event.RELEASE_CONFIRMED,
        Event.PIPELINE_END,
    ):
        assert event in text, event
    assert "SET_DEFAULT_HOLD_BY_Operation_Start" in text
    assert '"lot_id": "LOT1"' in text
    assert "A1-03" in text or "A2-02" in text
    assert '"facts"' in text
    assert '"hold_query"' in text
    assert '"own_hold_count"' in text
