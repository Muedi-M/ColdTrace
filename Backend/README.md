# ColdTrace backend: detection model + NVIDIA NIM

Owner: Muedi (AI research foundations: baselines and evaluation). Status: Week 2 handoff, 2026-11-10.

## What is here

| Path | Purpose |
|---|---|
| `scripts/generate_data.py` | Seeded simulator: 3 sites x 30-min x 2022-01..2026-10, with injected ground truth `Exception_Type` |
| `coldtrace/features.py` | Causal features, identical for training and streaming |
| `coldtrace/rules.py` | SOP-style rule detector (fixed thresholds) = the baseline to beat |
| `coldtrace/model.py` | RandomForest, time-based splits, artifact with provenance |
| `coldtrace/evaluate.py` | Event-level recall, time-to-detect, false alerts per location-day |
| `coldtrace/service.py` | Per-location streaming detector, debounced alerts, sha256-sealed evidence |
| `coldtrace/nim.py` | NVIDIA NIM client (`requests`, retries, JSON validation) + classify/explain prompts |
| `coldtrace/api.py` | FastAPI for Cloud Run: `/ingest`, `/alerts/{id}/explain`, `/healthz` |
| `scripts/train_eval.py` | Train + score threshold-only vs rules vs RF; writes `artifacts/metrics.json` |
| `scripts/replay.py` | Replays sample readings through the detector (`--local`) or a running API; prints every alert |
| `scripts/compare_nim.py` | Scores NIM models against the same labeled windows as the baselines |

## Exception types (assumption: the handbook does not name them; edit `features.LABELS` if the team chose others)

| Type | Signature in the data |
|---|---|
| `TEMP_EXCURSION` | Warehouse temperature rises out of the 2-8 C band (door open / power loss); cooling load rises |
| `COOLING_FAILURE` | Temperature drifts up while cooling load is abnormally low (compressor fault) |
| `SENSOR_DROPOUT` | Connectivity collapses and the temperature/humidity readings freeze |

## Run

```bash
pip install -r requirements.txt
python scripts/generate_data.py data/cold_chain_labeled_2022_2026.csv     # ~1 min
python scripts/train_eval.py --data data/cold_chain_labeled_2022_2026.csv # ~40 s on 2 cores
pytest -q tests
export NVIDIA_API_KEY=nvapi-...                                           # never commit
python scripts/compare_nim.py --per-class 30
python scripts/compare_nim.py --mock                                      # offline plumbing check
python scripts/replay.py --local                                           # replay 14 days of readings, print alerts
INGEST_API_KEY=dev MODEL_PATH=artifacts/coldtrace_rf.joblib uvicorn coldtrace.api:app --port 8080
```

Splits (time-based, no shuffling): train 2022-2024, val 2025, test 2026-01..10.

## Baseline results (test split, 283 true events, alert = 2 consecutive predictions)

| Detector | Step macro-F1 | Event recall (right type) | False alerts / location-day | Alert precision |
|---|---|---|---|---|
| Threshold only (>8 C) | 0.284 | 0.049 | 0.024 | 0.371 |
| Rules (SOP-style) | 0.726 | 0.837 | 0.088 | 0.754 |
| Random forest | 0.810 | 0.943 | 0.106 | 0.736 |

| Type (events) | Rules recall / median TTD | RF recall / median TTD |
|---|---|---|
| TEMP_EXCURSION (68) | 0.43 / 1.5 h | 0.79 / 0.5 h |
| COOLING_FAILURE (45) | 0.84 / 2.5 h | 0.96 / 1.0 h |
| SENSOR_DROPOUT (170) | 1.00 / 0.5 h | 1.00 / 0.5 h |

The RF buys recall and speed; it does not reduce false alerts (about 1 per 10 location-days either way).

## Limits that matter

1. **Synthetic data.** The RF recovers signatures the simulator injected (for example, cooling load -30 points during compressor faults). These numbers validate the pipeline and rank methods against each other; they are not a claim about real-world accuracy. Re-run on real sensor logs before quoting any figure externally.
2. Event rates after 2024 are floored at about 0.07 big excursions per location-day so the test split has enough events. Real rates are likely lower, which makes false alerts per real event worse than shown.
3. Excursions that are masked by a sensor dropout are labeled `SENSOR_DROPOUT`.
4. `compare_nim.py` gives the LLM 12 h of readings; RF and rules also use a 24 h baseline. Treat LLM-vs-RF as indicative, not like-for-like.
5. NIM calls have not been run live from the build environment (no outbound access). Model IDs in `nim.DEFAULT_MODELS` come from a third-party write-up: the script lists `/models` for your key and warns on mismatches.

## NIM design rules

- Detection never depends on NIM. The detector raises and seals the alert; NIM only writes the incident note (`/alerts/{id}/explain`), and a NIM failure returns 503 while the alert stays valid.
- The note is grounded: the prompt forbids facts outside the case JSON, output is schema-checked (`valid` flag), and anything invalid is surfaced rather than patched.
- Key comes from `NVIDIA_API_KEY` or Secret Manager (`NIM_SECRET_NAME`). It is not logged and not included in error text (tested).
- Evidence handoff: every alert carries `evidence_sha256` over the exact rows that triggered it; recompute it at each hop (Firestore, dashboard) to prove nothing changed.

## Interface for Moorthy / Chantell / Peter

`POST /ingest` (header `X-API-Key`): `{location_id, ts, warehouse_temperature_c, warehouse_humidity_percent, cooling_load_percent, sensor_connectivity, [product_sensitivity, estimated_freshness_percent, spoilage_risk]}` returns `{status, rf_label, rf_confidence, rule_label, alert}`. Locations: `JHB-DC01`, `DBN-DC02`, `CPT-DC03`. The first 50 readings per location return `warming_up` (the baseline needs 24 h). Alert state is in memory; persisting to Firestore and the OPEN -> ACKNOWLEDGED -> CLOSED review flow is Moorthy's integration point (`Alert.to_case_json()`).

Chantell: schema checks to run on any real feed before it reaches the model: ranges as in `SensorEvent`, 30-min cadence with no duplicate `(location_id, ts)`, and flat-run detection (frozen values) which doubles as the dropout signal.
Peter: `/ingest` and `/explain` need `INGEST_API_KEY` (constant-time compare); in-memory alert store has no auth per alert or rate limiting yet; the dev key is not for Cloud Run.
