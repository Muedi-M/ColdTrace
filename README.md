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
- **Presentation Deck (8 slides):** [PROJECT_DOCS/ColdTrace — Cold-Chain Operations Console (1).pptx](<PROJECT_DOCS/ColdTrace — Cold-Chain Operations Console (1).pptx>)
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
| **Target audience** | Cold-chain operations leads, quality reviewers, and compliance auditors across **JHB-DC01** (`2°C–8°C` pharma band), **DBN-DC02** (`≤ 2°C` perishables), and **CPT-DC03** (last-mile facility with continuous audit). |
| **Problem** | Reactive cold-room monitoring detects temperature excursions, cooling failures, and sensor dropouts after warming or spoilage occurs, while noisy threshold blips cause alert fatigue and manual log stitching slows compliance audits. |
| **SDG alignment** | **UN SDG 3 — Good Health and Well-Being.** Prevents spoilage of temperature-sensitive vaccines, medicines, and perishable food by enabling early human intervention. |

### 1.1 Operational Evidence & Context

* Evaluates `2°C–8°C` (pharma/biologics) and `≤ 2°C` (perishables) across 30-minute telemetry (`254,160` rows in `cold_chain_labeled_2022_2026.csv`).
* Early excursion and cooling-drift detection supports timely intervention before product warming or spoilage.

### 1.2 Friction Points & Console Mapping

| Friction Point | Operational Impact | ColdTrace Capability |
|---|---|---|
| **Late discovery** | Excursions noticed after warming or at shift handover | 30-min telemetry ingestion, 24h causal rolling features, Random Forest + SOP scoring, and CSV replay |
| **Alert fatigue** | Operators mute or ignore repetitive threshold blips | Causal rolling features, alert debouncing, and `Flagged` / `Watch` / `Cleared` band filters |
| **Audit trail gaps** | Slow manual reconstruction during QA/compliance reviews | `OPEN → ACKNOWLEDGED → CLOSED` lifecycle and tamper-evident `evidence_sha256` sealing |

### 1.3 Synthetic Telemetry & Evaluation Dataset

* Uses `cold_chain_labeled_2022_2026.csv` (`254,160` rows across `JHB-DC01`, `DBN-DC02`, and `CPT-DC03`) covering nominal operation, drift, `TEMP_EXCURSION`, `COOLING_FAILURE`, and `SENSOR_DROPOUT` without exposing live facility data.

---

## 2. System Architecture

ColdTrace runs a four-stage FastAPI pipeline paired with a control-room UI on serverless GCP (`us-central1`), combining deterministic rules, Random Forest detection, SHA-256 evidence hashing, and human-reviewed NVIDIA NIM explanations.

### 2.1 Application Data Flow

```mermaid
flowchart LR
    A[Sensor reading<br/>every 30 min] -->|POST /ingest & replay| B[FastAPI<br/>api.py]
    B --> C[features.py<br/>24h causal rolling features]
    C --> D[model.py<br/>Random Forest]
    C --> E[rules.py<br/>SOP threshold baseline]
    D --> F[service.py<br/>debounce + SHA-256 evidence seal]
    E --> F
    F --> G[(Alerts<br/>OPEN / ACK / CLOSED)]
    G --> H[Operations Console<br/>frontend/index.html & app.js]
    G -->|POST /alerts/id/explain| I[nim.py<br/>NVIDIA NIM]
    I -->|AI-GENERATED note<br/>review before acting| H
2.2 Cloud Platform ArchitectureCode snippetflowchart TB
    subgraph DEV[Delivery pipeline]
        GH[GitHub repository] -->|push / PR| GHA[GitHub Actions<br/>ci-deploy.yml]
        GHA -->|OIDC token, keyless| WIF[Workload Identity Federation]
        WIF -->|impersonates| CICD[coldtrace-cicd-sa]
        TF[Terraform IaC] -.->|provisions| GCP
    end

    CICD -->|push image| AR[Artifact Registry]
    CICD -->|deploy revision| CR

    subgraph GCP[Google Cloud project - us-central1]
        AR --> CR[Cloud Run<br/>coldtrace-app<br/>scale-to-zero]
        SCH[Cloud Scheduler] -->|trigger| PS[Pub/Sub<br/>telemetry_events]
        PS -->|push / pull| CR
        CR <--> FS[(Firestore<br/>USE_FIRESTORE)]
        CR -->|read / query| BQ[(BigQuery<br/>coldtrace_warehouse.telemetry_2022_2026)]
        SM[Secret Manager] -->|runtime secrets| CR
        CR --> LOG[Cloud Logging & Monitoring]
        AUD[Cloud Audit Logs] --> LOG
    end

    CR -->|explain alert| NIM[NVIDIA NIM]
    SENS[Cold-room sensors / replay] -->|X-API-Key| CR
    ANALYST[Data analyst<br/>bq load batch jobs] --> BQ
    OPS[Operations console users] --> CR
    SEC[Security reviewer<br/>read-only audit] -.-> LOG
2.3 Component ResponsibilitiesComponentPurposeFastAPI (api.py)Serves the dashboard, authenticates requests, and exposes /healthz, /ingest, /api/demo/replay, alert lifecycle, and NIM routes.Feature engine (features.py)Causal 24-hour rolling features with zero look-ahead leakage.Detector (model.py, rules.py)Random Forest classifier plus SOP threshold baseline for comparison.Service layer (service.py)Streaming state, debouncing, OPEN → ACKNOWLEDGED → CLOSED transitions, and evidence_sha256 sealing.NIM client (nim.py)Generates schema-validated incident notes labeled AI-GENERATED, REVIEW BEFORE ACTING.Cloud Run & GCP ServicesHosts coldtrace-app (us-central1) with BigQuery (coldtrace_warehouse), Firestore (USE_FIRESTORE), Pub/Sub (telemetry_events), Secret Manager, and Terraform/WIF automation.3. Repository StructurePlaintextcoldtrace/
├── README.md                                              # Project overview, team, setup & submission links
├── LICENSE                                                # MIT License
├── env.example                                            # Sample environment variables (never commit .env)
├── PROJECT_DOCS/
│   ├── RESEARCH_SUMMARY.md                                # Research & evaluation summary
│   └── ColdTrace — Cold-Chain Operations Console (1).pptx # 8-slide presentation deck
├── terraform/                                             # Infrastructure as Code (project, IAM, WIF, budget)
├── .github/workflows/ci-deploy.yml                        # Tests, Terraform validate & WIF Cloud Run deploy
└── Backend/
    ├── coldtrace/                                         # FastAPI app, features, RF/SOP models, service, NIM, eval
    ├── frontend/                                          # Console UI (index.html, app.js)
    ├── data/cold_chain_labeled_2022_2026.csv              # Primary 2022–2026 dataset (254,160 rows)
    ├── artifacts/                                         # Trained Random Forest model & evaluation outputs
    ├── scripts/                                           # Data generation, training/eval, replay & NIM scripts
    ├── tests/                                             # Automated pytest suite
    ├── Dockerfile                                         # Production container for Cloud Run
    └── requirements.txt                                   # Python 3.12 dependencies
4. Detection Model & Exception TypesException TypeSensor SignatureOperational ActionTEMP_EXCURSIONTemperature exits safe band (2°C–8°C pharma/biologics; ≤ 2°C perishables) with rising cooling loadInspect unit immediately; protect/relocate at-risk batchesCOOLING_FAILURETemperature rises while cooling load drops abnormally (compressor/cooling fault)Dispatch maintenance; transfer high-sensitivity stockSENSOR_DROPOUTSensor connectivity drops or temperature/humidity readings stallVerify temperature manually; treat unit status carefullyBenchmark Summary ($N = 120$ Test Windows)MetricResultRandom Forest macro-F1 ($N = 120$, 30 per class)0.918SOP threshold rules macro-F10.626AI triage roleOptional NVIDIA NIM note (AI-GENERATED, REVIEW BEFORE ACTING)5. Team, Roles & ResponsibilitiesTeam ColdTrace divides ownership across four tracks:Moorthy (DevOps & Cloud): Owns GCP project/billing setup, Terraform IaC, keyless GitHub Actions CI/CD with Workload Identity Federation, Secret Manager rotation, Cloud Run deployments, and runtime reliability.Chantell (Data Analytics): Owns BigQuery batch loading (bq load), Timestamp-partitioned queries, schema checks, and telemetry quality/dropout validation.Muedi (AI & Cloud Foundation): Owns Random Forest anomaly detection, N = 120 evaluation, NVIDIA NIM integration, and serverless Pub/Sub, Scheduler, Firestore, and Cloud Run foundations.Peter (Security Review): Performs read-only audits across IAM/WIF bindings, authentication/secret controls, Cloud Audit/Monitoring logs, and evidence_sha256 integrity.6. IAM Access Matrix & Service Accounts6.1 Human Access MatrixRole / PermissionMoorthyChantellMuediPeterProject Owner & Billing Admin✅bigquery.jobUser✅✅✅bigquery.dataEditor (coldtrace_warehouse only)✅bigquery.dataViewer✅✅run.developer, artifactregistry.writer, pubsub.editor, cloudscheduler.admin, datastore.user, iam.serviceAccountUser✅secretmanager.viewer (metadata only)✅✅iam.securityReviewer, logging.viewer, logging.privateLogViewer, monitoring.viewer✅6.2 Service AccountsService AccountUsed ByLeast-Privilege Scopecoldtrace-runtime-saCloud Run (coldtrace-app)Read/query BigQuery, Firestore & Pub/Sub access, Cloud Logging/Monitoring, and runtime Secret Manager accesscoldtrace-cicd-saGitHub Actions (ci-deploy.yml)Keyless WIF impersonation to push images and deploy Cloud Run revisions (no JSON keys)7. CI/CD & Infrastructure as CodeThe pipeline lives in .github/workflows/ci-deploy.yml and uses short-lived OIDC tokens via Workload Identity Federation (no service-account JSON keys), with Terraform managing GCP resources and WIF trust conditions scoped to Muedi-M/ColdTrace.Job / ControlTrigger / ScopeBehaviorOwnertest-and-validatePush to main, PR, manualRuns pytest and Terraform fmt/validate (blocks merge)MoorthydeployPush to main after checks, manualKeyless WIF auth, Artifact Registry push, Cloud Run deployMoorthy / MuediWIF & Branch ProtectionMuedi-M/ColdTrace, main branchRepo-scoped WIF condition; PR + required check + no force pushMoorthy / Peter8. Cost, Quota & Free-Tier GuardrailsGuardrailSettingOwnerCloud Run idle cost--min-instances 0 (scale-to-zero)Moorthy / MuediCloud Run scaling & concurrencyBounded instances/concurrency & memory limitsMoorthy / MuediBudget & quota reviewBudget cap, alerts & ongoing quota checksMoorthyBigQuery batch loadsFree batch bq load jobs (no streaming inserts)ChantellBigQuery queriesPartition filter on Timestamp to bound scanned bytesChantellSecrets & auditSecret Manager only; no plaintext access for engineersMoorthy / Peter9. Data Warehouse ConventionsDataset: coldtrace_warehouse (coldtrace_warehouse.telemetry_2022_2026, 254,160 rows at 30-minute intervals across JHB-DC01, DBN-DC02, and CPT-DC03).Batch load: Use bq load jobs rather than streaming inserts.Partitioning: Filter queries on Timestamp to bound scanned bytes:SQLSELECT Storage_Location_ID, AVG(Warehouse_Temperature_C) AS avg_temp
FROM `coldtrace_warehouse.telemetry_2022_2026`
WHERE Timestamp BETWEEN TIMESTAMP('2026-11-01') AND TIMESTAMP('2026-11-14')
GROUP BY Storage_Location_ID;
Access & validation: Dataset-scoped dataEditor for Data Analytics; read-only for other roles and Cloud Run runtime. Validates required columns, 30-minute cadence, non-null critical fields, exception labels (NONE, SENSOR_DROPOUT, COOLING_FAILURE, TEMP_EXCURSION), and warehouse schema columns (Warehouse_Temperature_C, Warehouse_Humidity_Percent, Cooling_Load_Percent, Sensor_Connectivity, Exception_Type, Storage_Location_ID, Timestamp).10. Environment Configuration & SecretsVariableRequiredDescriptionINGEST_API_KEYYesShared key passed in X-API-Key for /ingest, /api/demo/replay, /alerts/{id}/explain, and case state routesNVIDIA_API_KEYYesNVIDIA NGC API key used by coldtrace/nim.py for incident explanationsUSE_FIRESTOREOptionalEnables Firestore persistence for alert state when configuredNIM_MODEL / NIM_TIMEOUTOptionalOverrides default NVIDIA NIM model ID or request timeoutMODEL_PATHOptionalPath to the trained Random Forest model artifact11. Local Setup & Running InstructionsBashcd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INGEST_API_KEY="your-ingest-key"
export NVIDIA_API_KEY="your-nvidia-key"
uvicorn coldtrace.api:app --reload --port 8000
pytest -q tests
12. Google Cloud Run DeploymentBashcd Backend
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
13. API ReferenceMethod & PathAuthPurposeGET /PublicServes the ColdTrace Operations Console web UIGET /healthzPublicHealth check and active storage / Pub/Sub statusPOST /ingestX-API-KeyIngests a 30-min reading, updates 24h causal rolling features, and evaluates alertsPOST /api/demo/replayX-API-Key / ConsoleReplays cold_chain_labeled_2022_2026.csv into the streaming detector and syncs UI stateGET /api/locations & GET /api/alertsOptionalReturns hub telemetry and alerts with evidence_sha256 and lifecycle statePOST /api/alerts/{id}/ack & /closeX-API-KeyTransitions alerts through OPEN → ACKNOWLEDGED → CLOSEDPOST /alerts/{id}/explainX-API-KeyGenerates a schema-validated NVIDIA NIM incident note (AI-GENERATED, REVIEW BEFORE ACTING)14. Security & Design GuardrailsPrimary anomaly detection never depends on the LLM; NVIDIA NIM notes are labeled AI-GENERATED, REVIEW BEFORE ACTING and never auto-acknowledge or auto-close alerts.Triggering telemetry windows are hashed deterministically into evidence_sha256, backed by constant-time X-API-Key checks, Secret Manager, keyless WIF CI/CD, and least-privilege IAM.15. Security Practices & Secret HandlingNever commit .env or real secrets; keep env.example placeholder-only and enable GitHub secret scanning and push protection.Rotate keys via Secret Manager versions, roll out Cloud Run to :latest, verify behavior, and disable old versions.Run local checks (pytest -q tests, gitleaks detect --source . --redact --verbose, and terraform -chdir=terraform fmt -check -recursive) before pushing.16. Ownership Summary (RACI)R = Responsible, A = Accountable, C = Consulted, I = InformedAreaMoorthyChantellMuediPeterGCP project, billing, budget & Terraform IaCA/RICCGitHub Actions CI/CD (WIF) & Secret ManagerA/RICCContainer builds & Cloud Run (us-central1)AIRIRandom Forest model, evaluation & NIM clientICA/RIBigQuery batch loads, partitions & data QAIA/RCIPub/Sub, Scheduler & Firestore pipelinesAIRIIAM/WIF audit, logs & evidence reviewCICA/R17. Implementation Plan, Risk Register & Roadmap17.1 Milestones & Next StepsFinalized core pipeline, 24h causal features, OPEN → ACKNOWLEDGED → CLOSED workflow, evidence_sha256 sealing, cold_chain_labeled_2022_2026.csv replay, N = 120 evaluation (0.918 vs. 0.626 F1), and 8-slide deck (PROJECT_DOCS/ColdTrace — Cold-Chain Operations Console (1).pptx).Post-BUILD: add the ≤ 5-minute walkthrough link at the top of README.md and calibrate physical sensors across JHB-DC01, DBN-DC02, and CPT-DC03.17.2 Risk RegisterRiskLikelihoodImpactMitigationNVIDIA NIM API errors or rate limitsMediumLowKeep Random Forest + SOP rules as primary detectors; label NIM notes for human reviewCloud Run cost or quota spikesLowMediumEnforce --min-instances 0, instance/concurrency caps, and budget alertsSim-to-real sensor gapMediumHighValidate safe bands and calibrate physical probes before production rolloutSecret exposureLowHighUse Secret Manager, WIF, and Gitleaks checks; rotate immediately if exposedCold starts during demosMediumLowWarm/verify endpoints before demos while keeping scale-to-zero enabled18. LicenseThis project is licensed under the MIT License. See the LICENSE file in the repository root for full terms.ColdTrace is built for SDG 3: because a vaccine that spoils in the dark helps no one.
