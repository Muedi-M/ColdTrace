"""RandomForest detector + persistence. Single artifact = model + feature list + provenance."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from .features import FEATURES, LABELS

SPLITS = {"train": ("2022-01-01", "2025-01-01"), "val": ("2025-01-01", "2026-01-01"), "test": ("2026-01-01", "2026-11-01")}


def split(df: pd.DataFrame, name: str) -> pd.DataFrame:
    lo, hi = SPLITS[name]
    return df[(df["Timestamp"] >= lo) & (df["Timestamp"] < hi)]


def fit_rf(X: pd.DataFrame, y: np.ndarray, seed: int = 0) -> RandomForestClassifier:
    rf = RandomForestClassifier(
        n_estimators=150, max_depth=14, min_samples_leaf=20, class_weight="balanced_subsample",
        n_jobs=-1, random_state=seed,
    )
    return rf.fit(X[FEATURES], y)


def proba_frame(rf: RandomForestClassifier, X: pd.DataFrame) -> pd.DataFrame:
    p = pd.DataFrame(rf.predict_proba(X[FEATURES]), columns=rf.classes_, index=X.index)
    return p.reindex(columns=LABELS, fill_value=0.0)


def predict(rf: RandomForestClassifier, X: pd.DataFrame, min_conf: float = 0.5) -> np.ndarray:
    """Argmax over classes; an exception is only raised when its probability >= min_conf."""
    p = proba_frame(rf, X)
    arg = p.to_numpy().argmax(1)
    lab = np.array(LABELS, dtype=object)[arg]
    conf = p.to_numpy().max(1)
    return np.where((lab != "NONE") & (conf < min_conf), "NONE", lab).astype(object)


def save(rf, path: str | Path, meta: dict) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": rf, "features": FEATURES, "labels": LABELS, "meta": meta}, path, compress=3)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: str | Path) -> dict:
    art = joblib.load(path)
    assert art["features"] == FEATURES, "feature list drifted from training artifact"
    return art


def data_fingerprint(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
