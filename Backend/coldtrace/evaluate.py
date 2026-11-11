"""Event-level evaluation: did we catch the failure, how fast, and how many false alarms.

Step-level F1 hides what an operations lead cares about. Here ground truth is a contiguous run of one
Exception_Type at one location; an alert is a run of >= k identical non-NONE predictions.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

STEP_H = 0.5
TYPES = ["TEMP_EXCURSION", "COOLING_FAILURE", "SENSOR_DROPOUT"]


def _runs(labels: np.ndarray):
    """Yield (label, start, end_inclusive) for contiguous runs of non-NONE labels."""
    i, n = 0, len(labels)
    while i < n:
        if labels[i] == "NONE":
            i += 1
            continue
        j = i
        while j + 1 < n and labels[j + 1] == labels[i]:
            j += 1
        yield labels[i], i, j
        i = j + 1


@dataclass
class Alert:
    loc: str
    kind: str
    run_start: int
    fire: int  # index at which the alert is raised (run_start + k - 1)
    run_end: int


def make_alerts(pred: np.ndarray, k: int, loc: str) -> list[Alert]:
    return [Alert(loc, lab, s, s + k - 1, e) for lab, s, e in _runs(pred) if e - s + 1 >= k]


def event_metrics(df: pd.DataFrame, pred: np.ndarray, k: int = 2, tol: int = 4) -> dict:
    """df: Timestamp, Storage_Location_ID, Exception_Type (aligned with pred, any order).

    tol: steps after the true event end during which an alert still counts (thermal lag).
    """
    d = df[["Timestamp", "Storage_Location_ID", "Exception_Type"]].copy()
    d["pred"] = pred
    d = d.sort_values(["Storage_Location_ID", "Timestamp"])
    res = {t: dict(events=0, caught_type=0, caught_any=0, ttd=[]) for t in TYPES}
    alerts_total, alerts_false, days = 0, 0, 0.0
    for loc, g in d.groupby("Storage_Location_ID", sort=False):
        truth = g["Exception_Type"].to_numpy(object)
        alerts = make_alerts(g["pred"].to_numpy(object), k, loc)
        events = list(_runs(truth))
        days += len(g) * STEP_H / 24
        used = set()
        for lab, s, e in events:
            r = res[lab]
            r["events"] += 1
            hit_t = [a for a in alerts if a.kind == lab and a.run_start <= e + tol and a.run_end >= s]
            hit_any = [a for a in alerts if a.run_start <= e + tol and a.run_end >= s]
            if hit_any:
                r["caught_any"] += 1
            if hit_t:
                r["caught_type"] += 1
                first = min(hit_t, key=lambda a: a.fire)
                r["ttd"].append(max(first.fire - s, 0) * STEP_H)
                used.update(id(a) for a in hit_t)
        for a in alerts:
            alerts_total += 1
            ok = id(a) in used or any(
                lab == a.kind and a.run_start <= e + tol and a.run_end >= s for lab, s, e in events
            )
            if not ok:
                alerts_false += 1
    out = {"per_type": {}, "false_alerts_per_loc_day": alerts_false / max(days, 1e-9),
           "alerts": alerts_total, "false_alerts": alerts_false,
           "alert_precision": 1 - alerts_false / max(alerts_total, 1)}
    tot_e = tot_c = tot_a = 0
    for t, r in res.items():
        tot_e += r["events"]; tot_c += r["caught_type"]; tot_a += r["caught_any"]
        out["per_type"][t] = {
            "events": r["events"],
            "recall_type": r["caught_type"] / max(r["events"], 1),
            "recall_any": r["caught_any"] / max(r["events"], 1),
            "ttd_median_h": float(np.median(r["ttd"])) if r["ttd"] else None,
            "ttd_p90_h": float(np.percentile(r["ttd"], 90)) if r["ttd"] else None,
        }
    out["event_recall_type"] = tot_c / max(tot_e, 1)
    out["event_recall_any"] = tot_a / max(tot_e, 1)
    out["events"] = tot_e
    return out
