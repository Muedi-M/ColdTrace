"""Pub/Sub publishing and push-envelope decoding."""
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


# --- Pub/Sub ------------------------------------------------------------------------------------
class _Future:
    def add_done_callback(self, cb):
        pass


class _FakePublisher:
    def __init__(self):
        self.sent = []

    def publish(self, path, data, **attrs):
        self.sent.append((path, json.loads(data), attrs))
        return _Future()


def test_publish_disabled_without_topic(monkeypatch):
    monkeypatch.delenv("PUBSUB_TOPIC", raising=False)
    assert pubsub.publish("alert", {"a": 1}, publisher=_FakePublisher()) is False


def test_publish_with_topic(monkeypatch):
    monkeypatch.setenv("PUBSUB_TOPIC", "coldtrace-telemetry-events")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-proj")
    fake = _FakePublisher()
    assert pubsub.publish("alert", {"kind": "COOLING_FAILURE"}, "JHB-DC01", publisher=fake)
    path, body, attrs = fake.sent[0]
    assert path == "projects/demo-proj/topics/coldtrace-telemetry-events"
    assert body == {"kind": "COOLING_FAILURE"} and attrs == {"type": "alert", "location_id": "JHB-DC01"}


def test_decode_push():
    env = {"message": {"data": base64.b64encode(b'{"location_id": "JHB-DC01"}').decode(), "attributes": {"type": "reading"}}}
    assert pubsub.decode_push(env) == ({"location_id": "JHB-DC01"}, {"type": "reading"})
    with pytest.raises(ValueError):
        pubsub.decode_push({"message": {}})
