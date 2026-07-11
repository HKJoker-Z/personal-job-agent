# Production Security

Version 1.9 applies practical hardening for the current single-instance deployment model:

- Backend and frontend images run as non-root users.
- Compose drops Linux capabilities, enables `no-new-privileges`, uses read-only root filesystems, and does not mount the Docker socket.
- Secrets are runtime environment values and are excluded from images, build arguments, static frontend bundles, logs, and backups.
- Production requires explicit Trusted Hosts and rejects wildcard origins/hosts.
- API docs are disabled by default in production.
- Nginx adds content-type, framing, referrer, permissions, and CSP headers. HSTS is intentionally omitted until an external proxy actually terminates HTTPS.
- Every response has a validated or generated request ID. Structured logs record route templates, status, duration, safe workflow correlation, and safe error codes without request bodies, query strings, credentials, resumes, job descriptions, prompts, RAG chunks, model output, email, phone, or address data.
- Monitoring destructive APIs remain disabled without an admin token and remote destructive access remains disabled by default.
- SQLite and backup directories should be readable only by the deployment operator and container UID 10001.
- Images should be rebuilt regularly from maintained base images and reviewed before promotion.

Public deployments should use HTTPS through a protected reverse proxy. Backups must be stored with restricted permissions and tested for restoration. These controls do not constitute a security certification, penetration-test certification, SOC 2, ISO 27001, or perfect prompt-injection prevention.
