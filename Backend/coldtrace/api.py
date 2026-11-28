from __future__ import annotations
from coldtrace.storage import storage_status
from fastapi.staticfiles import StaticFiles
"""FastAPI service for Cloud Run.  uvicorn coldtrace.api:app --host 0.0.0.0 --port 8080

Env: MODEL_PATH, INGEST_API_KEY (required), NVIDIA_API_KEY | NIM_SECRET_NAME, NIM_MODEL.
"""

import hmac
import hashlib
import json
import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from . import cases as CS, nim, pubsub, storage
from . import thresholds as TH
from .service import LOCATIONS, Detector

from pathlib import Path
app = FastAPI(title="ColdTrace", version="0.1.0")

from coldtrace.security import SecurityHardeningMiddleware, verify_model_artifacts
app.add_middleware(SecurityHardeningMiddleware)
verify_model_artifacts(Path(__file__).resolve().parent.parent / "artifacts")

_state: dict = {"det": None, "alerts": {}, "nim": None}


def detector() -> Detector:
    if _state["det"] is None:
        _state["det"] = Detector(os.getenv("MODEL_PATH", "artifacts/coldtrace_rf.joblib"))
    return _state["det"]


def _valid_hashed_key(raw_key: str) -> bool:
    raw_json = os.getenv("API_KEY_HASHES_JSON", "").strip()
    if not raw_json or not raw_key:
        return False
    try:
        entries = json.loads(raw_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(entries, dict):
        return False
    candidate_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest().lower()
    return any(
        hmac.compare_digest(candidate_hash, str(stored_hash).strip().lower())
        for stored_hash in entries.keys()
    )


def require_key(x_api_key: str = Header(default="")):
    if _valid_hashed_key(x_api_key):
        return
    expected = os.getenv("INGEST_API_KEY", "")
    if expected and hmac.compare_digest(x_api_key.encode(), expected.encode()):
        return
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


@app.get("/health")
@app.get("/healthz")
def healthz():
    """/health is the public alias: Cloud Run's front end reserves /healthz and returns 404 for it."""
    cfg = TH.load()
    return {"ok": True, "locations": LOCATIONS, "thresholds_version": cfg["version"],
            "storage": {**storage_status(),
                        "pubsub_publishing": bool(pubsub.topic_path()),
                        "case_events_path": os.getenv("CASE_EVENTS_PATH") or None}}


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
        _register_alert(det.alert)
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

# --- Operations Console UI & Dashboard Endpoints ---
from pathlib import Path
import csv
from fastapi.responses import FileResponse, HTMLResponse

_latest_readings: dict[str, dict] = {}
_reading_counts: dict[str, int] = {"JHB-DC01": 0, "DBN-DC02": 0, "CPT-DC03": 0}

app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend"), name="static")

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = Path(__file__).resolve().parent.parent / "frontend" / "index.html"
    return html_path.read_text(encoding="utf-8") if html_path.exists() else "<h1>ColdTrace API</h1>"

@app.get("/api/locations")
def list_locations():
    cities = {"JHB-DC01": "Johannesburg", "DBN-DC02": "Durban", "CPT-DC03": "Cape Town"}
    out = []
    for loc_id, city in cities.items():
        loc_alerts = [a for a in _state["alerts"].values() if a.location_id == loc_id and getattr(a, "state", "OPEN") != "CLOSED"]
        latest = _latest_readings.get(loc_id)
        status = "exception" if loc_alerts else ("warming_up" if _reading_counts.get(loc_id, 0) < 50 else "ok")
        out.append({"id": loc_id, "city": city, "status": status, "open_alerts": len(loc_alerts), "latest": latest})
    return {"locations": out}

@app.get("/api/alerts")
def list_alerts():
    items = []
    for a in _state["alerts"].values():
        d = a.to_case_json()
        d.setdefault("state", getattr(a, "state", "OPEN"))
        items.append(d)
    return {"alerts": list(reversed(items))}

@app.post("/api/alerts/{alert_id}/ack", dependencies=[Depends(require_key)])
def ack_alert(alert_id: str):
    alert = _state["alerts"].get(alert_id)
    if not alert:
        raise HTTPException(404, "unknown alert")
    alert.state = "ACKNOWLEDGED"
    return {"status": "acknowledged", "alert_id": alert_id}

@app.post("/api/alerts/{alert_id}/close", dependencies=[Depends(require_key)])
def close_alert(alert_id: str):
    alert = _state["alerts"].get(alert_id)
    if not alert:
        raise HTTPException(404, "unknown alert")
    alert.state = "CLOSED"
    return {"status": "closed", "alert_id": alert_id}

def require_demo_replay_auth(request: Request, x_api_key: str = Header(default="")) -> None:
    """Allow valid X-API-Key or same-origin browser console requests on /api/demo/replay."""
    try:
        require_key(x_api_key=x_api_key)
        return
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    host = (request.url.hostname or "").lower()
    origin = (request.headers.get("origin") or "").lower()
    referer = (request.headers.get("referer") or "").lower()
    if host and (
        f"://{host}" in origin
        or f"://{host}" in referer
        or (host in {"localhost", "127.0.0.1"} and not origin and not referer)
    ):
        return
    raise HTTPException(401, "invalid or missing X-API-Key")


_ai_calls: dict = {"per_case": {}, "window": []}
AI_PER_CASE_SECONDS = int(os.getenv("AI_PER_CASE_SECONDS", "30"))
AI_PUBLIC_PER_HOUR = int(os.getenv("AI_PUBLIC_PER_HOUR", "60"))


def require_demo_ai_auth(inv_id: str, request: Request, x_api_key: str = Header(default="")) -> None:
    """Ask AI from the console: a valid X-API-Key, or a same-origin browser request under a rate limit.

    Ask AI only writes a triage note (human review required) and never changes case state,
    so the console may call it without the operator key, as it does for Replay. Assign,
    resolve, inject and ingest still require the key.
    """
    try:
        require_key(x_api_key=x_api_key)
        return
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
    require_demo_replay_auth(request, x_api_key="")  # same-origin check; raises 401 otherwise
    now = datetime.now(timezone.utc).timestamp()
    last = _ai_calls["per_case"].get(inv_id, 0.0)
    if now - last < AI_PER_CASE_SECONDS:
        raise HTTPException(429, f"Ask AI was just run for {inv_id}; try again in {int(AI_PER_CASE_SECONDS - (now - last)) + 1}s")
    _ai_calls["window"] = [t for t in _ai_calls["window"] if now - t < 3600]
    if len(_ai_calls["window"]) >= AI_PUBLIC_PER_HOUR:
        raise HTTPException(429, "Ask AI hourly limit reached for the public console; use an operator key")
    _ai_calls["per_case"][inv_id] = now
    _ai_calls["window"].append(now)


# --- Cold Chain Alerts Video UI Endpoints (Backed by cold_chain_labeled_2022_2026.csv) ---
import csv
from pathlib import Path

def _resolve_dataset_path() -> Path | None:
    base = Path(__file__).resolve().parent.parent / "data"
    for name in ("cold_chain_labeled_2022_2026.csv", "cold_chain_labeled_2022_2026.csv"):
        p = base / name
        if p.exists():
            return p
    return None

def _load_csv_telemetry() -> dict[str, list[dict]]:
    path = _resolve_dataset_path()
    grouped: dict[str, list[dict]] = {"JHB-DC01": [], "DBN-DC02": [], "CPT-DC03": []}
    if not path:
        return grouped
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            loc = row.get("Storage_Location_ID") or row.get("location_id")
            if loc not in grouped:
                continue
            grouped[loc].append({
                "ts": row.get("Timestamp") or row.get("ts"),
                "T": float(row.get("Warehouse_Temperature_C") or row.get("warehouse_temperature_c") or 0.0),
                "H": float(row.get("Warehouse_Humidity_Percent") or row.get("warehouse_humidity_percent") or 0.0),
                "C": float(row.get("Cooling_Load_Percent") or row.get("cooling_load_percent") or 0.0),
                "S": float(row.get("Sensor_Connectivity") or row.get("sensor_connectivity") or 0.0),
                "label": row.get("Exception_Type") or row.get("exception_type") or "NONE",
            })
    return grouped

import time

_csv_cache: dict[str, list[dict]] | None = None

def _get_csv_cache() -> dict[str, list[dict]]:
    global _csv_cache
    if _csv_cache is None:
        _csv_cache = _load_csv_telemetry()
    return _csv_cache

def _tail_series(loc: str, n: int = 14) -> list[float]:
    rows = _get_csv_cache().get(loc, [])
    if not rows:
        return [1.2, 1.4, 1.3, 1.6, 2.1, 4.5, 6.1]
    # Sample 14 points across the last 7 days (336 x 30-min intervals)
    window = rows[-336:] if len(rows) >= 336 else rows
    step = max(1, len(window) // n)
    return [round(window[i]["T"], 1) for i in range(0, len(window), step)][:n]

_ui_store = {
    "datasetFile": _resolve_dataset_path().name if _resolve_dataset_path() else "mock",
    "units": [
        {"locationId": "JHB-DC01", "shortCode": "U12", "unitName": "Unit 12 (JHB-DC01)", "siteName": "Johannesburg DC • Waterfall", "temp": 11.2, "flaggedCount": 1, "invCode": "INV-2048", "warmestBatch": "7F-442", "series": _tail_series("JHB-DC01")},
        {"locationId": "DBN-DC02", "shortCode": "U14", "unitName": "Unit 14 (DBN-DC02)", "siteName": "Durban DC • Durban North", "temp": 9.8, "flaggedCount": 1, "invCode": "INV-2047", "warmestBatch": "8A-118", "series": _tail_series("DBN-DC02")},
        {"locationId": "CPT-DC03", "shortCode": "U22", "unitName": "Unit 22 (CPT-DC03)", "siteName": "Cape Town DC • Cape Town Harbour", "temp": 1.2, "flaggedCount": 1, "invCode": "INV-2046", "warmestBatch": "9C-301", "series": _tail_series("CPT-DC03")},
    ],
    "batches": [
        {"code": "7F-442", "category": "Pharmaceuticals", "product": "Insulin pens", "locationSite": "Johannesburg DC (JHB-DC01)", "unitName": "Unit 12", "locationId": "JHB-DC01", "units": 4, "arrived": "2026-10-28 00:30", "temp": 11.2, "peak": 11.2, "aboveHours": 18, "sensorId": "JHB-S2", "shipmentId": "SH-7713", "destination": "Waterfall Corner locker", "invId": "INV-2048", "invStatus": "Open", "handoffs": 4, "status": "Out of range", "stageIndex": 2, "series": _tail_series("JHB-DC01")},
        {"code": "8A-118", "category": "Biologics", "product": "Flu vaccine vials", "locationSite": "Durban DC (DBN-DC02)", "unitName": "Unit 14", "locationId": "DBN-DC02", "units": 5, "arrived": "2026-10-27 12:30", "temp": 9.8, "peak": 9.8, "aboveHours": 14, "sensorId": "DBN-S1", "shipmentId": "SH-7712", "destination": "Durban North depot", "invId": "INV-2047", "invStatus": "In progress", "handoffs": 3, "status": "Out of range", "stageIndex": 2, "series": _tail_series("DBN-DC02")},
        {"code": "9C-301", "category": "Pharmaceuticals", "product": "Eye drops", "locationSite": "Cape Town DC (CPT-DC03)", "unitName": "Unit 22", "locationId": "CPT-DC03", "units": 3, "arrived": "2026-10-26 17:30", "temp": 1.2, "peak": 1.2, "aboveHours": 12, "sensorId": "CPT-S2", "shipmentId": "SH-7769", "destination": "Cape Town Harbour pick-up", "invId": "INV-2046", "invStatus": "Under review", "handoffs": 5, "status": "Out of range", "stageIndex": 3, "series": _tail_series("CPT-DC03")},
        {"code": "7F-451", "category": "Seafood", "product": "Hake fillets", "locationSite": "Johannesburg DC (JHB-DC01)", "unitName": "Unit 12", "locationId": "JHB-DC01", "units": 9, "arrived": "2026-10-26 20:30", "temp": 1.5, "peak": 1.8, "aboveHours": 0, "sensorId": "JHB-S1", "shipmentId": "SH-7755", "destination": "Waterfall Corner locker", "invId": "INV-2048", "invStatus": "Open", "handoffs": 1, "status": "In range", "stageIndex": 1, "series": [1.1, 1.2, 1.4, 1.3, 1.5, 1.4, 1.5]},
        {"code": "7F-558", "category": "Bakery", "product": "Baked cheesecake", "locationSite": "Durban DC (DBN-DC02)", "unitName": "Unit 14", "locationId": "DBN-DC02", "units": 4, "arrived": "2026-10-25 16:30", "temp": 1.0, "peak": 1.4, "aboveHours": 0, "sensorId": "DBN-S3", "shipmentId": "SH-7724", "destination": "Midrand Hub", "invId": "INV-2045", "invStatus": "Closed", "handoffs": 2, "status": "In range", "stageIndex": 0, "series": [1.1, 1.0, 1.2, 1.1, 0.9, 1.1, 1.0]},
    ],
    "investigations": [
        {
            "id": "INV-2048", "batchCode": "7F-442", "unitName": "Unit 12 (JHB-DC01)", "reason": "COOLING_FAILURE",
            "temp": 11.2, "units": 4, "statusText": "Unassigned", "state": "Open", "priority": "High", "age": "38m ago",
            "assignee": "Unassigned", "shipmentId": "SH-7713", "handoffs": 4, "sha256": "d773916a96ad23f94b6f3c8760e827aaba6b5cd8b509aa83b9c627bfe6b4cb8e",
            "aiSummary": "SUMMARY\n• High-priority open investigation INV-2048 at JHB-DC01 (Unit 12).\n• Labeled dataset telemetry shows temperature drift above safe threshold with reduced cooling load.\n\nAFFECTED INVENTORY\n• 7F-442: 4 insulin pens at risk; shipment SH-7713 placed on hold.",
            "timeline": [
                {"icon": "🌡", "tone": "warn", "title": "Temperature rising in JHB-DC01", "detail": "Telemetry sourced from cold_chain_labeled_2022_2026.csv", "source": "Sensor JHB-S2", "time": "2026-10-28 17:30"},
                {"icon": "⚠️", "tone": "warn", "title": "Batch 7F-442 flagged", "detail": "Exceeded safe band; shipment SH-7713 held.", "source": "RandomForest Detector", "time": "2026-10-28 20:00"},
            ]
        },
        {
            "id": "INV-2047", "batchCode": "8A-118", "unitName": "Unit 14 (DBN-DC02)", "reason": "TEMP_EXCURSION",
            "temp": 9.8, "units": 5, "statusText": "Sipho Peters", "state": "In progress", "priority": "Medium", "age": "3h ago",
            "assignee": "Sipho Peters", "shipmentId": "SH-7712", "handoffs": 3, "sha256": "3ba1a60b88391393658826a166feb4a42a5278f0b5d354aa46382e7730f3eb20",
            "aiSummary": "SUMMARY\n• DBN-DC02 drifted out of band; Sipho Peters assigned to verify door seal and relocate 5 flu vaccine vials.",
            "timeline": [
                {"icon": "⚠️", "tone": "warn", "title": "Batch 8A-118 flagged", "detail": "Excursion detected in DBN-DC02", "source": "RandomForest Detector", "time": "2026-10-28 17:00"}
            ]
        },
        {
            "id": "INV-2046", "batchCode": "9C-301", "unitName": "Unit 22 (CPT-DC03)", "reason": "TEMP_EXCURSION",
            "temp": 1.2, "units": 3, "statusText": "Aisha Dlamini", "state": "Under review", "priority": "High", "age": "1d ago",
            "assignee": "Aisha Dlamini", "shipmentId": "SH-7769", "handoffs": 5, "sha256": "3c5517c4fd1ed8d49762458925f240427d8ff36860ad0f5e1924fc8b99f084a0",
            "aiSummary": "SUMMARY\n• Temperature excursion (1.2°C) detected on batch 9C-301 at CPT-DC03 (Unit 22); Aisha Dlamini reviewing storage band compliance.",
            "timeline": [
                {"icon": "⚠️", "tone": "warn", "title": "Batch 9C-301 flagged", "detail": "Temperature excursion (1.2°C) detected in CPT-DC03", "source": "ColdChain rules", "time": "2026-10-27 20:00"}
            ]
        }
    ],
    "tasks": [
        {"icon": "!", "badgeClass": "high", "title": "Assign INV-2048", "sub": "JHB-DC01 • Cooling failure", "badge": "High", "invId": "INV-2048"},
        {"icon": "👤", "badgeClass": "progress", "title": "Review 8A-118 telemetry", "sub": "DBN-DC02 • Temperature excursion", "badge": "In progress", "invId": "INV-2047"},
        {"icon": "✦", "badgeClass": "neutral", "title": "AI triage INV-2047", "sub": "DBN-DC02 • Temperature excursion", "badge": "Next", "invId": "INV-2047"},
        {"icon": "✓", "badgeClass": "neutral", "title": "Review 9C-301 excursion", "sub": "CPT-DC03 • Temperature excursion", "badge": "Pending", "invId": "INV-2046"},
    ]
}

def _is_temp_out_of_range(temp_val: float, cat: str) -> bool:
    """Category band from the versioned thresholds file (pharma 2-8 C, chilled food <= 2 C)."""
    return TH.is_out_of_band(temp_val, cat)

_EXCURSION_TEMPS = {
    "7F-442": 11.2,
    "8A-118": 9.8,
    "9C-301": 1.2,
}

def _evaluate_batch_status(batch: dict, temp_val: float) -> str:
    if _is_temp_out_of_range(temp_val, batch.get("category", "")):
        return "Out of range"
    if batch.get("status") == "Monitoring":
        return "Monitoring"
    return "In range"

_ui_sync_ts = 0.0
_UI_SYNC_TTL_SEC = 5.0

def _sync_csv_and_alerts_to_ui(force: bool = False):
    global _ui_sync_ts
    now = time.monotonic()
    if not force and (now - _ui_sync_ts) < _UI_SYNC_TTL_SEC:
        return
    # Populate latest readings & 7-day series from cold_chain_labeled_2022_2026.csv
    csv_data = _get_csv_cache()
    for u in _ui_store["units"]:
        loc = u["locationId"]
        rows = csv_data.get(loc, [])
        if rows:
            u["temp"] = round(rows[-1]["T"], 1)
            u["series"] = _tail_series(loc)
            b = next((x for x in _ui_store["batches"] if x["locationId"] == loc and x["status"] == "Out of range"), None)
            if b:
                b["temp"] = u["temp"]
                b["peak"] = round(max(u["series"]), 1)
                b["series"] = u["series"]
    for b in _ui_store["batches"]:
        if b.get("code") in _EXCURSION_TEMPS and b.get("invStatus") != "Closed":
            b["temp"] = _EXCURSION_TEMPS[b["code"]]
            b["peak"] = _EXCURSION_TEMPS[b["code"]]
        b["status"] = _evaluate_batch_status(b, b.get("temp", 0.0))
        b["band"] = TH.band_label(b.get("category"))
        b["held"] = b["status"] == "Out of range" and b.get("invStatus") != "Closed"

    # A unit card shows the probe of its worst batch so unit and batch never disagree.
    for u in _ui_store["units"]:
        flagged = [b for b in _ui_store["batches"] if b["locationId"] == u["locationId"] and b["status"] == "Out of range"]
        if flagged:
            worst = max(flagged, key=lambda b: abs(float(b["temp"]) - 5.0))
            u["temp"] = worst["temp"]
            u["warmestBatch"] = worst["code"]
            u["band"] = worst["band"]
        u["flaggedCount"] = len(flagged)
        u["outOfBand"] = bool(flagged)
    for inv in _ui_store["investigations"]:
        c = _cases.cases.get(inv["id"]) if "_cases" in globals() else None
        if c:
            inv["age"] = _age(c.created_at)
            inv["createdAt"], inv["reviewDueAt"], inv["closeDueAt"] = c.created_at, c.review_due_at, c.close_due_at

    # Override with any newly injected or replayed live detector alerts
    for a in _state["alerts"].values():
        u = next((x for x in _ui_store["units"] if x["locationId"] == a.location_id), None)
        b = next((x for x in _ui_store["batches"] if x["locationId"] == a.location_id and x["status"] == "Out of range"), None)
        inv = next((x for x in _ui_store["investigations"] if a.location_id in x["unitName"]), None)
        if u and a.evidence:
            latest_t = round(float(a.evidence[-1].get("T", u["temp"])), 1)
            u["temp"] = latest_t
            u["series"] = (u["series"] + [latest_t])[-14:]
            if b:
                b["temp"] = latest_t
                b["peak"] = max(b["peak"], latest_t)
                b["series"] = u["series"]
            if inv:
                inv["temp"] = latest_t
                inv["reason"] = a.kind
                inv["sha256"] = a.evidence_sha256

@app.get("/api/ui/state")
def get_video_ui_state():
    _sync_csv_and_alerts_to_ui()  # cheap: skipped within the 5 s TTL
    return {**_ui_store, "thresholdsVersion": TH.load()["version"]}

@app.post("/api/demo/replay", dependencies=[Depends(require_demo_replay_auth)])
def replay_labeled_csv():
    path = _resolve_dataset_path()
    if not path:
        raise HTTPException(404, "Dataset CSV not found in Backend/data/")
    # Replay the tail 300 rows per site (covers 24h warm-up + recent labeled anomalies)
    count = 0
    for loc, rows in _get_csv_cache().items():
        for r in rows[-300:]:
            ev = {"location_id": loc, "ts": r["ts"], "T": r["T"], "H": r["H"], "C": r["C"], "S": r["S"]}
            det = detector().ingest(ev)
            count += 1
            if det.alert:
                _register_alert(det.alert)
    _sync_csv_and_alerts_to_ui(force=True)
    return {"status": "replayed", "source": path.name, "rows_processed": count, "alerts_total": len(_state["alerts"])}

@app.post("/api/demo/inject", dependencies=[Depends(require_key)])
async def inject_demo_fault(req: Request):
    body = await req.json()
    loc = body.get("location_id", "JHB-DC01")
    kind = str(body.get("kind", "COOLING_FAILURE")).upper()
    if loc not in LOCATIONS:
        raise HTTPException(422, f"unknown location {loc!r}")

    last = _latest_readings.get(loc, {"T": 4.0, "H": 75.0, "C": 60.0, "S": 98.0})
    if kind == "SENSOR_DROPOUT":
        ev = {"location_id": loc, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
              "T": float(last.get("T", 4.0)), "H": float(last.get("H", 75.0)),
              "C": float(last.get("C", 60.0)), "S": 10.0}
    elif kind == "COOLING_FAILURE":
        ev = {"location_id": loc, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
              "T": max(float(last.get("T", 4.0)) + 4.5, 9.5), "H": float(last.get("H", 75.0)),
              "C": 20.0, "S": 95.0}
    else:
        ev = {"location_id": loc, "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
              "T": max(float(last.get("T", 4.0)) + 5.0, 10.2), "H": float(last.get("H", 75.0)),
              "C": 55.0, "S": 95.0}

    _latest_readings[loc] = {"T": ev["T"], "H": ev["H"], "C": ev["C"], "S": ev["S"]}
    _reading_counts[loc] = _reading_counts.get(loc, 0) + 1
    det = detector().ingest(ev)
    if det.alert:
        _register_alert(det.alert)

    _sync_csv_and_alerts_to_ui(force=True)
    inv = next((x for x in _ui_store["investigations"] if loc in x["unitName"]), None)
    if inv:
        inv["temp"] = round(float(ev["T"]), 1)
        inv["reason"] = kind
        inv["timeline"].insert(0, {
            "icon": "⚡", "tone": "warn",
            "title": f"Simulated {kind} injected",
            "detail": f"Telemetry T={ev['T']}°C, C={ev['C']}%, S={ev['S']}% at {loc}",
            "source": "Demo Fault Injector",
            "time": "Just now"
        })
        if inv["id"] in _cases.cases and _cases.cases[inv["id"]].state != "Closed":
            _cases.note(inv["id"], "Demo Fault Injector", f"Simulated {kind}: T={ev['T']} C={ev['C']} S={ev['S']}")

    return {
        "status": "injected",
        "location_id": loc,
        "kind": kind,
        "detector_status": det.status,
        "alerts_total": len(_state["alerts"]),
    }


@app.post("/api/ui/investigations/{inv_id}/assign", dependencies=[Depends(require_key)])
async def assign_video_investigation(inv_id: str, req: Request):
    body = await req.json()
    assignee = body.get("assignee", "Naledi Mokoena")
    note = body.get("note", "")
    inv = next((x for x in _ui_store["investigations"] if x["id"] == inv_id), None)
    if not inv:
        raise HTTPException(404, "unknown investigation")
    if inv["state"] == "Closed":
        raise HTTPException(409, f"{inv_id} is closed")
    if inv_id in _cases.cases:
        _cases.transition(inv_id, "In progress", "Operations Lead", note or f"assigned to {assignee}", assignee=assignee)
        pubsub.publish("case_event", _cases.cases[inv_id].events[-1].__dict__, _cases.cases[inv_id].location_id)
    inv["assignee"] = assignee
    inv["statusText"] = assignee
    inv["state"] = "In progress"
    inv["handoffs"] += 1
    inv["timeline"].insert(0, {
        "icon": "👤", "tone": "info",
        "title": f"Assigned to {assignee}",
        "detail": note,
        "source": "Operations Lead",
        "time": "Just now"
    })
    return {"status": "assigned", "inv_id": inv_id, "assignee": assignee}

@app.post("/api/ui/investigations/{inv_id}/ask-ai", dependencies=[Depends(require_demo_ai_auth)])
def ask_video_ai(inv_id: str):
    inv = next((x for x in _ui_store["investigations"] if x["id"] == inv_id), None)
    if not inv:
        raise HTTPException(404, "unknown investigation")
    live_alerts = list(_state["alerts"].values())
    if live_alerts:
        try:
            if _state["nim"] is None:
                _state["nim"] = nim.NimClient()
            out = nim.explain(_state["nim"], os.getenv("NIM_MODEL", nim.DEFAULT_MODELS[0]), live_alerts[-1].to_case_json())
            note_obj = out.get("note", out)
            if isinstance(note_obj, dict):
                formatted = (
                    f"SUMMARY\n• {note_obj.get('summary', '')}\n• Likely cause: {note_obj.get('likely_cause', '')}\n\n"
                    f"AFFECTED INVENTORY\n• {note_obj.get('batches_at_risk', inv['batchCode'])}\n\n"
                    f"RECOMMENDED ACTIONS\n" + "\n".join(f"• {a}" for a in note_obj.get("recommended_actions", []))
                )
            else:
                formatted = str(note_obj)
            inv["aiSummary"] = formatted
            if inv_id in _cases.cases:
                _cases.note(inv_id, "NVIDIA NIM", "AI triage note generated (human review required)")
            return {"status": "ok", "narrative": formatted}
        except Exception as e:
            return {"status": "fallback", "narrative": inv["aiSummary"] + f"\n\n(NIM note: {type(e).__name__})"}
    return {"status": "ok", "narrative": inv["aiSummary"]}

@app.post("/api/ui/investigations/{inv_id}/resolve", dependencies=[Depends(require_key)])
def resolve_video_investigation(inv_id: str):
    inv = next((x for x in _ui_store["investigations"] if x["id"] == inv_id), None)
    if not inv:
        raise HTTPException(404, "unknown investigation")
    if inv_id in _cases.cases and _cases.cases[inv_id].state != "Closed":
        _cases.transition(inv_id, "Closed", "QA Reviewer", "disposition recorded; evidence hash archived")
        pubsub.publish("case_event", _cases.cases[inv_id].events[-1].__dict__, _cases.cases[inv_id].location_id)
    inv["state"] = "Closed"
    inv["statusText"] = "Resolved"
    inv["timeline"].insert(0, {
        "icon": "✓", "tone": "ok",
        "title": "Investigation resolved & closed",
        "detail": "Disposition recorded and evidence hash archived.",
        "source": "QA Reviewer",
        "time": "Just now"
    })
    b = next((x for x in _ui_store["batches"] if x["invId"] == inv_id), None)
    if b:
        b["stageIndex"] = 3
        b["invStatus"] = "Closed"
    return {"status": "resolved", "inv_id": inv_id}


# --- Case log, Insights MVP, thresholds, validation and Pub/Sub ------------------------------
_cases = CS.CaseStore()


def _age(iso_ts: str) -> str:
    mins = int((datetime.now(timezone.utc) - CS._parse(iso_ts)).total_seconds() // 60)
    if mins < 60:
        return f"{max(mins, 0)}m ago"
    if mins < 48 * 60:
        return f"{mins // 60}h ago"
    return f"{mins // 1440}d ago"


def _seed_cases() -> None:
    """Live cases for the three console investigations + seeded synthetic history from labels."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    seed = {  # id: (created minutes ago, path of (state, minutes ago, actor, assignee))
        "INV-2048": (38, []),
        "INV-2047": (180, [("In progress", 150, "Operations Lead", "Sipho Peters")]),
        "INV-2046": (1440, [("In progress", 1380, "Operations Lead", "Aisha Dlamini"),
                            ("Under review", 600, "QA reviewer", None)]),
    }
    for inv in _ui_store["investigations"]:
        created_ago, path = seed.get(inv["id"], (60, []))
        loc = next((l for l in LOCATIONS if l in inv["unitName"]), LOCATIONS[0])
        _cases.create(inv["id"], loc, inv["reason"], inv["priority"], batch_code=inv["batchCode"],
                      detected_at=now - timedelta(minutes=created_ago + 30), created_at=now - timedelta(minutes=created_ago))
        for state, ago, actor, assignee in path:
            _cases.transition(inv["id"], state, actor, ts=now - timedelta(minutes=ago), assignee=assignee)


def _register_alert(alert) -> None:
    _state["alerts"][alert.alert_id] = alert
    pubsub.publish("alert", alert.to_case_json(), alert.location_id)
    if alert.alert_id not in _cases.cases:
        _cases.create(alert.alert_id, alert.location_id, alert.kind, "High", actor="detector")


_seed_cases()
_backfill_done = False


def _ensure_backfill() -> None:
    """Synthetic history is built on first use, so start-up stays fast (CSV is lazy-loaded)."""
    global _backfill_done
    if _backfill_done:
        return
    _backfill_done = True
    if os.getenv("SYNTHETIC_CASE_BACKFILL", "true").lower() == "true":
        CS.backfill_from_labels(_cases, _get_csv_cache(), days=int(os.getenv("BACKFILL_DAYS", "60")))


@app.get("/api/insights")
def get_insights(days: int = 30, include_synthetic: bool = True):
    _ensure_backfill()
    days = max(1, min(days, 120))
    pool = [c for c in _cases.all() if include_synthetic or not c.synthetic]
    return CS.insights(pool, window_days=days)


@app.get("/api/cases")
def list_cases(state: str | None = None, include_synthetic: bool = False, limit: int = 50):
    if include_synthetic:
        _ensure_backfill()
    rows = [c for c in _cases.all() if (include_synthetic or not c.synthetic) and (not state or c.state == state)]
    rows.sort(key=lambda c: c.created_at, reverse=True)
    return {"cases": [c.public() for c in rows[: max(1, min(limit, 500))]]}


@app.get("/api/cases/{case_id}/events")
def case_events(case_id: str):
    c = _cases.cases.get(case_id)
    if not c:
        raise HTTPException(404, "unknown case")
    return {"case": c.public(), "events": [e.__dict__ for e in c.events], "chain_valid": _cases.verify_chain(case_id)}


@app.get("/api/thresholds")
def get_thresholds():
    return TH.summary()


@app.get("/api/validation")
def get_validation_report():
    """Latest data-validation report (python -m coldtrace.validation <csv>) plus live reference check."""
    from . import validation as V
    report_path = Path(__file__).resolve().parent.parent / "artifacts" / "validation_report.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else None
    ref_dir = Path(__file__).resolve().parent.parent / "data" / "reference"
    ref = V.validate_references(*V.load_reference(ref_dir)) if ref_dir.exists() else None
    return {"telemetry": report, "reference_integrity": ref}


@app.post("/pubsub/push")
async def pubsub_push(req: Request, token: str = ""):
    """Push endpoint for sensor readings published to the telemetry topic by field gateways."""
    expected = os.getenv("PUBSUB_PUSH_TOKEN", "")
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(401, "invalid push token")
    try:
        payload, attrs = pubsub.decode_push(await req.json())
    except ValueError as e:
        raise HTTPException(400, str(e))
    if attrs.get("type", "reading") != "reading":
        return {"status": "ignored", "type": attrs.get("type")}  # our own alert/case messages
    try:
        event = SensorEvent(**payload)
    except Exception:
        raise HTTPException(400, "payload is not a valid SensorEvent")
    return ingest(event)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(Path(__file__).resolve().parent / "static" / "favicon.ico", media_type="image/x-icon")
