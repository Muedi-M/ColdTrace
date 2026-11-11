"""Train RF, evaluate rules vs RF vs threshold-only on val/test, write artifacts/metrics.json.

    python scripts/train_eval.py --data data/cold_chain_labeled_2022_2026.csv.gz
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coldtrace import model as M
from coldtrace.evaluate import event_metrics
from coldtrace.features import FEATURES, LABELS, build_features
from coldtrace.rules import rule_predict, threshold_only_predict

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/cold_chain_labeled_2022_2026.csv")
ap.add_argument("--out", default="artifacts")
ap.add_argument("--k", type=int, default=2, help="consecutive predictions needed to raise an alert")
ap.add_argument("--min-conf", type=float, default=0.5)
a = ap.parse_args()

df = pd.read_csv(a.data, keep_default_na=False, parse_dates=["Timestamp"]).sort_values(["Storage_Location_ID", "Timestamp"]).reset_index(drop=True)
feats = build_features(df)
df = pd.concat([df, feats.add_prefix("f_")], axis=1)
F = lambda part: part[[f"f_{c}" for c in FEATURES]].set_axis(FEATURES, axis=1)

tr, va, te = (M.split(df, s) for s in ("train", "val", "test"))
t0 = time.time()
rf = M.fit_rf(F(tr), tr["Exception_Type"].to_numpy())
fit_s = time.time() - t0

def step_report(part, pred):
    return {"macro_f1": f1_score(part["Exception_Type"], pred, labels=LABELS, average="macro", zero_division=0),
            "report": classification_report(part["Exception_Type"], pred, labels=LABELS, output_dict=True, zero_division=0)}

results = {}
for name, part in (("val", va), ("test", te)):
    X = F(part)
    preds = {
        "threshold_only": threshold_only_predict(X),
        "rules": rule_predict(X),
        "random_forest": M.predict(rf, X, a.min_conf),
    }
    results[name] = {}
    for m, p in preds.items():
        results[name][m] = {"step": step_report(part, p), "event": event_metrics(part, p, k=a.k)}

# feature importance for the evaluation write-up
imp = dict(sorted(zip(FEATURES, map(float, rf.feature_importances_)), key=lambda kv: -kv[1]))

out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
sha = M.save(rf, out / "coldtrace_rf.joblib", {
    "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "data_sha256": M.data_fingerprint(a.data),
    "splits": M.SPLITS, "k": a.k, "min_conf": a.min_conf, "fit_seconds": round(fit_s, 1),
})
summary = {"model_sha256": sha, "fit_seconds": round(fit_s, 1), "alert_k": a.k, "min_conf": a.min_conf,
           "rows": {"train": len(tr), "val": len(va), "test": len(te)}, "feature_importance": imp, "results": results}
(out / "metrics.json").write_text(json.dumps(summary, indent=2, default=float))

print(f"fit {fit_s:.0f}s  model_sha256 {sha[:12]}")
print(f"{'split':5} {'model':15} {'stepF1':>7} {'evRecall(type)':>15} {'evRecall(any)':>14} {'FA/loc-day':>11} {'alertPrec':>10}")
for s in results:
    for m, r in results[s].items():
        e = r["event"]
        print(f"{s:5} {m:15} {r['step']['macro_f1']:7.3f} {e['event_recall_type']:15.3f} {e['event_recall_any']:14.3f} {e['false_alerts_per_loc_day']:11.3f} {e['alert_precision']:10.3f}")
print("\nTEST per-type (event recall by type | median TTD h):")
for m, r in results["test"].items():
    print(m, {t: (round(v["recall_type"], 2), v["ttd_median_h"]) for t, v in r["event"]["per_type"].items()})
