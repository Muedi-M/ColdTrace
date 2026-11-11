"""Replay labeled sample readings through the detector and print every alert it raises.

    python scripts/replay.py --local                      # in-process, no server needed
    python scripts/replay.py                              # POST to a running API (INGEST_API_KEY must match)
    python scripts/replay.py --explain                    # also ask NIM to write a note for the first alert
"""
import argparse
import os
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/sample_14d.csv")
ap.add_argument("--url", default="http://localhost:8080")
ap.add_argument("--key", default=os.getenv("INGEST_API_KEY", ""))
ap.add_argument("--model", default=os.getenv("MODEL_PATH", "artifacts/coldtrace_rf.joblib"))
ap.add_argument("--local", action="store_true", help="skip HTTP and call the detector directly")
ap.add_argument("--explain", action="store_true", help="ask NIM for an incident note on the first alert")
a = ap.parse_args()

df = pd.read_csv(a.data, keep_default_na=False, parse_dates=["Timestamp"]).sort_values("Timestamp").reset_index(drop=True)
truth_events = Counter()
prev = {}
for r in df.itertuples():
    p = prev.get(r.Storage_Location_ID, "NONE")
    if r.Exception_Type != "NONE" and r.Exception_Type != p:
        truth_events[r.Exception_Type] += 1
    prev[r.Storage_Location_ID] = r.Exception_Type

if a.local:
    from coldtrace.service import Detector
    det = Detector(a.model)
else:
    import requests
    s = requests.Session()
    s.headers["X-API-Key"] = a.key
    if not a.key:
        sys.exit("Set INGEST_API_KEY (same value the server was started with) or pass --key")

raised, first_alert_id = Counter(), None
for r in df.itertuples():
    body = {"location_id": r.Storage_Location_ID, "ts": r.Timestamp.isoformat(),
            "warehouse_temperature_c": r.Warehouse_Temperature_C, "warehouse_humidity_percent": r.Warehouse_Humidity_Percent,
            "cooling_load_percent": r.Cooling_Load_Percent, "sensor_connectivity": r.Sensor_Connectivity}
    if a.local:
        d = det.ingest({"location_id": body["location_id"], "ts": body["ts"], "T": body["warehouse_temperature_c"],
                        "H": body["warehouse_humidity_percent"], "C": body["cooling_load_percent"], "S": body["sensor_connectivity"]})
        alert = d.alert and {"alert_id": d.alert.alert_id, "kind": d.alert.kind, "evidence_sha256": d.alert.evidence_sha256}
    else:
        resp = s.post(f"{a.url}/ingest", json=body, timeout=30)
        if resp.status_code != 200:
            sys.exit(f"HTTP {resp.status_code}: {resp.text[:200]}")
        alert = resp.json()["alert"]
    if alert:
        raised[alert["kind"]] += 1
        first_alert_id = first_alert_id or alert["alert_id"]
        print(f"{r.Timestamp:%m-%d %H:%M}  {r.Storage_Location_ID}  ALERT {alert['kind']:16} truth={r.Exception_Type:16} sha256={alert['evidence_sha256'][:10]}")

print(f"\nreadings sent: {len(df)}   alerts raised: {dict(raised)}   true events in this file: {dict(truth_events)}")
if a.explain:
    if a.local or not first_alert_id:
        print("--explain needs the running API and at least one alert")
    else:
        e = s.post(f"{a.url}/alerts/{first_alert_id}/explain", timeout=90)
        print(e.status_code, e.text[:1500])
