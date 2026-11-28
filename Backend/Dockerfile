FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENV=production \
    PORT=8080

WORKDIR /app

# Create non-root user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY coldtrace ./coldtrace
COPY frontend ./frontend
COPY artifacts ./artifacts
COPY data ./data
COPY config ./config

RUN chown -R appuser:appgroup /app
USER 10001

EXPOSE 8080
CMD ["uvicorn", "coldtrace.api:app", "--host", "0.0.0.0", "--port", "8080", "--no-server-header"]
