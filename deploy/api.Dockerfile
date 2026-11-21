# The Personalized Roadmap API. Build from the repository root:
#   docker build -f deploy/api.Dockerfile -t roadmap-api .
FROM python:3.11-slim

# git checks out the curriculum versions; nothing else is installed beyond the package.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml requirements.txt README.md LICENSE ./
COPY requirements ./requirements
COPY src ./src
RUN pip install --no-cache-dir ".[api]"

COPY config ./config
COPY checkpoints ./checkpoints
# The curriculum versions in config/curriculum.yaml, checked out at build time so the API starts offline.
RUN python -m roadmap fetch

RUN useradd --create-home roadmap && mkdir -p /app/state && chown roadmap /app/state
USER roadmap

# Accounts, paths, submissions, question reports and shared progress are in PostgreSQL (DATABASE_URL, set by
# compose.yml). Archives of submitted projects live in /app/state, a volume, so they survive a new image.
ENV API_UPLOADS_DIR=/app/state/uploads
EXPOSE 8000
# One worker: the rate limit is kept in memory (the database itself would take several). --proxy-headers: behind Caddy, the client is the learner.
# --no-access-log: the access log would keep learners' IP addresses, which we do not store.
CMD ["uvicorn", "roadmap.api:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
