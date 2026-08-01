ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

COPY --chown=10001:10001 \
    ops/candidate/java-normalization/candidate_runtime.py \
    ops/candidate/java-normalization/fault_stub.py \
    /app/backend/candidate/

ENV PYTHONPATH=/app/backend

CMD ["uvicorn", "candidate.candidate_runtime:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-access-log"]
