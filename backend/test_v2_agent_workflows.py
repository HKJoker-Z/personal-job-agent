import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent_runs.definitions import APPLICATION_PACKAGE_STEPS, QUEUE_PAYLOAD_KEYS, validate_queue_payload
from app.agent_runs.outbox import dispatch_batch, recover_orphaned_deliveries
from app.agent_runs.service import AgentBudgetExceeded, AgentRunService
from app.agent_runs.state_machine import IllegalTransition, require_run_transition, require_step_transition
from app.agent_runs.workflow import execute_delivery
from app.agent_runs.worker import heartbeat, pulse
from app.api.routers import agent_runs, applications, auth, jobs, matching, materials
from app.auth.middleware import V2SecurityMiddleware
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.base import Base
from app.db.engine import build_engine
from app.db.models import (
    AIUsageLedger,
    AgentOutboxEvent,
    AgentRun,
    AgentRunEvent,
    AgentStep,
    ApplicationMaterial,
    ApprovalRequest,
    DeadLetterRecord,
    UserAIBudget,
    WorkerHeartbeat,
    utc_now,
)
from app.db.session import session_factory
import test_v2_matching_materials as v203_fixtures


class V204ReliableAgentWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test",
            "AUTH_ENABLED": "true",
            "TEST_DATABASE_URL": f"sqlite+pysqlite:///{root / 'v204-test.db'}",
            "APP_DATABASE_PATH": str(root / "legacy-test.db"),
            "FILE_STORAGE_ROOT": str(root / "files"),
            "SESSION_COOKIE_SECURE": "false",
            "AUTH_TRUSTED_ORIGINS": "http://testserver",
            "AUTH_FINGERPRINT_KEY": "TEST_ONLY_FINGERPRINT_KEY_32_BYTES_LONG",
            "DEEPSEEK_API_KEY": "TEST_ONLY_NEVER_SENT",
            "REDIS_URL": "redis://127.0.0.1:6379/15",
            "SSE_HEARTBEAT_SECONDS": "5",
        })
        self.environment.start()
        build_engine.cache_clear()
        self.settings = load_v2_settings()
        self.engine = build_engine(self.settings.database_url)
        Base.metadata.create_all(self.engine)
        db = session_factory(self.settings.database_url)()
        try:
            auth_service = AuthService(db, self.settings)
            owner = auth_service.create_user(
                "agent-owner@example.com", "correct horse battery staple", "Owner", "admin",
            )
            other = auth_service.create_user(
                "agent-other@example.com", "another correct passphrase", "Other", "user",
            )
            self.owner_id, self.other_id = owner.id, other.id
            self.seed = v203_fixtures.V203MatchingMaterialsTest._seed(self, db, owner.id, "Agent", False)
            self.other_seed = v203_fixtures.V203MatchingMaterialsTest._seed(self, db, other.id, "OtherAgent", False)
            db.commit()
        finally:
            db.close()
        app = FastAPI()
        for router in (
            auth.router, matching.router, jobs.router, applications.router,
            materials.router, agent_runs.router,
        ):
            app.include_router(router)
        app.add_middleware(V2SecurityMiddleware, settings=self.settings)
        self.client = TestClient(app)
        self.other_client = TestClient(app)
        self.csrf = self._login(
            self.client, "agent-owner@example.com", "correct horse battery staple",
        )
        self.other_csrf = self._login(
            self.other_client, "agent-other@example.com", "another correct passphrase",
        )

    def tearDown(self):
        self.client.close()
        self.other_client.close()
        self.engine.dispose()
        build_engine.cache_clear()
        self.environment.stop()
        self.temporary.cleanup()

    def _login(self, client, email, password):
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["csrf_token"]

    def headers(self, key=None, other=False):
        values = {
            "Origin": "http://testserver",
            "X-CSRF-Token": self.other_csrf if other else self.csrf,
        }
        if key:
            values["Idempotency-Key"] = key
        return values

    def package(self, seed=None, client=None, other=False, title="Agent Package"):
        seed = seed or self.seed
        client = client or self.client
        match = client.post(
            f"/api/jobs/{seed['job']}/match",
            json={"resume_version_id": seed["resume"]},
            headers=self.headers(other=other),
        )
        self.assertEqual(match.status_code, 200, match.text)
        response = client.post(
            f"/api/applications/{seed['application']}/packages",
            json={
                "source_resume_version_id": seed["resume"],
                "match_analysis_id": match.json()["id"],
                "title": title,
            },
            headers=self.headers(other=other),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def create_run(self, package_id, key="agent-run-key-0001", **extra):
        response = self.client.post(
            "/api/agent-runs",
            json={"package_id": package_id, **extra},
            headers=self.headers(key),
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def _run_row(self, run_id):
        db = session_factory(self.settings.database_url)()
        try:
            return db.get(AgentRun, UUID(str(run_id)))
        finally:
            db.close()

    def drive(self, run_id, until=("waiting_for_approval", "completed", "failed", "dead_letter")):
        for _ in range(40):
            db = session_factory(self.settings.database_url)()
            try:
                run = db.get(AgentRun, UUID(str(run_id)))
                if run.status in until:
                    return run.status
                step = db.scalar(select(AgentStep).where(
                    AgentStep.run_id == run.id,
                    AgentStep.status == "queued",
                ).order_by(AgentStep.step_order))
                self.assertIsNotNone(step, f"No queued step for Run status {run.status}")
                payload = {
                    "run_id": str(run.id),
                    "step_id": str(step.id),
                    "workflow_type": run.workflow_type,
                    "attempt": step.attempt,
                    "correlation_id": run.correlation_id,
                }
            finally:
                db.close()
            execute_delivery(payload, "unit-worker")
        self.fail("Workflow did not reach the expected state.")

    def approve_pending(self, run_id, suffix):
        response = self.client.get("/api/approvals?status=pending")
        self.assertEqual(response.status_code, 200, response.text)
        approval = next(value for value in response.json() if value["run_id"] == str(run_id))
        decided = self.client.post(
            f"/api/approvals/{approval['id']}/decide",
            json={
                "decision": "approve",
                "expected_revision": approval["revision"],
                "idempotency_key": f"approval-{suffix}-0001",
                "safe_reason": "Synthetic unit-test approval.",
            },
            headers=self.headers(),
        )
        self.assertEqual(decided.status_code, 200, decided.text)
        replay = self.client.post(
            f"/api/approvals/{approval['id']}/decide",
            json={
                "decision": "approve",
                "expected_revision": approval["revision"],
                "idempotency_key": f"approval-{suffix}-0001",
                "safe_reason": "Replay must not append another decision.",
            },
            headers=self.headers(),
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(len(replay.json()["decisions"]), 1)

    def test_run_creation_idempotency_force_new_ownership_and_concurrent_limit(self):
        package = self.package()
        missing_key = self.client.post(
            "/api/agent-runs", json={"package_id": package["id"]}, headers=self.headers(),
        )
        self.assertEqual(missing_key.status_code, 400)
        first = self.create_run(package["id"])
        self.assertFalse(first["reused"])
        self.assertEqual(len(first["run"]["steps"]), len(APPLICATION_PACKAGE_STEPS))
        repeated = self.create_run(package["id"])
        self.assertTrue(repeated["reused"])
        self.assertEqual(repeated["run"]["id"], first["run"]["id"])
        forced = self.create_run(
            package["id"], force_new=True, force_confirmation="FORCE NEW",
        )
        self.assertNotEqual(forced["run"]["id"], first["run"]["id"])
        self.assertTrue(self.create_run(
            package["id"], force_new=True, force_confirmation="FORCE NEW",
        )["reused"])
        third = self.client.post(
            "/api/agent-runs",
            json={"package_id": package["id"]},
            headers=self.headers("agent-run-key-0003"),
        )
        self.assertEqual(third.status_code, 429)
        self.assertEqual(
            self.other_client.get(f"/api/agent-runs/{first['run']['id']}").status_code, 404,
        )
        idor = self.other_client.post(
            "/api/agent-runs",
            json={"package_id": package["id"]},
            headers=self.headers("other-agent-run-0001", other=True),
        )
        self.assertEqual(idor.status_code, 404)
        db = session_factory(self.settings.database_url)()
        try:
            outbox = db.scalar(select(AgentOutboxEvent).where(
                AgentOutboxEvent.run_id == UUID(first["run"]["id"]),
            ))
            self.assertEqual(set(outbox.payload), QUEUE_PAYLOAD_KEYS)
            serialized = json.dumps(outbox.payload).casefold()
            for forbidden in ("resume", "description", "cookie", "api_key", "database_url"):
                self.assertNotIn(forbidden, serialized)
        finally:
            db.close()

    def test_state_machine_duplicate_delivery_cancel_and_crash_resume(self):
        package = self.package()
        created = self.create_run(package["id"])
        run_id = UUID(created["run"]["id"])
        step_id = UUID(created["run"]["steps"][0]["id"])
        db = session_factory(self.settings.database_url)()
        try:
            service = AgentRunService(db, self.owner_id, self.settings)
            claim = service.claim_step(run_id, step_id, "worker-a", delivery_attempt=0)
            db.commit()
            self.assertIsNotNone(claim)
        finally:
            db.close()
        db = session_factory(self.settings.database_url)()
        try:
            duplicate = AgentRunService(db, self.owner_id, self.settings).claim_step(
                run_id, step_id, "worker-b", delivery_attempt=0,
            )
            db.commit()
            self.assertIsNone(duplicate)
        finally:
            db.close()
        current = self.client.get(f"/api/agent-runs/{run_id}").json()
        cancel = self.client.post(
            f"/api/agent-runs/{run_id}/cancel",
            json={"expected_revision": current["revision"]}, headers=self.headers(),
        )
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertTrue(cancel.json()["cancel_requested"])
        db = session_factory(self.settings.database_url)()
        try:
            completed = AgentRunService(db, self.owner_id, self.settings).complete_step(
                run_id, step_id, claim["execution_token"], {}, None,
            )
            db.commit()
            self.assertFalse(completed)
        finally:
            db.close()
        cancelled = self.client.get(f"/api/agent-runs/{run_id}").json()
        replay = self.client.post(
            f"/api/agent-runs/{run_id}/cancel",
            json={"expected_revision": 1}, headers=self.headers(),
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(cancelled["status"], "cancelled")
        with self.assertRaises(IllegalTransition):
            require_run_transition("completed", "running")
        with self.assertRaises(IllegalTransition):
            require_step_transition("completed", "running")

        crash_package = self.package(title="Crash Package")
        crash = self.create_run(crash_package["id"], key="crash-run-key-0001")
        crash_id = UUID(crash["run"]["id"])
        crash_step = UUID(crash["run"]["steps"][0]["id"])
        db = session_factory(self.settings.database_url)()
        try:
            service = AgentRunService(db, self.owner_id, self.settings)
            service.claim_step(crash_id, crash_step, "crashed-worker", delivery_attempt=0)
            step = db.get(AgentStep, crash_step)
            step.lease_expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        finally:
            db.close()
        current = self.client.get(f"/api/agent-runs/{crash_id}").json()
        resumed = self.client.post(
            f"/api/agent-runs/{crash_id}/resume",
            json={"expected_revision": current["revision"]}, headers=self.headers(),
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["status"], "queued")

    def test_complete_package_workflow_approvals_sse_and_exactly_once_artifacts(self):
        package = self.package()
        created = self.create_run(package["id"])
        run_id = created["run"]["id"]
        for suffix in ("resume", "letter", "package"):
            self.assertEqual(self.drive(run_id), "waiting_for_approval")
            pending = self.client.get(f"/api/agent-runs/{run_id}").json()["pending_approval"]
            stale = self.client.post(
                f"/api/approvals/{pending['id']}/decide",
                json={
                    "decision": "approve", "expected_revision": pending["revision"] + 1,
                    "idempotency_key": f"stale-{suffix}-0001", "safe_reason": "",
                },
                headers=self.headers(),
            )
            self.assertEqual(stale.status_code, 409)
            self.approve_pending(run_id, suffix)
        self.assertEqual(self.drive(run_id), "completed")
        detail = self.client.get(f"/api/agent-runs/{run_id}").json()
        self.assertEqual(detail["progress_percent"], 100)
        self.assertTrue(all(step["status"] == "completed" for step in detail["steps"]))
        stream = self.client.get(
            f"/api/agent-runs/{run_id}/events/stream", headers={"Last-Event-ID": "0"},
        )
        self.assertEqual(stream.status_code, 200, stream.text)
        self.assertIn("event: stream.complete", stream.text)
        self.assertEqual(
            self.other_client.get(f"/api/agent-runs/{run_id}/events/stream").status_code,
            404,
        )
        self.assertEqual(
            TestClient(self.client.app).get(f"/api/agent-runs/{run_id}/events/stream").status_code,
            401,
        )
        db = session_factory(self.settings.database_url)()
        try:
            materials_count = db.scalar(select(func.count()).select_from(ApplicationMaterial).where(
                ApplicationMaterial.package_id == UUID(package["id"]),
            ))
            usage_count = db.scalar(select(func.count()).select_from(AIUsageLedger).where(
                AIUsageLedger.run_id == UUID(run_id),
            ))
            self.assertEqual(materials_count, 3)
            self.assertEqual(usage_count, 3)
            events = db.scalars(select(AgentRunEvent).where(AgentRunEvent.run_id == UUID(run_id))).all()
            serialized = json.dumps([event.safe_payload for event in events]).casefold()
            for forbidden in ("correct horse", "python data engineer", "description", "prompt"):
                self.assertNotIn(forbidden, serialized)
        finally:
            db.close()

    def test_retry_backoff_dead_letter_budget_usage_and_outbox_recovery(self):
        package = self.package()
        created = self.create_run(package["id"])
        run_id = UUID(created["run"]["id"])
        step_id = UUID(created["run"]["steps"][0]["id"])
        for attempt_number in range(4):
            db = session_factory(self.settings.database_url)()
            try:
                service = AgentRunService(db, self.owner_id, self.settings)
                step = db.get(AgentStep, step_id)
                claim = service.claim_step(
                    run_id, step_id, f"retry-worker-{attempt_number}",
                    delivery_attempt=step.attempt,
                )
                service.fail_step(
                    run_id, step_id, claim["execution_token"],
                    "provider_temporary_failure", "Temporary provider failure.", True,
                    {
                        "provider": "mock", "model": "mock-model", "input_tokens": 10,
                        "output_tokens": 5, "total_tokens": 15,
                        "estimated_cost_usd": Decimal("0.001"),
                    },
                )
                db.commit()
            finally:
                db.close()
            current = self.client.get(f"/api/agent-runs/{run_id}").json()
            if attempt_number < 3:
                self.assertEqual(current["status"], "retry_scheduled")
                resumed = self.client.post(
                    f"/api/agent-runs/{run_id}/resume",
                    json={"expected_revision": current["revision"]}, headers=self.headers(),
                )
                self.assertEqual(resumed.status_code, 200, resumed.text)
            else:
                self.assertEqual(current["status"], "dead_letter")
        db = session_factory(self.settings.database_url)()
        try:
            self.assertEqual(db.scalar(select(func.count()).select_from(DeadLetterRecord)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(AIUsageLedger)), 4)
            run = db.get(AgentRun, run_id)
            step = db.get(AgentStep, step_id)
            service = AgentRunService(db, self.owner_id, self.settings)
            self.assertFalse(service.record_usage(
                run, step,
                {"provider": "mock", "model": "mock", "total_tokens": 999},
                f"{step.id}:failed:4",
            ))
            budget = db.scalar(select(UserAIBudget).where(UserAIBudget.user_id == self.owner_id))
            budget.step_token_limit = 100
            with self.assertRaises(AgentBudgetExceeded):
                service.ensure_budget(run, step, projected_tokens=101, projected_cost=0)
            db.rollback()
        finally:
            db.close()

        recovery_package = self.package(title="Redis Recovery Package")
        recovery = self.create_run(recovery_package["id"], key="redis-recovery-key-0001")
        db = session_factory(self.settings.database_url)()
        try:
            event = db.scalar(select(AgentOutboxEvent).where(
                AgentOutboxEvent.run_id == UUID(recovery["run"]["id"]),
            ))
            event.status = "published"
            event.published_at = utc_now() - timedelta(minutes=2)
            db.commit()
        finally:
            db.close()
        self.assertGreaterEqual(recover_orphaned_deliveries(stale_seconds=30), 1)
        with patch("app.agent_runs.tasks.run_agent_step.send", side_effect=ConnectionError("redis down")):
            self.assertEqual(dispatch_batch("unit-dispatcher"), 0)

    def test_approval_expiry_high_cost_approval_heartbeat_and_privacy_guards(self):
        package = self.package()
        created = self.create_run(package["id"])
        run_id = UUID(created["run"]["id"])
        self.assertEqual(self.drive(run_id), "waiting_for_approval")
        db = session_factory(self.settings.database_url)()
        try:
            approval = db.scalar(select(ApprovalRequest).where(
                ApprovalRequest.run_id == run_id, ApprovalRequest.status == "pending",
            ))
            approval.expires_at = utc_now() - timedelta(seconds=1)
            approval_id, revision = approval.id, approval.revision
            db.commit()
        finally:
            db.close()
        expired = self.client.post(
            f"/api/approvals/{approval_id}/decide",
            json={
                "decision": "approve", "expected_revision": revision,
                "idempotency_key": "expired-approval-0001", "safe_reason": "",
            },
            headers=self.headers(),
        )
        self.assertEqual(expired.status_code, 409)
        self.assertEqual(self.client.get(f"/api/agent-runs/{run_id}").json()["status"], "failed")

        high_package = self.package(title="High Cost Package")
        high = self.create_run(high_package["id"], key="high-cost-run-key-0001")
        high_run_id = UUID(high["run"]["id"])
        high_step_id = UUID(high["run"]["steps"][0]["id"])
        db = session_factory(self.settings.database_url)()
        try:
            low_threshold = replace(self.settings, agent_high_cost_approval_usd=0.01)
            service = AgentRunService(db, self.owner_id, low_threshold)
            claim = service.claim_step(high_run_id, high_step_id, "cost-worker", delivery_attempt=0)
            self.assertTrue(service.high_cost_approval_required(
                db.get(AgentRun, high_run_id), db.get(AgentStep, high_step_id), 0.05,
            ))
            self.assertTrue(service.request_high_cost_approval(
                high_run_id, high_step_id, claim["execution_token"],
            ))
            db.commit()
        finally:
            db.close()
        pending = self.client.get(f"/api/agent-runs/{high_run_id}").json()["pending_approval"]
        self.assertEqual(pending["approval_type"], "high_cost_generation")

        heartbeat("unit-worker-heartbeat", "busy", 1)
        pulse("unit-worker-heartbeat")
        db = session_factory(self.settings.database_url)()
        try:
            stored = db.get(WorkerHeartbeat, "unit-worker-heartbeat")
            self.assertEqual(stored.concurrency, self.settings.worker_concurrency)
            self.assertEqual(stored.status, "busy")
            self.assertEqual(stored.active_tasks, 1)
            with self.assertRaises(ValueError):
                validate_queue_payload({
                    "run_id": str(high_run_id), "step_id": str(high_step_id),
                    "workflow_type": "generate_application_package", "attempt": 0,
                    "correlation_id": "safe", "resume_body": "forbidden",
                })
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
