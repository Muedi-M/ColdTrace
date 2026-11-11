"""FastAPI service for Cloud Run.  uvicorn coldtrace.api:app --host 0.0.0.0 --port 8080

Env: MODEL_PATH, INGEST_API_KEY (required), NVIDIA_API_KEY | NIM_SECRET_NAME, NIM_MODEL.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import nim
from .service import LOCATIONS, Detector

app = FastAPI(title="ColdTrace", version="0.1.0")
_state: dict = {"det": None, "alerts": {}, "nim": None}


def detector() -> Detector:
    if _state["det"] is None:
        _state["det"] = Detector(os.getenv("MODEL_PATH", "artifacts/coldtrace_rf.joblib"))
    return _state["det"]


def require_key(x_api_key: str = Header(default="")):
    expected = os.getenv("INGEST_API_KEY", "")
    if not expected or not hmac.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(401, "invalid or missing X-API-Key")


class SensorEvent(BaseModel):
    location_id: str
    ts: datetime
    warehouse_temperature_c: float = Field(ge=-30, le=60)
    warehouse_humidity_percent: float = Field(ge=0, le=100)
    cooling_load_percent: float = Field(ge=0, le=100)
    sensor_connectivity: float = Field(ge=0, le=100)
    product_sensitivity: str | None = Field(default=None, max_length=16)
    estimated_freshness_percent: float | None = Field(default=None, ge=0, le=100)
    spoilage_risk: float | None = Field(default=None, ge=0, le=1)


@app.get("/healthz")
def healthz():
    return {"ok": True, "locations": LOCATIONS}


@app.post("/ingest", dependencies=[Depends(require_key)])
def ingest(e: SensorEvent):
    if e.location_id not in LOCATIONS:
        raise HTTPException(422, f"unknown location {e.location_id!r}")
    ev = {"location_id": e.location_id, "ts": e.ts.isoformat(), "T": e.warehouse_temperature_c,
          "H": e.warehouse_humidity_percent, "C": e.cooling_load_percent, "S": e.sensor_connectivity}
    for k in ("product_sensitivity", "estimated_freshness_percent", "spoilage_risk"):
        if getattr(e, k) is not None:
            ev[k] = getattr(e, k)
    det = detector().ingest(ev)
    if det.alert:
        _state["alerts"][det.alert.alert_id] = det.alert
    return {"status": det.status, "rf_label": det.rf_label, "rf_confidence": round(det.rf_confidence, 3),
            "rule_label": det.rule_label, "alert": det.alert.to_case_json() if det.alert else None}


@app.post("/alerts/{alert_id}/explain", dependencies=[Depends(require_key)])
def explain(alert_id: str):
    alert = _state["alerts"].get(alert_id)
    if alert is None:
        raise HTTPException(404, "unknown alert")
    try:
        if _state["nim"] is None:
            _state["nim"] = nim.NimClient()
        out = nim.explain(_state["nim"], os.getenv("NIM_MODEL", nim.DEFAULT_MODELS[0]), alert.to_case_json())
    except (RuntimeError, nim.NimError) as e:
        # detection result stays valid; only the narrative is unavailable
        raise HTTPException(503, f"NIM unavailable: {type(e).__name__}")
    return {"alert_id": alert_id, "evidence_sha256": alert.evidence_sha256, "explanation": out}
