# ColdTrace — Research & Evaluation Summary

## 1. Problem Grounding & Operational Context
* **Cold-Chain Spoilage Risk:** Vaccines, biologics, medicines, and perishable goods degrade rapidly when storage temperatures drift outside safe bands (`2°C–8°C` for pharmaceuticals/biologics; `≤ 2°C` for cold/perishables), compressor/cooling units fail, or sensor dropouts obscure real conditions.
* **Multi-Site Scope:** Designed for regional cold-chain distribution operations (`JHB-DC01`, `DBN-DC02`, `CPT-DC03`) supporting **SDG 3 (Good Health and Well-Being)** by flagging drift early enough for human intervention before batches spoil.
* **Key Operational Friction Points:**
  * **Late detection:** Issues discovered at shift change or after product warming.
  * **Alert fatigue:** Noisy threshold blips causing operators to ignore or mute alerts.
  * **Audit trail gaps:** Manual effort required to reconstruct timelines, assignments, and evidence hashes during QA/compliance reviews.

## 2. Synthetic Telemetry & Simulator Design
* **Why Simulated Telemetry:** Production facility telemetry and proprietary batch-loss logs are sensitive and not publicly available for reproducible benchmarking.
* **Simulator Behavior (`cold_chain_labeled_2022_2026.csv` & `sample_14d.csv`):** Models 30-minute cold-room readings, rolling temporal features, safe operating bands, and labeled fault regimes (`NONE`, `TEMP_EXCURSION`, `COOLING_FAILURE`, `SENSOR_DROPOUT`) so evaluation covers both true anomalies and normal/noisy baselines.

## 3. Model & NIM Evaluation Results ($n = 120$)
Evaluated on test windows (`30` samples per class across `TEMP_EXCURSION`, `COOLING_FAILURE`, `SENSOR_DROPOUT`, and `NONE`, total $n = 120$):

* **Random Forest (`0.918` macro-F1):** Strongest overall detector (`0.97` NONE recall, `0.80` excursion recall, `0.90` cooling-failure recall, `1.00` sensor-dropout recall).
* **SOP Rules Baseline (`0.626` macro-F1):** Deterministic threshold baseline (`1.00` NONE recall, `1.00` dropout recall, lower recall on subtle excursion/cooling patterns), useful as a transparent guardrail.
* **NVIDIA NIM Role:** Positioned as an **incident-explanation and triage-summary layer** (explicitly labeled for human review before action), rather than the primary anomaly detector—keeping detection reliable and zero-cost even when external LLM endpoints are rate-limited or offline.

## 4. Sustainability, Cost & Real-Sensor Calibration
* **Free-Tier / Low-Cost Operation:** Serverless Cloud Run (scale-to-zero without forced always-on paid instances), lightweight payloads, and optional/on-demand NIM calls keep baseline operating costs near zero across pilot sites (`3` sites scaling toward `50` sites with budget alerts enabled).
* **Moving to Real Sensors:** Replacing synthetic feeds requires physical probe calibration, verification of 30-minute sampling cadence and connectivity/dropout handling, and site-specific validation of category temperature bands.
