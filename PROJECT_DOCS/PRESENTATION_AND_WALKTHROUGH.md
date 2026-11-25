# ColdTrace — Presentation Deck Outline & Walkthrough Script

## Part 1: 10-Slide Presentation Outline (~10 Slides)

### Slide 1 — Title & SDG 3 Alignment
* **Headline:** ColdTrace: Know Before the Product Spoils
* **Subtitle:** Cold-Chain Operations & Spoilage Prevention Console for `JHB-DC01`, `DBN-DC02`, and `CPT-DC03`
* **Key Points:** Supports **SDG 3 (Good Health and Well-Being)** by catching temperature excursions, cooling failures, and sensor dropouts early enough for human intervention.

### Slide 2 — Cold-Chain Problem & Operator Friction
* **Headline:** Why Reactive Monitoring Fails Cold Storage
* **Key Points:**
  * **Late discovery:** Excursions noticed at shift change or after product warming.
  * **Alert fatigue:** Noisy threshold blips cause operators to mute or ignore alerts.
  * **Audit gaps:** Reconstructing timelines, assignments, and evidence hashes by hand slows compliance checks.

### Slide 3 — Category Bands & Simulator Grounding
* **Headline:** Safe Operating Bands & Synthetic Telemetry
* **Key Points:**
  * Category-aware thresholds (`2°C–8°C` for pharma/biologics; `≤ 2°C` for cold/perishables).
  * 30-minute sampling cadence modeled across `cold_chain_labeled_2022_2026.csv` and `sample_14d.csv` to test normal drift, excursions, cooling failures, and sensor dropouts safely.

### Slide 4 — System Architecture
* **Headline:** FastAPI Console + Causal Features + Tamper-Evident Evidence
* **Key Points:**
  * `POST /ingest` computes 24-hour causal rolling features with zero look-ahead leakage.
  * Random Forest and SOP rules run alongside debounced `OPEN → ACKNOWLEDGED → CLOSED` alert state and `evidence_sha256` sealing.
  * Console served directly by FastAPI (`127.0.0.1:8081` local testing, `coldtrace-app-00022-b2k` on Cloud Run).

### Slide 5 — Live Console & Triage UX
* **Headline:** Calm Control-Room Triage & Reconciled Metrics
* **Key Points:**
  * Category chips, band filters, and batch/unit status views (`Flagged`, `Watch`, `Cleared`).
  * Reconciled KPI counts (`Held`, `Assigned`, `Open`), unit temperatures matched to flagged batches, and responsive evidence hash wrapping.

### Slide 6 — NVIDIA NIM Incident Explanation Layer
* **Headline:** Human-Reviewed AI Explanations, Never Blind Automation
* **Key Points:**
  * Rules and Random Forest handle primary anomaly detection; **NVIDIA NIM** generates optional incident explanations/triage notes.
  * Every AI output is labeled **AI-GENERATED, REVIEW BEFORE ACTING** and never auto-closes or auto-acknowledges cases.

### Slide 7 — Evaluation Results ($n = 120$)
* **Headline:** Benchmarking Detection vs. Rules & NIM ($n = 120$)
* **Key Points:**
  * Evaluated across 120 test windows (`30` per class: `TEMP_EXCURSION`, `COOLING_FAILURE`, `SENSOR_DROPOUT`, `NONE`).
  * **Random Forest (`0.918` macro-F1)** outperforms **SOP rules (`0.626` macro-F1)**, confirming why NIM is scoped to explanation rather than primary detection.

### Slide 8 — GCP Architecture, Data & Storage Modes
* **Headline:** Serverless GCP Foundation with Explicit Runtime Modes
* **Key Points:**
  * Cloud Run (`coldtrace-app-00022-b2k`), Firestore, BigQuery (`coldtrace_warehouse` batch `bq load` + `Timestamp` partitions), Pub/Sub (`telemetry_events`), and Secret Manager.
  * `/healthz` reports active runtime storage and Pub/Sub status cleanly.

### Slide 9 — Security, IAM & Cost Guardrails
* **Headline:** Keyless CI/CD, Least Privilege & Zero-Extra-Cost Operation
* **Key Points:**
  * GitHub Actions + Workload Identity Federation (no JSON keys), constant-time `X-API-Key` auth, read-only security audit roles, and Gitleaks/pre-push checks.
  * Scale-to-zero Cloud Run defaults (`--min-instances 0`) and `$1/month` budget guardrails.

### Slide 10 — Team Ownership, Risks & Post-BUILD Roadmap
* **Headline:** Clear RACI, Risk Mitigations & Multi-Site Path
* **Key Points:**
  * Defined owners across DevOps/Cloud (Moorthy R), Data Analytics (Chantell N.), AI/Cloud Foundation (Mbambala T), and Security Review (Peter O.).
  * Post-BUILD: finalize deck/video links, calibrate physical sensors across `JHB-DC01`, `DBN-DC02`, and `CPT-DC03`, and expand toward 50 sites.

---

## Part 2: 3–5 Minute Walkthrough Script (~4:15 Target)

* **0:00–0:35 — Intro & Problem:**
  "Hi, I'm Moorthy walking through **ColdTrace**, our cold-chain operations console built for SDG 3 across `JHB-DC01`, `DBN-DC02`, and `CPT-DC03`. Cold-chain teams face late excursion discovery, alert fatigue from noisy thresholds, and slow manual audit trails."
* **0:35–1:45 — Live Console, Replay & Batch Triage:**
  "Opening the live Cloud Run app (`https://coldtrace-app-uxg3hjnrfa-uc.a.run.app/`), we replay `sample_14d.csv` and filter by category band (`2°C–8°C` vs. `≤ 2°C`) and status. Notice how KPI counts (`Held`, `Assigned`, `Open`) and unit temperatures stay aligned with flagged batches."
* **1:45–2:45 — Evidence Hash & NIM Incident Note:**
  "Selecting an active alert shows its `evidence_sha256` seal over the triggering sensor window and moves it through `OPEN → ACKNOWLEDGED → CLOSED`. Clicking **Generate AI Note** calls NVIDIA NIM for an explanation clearly marked **AI-GENERATED, REVIEW BEFORE ACTING**—while Random Forest and rules do the primary detection."
* **2:45–3:30 — Evaluation ($n = 120$) & `/healthz` Storage Mode:**
  "On our $n = 120$ benchmark (`30` per class), Random Forest reaches `0.918` macro-F1 versus `0.626` for rules. Checking `/healthz` also confirms runtime storage and Pub/Sub modes (`USE_FIRESTORE`, `USE_BIGQUERY`, `telemetry_events`) without forcing paid always-on instances."
* **3:30–4:15 — Security, Cost & Next Steps:**
  "Everything is provisioned via Terraform with keyless WIF CI/CD, Secret Manager, and scale-to-zero cost guardrails. Next after BUILD, we link our final deck and video, complete per-member commits, and pilot calibrated sensors before multi-site rollout."
