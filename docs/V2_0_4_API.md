# Version 2.0.4 Agent API

All endpoints require the existing opaque server-side Session Cookie. Mutations additionally require a trusted `Origin` and the Session-bound `X-CSRF-Token`. IDs are never authorization: every query is scoped to the authenticated owner. Mutations with an expected revision return `409` when stale.

## Agent Runs

- `GET /api/agent-runs`: list owned Runs; optional `status` and bounded `limit`.
- `POST /api/agent-runs`: create `generate_application_package`; returns `202`. An `Idempotency-Key` header (or validated body key) is required. The same key and input returns the existing Run. `force_new` also requires `force_confirmation: "FORCE NEW"` and has its own idempotency namespace.
- `GET /api/agent-runs/{id}`: detail including ordered Steps and any pending Approval.
- `POST /api/agent-runs/{id}/cancel`: idempotent cancellation with `expected_revision`.
- `POST /api/agent-runs/{id}/retry`: explicit retry with `expected_revision` and `acknowledge_possible_cost` when usage may already exist.
- `POST /api/agent-runs/{id}/resume`: recover a failed, scheduled-retry, or expired-lease Run without rerunning completed Steps.
- `GET /api/agent-runs/{id}/steps`: ordered Step state and safe usage/error fields.
- `GET /api/agent-runs/{id}/events`: append-only events after optional `after_id`.

Creation accepts only safe references:

```json
{
  "workflow_type": "generate_application_package",
  "package_id": "00000000-0000-0000-0000-000000000000",
  "force_new": false
}
```

## SSE progress

`GET /api/agent-runs/{id}/events/stream` returns `text/event-stream`. Authentication uses the ordinary HttpOnly Cookie; no Session token is accepted in the URL. Reconnect with `Last-Event-ID`. Each event includes an integer `id`, safe `event` type, and compact JSON `data`. The server emits heartbeat comments and a terminal `stream.complete` event. Production uses a Redis-coordinated per-user connection limit and returns `429` when exceeded or `503` when required coordination is unavailable.

Events contain safe status and identifier summaries only. They never contain full Prompt/response text, Resume/JD/Material bodies, Profile PII, Cookie/Session/CSRF values, API keys, or `DATABASE_URL`.

## Approvals

- `GET /api/approvals`: list owned requests; optional `status` and bounded `limit`.
- `GET /api/approvals/{id}`: request plus append-only decision history.
- `POST /api/approvals/{id}/decide`: approve or reject using `expected_revision` and a unique decision `idempotency_key`.

Approval replay with the same decision key returns the recorded result. A different stale decision returns `409`; expired requests fail safely. Approvals cover tailored Resume, Cover Letter, complete Package, and configured high-cost generation. Approval never bypasses independent unsupported-claim validation.

## Compatibility

Version 2.0.3 synchronous Match and Material APIs remain available. The React Application Package page defaults to `POST /api/agent-runs`, prevents duplicate clicks, navigates to the Run detail page, and requires confirmation for Force New.
