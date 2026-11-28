# ColdTrace — Implementation Plan, Progress & Risks

**Window:** 4-week BUILD phase, 2 Nov → 28 Nov 2026. Final package due **Sat 28 Nov 11:59 PM ET (Sun 29 Nov 06:59 SAST)**; the team's internal finish is **Fri 27 Nov 18:00 SAST**.
**Rule:** an item is done only when its proof exists (a commit, a passing test, a URL). Each week ends with a gate; a failed gate is fixed before new scope.

## 1. Team lanes and owners

| Person | Track | Lane | Owns |
|---|---|---|---|
| **Muedi Mbambala** (lead) | Google DeepMind: AI Research Foundations | Can detection be trusted? | Synthetic data simulator, rules baseline, Random Forest model, event-level evaluation, NIM comparison, case log and Insights, weekly meeting, submission package |
| **Chantell Masilela** | Cloud Data Analytics | Keep the data honest | Data validation rules, BigQuery batch loads and SQL quality checks, cadence and dropout verification |
| **Moorthy R** | Cloud Engineering | Tie the services together | Terraform, Cloud Run, CI/CD with WIF, Firestore, Pub/Sub, Scheduler, monitoring, console deployment |
| **Peter Opiyo** | Cloud Cybersecurity | Protect the evidence | Secrets and key rotation, API auth, evidence hashing and audit chain, SAST/DAST/dependency scans, IAM review |

Standing meeting: weekly, 30 minutes, plus a written Friday gate check in the team channel.

## 2. Timeline against the BUILD roadmap

| Week | Dates | Goal | Owner(s) | Status | Proof |
|---|---|---|---|---|---|
| 1 | 2–8 Nov | Team formed, scope agreed (3 locations, 3 exception types, detect → review → close); hackathons (NVIDIA Live Agent Gauntlet 5 Nov, Newly 6 Nov) | All | ✅ Done | Weekly plan PDF in `Weekly schedule/` |
| 2 | 9–15 Nov | Synthetic labelled dataset; rules baseline; Random Forest; event-level evaluation; NIM client and first comparison (due 10 Nov) | Muedi | ✅ Done | `artifacts/metrics.json`, `scripts/compare_nim.py`, first commit 16 Nov |
| 3 | 16–22 Nov | FastAPI on Cloud Run; Terraform; CI/CD with WIF; Secret Manager; security scans; operations console | Moorthy, Peter | ✅ Done | Live app, `ci-deploy.yml`, `terraform/`, Gitleaks/CodeQL/ZAP jobs |
| 4a | 23–27 Nov | UI audit fixes (category bands, honest errors, keyboard access, KPIs), demo replay on the full dataset | Moorthy | ✅ Done | Commits 24–27 Nov |
| 4b | 25–27 Nov | Data validation: BigQuery batch load, SQL checks (row counts, nulls, 2–8 °C excursions, cadence gaps, dropouts) | Chantell | ✅ Done | `bq_load_coldtrace.sh`, `Validation_coldtrace.sql` (PRs #5–#7) |
| 4c | 28 Nov | Same validation rules in the app: quarantine with reasons, reference joins, versioned thresholds | Muedi (from Chantell's rules) | ✅ Done | `Backend/coldtrace/validation.py`, `Backend/config/thresholds.json` |
| 4d | 28 Nov | Case event log + Insights MVP (frequency by location, detection-to-review, avg + median cycle time, throughput, overdue, burndown) | Muedi | ✅ Done | `Backend/coldtrace/cases.py`, `GET /api/insights`, Quality & Audit screen |
| 4e | 28 Nov | Pub/Sub publishing + push endpoint, BigQuery case-events subscription, `/health` alias, console fixes | Muedi, Moorthy (Terraform review) | ✅ Done in code · `terraform plan` pending | `Backend/coldtrace/pubsub.py`, `terraform/pubsub_case_events.tf` |
| 4f | 28 Nov | Security notes, endpoint auth + tamper tests; revoke the NVIDIA key committed in env.example on 19 Nov | Peter | 🟡 Draft, sign-off pending | `SECURITY.md`, `Backend/tests/test_security_endpoints.py` |
| 4g | 26–28 Nov | Balanced benchmark n = 120 (RF 0.918 vs rules 0.626 macro-F1); live NIM run at n = 120 | Muedi | 🟡 RF/rules done; NIM run used mock provider | `Backend/artifacts/nim_comparison_summary.json` |
| 4h | 25–28 Nov | User interviews and survey | Muedi, Chantell | ⬜ To do | `PROJECT_DOCS/USER_RESEARCH.md` |
| 4i | 27–28 Nov | README, 3-page brief, deck, recorded walkthrough | All | ✅ Done | README top links |
| Gate | 27 Nov 18:00 SAST | Click-through test on desktop and phone; PR from team branch to `main`, **not merged** | Muedi | ⬜ | PR URL |

## 3. Resources

| Resource | Use | Cost control |
|---|---|---|
| Google Cloud (free tier + credits) | Cloud Run, Firestore, BigQuery, Pub/Sub, Scheduler, Secret Manager, Artifact Registry, Monitoring | Budget alert, min/max instances, batch `bq load` only, partitioned tables |
| NVIDIA NIM API (build.nvidia.com) | Triage notes; model comparison | Per-model keys in Secret Manager; NIM optional at runtime |
| GitHub + Actions | Code, CI/CD, security scans | Free for public repo |
| Newly | Console build sprint (hackathon 6 Nov) | — |
| People | ~6–8 h per person per week | Weekly gate |

## 4. Risk register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|---|
| R1 | Synthetic data does not reflect real fridges, so accuracy claims do not transfer | High | High | Report all metrics as simulated; validation module ready for a real logger export; field replay is first next step | Muedi |
| R2 | False alerts erode trust (alarm fatigue) | Medium | High | Debounce (2 consecutive, conf ≥ 0.5); false alerts per location-day reported beside recall; thresholds versioned and reviewable | Muedi, Chantell |
| R3 | NVIDIA API outage, rate limit or key failure | Medium | Medium | Detection never depends on NIM; retries with backoff; console shows an honest error and keeps the last note | Muedi |
| R4 | Secret leak | Medium | High | Secret Manager, hashed API keys, Gitleaks on every push, rotation runbook; revoked the NVIDIA key committed in env.example on 19 Nov; .gitleaksignore covers only that historical commit | Peter |
| R5 | Evidence altered after the fact | Low | High | SHA-256 sealed evidence; hash-chained case events; `/api/cases/{id}/events` exposes `chain_valid` | Peter |
| R6 | GCP free-tier quota or budget exceeded | Low | Medium | Budget alert, batch loads, Pub/Sub → BigQuery subscription instead of streaming inserts | Moorthy |
| R7 | Cold start during judging makes the app look broken | Medium | Medium | Warm the service before demos and judging; keep scale-to-zero for the $1/month budget | Moorthy |
| R8 | Deadline pressure across four time zones | Medium | High | Internal finish 27 Nov 18:00 SAST; daily async check-in; scope frozen after 26 Nov | Muedi |
| R9 | Uneven visible contributions in the repo | Medium | Medium | Each person commits their own lane under their own name with `tools/ctpush`; shared work carries `Co-authored-by` | All |
| R10 | Terraform drift (e.g. WIF bound to an old repo name) | Medium | Medium | `terraform plan` before final deploy; check `github_repo` variable matches `Muedi-M/ColdTrace` | Moorthy, Peter |

## 5. After BUILD

1. Pilot with one real cold room: replay a month of logger data, measure false alerts per location-day.
2. Move console records fully onto Firestore cases; retire seeded demo records.
3. QA sign-off of `config/thresholds.json` and per-product bands.
4. Mobile push for High-priority cases; WhatsApp/SMS escalation when the review SLA is breached.
5. Scale from 3 to N locations: the detector is per-location and stateless across sites; Pub/Sub fans out.
