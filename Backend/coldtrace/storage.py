import os
from datetime import datetime, timezone
from typing import Any

_firestore_client = None
_bq_client = None

def get_firestore():
    global _firestore_client
    if _firestore_client is None and os.getenv("USE_FIRESTORE", "false").lower() == "true":
        from google.cloud import firestore
        _firestore_client = firestore.Client()
    return _firestore_client

def persist_alert_and_audit(alert_dict: dict[str, Any], chain_hmac: str, actor: str = "detector") -> None:
    db = get_firestore()
    if not db:
        return
    alert_id = alert_dict["alert_id"]
    payload = {**alert_dict, "chain_hmac": chain_hmac, "updated_at": datetime.now(timezone.utc).isoformat()}
    db.collection("alerts").document(alert_id).set(payload, merge=True)
    # Append-only audit entry
    db.collection("audit_log").add({
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": "ALERT_RECORDED",
        "alert_id": alert_id,
        "chain_hmac": chain_hmac,
    })

def append_audit_event(actor: str, role: str, action: str, alert_id: str, chain_hmac: str = "") -> None:
    db = get_firestore()
    if not db:
        return
    db.collection("audit_log").add({
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "role": role,
        "action": action,
        "alert_id": alert_id,
        "chain_hmac": chain_hmac,
    })

def query_bigquery_summary() -> list[dict[str, Any]]:
    global _bq_client
    if os.getenv("USE_BIGQUERY", "false").lower() != "true":
        return []
    try:
        if _bq_client is None:
            from google.cloud import bigquery
            _bq_client = bigquery.Client()
        sql = """
            SELECT Storage_Location_ID, Exception_Type, COUNT(*) AS readings, ROUND(MAX(Warehouse_Temperature_C), 2) AS max_temp
            FROM `coldtrace_warehouse.telemetry_2022_2026`
            GROUP BY 1, 2
        """
        return [dict(row) for row in _bq_client.query(sql).result()]
    except Exception:
        return []
def storage_status() -> dict[str, Any]:
    use_fs = os.getenv("USE_FIRESTORE", "false").lower() == "true"
    use_bq = os.getenv("USE_BIGQUERY", "false").lower() == "true"
    topic = os.getenv("PUBSUB_TOPIC", "") or os.getenv("TELEMETRY_TOPIC", "")
    return {
        "firestore": "enabled" if use_fs else "in-memory-simulated",
        "bigquery": "enabled" if use_bq else "disabled",
        "pubsub_topic": topic or "provisioned-via-terraform-only",
    }
