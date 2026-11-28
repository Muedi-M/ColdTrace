# ColdTrace: catch the failing cold room before the stock is lost

**Capstone brief · Google Cloud Launchpad BUILD · SDG 3 Good Health and Well-Being**
Team ColdTrace: Muedi Mbambala (lead, AI Research Foundations) · Chantell Masilela (Cloud Data Analytics) · Moorthy R (Cloud Engineering) · Peter Opiyo (Cloud Cybersecurity)
Live app: https://coldtrace-app-uxg3hjnrfa-uc.a.run.app · Code: https://github.com/Muedi-M/ColdTrace

## 1. The problem

Insulin, vaccines and biologics must stay between 2 °C and 8 °C; chilled food must stay at or below 2 °C. When a cold room drifts, the person responsible usually finds out at the next shift check or when stock is already compromised. The cost is large: the biopharma industry loses about **US$35 billion a year** to failures in temperature-controlled logistics, and in a 2019 industry survey **44.6 %** of organisations reported multiple excursions a year (IQVIA Institute, via Air Cargo News). Damage happens in storage, not only in transit: a WHO Bulletin study found vaccines exposed to more than 8 °C at every storage level, and a review of 45 studies found a third or more of vaccines exposed to below-range temperatures in storage (CIDRAP). In South Africa, 8-month monitoring showed government clinic fridges could not hold stable temperatures (Western Cape study), even though National Department of Health SOPs already require continuous monitoring with alarms and a record of every excursion and action.

Monitoring alone does not fix this. When data exists, it often goes unreviewed — more than half of health workers in one study did not review monthly temperature logs — and when alarms exist, there are too many: one health system logged about **11,000 environmental excursion alerts a month and addressed 22 %** (Rutgers). A fixed "above 8 °C" alarm misses slow drifts, cooling failures, freezing and dead sensors entirely.

**Who we serve.** The operations lead at a regional distribution centre (Johannesburg, Durban, Cape Town) who watches several units and needs to know, at a glance, which unit is failing and which batches are at risk *now*. The QA reviewer who must confirm or dismiss the exception and release or destroy stock, and the auditor who later checks the record, use the same case.

**Friction points.** (1) Failures are found late. (2) Slow and silent failures never trip a threshold. (3) Alarm fatigue. (4) Nobody knows which batches and shipments are affected. (5) Ownership of an alert is unclear. (6) Proving what happened takes days.

## 2. The solution

ColdTrace is a cloud operations console and API that runs the whole path **detect → identify affected batches → assign → human review → close**, for three storage locations and three exception types.

| Friction | ColdTrace feature |
|---|---|
| Found late | Random Forest detector on 30-minute readings; median time-to-detect **0.5 h** for excursions, **1.0 h** for cooling failures |
| Silent failures | Three exception types — temperature excursion, cooling failure (temperature drifting while cooling load drops), sensor dropout (frozen or missing readings) — plus category bands that also catch freezing |
| Alarm fatigue | Debounced alerts; false alerts per location-day measured and shown beside recall |
| Which stock? | Alert joined to batches and shipments; out-of-band shipments held automatically |
| Ownership | Assignment, review and close SLAs, overdue list |
| Proof | SHA-256-sealed evidence; hash-chained case events with timestamps; one-click audit-chain verification |

**Innovation.** Three things set ColdTrace apart from a temperature alarm: it is evaluated against an explicit baseline at the level operators care about (was the failure caught, and how fast?), it treats the *human handoff* as data (every assignment and review is a timestamped, tamper-evident event feeding cycle-time insights), and it uses generative AI only where it is safe — NVIDIA NIM writes a triage note grounded in sealed evidence, but detection is done by a measured model and a human closes every case.

**Insights MVP.** From the event log: exception frequency by location and type, detection-to-review time, investigation cycle time (average **and** median), throughput per week, unresolved and overdue cases, and a backlog burndown for the scoped window.

## 3. Can detection be trusted?

Synthetic labelled telemetry, 2022–2026, 254,160 readings, time-ordered split; the test period contains **283 labelled failure events**.

| Detector | Event recall | Median time to detect (excursion / cooling) | False alerts per location-day |
|---|---|---|---|
| Fixed > 8 °C alarm | 4.9 % | 2.25 h / missed | 0.024 |
| SOP rules baseline | 83.7 % | 1.5 h / 2.5 h | 0.088 |
| **ColdTrace Random Forest** | **94.3 %** | **0.5 h / 1.0 h** | 0.106 |

The model catches more failures, an hour or more earlier, for about one extra false alert per location every 9–10 days. On a balanced 120-window benchmark the Random Forest scores 0.918 macro-F1 against 0.626 for the rules. A first live NVIDIA NIM comparison (8 windows) placed Nemotron models below both at classification (0.56–0.64), which is why NIM explains rather than detects. All metrics are from simulated data and validate the method, not field accuracy.

## 4. How it is built

* **Google Cloud:** Cloud Run (FastAPI + console), Artifact Registry, Secret Manager (API and NIM keys), Firestore (alert and case state), BigQuery (month-partitioned telemetry; case events via a Pub/Sub BigQuery subscription), Pub/Sub (alerts and case events; push endpoint for sensor gateways), Cloud Scheduler (simulated sensors every 15 minutes), Cloud Monitoring, Workload Identity Federation for keyless deploys — all in Terraform.
* **NVIDIA:** NIM API client with retries, per-model keys and key redaction; grounded triage notes; model comparison harness.
* **Data quality:** BigQuery batch loads and SQL checks (completeness, 2–8 °C excursions, cadence gaps, dropouts), mirrored in the app as validation with quarantine reasons (duplicates, conflicts, missing or impossible values, unknown locations), cadence-gap and flat-run reporting, referential checks across locations → batches → shipments, and a versioned, hashed thresholds file.
* **Security:** hashed API keys, security-header middleware, model artifact hash check, Gitleaks, CodeQL, Bandit, pip-audit and OWASP ZAP in CI.

## 5. Implementation plan

| Week | Outcome | Lead |
|---|---|---|
| 1 (2–8 Nov) | Scope, team rhythm, hackathons | All |
| 2 (9–15 Nov) | Dataset, baseline, Random Forest, evaluation, NIM client | Muedi |
| 3 (16–22 Nov) | Cloud Run, Terraform, CI/CD, security scans, console | Moorthy, Peter |
| 4 (23–28 Nov) | Data validation, insights, Pub/Sub → BigQuery, audit chain, user interviews, submission | Chantell, Muedi, Moorthy, Peter |

Top risks and mitigations: synthetic data may not transfer (report as simulated; validation ready for a real logger export); false alerts erode trust (debounce, publish false-alert rate, versioned thresholds); NIM outage (detection never depends on it); secret leak (Secret Manager, Gitleaks, rotation runbook); cold starts in judging (warm the service before demos; scale-to-zero keeps cost near zero). Full plan, owners and risk register: `PROJECT_DOCS/IMPLEMENTATION_PLAN.md`.

## 6. Impact and sustainability

Every hour earlier is an hour in which stock can be moved to a working unit. ColdTrace runs on free-tier-scale Google Cloud services, keeps the detector per-location and stateless so new sites add load linearly, and moves analytics through batch loads and a Pub/Sub BigQuery subscription instead of paid streaming inserts. The next step is a pilot on one real cold room: replay a month of logger data, measure false alerts per location-day, and have a QA pharmacist sign the threshold file.

**Sources:** IQVIA Institute figure via Air Cargo News (aircargonews.net/?p=1023281); Murhekar et al., Bull WHO 2013; CIDRAP on the *Vaccine* supplement; PMC9713142 (Tanzania); PMC5357745 (Western Cape); SA NDoH SOP, Routine Monitoring of Vaccine Handling (2021); Rutgers dissertation on temperature-monitoring alarm fatigue (rucore 65271). Full links: `PROJECT_DOCS/RESEARCH_SUMMARY.md`.
