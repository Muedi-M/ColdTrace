import os

# Test-only dummy values. Real keys come from Secret Manager in production.
os.environ.setdefault("INGEST_API_KEY", "change-me-local-only")
os.environ.setdefault("NVIDIA_API_KEY", "dummy-key-for-tests")
