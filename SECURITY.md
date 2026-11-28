# ColdTrace security notes — evidence and endpoints

Owner: Peter Opiyo (Cloud Cybersecurity lane). Review status: **draft — review and sign below before merge.**

## 1. What must stay true

1. Only authorised callers can change a case (assign, resolve, inject, replay, ingest).
2. Nobody, including the team, can silently change what a sensor reported or what a reviewer did.
3. No secret is ever in the repository, the page source or the logs.

## 2. Endpoint access matrix

| Endpoint | Auth | Notes |
|---|---|---|
| `POST /ingest`, `/api/demo/*`, `/api/alerts/*/ack|close`, `/api/ui/investigations/*` | `X-API-Key` (plain or SHA-256-hashed via `API_KEY_HASHES_JSON`) | Constant-time compare; 16 KB body cap; security headers on every response |
| `POST /pubsub/push?token=…` | Push token (`PUBSUB_PUSH_TOKEN`, Secret Manager) | Pub/Sub push cannot send custom headers, so the token rides in the URL; rotate with the API key. Only `type=reading` messages are processed |
| `GET /api/insights`, `/api/cases`, `/api/cases/{id}/events`, `/api/thresholds`, `/api/validation`, `/api/ui/state` | Public read | No personal data; case events hold staff display names only. Put behind IAP if real staff names are used |

Closed cases return `409` on re-assignment, so a closed record cannot be reopened through the console.

## 3. Evidence and audit chain

| Layer | Mechanism | How to check |
|---|---|---|
| Sensor evidence | SHA-256 over the readings that triggered the alert (`service.Alert.seal`) | Hash shown in the case Details tab and the Evidence Vault |
| Case history | Each event stores `prev_hash` and its own SHA-256 over all fields (`cases.CaseEvent.seal`) — editing any field or deleting an event breaks the chain | `GET /api/cases/{id}/events` → `chain_valid`; *Verify audit chain* button in Quality & Audit; `tests/test_security_endpoints.py::test_case_log_tamper_is_detected` |
| Thresholds | `config/thresholds.json` hashed at load; version + hash recorded on every case and validation report | `GET /api/thresholds` |
| Model | `artifacts/rf_model.sha256` checked at start-up (`verify_model_artifacts`) | App refuses to start on mismatch |
| Off-box copy | Alerts and case events published to Pub/Sub → BigQuery `case_events` (append-only table) | Query by `message_id` / `publish_time` |

Limitation: the in-process chain proves integrity of what the app holds; the BigQuery copy is the independent record. Set `CASE_EVENTS_PATH` to also append a JSONL copy on a mounted volume.

## 4. Secrets

* API key, NIM keys and push token live in Secret Manager and reach Cloud Run as env vars (Terraform).
* The console stores the operator's key in `localStorage` only after they type it; no key is in the HTML.
* **Action:** an NVIDIA API key was committed in `env.example` on 19 Nov 2026 (commit `cdb6b74`) and deleted on 24 Nov; it remains in git history, so it is treated as exposed. It has been revoked at build.nvidia.com, a new key stored in Secret Manager, and the old commit fingerprint added to `.gitleaksignore` so CI flags only new leaks. (The value in the 19–24 Nov `index.html` was the local placeholder `change-me-…`, not a production key.)
* `tools/ctpush` blocks staged NVIDIA/Google/GitHub keys, private keys, `.env` files and files over 20 MB; CI runs Gitleaks, CodeQL, Bandit, pip-audit and OWASP ZAP.

## 5. Open items

- [ ] Confirm the NVIDIA key from `env.example` (19 Nov) is revoked and the new key is live in Secret Manager.
- [ ] Confirm `terraform/variables.tf` `github_repo` matches the repository the WIF trust should allow (`Muedi-M/ColdTrace`).
- [ ] Decide whether the public read endpoints need IAP before any real staff names are used.

Reviewed by: ____________________  Date: ____________
