"""API surface for the case log, insights, thresholds, validation and Pub/Sub push."""
import base64
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # MODEL_PATH default is relative to Backend/

from fastapi.testclient import TestClient  # noqa: E402

from coldtrace.api import app  # noqa: E402

client = TestClient(app)
KEY = {"X-API-Key": os.environ["INGEST_API_KEY"]}


def test_healthz_reports_storage_and_thresholds():
    d = client.get("/healthz").json()
    assert d["ok"] and d["thresholds_version"]
    assert set(d["storage"]) >= {"firestore", "bigquery", "pubsub_topic"}


def test_thresholds_endpoint():
    d = client.get("/api/thresholds").json()
    assert d["bands"]["pharma"]["min_c"] == 2.0 and len(d["sha256"]) == 64


def test_insights_shape():
    d = client.get("/api/insights?days=30").json()
    for k in ("exception_frequency_by_location", "detection_to_review", "cycle_time", "throughput_per_week",
              "unresolved", "overdue", "burndown"):
        assert k in d
    assert d["live_cases"] >= 3


def test_ui_state_is_consistent():
    d = client.get("/api/ui/state").json()
    for b in d["batches"]:
        if b["status"] == "Out of range":
            assert b["held"] is True
    for u in d["units"]:
        worst = [b for b in d["batches"] if b["locationId"] == u["locationId"] and b["status"] == "Out of range"]
        if worst:
            match = [b for b in worst if b["code"] == u["warmestBatch"]]
            assert match and u["temp"] == match[0]["temp"]


def test_assign_and_resolve_write_case_events():
    r = client.post("/api/ui/investigations/INV-2048/assign", headers=KEY,
                    json={"assignee": "Naledi Mokoena", "note": "check door seal"})
    assert r.status_code == 200
    ev = client.get("/api/cases/INV-2048/events").json()
    assert ev["case"]["state"] == "In progress" and ev["case"]["assignee"] == "Naledi Mokoena"
    assert ev["chain_valid"] is True
    assert client.post("/api/ui/investigations/INV-2048/resolve", headers=KEY).status_code == 200
    ev = client.get("/api/cases/INV-2048/events").json()
    assert ev["case"]["state"] == "Closed" and ev["case"]["completed_at"]
    # closed cases cannot be re-assigned
    assert client.post("/api/ui/investigations/INV-2048/assign", headers=KEY, json={"assignee": "x"}).status_code == 409


def test_validation_endpoint_reference_ok():
    d = client.get("/api/validation").json()
    assert d["reference_integrity"]["ok"] is True
