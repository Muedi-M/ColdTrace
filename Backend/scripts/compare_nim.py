"""Compare NVIDIA NIM models against the rules and RF baselines on identical labeled windows.

    export NVIDIA_API_KEY=nvapi-...
    python scripts/compare_nim.py --data data/cold_chain_labeled_2022_2026.csv --per-class 30
    python scripts/compare_nim.py --mock        # offline plumbing test, no key, no network

Windows are drawn from the TEST split only (2026). Positives are sampled 3 steps (1.5 h) into each true
event so the evidence is visible but the event is still young; negatives are random clean NONE steps.
The LLM sees 24 steps (12 h); RF/rules see the same row plus their own 24 h baseline features.
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coldtrace import model as M
from coldtrace import nim
from coldtrace.evaluate import _runs
from coldtrace.features import FEATURES, LABELS, build_features
from coldtrace.rules import rule_predict

ap = argparse.ArgumentParser()
ap.add_argument("--data", default="data/cold_chain_labeled_2022_2026.csv")
ap.add_argument("--model-path", default="artifacts/coldtrace_rf.joblib")
ap.add_argument("--models", nargs="*", default=nim.DEFAULT_MODELS)
ap.add_argument("--per-class", type=int, default=30)
ap.add_argument("--window", type=int, default=24)
ap.add_argument("--workers", type=int, default=2)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--out", default="artifacts/nim_comparison")
ap.add_argument("--mock", action="store_true")
a = ap.parse_args()
rng = np.random.default_rng(a.seed)

df = pd.read_csv(a.data, keep_default_na=False, parse_dates=["Timestamp"]).sort_values(["Storage_Location_ID", "Timestamp"]).reset_index(drop=True)
feats = build_features(df)
art = M.load(a.model_path)

# ---- sample windows (test split only)
test_mask = (df["Timestamp"] >= M.SPLITS["test"][0]) & (df["Timestamp"] < M.SPLITS["test"][1])
picks = []  # (row index, true label)
for loc, g in df[test_mask].groupby("Storage_Location_ID"):
    idx = g.index.to_numpy()
    lab = g["Exception_Type"].to_numpy(object)
    for kind, s, e in _runs(lab):
        if s >= a.window:
            picks.append((idx[min(s + 3, e)], kind))
by = {}
for i, k in picks:
    by.setdefault(k, []).append(i)
sel = []
for k in LABELS[1:]:
    ids = by.get(k, [])
    take = rng.choice(len(ids), size=min(a.per_class, len(ids)), replace=False)
    sel += [(ids[j], k) for j in take]
clean = df.index[test_mask & (df["Exception_Type"] == "NONE")].to_numpy()
clean = [i for i in clean if (df.loc[i - a.window:i, "Exception_Type"] == "NONE").all() and df.at[i, "Storage_Location_ID"] == df.at[i - a.window, "Storage_Location_ID"]]
sel += [(i, "NONE") for i in rng.choice(clean, size=a.per_class, replace=False)]
rows = pd.DataFrame(sel, columns=["row", "truth"])
print("windows:", rows.truth.value_counts().to_dict())

def window_for(i):
    g = df.loc[i - a.window + 1:i]
    return [{"ts": r.Timestamp.strftime("%m-%d %H:%M"), "T": r.Warehouse_Temperature_C, "H": r.Warehouse_Humidity_Percent,
             "C": r.Cooling_Load_Percent, "S": r.Sensor_Connectivity} for r in g.itertuples()]

X = feats.loc[rows.row]
base = {"rules": rule_predict(X), "random_forest": M.predict(art["model"], X, art["meta"].get("min_conf", 0.5))}
windows = [window_for(i) for i in rows.row]

# ---- clients
class Mock:
    """Offline stand-in: crude heuristics on the same text the real model sees."""
    def chat(self, model, messages, temperature=0.0, max_tokens=300):
        lines = messages[-1]["content"].splitlines()[2:]
        v = np.array([[float(x) for x in l.split(",")[1:]] for l in lines])
        T, C, S = v[:, 0], v[:, 2], v[:, 3]
        lab = "NONE"
        if S[-1] < 60 or np.ptp(T[-4:]) < 0.05: lab = "SENSOR_DROPOUT"
        elif T[-1] > 7 and C[-3:].mean() < 40: lab = "COOLING_FAILURE"
        elif T[-1] > 7: lab = "TEMP_EXCURSION"
        return nim.NimResult(json.dumps({"label": lab, "confidence": 0.5}), 0.01, 300, 12)

client = Mock() if a.mock else nim.NimClient()
models = ["mock"] if a.mock else a.models
if not a.mock:
    usable = []
    for m in models:
        try:
            client.key_for(m)
            usable.append(m)
        except RuntimeError as e:
            print(f"SKIP {m}: {e}")
    models = usable
    if not models:
        sys.exit("no model has an API key; see .nim_keys.json.example")
    try:
        avail = set(client.list_models())
        for m in models:
            if m not in avail:
                print(f"WARNING: {m} not in /models listing for the default key; it may still work with its own key")
    except (RuntimeError, nim.NimError) as e:
        print(f"model listing skipped ({type(e).__name__}); continuing")

def one(args):
    model, w = args
    try:
        lab, res, ok = nim.classify(client, model, w)
        note = "" if ok else f"finish={res.finish or '?'} text={res.text[:160]!r}"
        return lab, res.latency_s, res.prompt_tokens + res.completion_tokens, ok, note
    except (nim.NimError, RuntimeError) as e:
        return "ERROR", 0.0, 0, False, str(e)[:300]

summary, preds = {}, {"truth": rows.truth.to_numpy(), "rules": base["rules"], "random_forest": base["random_forest"]}
for m in models:
    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        out = list(ex.map(one, [(m, w) for w in windows]))
    preds[m] = np.array([o[0] for o in out], dtype=object)
    summary[m] = {"json_valid": float(np.mean([o[3] for o in out])), "errors": int(sum(o[0] == "ERROR" for o in out)), "invalid": int(sum(o[0] == "INVALID" for o in out)), "first_problem": next((o[4] for o in out if not o[3]), None),
                  "latency_median_s": float(np.median([o[1] for o in out])), "latency_p90_s": float(np.percentile([o[1] for o in out], 90)),
                  "tokens_per_call": float(np.mean([o[2] for o in out])), "wall_s": round(time.time() - t0, 1)}

truth = rows.truth.to_numpy(object)
for name in ["rules", "random_forest"] + models:
    p = preds[name]
    cm = confusion_matrix(truth, p, labels=LABELS)
    rec = {l: float(cm[i, i] / max(cm[i].sum(), 1)) for i, l in enumerate(LABELS)}
    s = summary.setdefault(name, {})
    s.update({"macro_f1": float(f1_score(truth, p, labels=LABELS, average="macro", zero_division=0)),
              "recall": rec, "false_alarm_rate_on_NONE": 1 - rec["NONE"]})
    if name in models:  # score only the calls that returned an answer (not transport errors), so rate limits don't masquerade as wrong labels
        ok = p != "ERROR"
        s["answered"] = int(ok.sum())
        s["macro_f1_answered"] = float(f1_score(truth[ok], p[ok], labels=LABELS, average="macro", zero_division=0)) if ok.any() else float("nan")
    s["agree_with_rf"] = float(np.mean(p == preds["random_forest"]))

out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
pd.DataFrame(preds).assign(row=rows.row.to_numpy(), ts=df.loc[rows.row, "Timestamp"].to_numpy(),
                           loc=df.loc[rows.row, "Storage_Location_ID"].to_numpy()).to_csv(f"{out}_predictions.csv", index=False)
Path(f"{out}_summary.json").write_text(json.dumps({"n": len(rows), "window_steps": a.window, "seed": a.seed, "results": summary}, indent=2))
print(f"\n{'model':48} {'macroF1':>8} {'recNONE':>8} {'recEXC':>7} {'recCOOL':>8} {'recDROP':>8} {'valid':>6} {'p50 s':>6} {'answ':>5} {'F1ans':>6}")
for name in ["rules", "random_forest"] + models:
    s = summary[name]; r = s["recall"]
    print(f"{name:48} {s['macro_f1']:8.3f} {r['NONE']:8.2f} {r['TEMP_EXCURSION']:7.2f} {r['COOLING_FAILURE']:8.2f} {r['SENSOR_DROPOUT']:8.2f} "
          f"{s.get('json_valid', float('nan')):6.2f} {s.get('latency_median_s', float('nan')):6.2f} {s.get('answered', len(rows)):5d} {s.get('macro_f1_answered', s['macro_f1']):6.3f}")

print()
for m in models:
    s = summary[m]
    if s.get("first_problem"):
        print(f"PROBLEM {m}: {s['errors']} errors, {s['invalid']} unparseable of {len(rows)}. First: {s['first_problem']}")