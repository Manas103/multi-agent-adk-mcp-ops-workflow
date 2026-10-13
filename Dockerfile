# Containerized to the Cloud Run contract: listens on $PORT, no state held
# outside Postgres. `gcloud run deploy` was not run this session (no gcloud
# credentials on this machine; see the README's Honest framing). This image
# was not built this session either (Docker Desktop's daemon is not running
# here; also disclosed in the README), so treat it as authored, not verified.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src

ENV PORT=8080
CMD ["sh", "-c", "uvicorn src.approval.api:app --host 0.0.0.0 --port ${PORT}"]
