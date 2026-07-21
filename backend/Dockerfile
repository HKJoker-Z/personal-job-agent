FROM python:3.12-slim AS runtime

ARG APP_VERSION=2.0.3
ARG POSTGRES_CLIENT_MAJOR=16

LABEL org.opencontainers.image.title="Personal Job Agent Backend" \
      org.opencontainers.image.version="${APP_VERSION}" \
      io.personal-job-agent.postgresql-client-major="${POSTGRES_CLIENT_MAJOR}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && install -d -m 0755 /usr/share/postgresql-common/pgdg \
    && curl --fail --show-error --silent \
      --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
      https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && printf 'Types: deb\nURIs: https://apt.postgresql.org/pub/repos/apt\nSuites: %s-pgdg\nArchitectures: %s\nComponents: main\nSigned-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc\n' \
      "${VERSION_CODENAME}" "$(dpkg --print-architecture)" \
      > /etc/apt/sources.list.d/pgdg.sources \
    && apt-get update \
    && apt-get install --yes --no-install-recommends "postgresql-client-${POSTGRES_CLIENT_MAJOR}" \
    && pg_dump --version | grep -E "^pg_dump \(PostgreSQL\) ${POSTGRES_CLIENT_MAJOR}(\\.|$)" \
    && pg_restore --version | grep -E "^pg_restore \(PostgreSQL\) ${POSTGRES_CLIENT_MAJOR}(\\.|$)" \
    && psql --version | grep -E "^psql \(PostgreSQL\) ${POSTGRES_CLIENT_MAJOR}(\\.|$)" \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY backend/agent_workflow.py backend/analysis_contract.py backend/analysis_fallback.py backend/config.py backend/data_management_service.py ./
COPY backend/database.py backend/evaluation_service.py backend/export_utils.py ./
COPY backend/knowledge_utils.py backend/logging_utils.py backend/main.py backend/legacy_application.py ./
COPY backend/monitoring_service.py backend/project_knowledge_runtime.py ./
COPY backend/readiness.py backend/recommendation_engine.py backend/safe_prompt.py backend/security_utils.py ./
COPY backend/app/ ./app/
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic/ ./alembic/
COPY backend/evals/ ./evals/
COPY scripts/v2_backup_restore.py scripts/postgres_restore_fixture.py /app/scripts/
COPY docs/PROJECT_KNOWLEDGE.md /app/seed/PROJECT_KNOWLEDGE.md

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/project-knowledge /app/runtime/files \
    && chown -R 10001:10001 /app/project-knowledge /app/runtime/files

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/ready', timeout=3).read()"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]
