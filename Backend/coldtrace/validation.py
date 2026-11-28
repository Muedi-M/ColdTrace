"""Telemetry and reference-data validation (data-validation lane).

`validate_readings` splits sensor readings into clean rows and a quarantine table, each
quarantined row carrying the reason it was held back. It also reports cadence gaps (missing
30-minute readings) and flat runs (frozen sensor values) per location; those are reported, not
quarantined, because a flat run is itself the SENSOR_DROPOUT signal the detector needs.

`validate_references` checks that sensor locations, batches and shipments tell one story:
every batch sits in a known location, every shipment points at a known batch, and every
out-of-band batch is linked to an investigation.

Run over a file:  python -m coldtrace.validation data/sample_14d.csv --out artifacts/validation_report.json
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import thresholds as TH

LOC = "Storage_Location_ID"
TS = "Timestamp"
KNOWN_LOCATIONS = ("JHB-DC01", "DBN-DC02", "CPT-DC03")
SENSOR_COLS = ["Warehouse_Temperature_C", "Warehouse_Humidity_Percent", "Cooling_Load_Percent", "Sensor_Connectivity"]
REQUIRED = [TS, LOC, *SENSOR_COLS]


def _quarantine(df: pd.DataFrame, mask: pd.Series, reason: str, held: list[pd.DataFrame]) -> pd.DataFrame:
    if mask.any():
        q = df.loc[mask].copy()
        q["quarantine_reason"] = reason
        held.append(q)
    return df.loc[~mask]


def validate_readings(df: pd.DataFrame, cfg: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Return (clean, quarantine, report). Never mutates the input."""
    cfg = cfg or TH.load()
    vcfg = cfg["validation"]
    missing_cols = [c for c in REQUIRED if c not in df.columns]
    if missing_cols:
        raise ValueError(f"missing required columns: {missing_cols}")

    n_in = len(df)
    d = df.copy()
    d[TS] = pd.to_datetime(d[TS], errors="coerce")
    for c in SENSOR_COLS:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    held: list[pd.DataFrame] = []

    d = _quarantine(d, d[TS].isna(), "unparseable_timestamp", held)
    d = _quarantine(d, ~d[LOC].isin(KNOWN_LOCATIONS), "unknown_location", held)
    d = _quarantine(d, d[SENSOR_COLS].isna().any(axis=1), "missing_sensor_value", held)
    out_of_range = pd.Series(False, index=d.index)
    for col, (lo, hi) in vcfg["ranges"].items():
        out_of_range |= (d[col] < lo) | (d[col] > hi)
    d = _quarantine(d, out_of_range, "physically_impossible_value", held)

    # duplicates: identical rows are dropped silently (keep first); same key with different values is a conflict
    key = [LOC, TS]
    exact_dup = d.duplicated(subset=key + SENSOR_COLS, keep="first")
    d = _quarantine(d, exact_dup, "duplicate_reading", held)
    conflict = d.duplicated(subset=key, keep=False)
    d = _quarantine(d, conflict, "conflicting_duplicate", held)

    d = d.sort_values(key).reset_index(drop=True)
    cadence = pd.Timedelta(minutes=int(vcfg["cadence_minutes"]))
    eps = float(vcfg["flat_eps_c"])
    flat_flag = int(vcfg["flat_run_flag_steps"])

    per_loc = {}
    for loc, g in d.groupby(LOC):
        ts = g[TS]
        gaps = ts.diff().dropna()
        missing_steps = int(((gaps / cadence).round() - 1).clip(lower=0).sum())
        expected = int(((ts.max() - ts.min()) / cadence)) + 1 if len(ts) else 0
        same = g["Warehouse_Temperature_C"].diff().abs().le(eps)
        run_id = (~same).cumsum()
        run_len = same.groupby(run_id).cumsum()
        flat_runs = int(((run_len == flat_flag)).sum())
        per_loc[loc] = {
            "rows": int(len(g)),
            "first": ts.min().isoformat() if len(ts) else None,
            "last": ts.max().isoformat() if len(ts) else None,
            "expected_rows": expected,
            "missing_readings": missing_steps,
            "completeness_pct": round(100 * len(g) / expected, 2) if expected else None,
            "max_gap_minutes": int(gaps.max().total_seconds() // 60) if len(gaps) else 0,
            "flat_runs_ge_%d" % flat_flag: flat_runs,
        }
        if "Exception_Type" in g.columns:
            per_loc[loc]["labelled_exception_rows"] = {
                k: int(v) for k, v in g["Exception_Type"].value_counts().items() if k != "NONE"
            }

    quarantine = pd.concat(held, ignore_index=True) if held else pd.DataFrame(columns=[*df.columns, "quarantine_reason"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds_version": cfg["version"],
        "thresholds_sha256": cfg["sha256"],
        "rows_in": int(n_in),
        "rows_clean": int(len(d)),
        "rows_quarantined": int(len(quarantine)),
        "quarantine_by_reason": {k: int(v) for k, v in quarantine["quarantine_reason"].value_counts().items()} if len(quarantine) else {},
        "locations": per_loc,
    }
    return d, quarantine, report


def validate_references(locations: pd.DataFrame, batches: pd.DataFrame, shipments: pd.DataFrame,
                        cfg: dict | None = None) -> dict:
    """Referential integrity across locations → batches → shipments, plus band/investigation consistency."""
    cfg = cfg or TH.load()
    problems: list[dict] = []
    loc_ids = set(locations["location_id"])
    batch_ids = set(batches["batch_code"])

    for col, frame, ref, name in (("location_id", batches, loc_ids, "batch_unknown_location"),
                                  ("batch_code", shipments, batch_ids, "shipment_unknown_batch")):
        for _, r in frame[~frame[col].isin(ref)].iterrows():
            problems.append({"type": name, "id": r.iloc[0], "value": r[col]})
    for _, r in batches[batches["batch_code"].duplicated(keep=False)].iterrows():
        problems.append({"type": "duplicate_batch_code", "id": r["batch_code"]})
    for _, r in shipments[shipments["shipment_id"].duplicated(keep=False)].iterrows():
        problems.append({"type": "duplicate_shipment_id", "id": r["shipment_id"]})

    joined = batches.merge(shipments, on="batch_code", how="left").merge(locations, on="location_id", how="left")
    for _, r in joined.iterrows():
        out = TH.is_out_of_band(r["last_temp_c"], r["category"], cfg)
        inv_id = r.get("investigation_id")
        if out and (pd.isna(inv_id) or not str(inv_id).strip()):
            problems.append({"type": "out_of_band_batch_without_investigation", "id": r["batch_code"]})
        if out and str(r.get("shipment_status", "")).lower() not in ("held", "on hold"):
            problems.append({"type": "out_of_band_batch_shipment_not_held", "id": r["batch_code"],
                             "shipment": r.get("shipment_id")})
    return {
        "thresholds_version": cfg["version"],
        "locations": len(locations), "batches": len(batches), "shipments": len(shipments),
        "ok": not problems, "problems": problems,
    }


def load_reference(dirpath: str | Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    p = Path(dirpath)
    return (pd.read_csv(p / "locations.csv"), pd.read_csv(p / "batches.csv"), pd.read_csv(p / "shipments.csv"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate ColdTrace telemetry and reference data")
    ap.add_argument("data", help="telemetry CSV (Timestamp, Storage_Location_ID, Warehouse_* columns)")
    ap.add_argument("--reference", default=str(Path(__file__).resolve().parent.parent / "data" / "reference"))
    ap.add_argument("--out", default="artifacts/validation_report.json")
    ap.add_argument("--quarantine-out", default=None, help="optional CSV path for quarantined rows")
    a = ap.parse_args(argv)

    df = pd.read_csv(a.data, keep_default_na=False, na_values=[""])
    _, q, report = validate_readings(df)
    if Path(a.reference).exists():
        report["reference_integrity"] = validate_references(*load_reference(a.reference))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(report, indent=2))
    if a.quarantine_out and len(q):
        q.to_csv(a.quarantine_out, index=False)
    print(json.dumps({k: report[k] for k in ("rows_in", "rows_clean", "rows_quarantined", "quarantine_by_reason")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
