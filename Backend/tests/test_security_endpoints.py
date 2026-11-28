"""Auth on case-workflow and Pub/Sub push endpoints; tamper-evidence of the case log."""
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


def test_write_endpoints_need_key():
    assert client.post("/api/ui/investigations/INV-2047/resolve").status_code == 401


def test_pubsub_push_requires_token(monkeypatch):
    monkeypatch.setenv("PUBSUB_PUSH_TOKEN", "t0k")
    env = {"message": {"data": base64.b64encode(json.dumps({
        "location_id": "JHB-DC01", "ts": "2026-11-25T10:00:00", "warehouse_temperature_c": 4.2,
        "warehouse_humidity_percent": 60, "cooling_load_percent": 55, "sensor_connectivity": 97}).encode()).decode(),
        "attributes": {"type": "reading"}}}
    assert client.post("/pubsub/push?token=wrong", json=env).status_code == 401
    r = client.post("/pubsub/push?token=t0k", json=env)
    assert r.status_code == 200 and r.json()["status"] in ("warming_up", "ok", "exception")
    env["message"]["attributes"]["type"] = "alert"
    assert client.post("/pubsub/push?token=t0k", json=env).json()["status"] == "ignored"


def test_case_log_tamper_is_detected():
    from coldtrace import api as A
    cid = "INV-2046"
    assert client.get(f"/api/cases/{cid}/events").json()["chain_valid"] is True
    ev = A._cases.cases[cid].events[0]
    original = ev.note
    try:
        ev.note = "rewritten after the fact"
        assert client.get(f"/api/cases/{cid}/events").json()["chain_valid"] is False
    finally:
        ev.note = original
