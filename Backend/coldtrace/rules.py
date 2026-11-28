"""Rule baseline = the SOP-style detector the ML model has to beat.

Thresholds are fixed domain values (2-8 C cold-chain band, connectivity floor), not fitted to
this data, so the baseline is not tuned against the test split.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import thresholds as TH

# Values live in config/thresholds.json (versioned, reviewed); same numbers as the original SOP baseline.
_D = TH.load()["detector"]
TEMP_LIMIT_C = float(_D["temp_limit_c"])
SENSOR_FLOOR = float(_D["sensor_floor_pct"])
FLAT_STEPS = int(_D["flat_steps"])
COOLING_LOW = float(_D["cooling_low_pct"])
WARMING_C = float(_D["warming_c"])
THRESHOLDS_VERSION = TH.load()["version"]


def rule_predict(f: pd.DataFrame) -> np.ndarray:
    """Priority: SENSOR_DROPOUT > COOLING_FAILURE > TEMP_EXCURSION."""
    pred = np.full(len(f), "NONE", dtype=object)
    excursion = (f["T"] > TEMP_LIMIT_C) | ((f["T_dev_base"] > 2.0) & (f["dT3"] > 0))
    cooling = (f["T_dev_base"] > WARMING_C) & (f["C_mean6"] < COOLING_LOW)
    dropout = (f["S"] < SENSOR_FLOOR) | (f["T_flat_run"] >= FLAT_STEPS)
    pred[excursion.values] = "TEMP_EXCURSION"
    pred[cooling.values] = "COOLING_FAILURE"
    pred[dropout.values] = "SENSOR_DROPOUT"
    return pred


def threshold_only_predict(f: pd.DataFrame) -> np.ndarray:
    """Weakest baseline: alert when the reading leaves the 2-8 C band."""
    return np.where(f["T"] > TEMP_LIMIT_C, "TEMP_EXCURSION", "NONE").astype(object)
