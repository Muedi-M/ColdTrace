"""Streaming detector: per-location rolling buffer -> same features as training -> rules + RF -> debounced alert.

Framework-agnostic so Cloud Run (FastAPI), Pub/Sub push handlers and tests all call the same code.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict

import pandas as pd

from . import model as M
from .features import FEATURES, build_features
from .rules import rule_predict

LOCATIONS = ("JHB-DC01", "DBN-DC02", "CPT-DC03")
BUFFER = 96  # 48 h; > 48-step baseline window so streaming features equal batch features
MIN_ROWS = 50  # baseline needs a full 24 h before the first detection is trusted


@dataclass
class Detection:
    location_id: str
    ts: str
    status: str  # warming_up | ok | exception
    rf_label: str = "NONE"
    rf_confidence: float = 1.0
    rule_label: str = "NONE"
    alert: "Alert | None" = None


@dataclass
class Alert:
    alert_id: str
    location_id: str
    kind: str
    first_seen: str
    raised_at: str
    model_sha256: str
    evidence: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    evidence_sha256: str = ""
    state: str = "OPEN"  # OPEN -> ACKNOWLEDGED -> CLOSED (human review lives in the case store)

    def seal(self) -> "Alert":
        """Hash the evidence so later handoffs (Firestore, dashboard, NIM note) are provably unchanged."""
        payload = json.dumps({"kind": self.kind, "loc": self.location_id, "rows": self.evidence}, sort_keys=True, default=str)
        self.evidence_sha256 = hashlib.sha256(payload.encode()).hexdigest()
        return self

    def to_case_json(self) -> dict:
        d = asdict(self)
        d["evidence"] = self.evidence[-12:]
        return d


class Detector:
    def __init__(self, artifact_path: str, k: int = 2, min_conf: float | None = None):
        art = M.load(artifact_path)
        self.rf = art["model"]
        self.sha = art["meta"].get("sha", "") or M.data_fingerprint(artifact_path)
        self.k = k
        self.min_conf = art["meta"].get("min_conf", 0.5) if min_conf is None else min_conf
        self.buf = {loc: deque(maxlen=BUFFER) for loc in LOCATIONS}
        self.streak = {loc: ("NONE", 0, None) for loc in LOCATIONS}  # (label, run length, first_seen)
        self.active = {loc: None for loc in LOCATIONS}  # kind of alert already raised for the current run

    def ingest(self, ev: dict) -> Detection:
        """ev keys: location_id, ts, T, H, C, S (+ optional context such as batch / freshness fields)."""
        loc = ev["location_id"]
        if loc not in self.buf:
            raise ValueError(f"unknown location {loc!r}")
        buf = self.buf[loc]
        buf.append(ev)
        if len(buf) < MIN_ROWS:
            return Detection(loc, ev["ts"], "warming_up")
        f = self._features(loc)
        row = f.iloc[[-1]]
        proba = pd.Series(self.rf.predict_proba(row[FEATURES])[0], index=self.rf.classes_)
        label = proba.idxmax()
        conf = float(proba.max())
        if label != "NONE" and conf < self.min_conf:
            label = "NONE"
        rule = str(rule_predict(row)[0])
        det = Detection(loc, ev["ts"], "ok", label, conf, rule)

        prev, n, first = self.streak[loc]
        if label == "NONE":
            self.streak[loc] = ("NONE", 0, None)
            self.active[loc] = None
            return det
        if label == prev:
            n += 1
        else:
            n, first = 1, ev["ts"]
        self.streak[loc] = (label, n, first)
        det.status = "exception"
        if n >= self.k and self.active[loc] != label:
            self.active[loc] = label
            rows = [dict(r) for r in list(buf)[-12:]]
            ctx = {k: v for k, v in ev.items() if k not in ("location_id", "ts", "T", "H", "C", "S")}
            det.alert = Alert(str(uuid.uuid4()), loc, label, first, ev["ts"], self.sha, rows, ctx).seal()
        return det

    def _features(self, loc: str) -> pd.DataFrame:
        rows = pd.DataFrame(list(self.buf[loc]))
        rows = rows.rename(columns={"location_id": "Storage_Location_ID", "ts": "Timestamp", "T": "Warehouse_Temperature_C",
                                    "H": "Warehouse_Humidity_Percent", "C": "Cooling_Load_Percent", "S": "Sensor_Connectivity"})
        rows["Timestamp"] = pd.to_datetime(rows["Timestamp"])
        rows = rows[["Timestamp", "Storage_Location_ID", "Warehouse_Temperature_C", "Warehouse_Humidity_Percent",
                     "Cooling_Load_Percent", "Sensor_Connectivity"]]
        return build_features(rows)
