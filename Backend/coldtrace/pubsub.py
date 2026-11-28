"""Pub/Sub handoff for alerts and case events.

When PUBSUB_TOPIC is set (Cloud Run, via Terraform), every raised alert and every case status
change is published as a JSON message with attributes `type` and `location_id`. A BigQuery
subscription on that topic (terraform/secrets_data_messaging.tf) lands the messages in
`coldtrace_warehouse.case_events`, which feeds the Insights MVP in BigQuery without streaming
inserts from the app.

Field sensors (or a gateway) can also publish readings to the topic; a push subscription to
POST /pubsub/push?token=... feeds them through the same detector as /ingest.

Publishing never blocks or fails a request: errors are counted and logged, detection continues.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import threading

log = logging.getLogger("coldtrace.pubsub")
_client = None
_lock = threading.Lock()
stats = {"published": 0, "errors": 0}


def topic_path() -> str:
    topic = os.getenv("PUBSUB_TOPIC", "").strip()
    if not topic:
        return ""
    if topic.startswith("projects/"):
        return topic
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT") or ""
    return f"projects/{project}/topics/{topic}" if project else topic


def _publisher():
    global _client
    with _lock:
        if _client is None:
            from google.cloud import pubsub_v1  # lazy: only needed on GCP
            _client = pubsub_v1.PublisherClient()
    return _client


def publish(kind: str, payload: dict, location_id: str = "", publisher=None) -> bool:
    """Publish one message. Returns False (and logs) when disabled or on error."""
    path = topic_path()
    if not path:
        return False
    try:
        pub = publisher or _publisher()
        data = json.dumps(payload, default=str, separators=(",", ":")).encode()
        future = pub.publish(path, data, type=kind, location_id=location_id or "")
        future.add_done_callback(lambda f: f.exception() and log.warning("pubsub publish failed: %s", f.exception()))
        stats["published"] += 1
        return True
    except Exception as e:  # never break detection because messaging is down
        stats["errors"] += 1
        log.warning("pubsub publish error: %s", type(e).__name__)
        return False


def decode_push(envelope: dict) -> tuple[dict, dict]:
    """Decode a Pub/Sub push envelope -> (payload, attributes). Raises ValueError on bad input."""
    msg = (envelope or {}).get("message") or {}
    raw = msg.get("data")
    if not raw:
        raise ValueError("push envelope has no message.data")
    try:
        payload = json.loads(base64.b64decode(raw))
    except Exception as e:
        raise ValueError("message.data is not base64 JSON") from e
    return payload, msg.get("attributes") or {}
