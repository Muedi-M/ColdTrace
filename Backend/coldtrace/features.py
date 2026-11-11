"""Causal feature engineering shared by batch training and streaming inference.

Every feature at row t uses rows <= t of the same storage location only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LABELS = ["NONE", "TEMP_EXCURSION", "COOLING_FAILURE", "SENSOR_DROPOUT"]
SENSOR_COLS = {
    "Warehouse_Temperature_C": "T",
    "Warehouse_Humidity_Percent": "H",
    "Cooling_Load_Percent": "C",
    "Sensor_Connectivity": "S",
}
LOC = "Storage_Location_ID"
TS = "Timestamp"
BASE_WIN = 48  # 24 h of 30-min steps
FLAT_EPS = 0.02  # deg C change treated as "no change"

FEATURES = [
    "T", "H", "C", "S",
    "dT1", "dT3", "dT6", "dH1",
    "T_mean6", "T_std4", "T_max6", "T_min6",
    "T_dev_base", "C_mean6", "C_dev_base", "S_min6",
    "T_flat_run", "H_flat_run", "T_gt7_6",
]


def _run_length(flag: pd.Series) -> pd.Series:
    """Consecutive-True run length ending at each row."""
    grp = (~flag).cumsum()
    return flag.groupby(grp).cumsum().astype(float)


def _one_location(g: pd.DataFrame) -> pd.DataFrame:
    T, H, C, S = g["T"], g["H"], g["C"], g["S"]
    out = pd.DataFrame(index=g.index)
    out["T"], out["H"], out["C"], out["S"] = T, H, C, S
    out["dT1"] = T.diff(1).fillna(0.0)
    out["dT3"] = T.diff(3).fillna(0.0)
    out["dT6"] = T.diff(6).fillna(0.0)
    out["dH1"] = H.diff(1).fillna(0.0)
    r6 = T.rolling(6, min_periods=1)
    out["T_mean6"] = r6.mean()
    out["T_std4"] = T.rolling(4, min_periods=2).std().fillna(0.0)
    out["T_max6"] = r6.max()
    out["T_min6"] = r6.min()
    # baseline = previous 24 h, excluding the current row, so an ongoing event cannot hide itself
    base_T = T.rolling(BASE_WIN, min_periods=6).mean().shift(1)
    base_C = C.rolling(BASE_WIN, min_periods=6).mean().shift(1)
    out["T_dev_base"] = (T - base_T).fillna(0.0)
    out["C_mean6"] = C.rolling(6, min_periods=1).mean()
    out["C_dev_base"] = (out["C_mean6"] - base_C).fillna(0.0)
    out["S_min6"] = S.rolling(6, min_periods=1).min()
    out["T_flat_run"] = _run_length(T.diff().abs().lt(FLAT_EPS) & T.diff().notna())
    out["H_flat_run"] = _run_length(H.diff().abs().lt(FLAT_EPS) & H.diff().notna())
    out["T_gt7_6"] = (T > 7.0).astype(float).rolling(6, min_periods=1).sum()
    return out


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """df needs Timestamp, Storage_Location_ID and the four sensor columns.

    Returns a frame aligned to df's index with FEATURES columns.
    """
    d = df.rename(columns=SENSOR_COLS)
    d = d.sort_values([LOC, TS])
    parts = [_one_location(g) for _, g in d.groupby(LOC, sort=False)]
    feats = pd.concat(parts)[FEATURES]
    return feats.reindex(df.index)
