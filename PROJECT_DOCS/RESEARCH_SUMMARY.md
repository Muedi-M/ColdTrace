# ColdTrace — Research, Evaluation & Implementation Summary

**Team ColdTrace · Google Cloud Launchpad BUILD · SDG 3 Good Health and Well-Being**
Muedi Mbambala (AI Research Foundations, lead) · Chantell Masilela (Cloud Data Analytics) · Moorthy R (Cloud Engineering) · Peter Opiyo (Cloud Cybersecurity)

---

## 1. Problem grounding

**Who we build for.** The operations lead at a regional distribution centre (Johannesburg, Durban, Cape Town) who watches several refrigerated storage units, is interrupted constantly, and today learns that a unit failed only after stock is already damaged. Two secondary users depend on the same record: the QA reviewer who confirms or dismisses an exception and releases or destroys stock, and the auditor who later checks that every handoff happened and was not altered.

**Why it matters (evidence).**

| Pain point | Evidence | Source |
|---|---|---|
| Temperature failures are expensive and frequent | Biopharma loses about **US$35 bn a year** to failures in temperature-controlled logistics; **44.6 %** of surveyed organisations reported multiple excursions a year and **16 %** reported them monthly | IQVIA Institute figure, 2019 Biopharma Cold Chain Logistics Survey, reported by [Air Cargo News](https://www.aircargonews.net/?p=1023281) |
| Damage happens in storage, not only in transit | Vaccines were exposed to temperatures above 8 °C at every level of storage in a 10-state study | [Murhekar et al., *Bulletin of the WHO* 2013](https://scielosp.org/article/bwho/2013.v91n12/906-913) |
| Freezing is as common as overheating | A literature review of 45 studies found **33 %** (higher-income) and **37.1 %** (lower-income) of vaccines exposed to below-range temperatures during storage | [CIDRAP summary of the *Vaccine* supplement](https://www.cidrap.umn.edu/public-health/freezing-shortages-among-global-vaccine-challenges) |
| Monitoring data exists but is not reviewed | More than half of health workers did not perform monthly temperature data reviews; some facilities logged exposure above +8 °C lasting 5.9 to 281 hours | [Tanzania cold-chain study, PMC9713142](https://pmc.ncbi.nlm.nih.gov/articles/PMC9713142) |
| South African storage is unstable | Temperature monitoring over 8 months showed government clinic vaccine fridges could not keep stable temperatures | [Western Cape outsourcing study, PMC5357745](https://pmc.ncbi.nlm.nih.gov/articles/PMC5357745) |
| South African clinics report storage problems | 6 of 11 clinics visited had storage problems; one Limpopo clinic fridge was twice as hot as recommended | [Health-e News investigation](https://health-e.org.za/2014/03/10/shots-dark-vaccines-south-africa/) |
| The standard already demands what ColdTrace does | SA National Department of Health SOPs require continuous temperature monitoring connected to an alarm/warning system and records of every excursion and action taken | [NDoH SOP: routine monitoring of vaccine handling](https://knowledgehub.health.gov.za/system/files/elibdownloads/2022-01/SOP_Routine%20Monitoring%20of%20Vaccine%20Handling_%2020122021.pdf) |
| Too many alarms means none are acted on | A health system's environmental monitoring produced about **11,000 excursion alerts a month, of which only 22 % were addressed** | [Rutgers dissertation on temperature-monitoring alarm fatigue](https://rucore.libraries.rutgers.edu/rutgers-lib/65271/) |

**Problem statement.** Cold-chain failures (temperature excursions, compressor/cooling failures and frozen sensors) are discovered late, often after product is lost, because monitoring systems either miss slow failures or raise so many false alarms that people stop reacting, and because the path from alert to a reviewed, closed case is not recorded. ColdTrace's goal is to **shorten the time from failure to a human decision** while keeping false alerts low enough to be trusted, and to **make every handoff provable**.

**User evidence status.** Field interviews are in progress; the guide, survey and evidence log are in [`USER_RESEARCH.md`](USER_RESEARCH.md). The pain points above are hypotheses from desk research until confirmed there.

---

## 2. Solution in one paragraph

ColdTrace watches three storage locations at a 30-minute cadence, detects three exception types (temperature excursion, cooling failure, sensor dropout) with a Random Forest that must beat an SOP rules baseline, seals the evidence with SHA-256, links the exception to the batches and shipments at risk, and takes each case through **assign → human review → close** with a hash-chained event log. NVIDIA NIM writes a grounded triage note for the reviewer, but never decides. An Insights view turns the event log into exception frequency, detection-to-review time, average and median cycle time, throughput, overdue cases and a backlog burndown.

---

## 3. Data design (synthetic, labelled)

| Item | Detail |
|---|---|
| Source | `scripts/generate_data.py` simulator, 2022-01-01 → 2026-10-31, 3 locations, 30-min cadence |
| Volume | **254,160 readings** (84,720 per location), 100 % complete after validation; also batch-loaded to BigQuery `coldtrace_warehouse.telemetry_2022_2026` with SQL checks (`Validation_coldtrace.sql`) |
| Labels | Rows tagged `NONE`, `TEMP_EXCURSION`, `COOLING_FAILURE`, `SENSOR_DROPOUT`; e.g. JHB-DC01 has 3,293 / 1,295 / 976 labelled dropout / cooling / excursion rows |
| Why synthetic | No operator would share real fridge logs and failure records within four weeks; a simulator lets us plant failures with known start times, so detection time can be measured exactly |
| Reference data | `data/reference/` joins locations → batches → shipments (5 batches, 5 shipments, 3 investigations) |
| Thresholds | `config/thresholds.json` (version `2026.11.2`, SHA-256 exposed at `/api/thresholds`): pharma 2–8 °C, chilled food ≤ 2 °C, detector constants, validation ranges, review/close SLAs, change history |

**Validation (data analytics lane, Chantell Masilela).** The checks were defined in BigQuery first (`Validation_coldtrace.sql`: row counts, null critical fields, 2–8 °C excursions per location, cadence gaps and dropout flat runs) and mirrored in the app by `coldtrace/validation.py`. Every reading is checked for unparseable timestamps, unknown locations, missing sensor values, physically impossible values, exact duplicates and conflicting duplicates. Failing rows go to a quarantine table with a reason; cadence gaps and flat runs are reported per location. On the full dataset: **0 rows quarantined, 0 missing readings, 1,030 flat runs ≥ 3 steps** (the dropout signal). The unit tests feed in deliberately corrupted data to prove each check fires. Reference integrity also checks that every out-of-band batch has an investigation and a held shipment.

---

## 4. Can detection be trusted? (evaluation)

Time-ordered split: train 157,824 rows · validation 52,560 · **test 43,776 rows, 283 labelled events**. Alerts are debounced (2 consecutive predictions, confidence ≥ 0.5) and scored per event, not per row, because an operator cares whether a failure was caught and how fast.

| Detector (test) | Macro-F1 (step) | Event recall | Alert precision | Median time-to-detect, excursion / cooling | False alerts per location-day |
|---|---|---|---|---|---|
| Fixed threshold (> 8 °C) | 0.284 | 4.9 % | 37.1 % | 2.25 h / not detected | 0.024 |
| SOP rules baseline | 0.726 | 83.7 % | 75.4 % | 1.5 h / 2.5 h | 0.088 |
| **Random Forest (active)** | **0.810** | **94.3 %** | 73.6 % | **0.5 h / 1.0 h** | 0.106 |

**Reading the result honestly.**
* The model beats the baseline the team agreed on first: +10.6 points of event recall, excursions caught 1 hour earlier and cooling failures 1.5 hours earlier.
* The cost is a slightly higher false-alert rate: 0.106 vs 0.088 per location-day, about one false alert per location every 9–10 days. We judged that acceptable because a missed failure destroys stock, but it is reported, not hidden.
* A fixed > 8 °C alarm misses almost everything: slow drifts, cooling failures and frozen sensors never cross the line. This is why "just set an alarm" does not solve the problem.
* All numbers come from simulated data. They validate the pipeline and the method, not field performance.

**Balanced window benchmark (n = 120).** `scripts/compare_nim.py --per-class 30` scores 24-step evidence windows, 30 per class:

| Detector | Macro-F1 | Recall NONE / EXCURSION / COOLING / DROPOUT | False alarms on NONE |
|---|---|---|---|
| SOP rules | 0.626 | 1.00 / 0.27 / 0.33 / 1.00 | 0 % |
| **Random Forest** | **0.918** | 0.97 / 0.80 / 0.90 / 1.00 | 3.3 % |

**NVIDIA NIM.** The committed n = 120 run used the harness's `mock` provider (0.59 macro-F1), which checks the pipeline but is not a model result. The earlier live run on 8 windows gave Nemotron-3 Ultra 0.64 and Nemotron-3.5 Lightning 0.56 macro-F1, below the rules (0.75) and the Random Forest (0.87) on the same windows, with 100 % valid JSON. Eight windows is too small to rank models, so the live NIM comparison at 120 windows is listed as next work. Conclusion so far: **NIM explains, the Random Forest detects.** NIM writes the grounded triage note for the reviewer; a human closes every case.

---

## 5. Implementation summary

| Layer | What exists | Where |
|---|---|---|
| Detection | Causal features, rules baseline, Random Forest, streaming detector with debounce and SHA-256 evidence sealing | `coldtrace/features.py`, `rules.py`, `model.py`, `service.py` |
| Data quality | Readings validation + quarantine, reference integrity, versioned thresholds | `coldtrace/validation.py`, `thresholds.py`, `config/thresholds.json` |
| Case workflow | Hash-chained event log with created / started / reviewed / completed / due timestamps; review and close SLAs | `coldtrace/cases.py` |
| Insights MVP | Exception frequency by location, detection-to-review, average AND median cycle time, throughput, unresolved and overdue cases, backlog burndown | `GET /api/insights`, Quality & Audit screen |
| AI | NVIDIA NIM client with retries, per-model keys, key redaction; triage note endpoint | `coldtrace/nim.py` |
| Google Cloud | Cloud Run, Artifact Registry, Secret Manager, Firestore, BigQuery (partitioned telemetry + case events), Pub/Sub (alerts and case events → BigQuery subscription; push endpoint for gateways), Cloud Scheduler, Cloud Monitoring, Workload Identity Federation | `terraform/`, `.github/workflows/ci-deploy.yml`, `coldtrace/pubsub.py` |
| Security | API keys (plain or SHA-256-hashed), security headers middleware, model artifact hash check, Gitleaks, CodeQL, Bandit, pip-audit, OWASP ZAP | `coldtrace/security.py`, CI |
| Console | Operations console: home alerts, batches & units, investigations, quality & audit, assign / AI triage / resolve | `frontend/` |

---

## 6. Sustainability and cost

* Cloud Run scales to zero, with instance caps and a budget alert; NIM calls are on demand, so baseline cost stays near zero for the 3 pilot sites.
* BigQuery uses batch `bq load` jobs and a Pub/Sub BigQuery subscription instead of paid streaming inserts; tables are partitioned on `Timestamp`.
* The detector is per-location and stateless across sites, so adding a site adds load linearly.
* Moving to real sensors needs probe calibration, verification of the 30-minute cadence and dropout handling, and QA sign-off of the category bands.

## 7. Limitations and next steps

1. **Field validation.** Replay one real logger export (e.g. a pharmacy fridge CSV) through `coldtrace.validation` and the detector before any claim about real-world accuracy.
2. **Console data.** The three showcase investigations and batches are seeded demo records; live alerts from `/ingest`, replay and fault injection create real cases next to them. Next: drive the console entirely from Firestore cases.
3. **Persistence.** Firestore and BigQuery are switched on by Terraform in Cloud Run; locally the app falls back to memory.
4. **Live NIM evaluation** at 120 windows (the committed n = 120 run used the mock provider), and a reviewer-usefulness rating of the triage notes.
5. **Threshold sign-off.** `config/thresholds.json` is `proposed`; a QA pharmacist should review and sign the bands before production use.
