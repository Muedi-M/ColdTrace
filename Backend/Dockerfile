FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY coldtrace ./coldtrace
COPY artifacts/coldtrace_rf.joblib ./artifacts/coldtrace_rf.joblib
ENV MODEL_PATH=/app/artifacts/coldtrace_rf.joblib PYTHONUNBUFFERED=1
# INGEST_API_KEY and NVIDIA_API_KEY / NIM_SECRET_NAME come from Cloud Run secrets, never the image
CMD ["sh", "-c", "uvicorn coldtrace.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
