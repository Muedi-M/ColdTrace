"""Versioned, reviewable thresholds.

One JSON file (config/thresholds.json) holds every number that decides whether a reading is an
exception: category temperature bands, detector constants, validation ranges and case SLAs.
Each alert and validation report records `version` and `sha256`, so a reviewer can prove which
thresholds were in force when an exception was raised.
"""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "thresholds.json"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    raw = Path(path).read_bytes()
    cfg = json.loads(raw)
    cfg["sha256"] = hashlib.sha256(raw).hexdigest()
    cfg["path"] = str(path)
    return cfg


def load(path: str | os.PathLike | None = None) -> dict:
    """Return the thresholds config plus its sha256. Path: arg > $THRESHOLDS_PATH > default."""
    return _load(str(path or os.getenv("THRESHOLDS_PATH") or DEFAULT_PATH))


def band_for(category: str | None, cfg: dict | None = None) -> tuple[str, dict]:
    cfg = cfg or load()
    c = (category or "").strip().lower()
    for name, band in cfg["bands"].items():
        if any(k in c for k in band.get("match", [])):
            return name, band
    return "chilled_food", cfg["bands"]["chilled_food"]


def is_out_of_band(temp_c: float, category: str | None, cfg: dict | None = None) -> bool:
    _, band = band_for(category, cfg)
    t = float(temp_c)
    lo, hi = band.get("min_c"), band.get("max_c")
    return (lo is not None and t < lo) or (hi is not None and t > hi)


def band_label(category: str | None, cfg: dict | None = None) -> str:
    _, band = band_for(category, cfg)
    lo, hi = band.get("min_c"), band.get("max_c")
    if lo is not None and hi is not None:
        return f"{lo:g}°C–{hi:g}°C"
    return f"≤ {hi:g}°C" if hi is not None else f"≥ {lo:g}°C"


def summary(cfg: dict | None = None) -> dict:
    """Small, API-safe view: version, status, reviewers, hash, bands, SLAs, history."""
    cfg = cfg or load()
    keep = ("version", "status", "reviewed_by", "reviewed_at", "sha256", "bands", "detector", "sla", "history")
    return {k: cfg.get(k) for k in keep}
