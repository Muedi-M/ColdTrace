import hashlib
import hmac
import json
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

ALLOWED_LOCATIONS = {"JHB-DC01", "DBN-DC02", "CPT-DC03"}
LOC_PATTERN = re.compile(r"^(JHB-DC01|DBN-DC02|CPT-DC03)$")

# --- 1. Sliding-Window Rate Limiter ---
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)

def check_rate_limit(bucket_key: str, max_calls: int, window_sec: int = 60) -> None:
    now = time.monotonic()
    q = _rate_buckets[bucket_key]
    while q and (now - q[0]) > window_sec:
        q.popleft()
    if len(q) >= max_calls:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    q.append(now)

# --- 2. Per-Client Hashed API Key & Location Binding ---
def _load_key_registry() -> dict[str, dict[str, Any]]:
    raw = os.getenv("API_KEY_HASHES_JSON", "").strip()
    if raw:
        return json.loads(raw)
    # Local dev fallback when API_KEY_HASHES_JSON is unset
    fallback_key = os.getenv("INGEST_API_KEY", "change-me-local-only")
    h = hashlib.sha256(fallback_key.encode("utf-8")).hexdigest()
    return {h: {"role": "admin", "locations": ["*"]}}

def authenticate_client(x_api_key: str | None = Header(default=None), target_location: str | None = None) -> dict[str, Any]:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    incoming_hash = hashlib.sha256(x_api_key.encode("utf-8")).hexdigest()
    registry = _load_key_registry()

    matched_record = None
    for stored_hash, meta in registry.items():
        if hmac.compare_digest(incoming_hash, stored_hash):
            matched_record = meta
            break

    if not matched_record:
        raise HTTPException(status_code=401, detail="Invalid API key")

    allowed_locs = matched_record.get("locations", [])
    if target_location and "*" not in allowed_locs and target_location not in allowed_locs:
        raise HTTPException(status_code=403, detail=f"API key not authorized for location {target_location}")

    return matched_record

# --- 3. Strict Pydantic Schema & Anti-Replay Guard ---
_last_seen_ts: dict[str, datetime] = {}

class StrictSensorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location_id: str
    ts: datetime
    warehouse_temperature_c: float = Field(..., ge=-40.0, le=60.0)
    warehouse_humidity_percent: float = Field(..., ge=0.0, le=100.0)
    cooling_load_percent: float = Field(..., ge=0.0, le=100.0)
    sensor_connectivity: float = Field(..., ge=0.0, le=100.0)
    product_sensitivity: Literal["Low", "Medium", "High"] | None = None
    estimated_freshness_percent: float | None = Field(default=None, ge=0.0, le=100.0)
    spoilage_risk: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("location_id")
    @classmethod
    def validate_loc(cls, v: str) -> str:
        if not LOC_PATTERN.match(v):
            raise ValueError("Invalid location_id format")
        return v

    @field_validator("ts")
    @classmethod
    def validate_timestamp(cls, v: datetime) -> datetime:
        ts_utc = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if ts_utc > now + timedelta(minutes=5):
            raise ValueError("Future timestamps are rejected")
        if ts_utc < now - timedelta(days=365 * 5):
            raise ValueError("Timestamp outside valid retention window")
        return ts_utc

def enforce_anti_replay(location_id: str, ts: datetime, allow_historical: bool = False) -> None:
    if allow_historical:
        return
    prev = _last_seen_ts.get(location_id)
    if prev and ts <= prev:
        raise HTTPException(status_code=409, detail="Replayed or out-of-order timestamp rejected")
    _last_seen_ts[location_id] = ts

# --- 4. Chained HMAC Evidence Seal ---
_last_chain_hmac: str = "GENESIS"

def compute_chained_hmac(alert_id: str, evidence_sha256: str) -> str:
    global _last_chain_hmac
    secret = os.getenv("EVIDENCE_HMAC_KEY", "local-dev-hmac-secret").encode("utf-8")
    msg = f"{_last_chain_hmac}:{alert_id}:{evidence_sha256}".encode("utf-8")
    digest = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    _last_chain_hmac = digest
    return digest

# --- 5. Signed ML Model Artifact Verification ---
def verify_model_artifacts(artifacts_dir: Path) -> None:
    manifest = artifacts_dir / "rf_model.sha256"
    if not manifest.exists():
        return
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        expected_hash, rel_path = line.split(maxsplit=1)
        target = artifacts_dir.parent / rel_path.lstrip("./")
        if not target.exists():
            raise RuntimeError(f"Missing signed model artifact: {target}")
        actual_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        if not hmac.compare_digest(expected_hash, actual_hash):
            raise RuntimeError(f"Model artifact integrity check failed for {target}")

# --- 6. Security Headers & Payload Cap Middleware ---
class SecurityHardeningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 16384:
            raise HTTPException(status_code=413, detail="Request payload exceeds 16KB limit")

        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response
