"""Case event log, audit chain and Insights MVP metrics."""
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from coldtrace import cases as CS, pubsub, thresholds as TH, validation as V

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _readings(n=10, loc="JHB-DC01", start="2026-11-01 00:00", temps=None):
    ts = pd.date_range(start, periods=n, freq="30min")
    temps = temps or [4.0 + 0.1 * i for i in range(n)]
    return pd.DataFrame({"Timestamp": ts.astype(str), "Storage_Location_ID": loc,
                         "Warehouse_Temperature_C": temps, "Warehouse_Humidity_Percent": 60.0,
                         "Cooling_Load_Percent": 55.0, "Sensor_Connectivity": 95.0})


# --- case log -----------------------------------------------------------------------------------
def _store():
    s = CS.CaseStore(events_path="")
    s.create("C1", "JHB-DC01", "COOLING_FAILURE", "High", detected_at=NOW - timedelta(hours=10), created_at=NOW - timedelta(hours=10))
    s.transition("C1", "In progress", "lead", ts=NOW - timedelta(hours=9), assignee="Naledi")
    s.transition("C1", "Under review", "qa", ts=NOW - timedelta(hours=6))
    s.transition("C1", "Closed", "qa", ts=NOW - timedelta(hours=4))
    s.create("C2", "DBN-DC02", "TEMP_EXCURSION", "High", detected_at=NOW - timedelta(hours=30), created_at=NOW - timedelta(hours=30))
    s.create("C3", "DBN-DC02", "SENSOR_DROPOUT", "Medium", detected_at=NOW - timedelta(hours=3), created_at=NOW - timedelta(hours=2))
    s.transition("C3", "In progress", "lead", ts=NOW - timedelta(hours=1), assignee="Sipho")
    return s


def test_case_timestamps_and_events():
    s = _store()
    c1 = s.cases["C1"]
    assert c1.started_at and c1.reviewed_at and c1.completed_at
    assert [e.event for e in c1.events] == ["created", "assigned", "status_changed", "closed"]
    assert c1.review_due_at < c1.close_due_at
    assert s.verify_chain("C1")


def test_tamper_breaks_chain():
    s = _store()
    s.cases["C1"].events[1].note = "edited later"
    assert not s.verify_chain("C1")


def test_closed_case_cannot_reopen():
    s = _store()
    with pytest.raises(ValueError):
        s.transition("C1", "In progress", "lead")


def test_insights_metrics():
    d = CS.insights(_store().all(), now=NOW, window_days=7)
    assert d["exception_frequency_by_location"]["DBN-DC02"]["total"] == 2
    assert d["cycle_time"] == {"n": 1, "avg_h": 6.0, "median_h": 6.0, "p90_h": 6.0}
    assert d["detection_to_review"]["n"] == 2  # C1 (1 h) and C3 (2 h)
    assert d["detection_to_review"]["median_h"] == 1.5
    assert d["unresolved"] == 2
    overdue = {o["case_id"]: o["reasons"] for o in d["overdue"]}
    assert overdue["C2"] == ["review_overdue", "close_overdue"]  # 30 h old, never picked up
    assert "C3" not in overdue
    assert d["burndown"][-1]["open"] == 2


def test_backfill_from_labels_is_seeded_and_marked_synthetic():
    rows = {"JHB-DC01": [{"ts": f"2026-10-{d:02d} 0{h}:00:00", "label": lab}
                         for d in range(1, 29) for h, lab in enumerate(["NONE", "COOLING_FAILURE", "COOLING_FAILURE", "NONE"])]}
    s1, s2 = CS.CaseStore(events_path=""), CS.CaseStore(events_path="")
    n1 = CS.backfill_from_labels(s1, rows, days=60, seed=3, now=NOW)
    n2 = CS.backfill_from_labels(s2, rows, days=60, seed=3, now=NOW)
    assert n1 == n2 == 28
    assert all(c.synthetic for c in s1.all())
    assert [c.state for c in s1.all()] == [c.state for c in s2.all()]


