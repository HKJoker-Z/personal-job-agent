FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY backend/agent_workflow.py backend/config.py backend/data_management_service.py ./
COPY backend/database.py backend/evaluation_service.py backend/export_utils.py ./
COPY backend/knowledge_utils.py backend/logging_utils.py backend/main.py backend/legacy_application.py ./
COPY backend/monitoring_service.py backend/project_knowledge_runtime.py ./
COPY backend/readiness.py backend/recommendation_engine.py backend/safe_prompt.py backend/security_utils.py ./
COPY backend/app/ ./app/
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic/ ./alembic/
COPY backend/evals/ ./evals/
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
