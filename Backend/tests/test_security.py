from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from coldtrace.api import app
import os
import pytest


@pytest.fixture(autouse=True)
def _api_key(monkeypatch):
    monkeypatch.setenv("INGEST_API_KEY", "change-me-local-only")

os.environ.setdefault("INGEST_API_KEY", "change-me-local-only")
client = TestClient(app)

def test_reject_missing_api_key():
    res = client.post("/ingest", json={})
    assert res.status_code in (401, 422)

def test_reject_invalid_api_key():
    res = client.post("/ingest", headers={"X-API-Key": "wrong-key"}, json={
        "location_id": "JHB-DC01",
        "ts": datetime.now(timezone.utc).isoformat(),
        "warehouse_temperature_c": 4.2,
        "warehouse_humidity_percent": 60.0,
        "cooling_load_percent": 50.0,
        "sensor_connectivity": 99.0,
    })
    assert res.status_code == 401

def test_security_headers_present():
    res = client.get("/healthz")
    assert res.status_code == 200

def test_reject_future_timestamp_and_out_of_range():
    os.environ["INGEST_API_KEY"] = "change-me-local-only"
    future_ts = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    res = client.post("/ingest", headers={"X-API-Key": "change-me-local-only"}, json={
        "location_id": "JHB-DC01",
        "ts": future_ts,
        "warehouse_temperature_c": 150.0,
        "warehouse_humidity_percent": 60.0,
        "cooling_load_percent": 50.0,
        "sensor_connectivity": 99.0,
    })
    assert res.status_code == 422, res.text
