"""Data validation, quarantine, reference integrity and versioned thresholds (data lane)."""
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


# --- thresholds ---------------------------------------------------------------------------------
def test_thresholds_versioned_and_hashed():
    cfg = TH.load()
    assert cfg["version"] and len(cfg["sha256"]) == 64
    assert cfg["history"][-1]["version"] == cfg["version"]


@pytest.mark.parametrize("temp,cat,out", [
    (11.2, "Pharmaceuticals", True), (1.2, "Pharmaceuticals", True), (5.0, "Biologics", False),
    (8.0, "Vaccines", False), (2.5, "Seafood", True), (1.5, "Seafood", False),
])
def test_category_bands(temp, cat, out):
    assert TH.is_out_of_band(temp, cat) is out


def test_band_labels():
    assert TH.band_label("Insulin pens") == "2°C–8°C"
    assert TH.band_label("Bakery") == "≤ 2°C"


# --- readings validation ------------------------------------------------------------------------
def test_clean_data_passes():
    clean, q, rep = V.validate_readings(_readings())
    assert len(clean) == 10 and len(q) == 0
    assert rep["locations"]["JHB-DC01"]["completeness_pct"] == 100.0


def test_quarantine_reasons_and_gaps():
    df = _readings(12)
    df = df.drop(index=[5, 6])  # two missing readings
    bad = pd.DataFrame([
        {**df.iloc[0].to_dict()},                                      # exact duplicate
        {**df.iloc[1].to_dict(), "Warehouse_Temperature_C": 9.9},      # conflicting duplicate
        {**df.iloc[2].to_dict(), "Timestamp": "not-a-date"},
        {**df.iloc[3].to_dict(), "Storage_Location_ID": "PTA-DC09"},
        {**df.iloc[4].to_dict(), "Sensor_Connectivity": 140.0},
        {**df.iloc[4].to_dict(), "Timestamp": "2026-11-09 00:00:00", "Cooling_Load_Percent": None},
    ])
    clean, q, rep = V.validate_readings(pd.concat([df, bad], ignore_index=True))
    reasons = rep["quarantine_by_reason"]
    assert reasons["duplicate_reading"] == 1
    assert reasons["conflicting_duplicate"] == 2  # both rows of the conflicting pair are held back
    assert reasons["unparseable_timestamp"] == 1
    assert reasons["unknown_location"] == 1
    assert reasons["physically_impossible_value"] == 1
    assert reasons["missing_sensor_value"] == 1
    # 2 dropped readings + the slot whose conflicting pair was quarantined
    assert rep["locations"]["JHB-DC01"]["missing_readings"] == 3
    assert rep["rows_in"] == rep["rows_clean"] + rep["rows_quarantined"]


def test_flat_run_reported_not_quarantined():
    df = _readings(8, temps=[4.0, 4.1, 4.2, 4.2, 4.2, 4.2, 4.3, 4.4])
    clean, q, rep = V.validate_readings(df)
    assert len(q) == 0 and rep["locations"]["JHB-DC01"]["flat_runs_ge_3"] == 1


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        V.validate_readings(_readings().drop(columns=["Sensor_Connectivity"]))


def test_reference_files_are_consistent():
    rep = V.validate_references(*V.load_reference(ROOT / "data" / "reference"))
    assert rep["ok"], rep["problems"]


def test_reference_problems_detected():
    locs, batches, ships = V.load_reference(ROOT / "data" / "reference")
    batches = batches.copy()
    batches.loc[0, "investigation_id"] = None             # out-of-band pharma batch with no case
    ships = ships.copy()
    ships.loc[len(ships)] = ["SH-9999", "ZZ-000", "Nowhere", "Scheduled", "2026-12-01 08:00"]
    kinds = {p["type"] for p in V.validate_references(locs, batches, ships)["problems"]}
    assert {"out_of_band_batch_without_investigation", "shipment_unknown_batch"} <= kinds


