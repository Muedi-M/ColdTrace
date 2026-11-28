Markdown
# ❄️ ColdTrace — AI Cold-Chain Operations & Spoilage Prevention Console

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![scikit-learn](https://img.shields.io/badge/Random%20Forest-F7931E?logo=scikitlearn&logoColor=white)
![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM-76B900?logo=nvidia&logoColor=white)
![Cloud Run](https://img.shields.io/badge/Google%20Cloud-Run-4285F4?logo=googlecloud&logoColor=white)
![Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC?logo=terraform&logoColor=white)
![SDG 3](https://img.shields.io/badge/SDG-3%20Good%20Health%20%26%20Well--Being-4C9F38)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**Know before the product spoils.**

- **Live Console:** <https://coldtrace-app-644777661209.us-central1.run.app>
- **Research & Evaluation Summary:** [PROJECT_DOCS/RESEARCH_SUMMARY.md](PROJECT_DOCS/RESEARCH_SUMMARY.md)
- **Presentation Deck (8 slides):** `PROJECT_DOCS/ColdTrace — Cold-Chain Operations Console (1).pptx`
- **Recorded Walkthrough (≤ 5 min):** *Add walkthrough link before final submission*
- **License:** MIT License (see [18. License](#18-license))

ColdTrace monitors refrigerated storage facilities in real time, detects temperature excursions, cooling failures, and sensor dropouts before spoilage occurs, links alerts to at-risk inventory batches, and generates grounded AI incident analyses via NVIDIA NIM.

---

## About ColdTrace

Vaccines, medicines, and perishable food lose value—and sometimes safety—the moment a cold room drifts out of its safe temperature band. In many distribution centers, problems such as a door left open, a failing compressor, or a frozen sensor are noticed only after inventory is already damaged, and fixed-threshold alarms fire so often that operators learn to ignore them.

ColdTrace is a cold-chain operations console that closes that gap. It ingests sensor readings every 30 minutes, scores them with a Random Forest anomaly detector alongside an SOP threshold baseline, and raises debounced alerts that move through an `OPEN → ACKNOWLEDGED → CLOSED` lifecycle. Each alert is sealed with a SHA-256 evidence hash over the exact triggering readings, so the record is tamper-evident. Operators can optionally request an NVIDIA NIM incident note, which is always labeled **AI-GENERATED, REVIEW BEFORE ACTING** and never acts on a case by itself.

**What it gives you**

- Early detection of temperature excursions, cooling failures, and sensor dropouts across multiple sites.
- Fewer false alarms through causal rolling features and alert debouncing.
- A calm, dark-mode control-room dashboard served directly by FastAPI.
- Tamper-evident evidence trails for quality reviewers and compliance auditors.
- A serverless, free-tier-first Google Cloud foundation, defined in Terraform and deployed through keyless CI/CD.

**Built with:** Python 3.12, FastAPI, scikit-learn (Random Forest), NVIDIA NIM, Google Cloud Run, Firestore, BigQuery, Pub/Sub, Secret Manager, Terraform, and GitHub Actions with Workload Identity Federation.

---

## 📑 Table of Contents

0. [About ColdTrace](#about-coldtrace)
1. [Problem, Audience & SDG Alignment](#1-problem-audience--sdg-alignment)
2. [System Architecture](#2-system-architecture)
3. [Repository Structure](#3-repository-structure)
4. [Detection Model & Exception Types](#4-detection-model--exception-types)
5. [Team, Roles & Responsibilities](#5-team-roles--responsibilities)
6. [IAM Access Matrix & Service Accounts](#6-iam-access-matrix--service-accounts)
7. [CI/CD & Infrastructure as Code](#7-cicd--infrastructure-as-code)
8. [Cost, Quota & Free-Tier Guardrails](#8-cost-quota--free-tier-guardrails)
9. [Data Warehouse Conventions](#9-data-warehouse-conventions)
10. [Environment Configuration & Secrets](#10-environment-configuration--secrets)
11. [Local Setup & Running Instructions](#11-local-setup--running-instructions)
12. [Google Cloud Run Deployment](#12-google-cloud-run-deployment)
13. [API Reference](#13-api-reference)
14. [Security & Design Guardrails](#14-security--design-guardrails)
15. [Security Practices & Secret Handling](#15-security-practices--secret-handling)
16. [Ownership Summary (RACI)](#16-ownership-summary-raci)
17. [Implementation Plan, Risk Register & Roadmap](#17-implementation-plan-risk-register--roadmap)
18. [License](#18-license)

---

## 1. Problem, Audience & SDG Alignment

| | |
|---|---|
| **Target audience** | Cold-chain operations leads, quality reviewers, and compliance auditors managing regional distribution centers: `JHB-DC01` (Johannesburg), `DBN-DC02` (Durban), `CPT-DC03` (Cape Town). |
| **Problem** | Temperature excursions outside safe bands (such as above 8 °C or below 2 °C for temperature-sensitive pharmaceuticals/biologics, and above 2 °C for cold/perishable goods), compressor failures, and frozen sensors are often discovered only after inventory is damaged, while high false-alarm rates cause alert fatigue. |
| **SDG alignment** | **SDG 3 — Good Health and Well-Being.** Prevents spoilage of temperature-sensitive vaccines, medicines, and perishable food by enabling human intervention within minutes. |

### 1.1 Cold-Chain Evidence & Operational Context

- **Global vaccine cold-chain wastage (WHO / UNICEF):** World Health Organization and UNICEF cold-chain guidance highlights that temperature excursions and cold-chain breaks remain a major driver of vaccine wastage globally, especially where monitoring gaps or delayed responses prevent timely stock triage.
- **Regional & perishable cold-chain losses (South Africa):** Distribution centers operating across warm transit corridors and multi-site storage (`JHB-DC01`, `DBN-DC02`, `CPT-DC03`) face compounding risks from ambient heat, power/compressor fluctuations, and high spoilage costs across temperature-sensitive pharmaceuticals, biologics, and chilled foods.
- **Single-excursion cost impact:** Even a single unmitigated excursion can jeopardize high-value batches, trigger shipment holds or quarantine investigations, and require costly batch re-testing or disposal—making early detection during the drift window critical.
- *(Detailed citations and evaluation findings are maintained in `PROJECT_DOCS/RESEARCH_SUMMARY.md`.)*

### 1.2 User Evidence & Pain-Point Friction Table

Operator walkthroughs across cold-store and distribution workflows highlight three recurring bottlenecks:

- **Late discovery:** *"We find out at shift change—or when someone opens the door and sees the product already warmed up."*
- **False-alarm fatigue:** *"When noisy threshold blips fire every hour, operators start muting or ignoring alerts until a real problem hits."*
- **Audit trail gaps:** *"When QA asks what happened at 02:00 and who checked it, stitching together logs and notes takes hours."*

| Friction Point | Operational Impact | ColdTrace Feature Addressing It |
|---|---|---|
| **Found late** | Excursions are caught after spoilage or at shift handover | 30-minute telemetry ingestion with rolling features, Random Forest + SOP baseline detection, and immediate alert triage |
| **False-alarm fatigue** | Operators tune out repetitive or transient threshold blips | Causal rolling features, alert debouncing, and clear batch/unit status filtering (`Flagged`, `Watch`, `Cleared`) |
| **No audit trail** | Slow, manual reconstruction during quality/compliance reviews | `OPEN → ACKNOWLEDGED → CLOSED` alert lifecycle, assignment tracking, and SHA-256 tamper-evident evidence records |

### 1.3 Synthetic Telemetry & Cold-Room Simulator Design

Because live production facility telemetry and confidential spoilage logs are not publicly exposed, ColdTrace uses a deterministic/configurable **synthetic sensor and cold-room simulator** (`cold_chain_labeled_2022_2026.csv` and generator scripts) to test edge cases safely:

- **Realistic cold-room dynamics:** Models nominal temperatures, 30-minute sampling cadence, diurnal/ambient drift, and category-aware safe bands (`2°C–8°C` for pharma/biologics; `≤ 2°C` for cold/perishables).
- **Fault & excursion scenarios:** Reproduces over-temperature excursions, near-freeze/freeze drops, compressor/cooling faults, and stuck/dropout sensor readings so evaluation tests both true excursions and non-excursion noise without risking real inventory.

---

## 2. System Architecture

ColdTrace combines a **Random Forest streaming anomaly detector**, **SHA-256 tamper-evident evidence hashing**, an **NVIDIA NIM incident explanation client**, and a **calm control-room web dashboard** served directly by FastAPI, deployed on a serverless, free-tier-first Google Cloud foundation.

### 2.1 Application data flow

```mermaid
flowchart LR
    A[Sensor reading<br/>every 30 min] -->|POST /ingest| B[FastAPI<br/>api.py]
    B --> C[features.py<br/>24h causal rolling features]
    C --> D[model.py<br/>Random Forest]
    C --> E[rules.py<br/>SOP threshold baseline]
    D --> F[service.py<br/>debounce + SHA-256 evidence seal]
    E --> F
    F --> G[(Alerts<br/>OPEN / ACK / CLOSED)]
    G --> H[Operations Console<br/>frontend/index.html]
    G -->|POST /alerts/id/explain| I[nim.py<br/>NVIDIA NIM]
    I -->|AI-GENERATED note<br/>review before acting| H
2.2 Cloud platform architecture
Code snippet
flowchart TB
    subgraph DEV[Delivery pipeline]
        GH[GitHub repository] -->|push / PR| GHA[GitHub Actions<br/>ci-deploy.yml]
        GHA -->|OIDC token, keyless| WIF[Workload Identity Federation]
        WIF -->|impersonates| CICD[coldtrace-cicd-sa]
        TF[Terraform IaC] -.->|provisions| GCP
    end

    CICD -->|push image| AR[Artifact Registry]
    CICD -->|deploy revision| CR

    subgraph GCP[Google Cloud project]
        AR --> CR[Cloud Run<br/>coldtrace-app<br/>runs as coldtrace-runtime-sa]
        SCH[Cloud Scheduler] -->|trigger| PS[Pub/Sub]
        PS -->|push / pull| CR
        CR <--> FS[(Firestore<br/>alert state)]
        CR -->|read / query| BQ[(BigQuery<br/>coldtrace_warehouse)]
        SM[Secret Manager] -->|INGEST_API_KEY<br/>NVIDIA_API_KEY| CR
        CR --> LOG[Cloud Logging & Monitoring]
        AUD[Cloud Audit Logs] --> LOG
    end

    CR -->|explain alert| NIM[NVIDIA NIM]
    SENS[Cold-room sensors / replay scripts] -->|X-API-Key| CR
    ANALYST[Data analyst<br/>bq load batch jobs] --> BQ
    OPS[Operations console users] --> CR
    SEC[Security reviewer<br/>read-only audit] -.-> LOG
2.3 Component responsibilities
Component	Purpose
FastAPI (api.py)	Serves the dashboard, authenticates requests, exposes ingest/alert/explain endpoints.
Feature engine (features.py)	Causal 24-hour rolling features; no look-ahead leakage.
Detector (model.py, rules.py)	Random Forest classifier plus SOP fixed-threshold baseline for comparison.
Service layer (service.py)	Streaming state, debouncing, alert lifecycle, and SHA-256 evidence sealing.
NIM client (nim.py)	Generates strict-JSON, schema-validated incident notes via NVIDIA NIM.
Cloud Run	Scale-to-zero container serving API and web UI.
Pub/Sub + Cloud Scheduler	Serverless scheduled and asynchronous pipelines.
Firestore	Persistent alert and case state (USE_FIRESTORE).
BigQuery (coldtrace_warehouse)	Partitioned telemetry and anomaly history (coldtrace_warehouse.telemetry_2022_2026).
Secret Manager	Holds INGEST_API_KEY and NVIDIA_API_KEY; injected at runtime.
Artifact Registry	Stores container images built by CI/CD.
Terraform	Declares infrastructure, IAM bindings, budgets, and guardrails.
GitHub Actions + WIF	Keyless build, push, and deploy via .github/workflows/ci-deploy.yml.
3. Repository Structure
Plaintext
coldtrace/
├── README.md               # Project overview, team, setup & submission links
├── LICENSE                 # MIT License
├── env.example             # Sample environment variables (never commit .env)
├── PROJECT_DOCS/           # Research summary & 8-slide presentation deck
├── terraform/              # Infrastructure as Code (project, IAM, WIF, budget, services)
├── .github/
│   └── workflows/
│       └── ci-deploy.yml   # Single pipeline: tests, Terraform validate, WIF deploy to Cloud Run
└── Backend/
    ├── coldtrace/
    │   ├── api.py          # FastAPI server, dashboard routes, auth & NIM endpoints
    │   ├── features.py     # Causal rolling features (24h baseline window)
    │   ├── model.py        # Random Forest classifier & model artifact loader
    │   ├── rules.py        # SOP fixed-threshold baseline detector
    │   ├── service.py      # Streaming state, debouncing & SHA-256 evidence sealing
    │   ├── nim.py          # NVIDIA NIM client with strict JSON schema validation
    │   └── evaluate.py     # Event-level recall, TTD & false-alert metrics
    ├── frontend/
    │   ├── index.html      # Operations console UI
    │   └── app.js          # Console state, replay, triage & filtering logic
    ├── data/
    │   └── cold_chain_labeled_2022_2026.csv # Primary 2022–2026 telemetry dataset (254,160 rows)
    ├── artifacts/          # Trained Random Forest model & evaluation artifacts
    ├── scripts/            # Data generation, training/eval, replay & NIM benchmark scripts
    ├── tests/              # Automated unit tests (pytest)
    ├── Dockerfile          # Production container for Google Cloud Run
    └── requirements.txt    # Python 3.12 dependencies
4. Detection Model & Exception Types
Exception type	Sensor signature	Operational action
TEMP_EXCURSION	Temperature leaves the safe band (door left open / power loss); cooling load rises.	Inspect unit immediately; relocate or protect at-risk batches.
COOLING_FAILURE	Temperature drifts upward while cooling load is abnormally low (compressor fault).	Dispatch maintenance; transfer high-sensitivity inventory.
SENSOR_DROPOUT	Sensor connectivity drops and temperature/humidity readings freeze.	Verify temperature manually; treat unit status as unknown.
Benchmark results
Metric	Result
Random Forest event recall	94%
Median excursion time-to-detect (TTD)	0.5 h
Cooling failure TTD	1.0 h
False alerts	~0.11 per location-day
Note: These metrics are derived from simulated data to validate pipeline performance. In the 
𝑛
=
120
n=120 test-window benchmark (30 per class), Random Forest achieved 0.918 macro-F1 vs. 0.626 for rules, supporting NIM as the human-reviewed incident-explanation layer rather than the primary anomaly detector.

5. Team, Roles & Responsibilities
Member	Role	Primary focus
Moorthy R	DevOps & Cloud Owner	GCP project, billing, Terraform, CI/CD, secrets, reliability
Chantell Ntokozo	Data Analyst	BigQuery data loading, partition-aware querying, telemetry validation
Mbambala T	AI & Cloud Foundation Engineer	AI/ML pipeline, container builds, Cloud Run, Pub/Sub, Scheduler, Firestore
Peter Opiyo	Cyber Security Reviewer	Read-only audit of IAM, WIF, logs, monitoring and evidence integrity
5.1 DevOps & Cloud Owner — Moorthy R
GitHub: @MOORTHYrm

Project Owner and Billing Account Administrator.

Owns the GCP project, billing account, budget guardrails, Terraform IaC, keyless GitHub Actions CI/CD (ci-deploy.yml with WIF), Secret Manager rotation, and production reliability.

Delivers local/WSL environment setup, API workflow endpoints, full-stack console integration, and Cloud Run deployments.

5.2 Data Analyst — Chantell Ntokozo
GitHub: @ntokozochantell396-lab

Holds roles/bigquery.jobUser (project-level) and roles/bigquery.dataEditor (scoped to coldtrace_warehouse).

Loads telemetry via free batch bq load jobs, enforces Timestamp partition filters, and validates 30-minute cadence, schema conformity, and flat-run sensor dropouts.

5.3 AI & Cloud Foundation Engineer — Mbambala T
GitHub: @Muedi-M

Holds project-level run.developer, artifactregistry.writer, pubsub.editor, cloudscheduler.admin, datastore.user, bigquery.jobUser, bigquery.dataViewer, secretmanager.viewer (metadata only), and iam.serviceAccountUser.

Builds and deploys Cloud Run revisions, maintains serverless Pub/Sub/Scheduler/Firestore/BigQuery pipelines, preserves scale-to-zero guardrails, and delivers ML/NIM integration.

5.4 Cyber Security Reviewer — Peter Opiyo
GitHub: @PeterOpiyo240

Holds read-only roles (iam.securityReviewer, logging.viewer, logging.privateLogViewer, monitoring.viewer, secretmanager.viewer, bigquery.dataViewer, bigquery.jobUser).

Audits IAM bindings, WIF trust rules, authentication rejections, Cloud Audit Logs, Cloud Monitoring alerts, and evidence_sha256 integrity without write access or raw secret values.

6. IAM Access Matrix & Service Accounts
6.1 Human access matrix
Role	Moorthy R	Chantell N.	Mbambala T	Peter O.
Project Owner	✅			
Billing Account Administrator	✅			
bigquery.jobUser		✅	✅	✅
bigquery.dataEditor (coldtrace_warehouse only)		✅		
bigquery.dataViewer			✅	✅
run.developer			✅	
artifactregistry.writer			✅	
pubsub.editor			✅	
cloudscheduler.admin			✅	
datastore.user			✅	
iam.serviceAccountUser			✅	
secretmanager.viewer (metadata only)			✅	✅
iam.securityReviewer				✅
logging.viewer / logging.privateLogViewer				✅
monitoring.viewer				✅
6.2 Service accounts
Service account	Used by	Permissions (least privilege)
coldtrace-runtime-sa	Cloud Run service	Firestore, Pub/Sub, BigQuery (read/query), Cloud Logging & Monitoring, and only the required Secret Manager secrets.
coldtrace-cicd-sa	GitHub Actions	Authenticates keylessly via Workload Identity Federation; pushes images to Artifact Registry and deploys Cloud Run revisions. No long-lived keys.
7. CI/CD & Infrastructure as Code
Owner: Moorthy R (with Mbambala T for build and deploy specifics)

The pipeline lives in .github/workflows/ci-deploy.yml:

Plaintext
git push ──► GitHub Actions (ci-deploy.yml) ──► OIDC token ──► Workload Identity Federation
                                                                      │
                                                         impersonate coldtrace-cicd-sa
                                                                      │
                                        ┌─────────────────────────────┴───────────────┐
                                        ▼                                             ▼
                              Build & push image                          Deploy Cloud Run revision
                              to Artifact Registry                        (runs as coldtrace-runtime-sa)
No service-account JSON keys exist in the repository or CI; GitHub authenticates via short-lived OIDC tokens.

WIF trust rules are scoped to this repository (assertion.repository == 'Muedi-M/ColdTrace') and reviewed by Peter Opiyo.

Terraform declares APIs, service accounts, IAM bindings, WIF, budget alerts, and Cloud Run guardrails.

7.1 Pipeline stages
Code snippet
flowchart LR
    PR[Pull request or push] --> T[test-and-validate<br/>pytest + terraform fmt/validate]
    T --> G{Tests green?}
    G -->|pull request| M[Eligible to merge]
    G -->|push to main| DEP[deploy<br/>WIF to Artifact Registry to Cloud Run]
7.2 Workflow: ci-deploy.yml
Job	Triggers	What it does	Blocks merge?	Owner
test-and-validate	push to main, pull request, manual	Installs dependencies, runs pytest, then Terraform fmt and validate	Yes	Moorthy R
deploy	push to main (after test-and-validate passes), manual	Authenticates through WIF, builds and pushes the image to Artifact Registry, deploys a new Cloud Run revision	n/a (runs after merge)	Moorthy R / Mbambala T
7.3 GitHub secrets & branch protection
Configure in repository Settings → Secrets and variables → Actions:

GCP_PROJECT_ID

GCP_WIF_PROVIDER

GCP_CICD_SA

Production runtime keys (INGEST_API_KEY, NVIDIA_API_KEY) live in Secret Manager and are injected at runtime. Enable branch protection on main requiring pull requests and the test-and-validate check to pass, and disallowing force pushes/deletions.

8. Cost, Quota & Free-Tier Guardrails
Guardrail	Setting	Owner
Monthly budget	Budget cap & alert thresholds	Moorthy R
Cloud Run idle cost	--min-instances 0 (scale-to-zero)	Moorthy R / Mbambala T
Cloud Run scaling & concurrency	Bounded instances/concurrency & memory limits	Moorthy R / Mbambala T
BigQuery loading	Free batch bq load only; no streaming inserts	Chantell Ntokozo
BigQuery querying	Partition filter on Timestamp; byte and daily query limits	Chantell Ntokozo
Secrets	Secret Manager only; no plaintext access for engineers	Moorthy R / Peter Opiyo
Cost & quota review	Ongoing monitoring of usage and quotas	Moorthy R
9. Data Warehouse Conventions
Dataset: coldtrace_warehouse (BigQuery)

Load method: Use free batch load jobs (bq load) rather than streaming inserts.

Partitioning: Tables are partitioned on Timestamp; queries filter on Timestamp to control scan volume.

SQL
SELECT Storage_Location_ID, AVG(Warehouse_Temperature_C) AS avg_temp
FROM `coldtrace_warehouse.telemetry_2022_2026`
WHERE Timestamp BETWEEN TIMESTAMP('2026-11-01') AND TIMESTAMP('2026-11-14')
GROUP BY Storage_Location_ID;
Access: Only the Data Analyst holds dataset-scoped write access (dataEditor); other roles and Cloud Run runtime operate read-only.

Dataset & Validation Summary:

Primary historical dataset: cold_chain_labeled_2022_2026.csv (coldtrace_warehouse.telemetry_2022_2026 — 254,160 records at 30-minute intervals across JHB-DC01, DBN-DC02, and CPT-DC03, 100% synthetic).

Validation checks: Verified required columns, timestamp continuity, non-null critical fields, and labeled exception distributions (NONE, SENSOR_DROPOUT, COOLING_FAILURE, TEMP_EXCURSION), plus reconciliation between operational state and warehouse tables.

Known limitations: Synthetic telemetry and fault injection represent simulated cold rooms rather than uncalibrated physical IoT probes; warehouse columns (Warehouse_Temperature_C, Warehouse_Humidity_Percent, Cooling_Load_Percent, Sensor_Connectivity, Exception_Type, Storage_Location_ID, Timestamp) are enforced in SQL validation.

10. Environment Configuration & Secrets
Secrets are injected via environment variables (locally via Backend/.env, in production via Secret Manager bound to Cloud Run) and are never committed to source control.

Variable	Required	Description
INGEST_API_KEY	✅ Yes	Shared API key required in the X-API-Key header for /ingest, /alerts/{id}/explain, and case mutation routes.
NVIDIA_API_KEY	✅ Yes	NVIDIA NGC API key used by coldtrace/nim.py to generate grounded incident notes.
NIM_MODEL	Optional	NVIDIA NIM model ID (defaults to nim.DEFAULT_MODELS[0]).
NIM_TIMEOUT	Optional	Request timeout in seconds for NVIDIA NIM calls (default: 120).
MODEL_PATH	Optional	Path to the trained Random Forest .joblib artifact.
11. Local Setup & Running Instructions
Prerequisites
Python 3.12+ (WSL Ubuntu 24.04, Linux, or macOS)

Step-by-step local launch
Create and activate a virtual environment

Bash
cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
Configure environment variables

Bash
cp ../env.example .env
# Set INGEST_API_KEY and NVIDIA_API_KEY in .env
export $(grep -v '^#' .env | xargs)
Start the full-stack server (API + web dashboard)

Bash
uvicorn coldtrace.api:app --reload --port 8000
Operations Console UI: http://localhost:8000

Interactive API docs (Swagger): http://localhost:8000/docs

Run unit tests

Bash
pytest -q tests
12. Google Cloud Run Deployment
The container packages the FastAPI backend and frontend console together and runs on Cloud Run with scale-to-zero (--min-instances 0) when idle. Production deployments run automatically via .github/workflows/ci-deploy.yml; manual deployment for bootstrap/troubleshooting:

Bash
cd Backend
gcloud run deploy coldtrace-app \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 3 \
  --concurrency 10 \
  --memory 512Mi \
  --service-account coldtrace-runtime-sa@<PROJECT_ID>.iam.gserviceaccount.com \
  --set-secrets "INGEST_API_KEY=INGEST_API_KEY:latest,NVIDIA_API_KEY=NVIDIA_API_KEY:latest"
13. API Reference
Method & path	Auth (X-API-Key)	Purpose
GET /	Public	Serves the ColdTrace Operations Console web UI.
GET /healthz	Public	Health check and active storage / Pub/Sub status.
POST /ingest	Required	Ingests a 30-min sensor reading, updates 24h causal rolling features, and raises alerts.
POST /alerts/{id}/explain	Required	Calls NVIDIA NIM to produce a schema-validated explanation (AI-GENERATED, REVIEW BEFORE ACTING) grounded in evidence_sha256.
GET /api/locations	Optional	Returns current status and latest telemetry for JHB-DC01, DBN-DC02, and CPT-DC03.
GET /api/alerts	Optional	Lists detected alerts with evidence_sha256 and lifecycle state (OPEN, ACKNOWLEDGED, CLOSED).
POST /api/alerts/{id}/ack	Required	Transitions an alert from OPEN to ACKNOWLEDGED.
POST /api/alerts/{id}/close	Required	Transitions an alert to CLOSED.
POST /api/demo/replay	Required	Replays cold_chain_labeled_2022_2026.csv into the streaming detector and refreshes UI state.
14. Security & Design Guardrails
AI safety: Primary anomaly detection never depends on the LLM. Every NVIDIA NIM note is labeled AI-GENERATED, REVIEW BEFORE ACTING and never auto-acknowledges or auto-closes alerts.

Tamper-evident evidence: Each alert computes a deterministic evidence_sha256 hash over triggering sensor records.

Authentication & secrets: Constant-time X-API-Key verification; secrets stored in Secret Manager and injected at runtime (secretmanager.viewer metadata-only for engineers/auditors).

Keyless CI/CD & least privilege: GitHub Actions uses OIDC + Workload Identity Federation with no JSON keys; IAM is least-privilege with read-only security auditing.

Persistence: Firestore (USE_FIRESTORE) persists alert state across instances/restarts when configured, with clean fallback/diagnostics reported in /healthz.

15. Security Practices & Secret Handling
Never commit .env or real secrets; keep env.example placeholder-only and enable GitHub secret scanning and push protection.

Rotate secrets via Secret Manager versions and roll out new Cloud Run revisions reading :latest, disabling superseded versions after verification.

Before pushing changes, run local checks as applicable:

Bash
cd Backend && pytest -q tests && cd ..
gitleaks detect --source . --redact --verbose
terraform -chdir=terraform fmt -check -recursive
16. Ownership Summary (RACI)
R = Responsible, A = Accountable, C = Consulted, I = Informed

Area	Moorthy R	Chantell N.	Mbambala T	Peter O.
GCP project, billing & budget guardrails	A/R	I	I	I
Terraform IaC	A/R		C	C
GitHub Actions CI/CD (ci-deploy.yml) & WIF	A/R		C	C
Secret Manager & rotation	A/R		I	C
Container build & Cloud Run deploy	A		R	I
Pub/Sub, Scheduler, Firestore pipelines	A		R	I
AI model, NIM integration & evaluation	I	C	A/R	I
BigQuery loading (bq load) & schema validation	I	A/R	C	I
Partition-aware querying & trend validation	I	A/R	C	I
IAM, WIF & audit-log review	C		C	A/R
Monitoring alerts & evidence integrity review	C		C	A/R
Secret handling, rotation & leak response	A/R		I	R
Branch protection & required checks	A/R		C	C
Production reliability & cost/quota oversight	A/R		R	C
17. Implementation Plan, Risk Register & Roadmap
17.1 Key Milestones
Core Pipeline & UI Polish: Category-aware safe bands (2°C–8°C pharma/biologics; ≤ 2°C perishables), 24h causal rolling features, OPEN → ACKNOWLEDGED → CLOSED workflow, evidence_sha256 sealing, and replay against cold_chain_labeled_2022_2026.csv.

Evaluation, GCP & Security Hardening: Random Forest vs. SOP rules benchmark (N = 120, 0.918 vs. 0.626 F1), human-reviewed NVIDIA NIM explanations, BigQuery (254,160 rows) / Firestore / Pub/Sub integration, and keyless WIF + Secret Manager + Gitleaks guardrails.

Submission Packaging: Finalized PROJECT_DOCS/RESEARCH_SUMMARY.md, 8-slide deck (PROJECT_DOCS/ColdTrace — Cold-Chain Operations Console (1).pptx), recorded walkthrough (≤ 5 min), and README.md links.

17.2 Risk Register
Risk	Likelihood	Impact	Mitigation
NVIDIA NIM API key or rate limits fail	Medium	Low	Rules and Random Forest remain primary detectors; NIM is optional and clearly labeled for human review
Cloud Run cost or quota pressure	Low	Medium	Keep scale-to-zero (--min-instances 0), bounded concurrency/instances, and budget alerts
Synthetic sensor data differs from real cold rooms	Medium	High	Validate category bands (2°C–8°C / ≤ 2°C) and run physical probe calibration before production cutover
Credential or API key leak	Low	High	Enforce Gitleaks/secret checks, store secrets in Secret Manager, and rotate keys immediately if exposed
Cloud Run cold starts during demos/judging	Medium	Low	Warm/verify endpoints prior to walkthroughs while preserving scale-to-zero configuration
17.3 What's Next After BUILD
Add the final ≤ 5-minute walkthrough video link at the top of README.md and verify all submission links.

Calibrate physical sensors across JHB-DC01, DBN-DC02, and CPT-DC03 and pilot real-sensor streams before expanding toward 50 sites.

18. License
This project is licensed under the MIT License. See the LICENSE file in the repository root for full terms.

ColdTrace is built for SDG 3: because a vaccine that spoils in the dark helps no one.
