"""Transactional Agent Run persistence, state changes, approvals, and budgets."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_runs.definitions import (
    APPLICATION_PACKAGE_STEPS,
    APPROVAL_REQUEST_STEPS,
    MODEL_STEPS,
    WORKFLOW_TYPE,
    validate_queue_payload,
)
from app.agent_runs.state_machine import require_run_transition, require_step_transition
from app.core.config import V2Settings, load_v2_settings
from app.db.models import (
    AIUsageLedger,
    AgentOutboxEvent,
    AgentRun,
    AgentRunEvent,
    AgentStep,
    ApplicationMaterial,
    ApplicationMaterialVersion,
    ApplicationPackage,
    ApprovalDecision,
    ApprovalRequest,
    AuditEvent,
    DeadLetterRecord,
    UserAIBudget,
    User,
    ensure_utc,
    utc_now,
)
from app.materials.service import MaterialConflict, MaterialNotFound, MaterialService


ACTIVE_RUN_STATUSES = ("queued", "running", "waiting_for_approval", "retry_scheduled")


class AgentNotFound(RuntimeError):
    pass


class AgentConflict(RuntimeError):
    pass


class AgentBudgetExceeded(RuntimeError):
    pass


class AgentLimitExceeded(RuntimeError):
    pass


def _iso(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _columns(value: Any, excluded: set[str] | None = None) -> dict[str, Any]:
    return {
        column.name: _iso(getattr(value, column.name))
        for column in value.__table__.columns
        if column.name not in (excluded or set())
    }


def _safe_error(code: str, summary: str) -> tuple[str, str]:
    safe_code = "".join(character for character in code if character.isalnum() or character in "_.-")[:80]
    safe_summary = " ".join(str(summary).split())[:500]
    return safe_code or "workflow_error", safe_summary or "The workflow step failed safely."


class AgentRunService:
    def __init__(self, db: Session, owner_id: UUID | None = None, settings: V2Settings | None = None):
        self.db = db
        self.owner_id = owner_id
        self.settings = settings or load_v2_settings()

    def create(self, values: dict[str, Any], idempotency_key: str) -> tuple[dict[str, Any], bool]:
        owner_id = self._owner()
        # Serialize Run creation per owner so concurrent duplicate requests and
        # concurrent-limit checks observe one authoritative PostgreSQL state.
        owner_exists = self.db.scalar(
            select(User.id).where(User.id == owner_id).with_for_update()
        )
        if owner_exists is None:
            raise AgentNotFound("Owning user not found.")
        if values.get("workflow_type") != WORKFLOW_TYPE:
            raise AgentConflict("Unsupported Agent workflow type.")
        package_id = UUID(str(values["package_id"]))
        package = self.db.scalar(select(ApplicationPackage).where(
            ApplicationPackage.id == package_id,
            ApplicationPackage.owner_user_id == owner_id,
        ))
        if package is None:
            raise AgentNotFound("Application Package not found.")
        force_new = bool(values.get("force_new"))
        mode = "force" if force_new else "normal"
        digest = hashlib.sha256(
            f"{owner_id}:{WORKFLOW_TYPE}:{mode}:{idempotency_key}".encode()
        ).hexdigest()
        existing = self.db.scalar(select(AgentRun).where(
            AgentRun.owner_user_id == owner_id,
            AgentRun.workflow_type == WORKFLOW_TYPE,
            AgentRun.idempotency_key_hash == digest,
        ))
        if existing is not None:
            if existing.package_id != package.id:
                raise AgentConflict("The Idempotency-Key was already used with different input references.")
            return self.run(existing.id), True
        budget = self._today_budget(owner_id)
        active = self.db.scalar(select(func.count()).select_from(AgentRun).where(
            AgentRun.owner_user_id == owner_id,
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )) or 0
        if active >= budget.concurrent_run_limit:
            raise AgentLimitExceeded("The per-user concurrent Agent Run limit has been reached.")
        run = AgentRun(
            owner_user_id=owner_id,
            workflow_type=WORKFLOW_TYPE,
            status="queued",
            idempotency_key_hash=digest,
            correlation_id=str(uuid4()),
            input_refs={
                "package_id": str(package.id),
                "application_id": str(package.application_id),
                "job_id": str(package.job_id),
                "resume_version_id": str(package.source_resume_version_id),
            },
            profile_revision=package.source_profile_revision,
            job_revision=package.source_job_revision,
            resume_version_id=package.source_resume_version_id,
            application_id=package.application_id,
            package_id=package.id,
            current_step_key=APPLICATION_PACKAGE_STEPS[0].key,
            token_limit=min(budget.run_token_limit, self.settings.agent_run_token_limit),
            cost_limit_usd=Decimal(str(self.settings.agent_run_cost_limit_usd)),
            max_attempts=self.settings.agent_max_auto_retries,
        )
        self.db.add(run)
        self.db.flush()
        steps: list[AgentStep] = []
        for order, definition in enumerate(APPLICATION_PACKAGE_STEPS, start=1):
            step = AgentStep(
                run_id=run.id,
                owner_user_id=owner_id,
                step_key=definition.key,
                step_order=order,
                status="queued" if order == 1 else "pending",
                idempotency_key=f"{run.id}:{definition.key}:v1",
                scheduled_at=utc_now() if order == 1 else None,
                max_attempts=1 + self.settings.agent_max_auto_retries,
            )
            self.db.add(step)
            steps.append(step)
        self.db.flush()
        self._event(run, "run.created", "Agent Run queued.", payload={"workflow_type": WORKFLOW_TYPE})
        self._enqueue(run, steps[0])
        self._audit("agent_run.created", run.id, {"workflow_type": WORKFLOW_TYPE})
        return self._run_detail(run), False

    def list(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        owner_id = self._owner()
        statement = select(AgentRun).where(AgentRun.owner_user_id == owner_id)
        if status:
            statement = statement.where(AgentRun.status == status)
        runs = self.db.scalars(statement.order_by(AgentRun.created_at.desc()).limit(min(limit, 200))).all()
        return [self._run_summary(item) for item in runs]

    def run(self, run_id: UUID) -> dict[str, Any]:
        run = self._owned_run(run_id)
        return self._run_detail(run)

    def steps(self, run_id: UUID) -> list[dict[str, Any]]:
        run = self._owned_run(run_id)
        values = self.db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.step_order)).all()
        return [self._step(item) for item in values]

    def events(self, run_id: UUID, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        run = self._owned_run(run_id)
        values = self.db.scalars(select(AgentRunEvent).where(
            AgentRunEvent.run_id == run.id,
            AgentRunEvent.id > max(after_id, 0),
        ).order_by(AgentRunEvent.id).limit(min(limit, 1000))).all()
        return [_columns(item) for item in values]

    def cancel(self, run_id: UUID, expected_revision: int) -> dict[str, Any]:
        run = self._owned_run(run_id, for_update=True)
        if run.status == "cancelled":
            return self._run_detail(run)
        self._expect_revision(run.revision, expected_revision)
        if run.status == "completed":
            raise AgentConflict("Completed Agent Runs cannot be cancelled.")
        if run.status == "dead_letter":
            raise AgentConflict("Dead-letter Agent Runs cannot be cancelled.")
        if run.status == "running":
            if not run.cancel_requested:
                run.cancel_requested = True
                run.revision += 1
                self._event(run, "run.cancel_requested", "Cancellation requested; the Worker will stop at a step boundary.")
        else:
            self._cancel_now(run)
        self._audit("agent_run.cancelled", run.id, {"status": run.status})
        return self._run_detail(run)

    def retry(self, run_id: UUID, expected_revision: int, acknowledge_possible_cost: bool) -> dict[str, Any]:
        run = self._owned_run(run_id, for_update=True)
        self._expect_revision(run.revision, expected_revision)
        if run.status != "failed":
            raise AgentConflict("Only a failed Agent Run can be retried explicitly.")
        if run.safe_error_code in {"approval_rejected", "approval_expired"}:
            raise AgentConflict("A rejected or expired approval requires a new Agent Run.")
        if (run.total_tokens or Decimal(run.estimated_cost_usd or 0) > 0) and not acknowledge_possible_cost:
            raise AgentConflict("Retry may incur additional token usage and estimated cost; acknowledgment is required.")
        self._restart_failed(run, "run.retry_requested", "Explicit retry queued; completed steps will be reused.")
        self._audit("agent_run.retry_requested", run.id, {"attempt": run.attempt}, user_id=run.owner_user_id)
        return self._run_detail(run)

    def resume(self, run_id: UUID, expected_revision: int) -> dict[str, Any]:
        run = self._owned_run(run_id, for_update=True)
        self._expect_revision(run.revision, expected_revision)
        if run.status == "running" and run.cancel_requested:
            self._cancel_now(run)
            return self._run_detail(run)
        if run.status == "failed":
            if run.safe_error_code in {"approval_rejected", "approval_expired"}:
                raise AgentConflict("A rejected or expired approval requires a new Agent Run.")
            self._restart_failed(run, "run.resume_requested", "Run resumed from its failed step; completed steps will be reused.")
            self._audit("agent_run.resume_requested", run.id, {"attempt": run.attempt}, user_id=run.owner_user_id)
            return self._run_detail(run)
        if run.status == "retry_scheduled":
            step = self.db.scalar(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.status == "retry_scheduled",
            ).with_for_update())
            if step is None:
                raise AgentConflict("No retryable step is available.")
            self._transition_run(run, "queued", "run.resume_requested", "Scheduled retry resumed now.")
            self._transition_step(run, step, "queued", "step.retry_queued", "Retry step queued.")
            run.retry_at = None
            self._enqueue(run, step)
            self._audit("agent_run.resume_requested", run.id, {"attempt": run.attempt}, user_id=run.owner_user_id)
            return self._run_detail(run)
        if run.status == "running":
            step = self.db.scalar(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.status == "running",
            ).with_for_update())
            if step and step.lease_expires_at and ensure_utc(step.lease_expires_at) <= utc_now():
                self._transition_step(run, step, "retry_scheduled", "step.crash_recovered", "Expired Worker lease recovered.")
                self._transition_run(run, "retry_scheduled", "run.crash_recovered", "Worker crash recovered; retry scheduled.")
                run.retry_at = utc_now()
                self._transition_run(run, "queued", "run.resume_requested", "Recovered step queued.")
                self._transition_step(run, step, "queued", "step.retry_queued", "Recovered step queued.")
                self._enqueue(run, step)
                return self._run_detail(run)
        raise AgentConflict("This Agent Run cannot be resumed in its current state.")

    def approvals(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        owner_id = self._owner()
        statement = select(ApprovalRequest).where(ApprovalRequest.owner_user_id == owner_id)
        if status:
            statement = statement.where(ApprovalRequest.status == status)
        values = self.db.scalars(statement.order_by(ApprovalRequest.created_at.desc()).limit(min(limit, 200))).all()
        return [self._approval(item) for item in values]

    def approval(self, approval_id: UUID) -> dict[str, Any]:
        approval = self._owned_approval(approval_id)
        return self._approval(approval, include_decisions=True)

    def decide_approval(
        self, approval_id: UUID, decision: str, expected_revision: int,
        idempotency_key: str, safe_reason: str,
    ) -> dict[str, Any]:
        approval = self._owned_approval(approval_id, for_update=True)
        duplicate = self.db.scalar(select(ApprovalDecision).where(
            ApprovalDecision.approval_request_id == approval.id,
            ApprovalDecision.idempotency_key == idempotency_key,
        ))
        if duplicate is not None:
            return self._approval(approval, include_decisions=True)
        self._expect_revision(approval.revision, expected_revision)
        run = self.db.scalar(select(AgentRun).where(AgentRun.id == approval.run_id).with_for_update())
        step = self.db.scalar(select(AgentStep).where(AgentStep.id == approval.step_id).with_for_update())
        if run is None or step is None or approval.status != "pending":
            raise AgentConflict("Approval is no longer pending.")
        if ensure_utc(approval.expires_at) <= utc_now():
            approval.status = "expired"
            approval.revision += 1
            approval.decided_at = utc_now()
            self._transition_step(run, step, "failed", "approval.expired", "Approval expired.")
            self._transition_run(run, "failed", "run.approval_expired", "Required approval expired.")
            raise AgentConflict("Approval has expired.")
        if decision == "approve":
            self._apply_approval_side_effects(run, approval)
        recorded = ApprovalDecision(
            approval_request_id=approval.id,
            run_id=run.id,
            owner_user_id=approval.owner_user_id,
            decided_by_user_id=self._owner(),
            decision=decision,
            request_revision=approval.revision,
            idempotency_key=idempotency_key,
            safe_reason=" ".join(safe_reason.split())[:500],
        )
        self.db.add(recorded)
        approval.status = "approved" if decision == "approve" else "rejected"
        approval.revision += 1
        approval.decided_at = utc_now()
        if decision == "reject":
            self._transition_step(run, step, "failed", "approval.rejected", "Approval rejected by the owning user.")
            self._transition_run(run, "failed", "run.approval_rejected", "Required approval was rejected.")
            run.safe_error_code = "approval_rejected"
            run.safe_error_summary = "A required approval was rejected."
        elif approval.approval_type == "high_cost_generation":
            self._transition_step(run, step, "queued", "approval.approved", "High-cost generation approved and queued.")
            self._transition_run(run, "queued", "run.approval_received", "High-cost generation approval received.")
            self._enqueue(run, step)
        else:
            self._transition_step(run, step, "completed", "approval.approved", "Approval received from the owning user.")
            step.completed_at = utc_now()
            self._transition_run(run, "queued", "run.approval_received", "Required approval received; workflow queued.")
            self._queue_after(run, step)
        self._audit("approval.decided", approval.id, {"decision": decision, "run_id": str(run.id)})
        self.db.flush()
        return self._approval(approval, include_decisions=True)

    def claim_step(
        self, run_id: UUID, step_id: UUID, worker_id: str,
        delivery_attempt: int | None = None,
    ) -> dict[str, Any] | None:
        run = self.db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        step = self.db.scalar(select(AgentStep).where(AgentStep.id == step_id, AgentStep.run_id == run_id).with_for_update())
        if run is None or step is None or run.workflow_type != WORKFLOW_TYPE:
            return None
        if step.status in {"completed", "skipped", "cancelled"}:
            return None
        if delivery_attempt is not None and delivery_attempt != step.attempt:
            self._event(
                run, "step.stale_delivery", "Stale step delivery ignored.", step=step,
                payload={"attempt": delivery_attempt},
            )
            return None
        now = utc_now()
        if run.cancel_requested or run.status == "cancelled":
            self._cancel_now(run)
            return None
        if step.status == "running":
            if not step.lease_expires_at or ensure_utc(step.lease_expires_at) > now:
                self._event(run, "step.duplicate_delivery", "Duplicate step delivery ignored.", step=step)
                return None
            self._transition_step(run, step, "retry_scheduled", "step.lease_expired", "Expired Worker lease recovered.")
            self._transition_run(run, "retry_scheduled", "run.retry_scheduled", "Worker lease expired; retry scheduled.")
        if step.status == "retry_scheduled":
            if run.retry_at and ensure_utc(run.retry_at) > now:
                return None
            self._transition_step(run, step, "queued", "step.retry_queued", "Retry step queued.")
            if run.status == "retry_scheduled":
                self._transition_run(run, "queued", "run.retry_due", "Scheduled retry is due.")
        if step.status != "queued" or run.status not in {"queued", "running"}:
            return None
        if run.status == "queued":
            self._transition_run(run, "running", "run.started", "Agent Run started.")
            run.started_at = run.started_at or now
        self._transition_step(run, step, "running", "step.started", f"Step {step.step_key} started.")
        step.attempt += 1
        step.execution_token = uuid4().hex
        step.worker_id = worker_id[:120]
        step.lease_expires_at = now + timedelta(seconds=self.settings.worker_step_lease_seconds)
        step.started_at = now
        run.current_step_key = step.step_key
        return {
            "run_id": str(run.id),
            "step_id": str(step.id),
            "step_key": step.step_key,
            "attempt": step.attempt,
            "execution_token": step.execution_token,
            "owner_user_id": str(run.owner_user_id),
            "package_id": str(run.package_id) if run.package_id else None,
        }

    def complete_step(
        self, run_id: UUID, step_id: UUID, execution_token: str,
        output_refs: dict[str, Any] | None = None, usage: dict[str, Any] | None = None,
    ) -> bool:
        run, step = self._locked_run_step(run_id, step_id)
        if step.status == "completed":
            return False
        if step.status != "running" or step.execution_token != execution_token:
            return False
        if run.cancel_requested:
            self._cancel_now(run)
            return False
        safe_refs = self._safe_refs(output_refs or {})
        if usage is not None:
            self.record_usage(run, step, usage, f"{step.id}:success")
        step.output_refs = safe_refs
        step.execution_token = None
        step.lease_expires_at = None
        step.completed_at = utc_now()
        self._transition_step(run, step, "completed", "step.completed", f"Step {step.step_key} completed.")
        if step.step_key in APPROVAL_REQUEST_STEPS:
            wait_key, approval_type = APPROVAL_REQUEST_STEPS[step.step_key]
            wait_step = self.db.scalar(select(AgentStep).where(
                AgentStep.run_id == run.id, AgentStep.step_key == wait_key,
            ).with_for_update())
            if wait_step is None:
                raise AgentConflict("Approval wait step is missing.")
            self._transition_step(run, wait_step, "waiting_for_approval", "approval.requested", "User approval requested.")
            self._transition_run(run, "waiting_for_approval", "run.waiting_for_approval", "Agent Run is waiting for user approval.")
            run.current_step_key = wait_step.step_key
            self._create_approval(run, wait_step, approval_type)
        else:
            self._queue_after(run, step)
        return True

    def fail_step(
        self, run_id: UUID, step_id: UUID, execution_token: str,
        code: str, summary: str, retriable: bool, usage: dict[str, Any] | None = None,
    ) -> None:
        run, step = self._locked_run_step(run_id, step_id)
        if step.status != "running" or step.execution_token != execution_token:
            return
        code, summary = _safe_error(code, summary)
        if usage is not None:
            self.record_usage(run, step, usage, f"{step.id}:failed:{step.attempt}")
        step.safe_error_code = code
        step.safe_error_summary = summary
        run.safe_error_code = code
        run.safe_error_summary = summary
        run.partial = bool(self.db.scalar(select(func.count()).select_from(AgentStep).where(
            AgentStep.run_id == run.id, AgentStep.status == "completed",
        )))
        step.execution_token = None
        step.lease_expires_at = None
        if retriable and step.attempt < step.max_attempts:
            delay = min(300, (2 ** max(step.attempt - 1, 0)) * 5 + (int(step.id.hex[:2], 16) % 4))
            retry_at = utc_now() + timedelta(seconds=delay)
            self._transition_step(run, step, "retry_scheduled", "step.retry_scheduled", "Temporary failure; retry scheduled.", {"attempt": step.attempt, "retry_in_seconds": delay})
            self._transition_run(run, "retry_scheduled", "run.retry_scheduled", "Temporary failure; retry scheduled.")
            run.retry_at = retry_at
            step.scheduled_at = retry_at
            self._enqueue(run, step, available_at=retry_at)
            return
        self._transition_step(run, step, "failed", "step.failed", summary, {"error_code": code})
        self._transition_run(run, "failed", "run.failed", "Agent Run failed safely.", {"error_code": code})
        if retriable and step.attempt >= step.max_attempts:
            self._transition_run(run, "dead_letter", "run.dead_letter", "Retry limit exhausted; Run moved to dead letter.")
            self.db.add(DeadLetterRecord(
                owner_user_id=run.owner_user_id,
                run_id=run.id,
                step_id=step.id,
                reason_code="retry_exhausted",
                safe_error_summary=summary,
                attempts=step.attempt,
                safe_payload={"run_id": str(run.id), "step_id": str(step.id), "workflow_type": run.workflow_type, "attempt": step.attempt, "correlation_id": run.correlation_id},
            ))

    def ensure_budget(self, run: AgentRun, step: AgentStep, projected_tokens: int = 1000, projected_cost: float = 0.05) -> None:
        budget = self._today_budget(run.owner_user_id)
        totals = self.db.execute(select(
            func.coalesce(func.sum(AIUsageLedger.total_tokens), 0),
            func.coalesce(func.sum(AIUsageLedger.estimated_cost_usd), 0),
        ).where(
            AIUsageLedger.owner_user_id == run.owner_user_id,
            AIUsageLedger.created_at >= utc_now().replace(hour=0, minute=0, second=0, microsecond=0),
        )).one()
        if projected_tokens > budget.step_token_limit:
            raise AgentBudgetExceeded("The projected step token usage exceeds the per-step limit.")
        if run.total_tokens + projected_tokens > min(run.token_limit, budget.run_token_limit):
            raise AgentBudgetExceeded("The projected token usage exceeds the Agent Run limit.")
        if int(totals[0]) + projected_tokens > budget.daily_token_limit:
            raise AgentBudgetExceeded("The projected token usage exceeds the daily limit.")
        if Decimal(totals[1] or 0) + Decimal(str(projected_cost)) > Decimal(budget.daily_cost_limit_usd):
            raise AgentBudgetExceeded("The projected estimated cost exceeds the daily limit.")
        if Decimal(run.estimated_cost_usd or 0) + Decimal(str(projected_cost)) > Decimal(run.cost_limit_usd):
            raise AgentBudgetExceeded("The projected estimated cost exceeds the Agent Run limit.")

    def record_usage(self, run: AgentRun, step: AgentStep, usage: dict[str, Any], usage_key: str) -> bool:
        existing = self.db.scalar(select(AIUsageLedger.id).where(AIUsageLedger.usage_key == usage_key))
        if existing is not None:
            return False
        input_tokens = max(int(usage.get("input_tokens") or 0), 0)
        output_tokens = max(int(usage.get("output_tokens") or 0), 0)
        total_tokens = max(int(usage.get("total_tokens") or input_tokens + output_tokens), 0)
        estimated_cost = max(Decimal(str(usage.get("estimated_cost_usd") or 0)), Decimal(0))
        ledger = AIUsageLedger(
            owner_user_id=run.owner_user_id,
            run_id=run.id,
            step_id=step.id,
            usage_key=usage_key,
            provider=str(usage.get("provider") or "unknown")[:80],
            model=str(usage.get("model") or "unknown")[:120],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost,
        )
        self.db.add(ledger)
        step.input_tokens += input_tokens
        step.output_tokens += output_tokens
        step.estimated_cost_usd = Decimal(step.estimated_cost_usd or 0) + estimated_cost
        run.total_tokens += total_tokens
        run.estimated_cost_usd = Decimal(run.estimated_cost_usd or 0) + estimated_cost
        return True

    def request_high_cost_approval(self, run_id: UUID, step_id: UUID, execution_token: str) -> bool:
        run, step = self._locked_run_step(run_id, step_id)
        if step.status != "running" or step.execution_token != execution_token:
            return False
        step.execution_token = None
        step.lease_expires_at = None
        self._transition_step(run, step, "waiting_for_approval", "approval.requested", "High-cost generation requires approval.")
        self._transition_run(run, "waiting_for_approval", "run.waiting_for_approval", "Agent Run is waiting for high-cost generation approval.")
        self._create_approval(run, step, "high_cost_generation", risk_level="high")
        return True

    def high_cost_approval_required(
        self, run: AgentRun, step: AgentStep, projected_cost: float = 0.75,
    ) -> bool:
        if Decimal(str(projected_cost)) < Decimal(str(self.settings.agent_high_cost_approval_usd)):
            return False
        approved = self.db.scalar(select(ApprovalRequest.id).where(
            ApprovalRequest.run_id == run.id,
            ApprovalRequest.step_id == step.id,
            ApprovalRequest.approval_type == "high_cost_generation",
            ApprovalRequest.status == "approved",
        ))
        return approved is None

    def _queue_after(self, run: AgentRun, step: AgentStep) -> None:
        next_step = self.db.scalar(select(AgentStep).where(
            AgentStep.run_id == run.id,
            AgentStep.step_order > step.step_order,
        ).order_by(AgentStep.step_order).limit(1).with_for_update())
        self.db.flush()
        completed = self.db.scalar(select(func.count()).select_from(AgentStep).where(
            AgentStep.run_id == run.id,
            AgentStep.status.in_(("completed", "skipped")),
        )) or 0
        run.progress_percent = min(100, round((completed / len(APPLICATION_PACKAGE_STEPS)) * 100))
        if next_step is None:
            self._transition_run(run, "completed", "run.completed", "Agent Run completed.")
            run.progress_percent = 100
            run.current_step_key = None
            run.completed_at = utc_now()
            return
        if next_step.step_key.startswith("wait_"):
            raise AgentConflict("Approval wait steps must be entered through an approval request step.")
        self._transition_step(run, next_step, "queued", "step.queued", f"Step {next_step.step_key} queued.")
        next_step.scheduled_at = utc_now()
        run.current_step_key = next_step.step_key
        self._enqueue(run, next_step)

    def _restart_failed(self, run: AgentRun, event_type: str, summary: str) -> None:
        step = self.db.scalar(select(AgentStep).where(
            AgentStep.run_id == run.id,
            AgentStep.status == "failed",
        ).order_by(AgentStep.step_order).limit(1).with_for_update())
        if step is None:
            raise AgentConflict("No failed Agent Step is available to restart.")
        if step.step_key.startswith("wait_"):
            raise AgentConflict("Approval failures require a new Agent Run.")
        self._transition_run(run, "queued", event_type, summary)
        self._transition_step(run, step, "queued", "step.retry_queued", "Failed step queued explicitly.")
        run.attempt += 1
        run.retry_at = None
        run.safe_error_code = None
        run.safe_error_summary = None
        step.safe_error_code = None
        step.safe_error_summary = None
        step.scheduled_at = utc_now()
        self._enqueue(run, step)

    def _create_approval(self, run: AgentRun, step: AgentStep, approval_type: str, risk_level: str = "normal") -> ApprovalRequest:
        existing = self.db.scalar(select(ApprovalRequest).where(
            ApprovalRequest.run_id == run.id,
            ApprovalRequest.step_id == step.id,
            ApprovalRequest.approval_type == approval_type,
        ))
        if existing is not None:
            return existing
        labels = {
            "resume_draft": "Review tailored Resume draft",
            "cover_letter_draft": "Review Cover Letter draft",
            "application_package": "Review complete Application Package",
            "high_cost_generation": "Approve high-cost generation",
        }
        approval = ApprovalRequest(
            run_id=run.id,
            step_id=step.id,
            owner_user_id=run.owner_user_id,
            approval_type=approval_type,
            title=labels.get(approval_type, "Review Agent action"),
            safe_summary="Review the generated artifact in the application workspace. No action will be sent externally.",
            risk_level=risk_level,
            expires_at=utc_now() + timedelta(days=7),
        )
        self.db.add(approval)
        self.db.flush()
        self._event(run, "approval.created", "Approval request created.", step=step, payload={"approval_id": str(approval.id), "approval_type": approval_type})
        return approval

    def _apply_approval_side_effects(self, run: AgentRun, approval: ApprovalRequest) -> None:
        if approval.approval_type == "high_cost_generation":
            return
        if run.package_id is None:
            raise AgentConflict("Application Package reference is missing.")
        materials = MaterialService(self.db, run.owner_user_id)
        try:
            if approval.approval_type in {"resume_draft", "cover_letter_draft"}:
                kind = "tailored_resume" if approval.approval_type == "resume_draft" else "cover_letter"
                material = self.db.scalar(select(ApplicationMaterial).where(
                    ApplicationMaterial.package_id == run.package_id,
                    ApplicationMaterial.owner_user_id == run.owner_user_id,
                    ApplicationMaterial.material_type == kind,
                ).order_by(ApplicationMaterial.created_at.desc()))
                if material is None or material.active_version_id is None:
                    raise AgentConflict("The generated draft is unavailable.")
                version = self.db.scalar(select(ApplicationMaterialVersion).where(
                    ApplicationMaterialVersion.id == material.active_version_id,
                ))
                if version is None or version.validation_status != "valid" or version.unsupported_claim_count:
                    raise AgentConflict("Unsupported or unvalidated claims must be resolved before approval.")
                materials.review(version.id, "approve", "Approved through the Agent workflow approval request.")
                materials.finalize(version.id)
            elif approval.approval_type == "application_package":
                package = self.db.get(ApplicationPackage, run.package_id)
                if package is None:
                    raise AgentConflict("Application Package is unavailable.")
                materials.approve_package(package.id, package.revision)
        except (MaterialConflict, MaterialNotFound) as exc:
            raise AgentConflict(str(exc)) from exc

    def _cancel_now(self, run: AgentRun) -> None:
        if run.status == "cancelled":
            return
        if run.status == "running":
            target_status = "cancelled"
        elif run.status in {"queued", "waiting_for_approval", "retry_scheduled", "failed"}:
            target_status = "cancelled"
        else:
            raise AgentConflict("Agent Run cannot be cancelled in its current state.")
        self._transition_run(run, target_status, "run.cancelled", "Agent Run cancelled at a safe step boundary.")
        run.cancel_requested = True
        run.cancelled_at = utc_now()
        run.partial = bool(self.db.scalar(select(func.count()).select_from(AgentStep).where(
            AgentStep.run_id == run.id, AgentStep.status == "completed",
        )))
        steps = self.db.scalars(select(AgentStep).where(
            AgentStep.run_id == run.id,
            AgentStep.status.in_(("pending", "queued", "running", "waiting_for_approval", "retry_scheduled", "failed")),
        ).with_for_update()).all()
        for step in steps:
            if step.status != "cancelled":
                self._transition_step(run, step, "cancelled", "step.cancelled", f"Step {step.step_key} cancelled.")
        approvals = self.db.scalars(select(ApprovalRequest).where(
            ApprovalRequest.run_id == run.id, ApprovalRequest.status == "pending",
        ).with_for_update()).all()
        for approval in approvals:
            approval.status = "cancelled"
            approval.revision += 1
            approval.decided_at = utc_now()

    def _enqueue(self, run: AgentRun, step: AgentStep, available_at: Any | None = None) -> AgentOutboxEvent:
        payload = validate_queue_payload({
            "run_id": str(run.id),
            "step_id": str(step.id),
            "workflow_type": run.workflow_type,
            "attempt": step.attempt,
            "correlation_id": run.correlation_id,
        })
        key = f"{step.id}:{step.revision}:{step.attempt}"
        existing = self.db.scalar(select(AgentOutboxEvent).where(AgentOutboxEvent.deduplication_key == key))
        if existing is not None:
            return existing
        value = AgentOutboxEvent(
            run_id=run.id,
            step_id=step.id,
            event_type="execute_agent_step",
            payload=payload,
            deduplication_key=key,
            available_at=available_at or utc_now(),
        )
        self.db.add(value)
        return value

    def _today_budget(self, owner_id: UUID) -> UserAIBudget:
        today = utc_now().date()
        budget = self.db.scalar(select(UserAIBudget).where(
            UserAIBudget.user_id == owner_id, UserAIBudget.budget_date == today,
        ).with_for_update())
        if budget is None:
            budget = UserAIBudget(
                user_id=owner_id,
                budget_date=today,
                daily_token_limit=self.settings.agent_daily_token_limit,
                daily_cost_limit_usd=Decimal(str(self.settings.agent_daily_cost_limit_usd)),
                run_token_limit=self.settings.agent_run_token_limit,
                step_token_limit=self.settings.agent_step_token_limit,
                concurrent_run_limit=self.settings.agent_user_concurrency_limit,
            )
            self.db.add(budget)
            self.db.flush()
        return budget

    def _run_detail(self, run: AgentRun) -> dict[str, Any]:
        value = self._run_summary(run)
        value["steps"] = self.steps(run.id) if self.owner_id is not None else [
            self._step(item) for item in self.db.scalars(select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.step_order)).all()
        ]
        approval = self.db.scalar(select(ApprovalRequest).where(
            ApprovalRequest.run_id == run.id,
            ApprovalRequest.status == "pending",
        ).order_by(ApprovalRequest.created_at.desc()))
        value["pending_approval"] = self._approval(approval) if approval else None
        return value

    def _run_summary(self, run: AgentRun) -> dict[str, Any]:
        return _columns(run, {"idempotency_key_hash"})

    def _step(self, step: AgentStep) -> dict[str, Any]:
        return _columns(step, {"execution_token", "worker_id", "lease_expires_at", "idempotency_key"})

    def _approval(self, approval: ApprovalRequest, include_decisions: bool = False) -> dict[str, Any]:
        value = _columns(approval)
        if include_decisions:
            decisions = self.db.scalars(select(ApprovalDecision).where(
                ApprovalDecision.approval_request_id == approval.id,
            ).order_by(ApprovalDecision.created_at)).all()
            value["decisions"] = [_columns(item, {"idempotency_key", "safe_reason"}) for item in decisions]
        return value

    def _owned_run(self, run_id: UUID, for_update: bool = False) -> AgentRun:
        statement = select(AgentRun).where(AgentRun.id == run_id, AgentRun.owner_user_id == self._owner())
        if for_update:
            statement = statement.with_for_update()
        value = self.db.scalar(statement)
        if value is None:
            raise AgentNotFound("Agent Run not found.")
        return value

    def _owned_approval(self, approval_id: UUID, for_update: bool = False) -> ApprovalRequest:
        statement = select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id, ApprovalRequest.owner_user_id == self._owner(),
        )
        if for_update:
            statement = statement.with_for_update()
        value = self.db.scalar(statement)
        if value is None:
            raise AgentNotFound("Approval Request not found.")
        return value

    def _locked_run_step(self, run_id: UUID, step_id: UUID) -> tuple[AgentRun, AgentStep]:
        run = self.db.scalar(select(AgentRun).where(AgentRun.id == run_id).with_for_update())
        step = self.db.scalar(select(AgentStep).where(AgentStep.id == step_id, AgentStep.run_id == run_id).with_for_update())
        if run is None or step is None:
            raise AgentNotFound("Agent Run Step not found.")
        return run, step

    def _transition_run(
        self, run: AgentRun, target: str, event_type: str, summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        require_run_transition(run.status, target)
        previous = run.status
        run.status = target
        run.revision += 1
        self._event(run, event_type, summary, payload={"from": previous, "to": target, **(payload or {})})
        self._audit(
            f"agent_run.transition.{target}", run.id,
            {"from": previous, "to": target, **(payload or {})},
            user_id=run.owner_user_id,
        )

    def _transition_step(
        self, run: AgentRun, step: AgentStep, target: str, event_type: str, summary: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        require_step_transition(step.status, target)
        previous = step.status
        step.status = target
        step.revision += 1
        run.revision += 1
        self._event(run, event_type, summary, step=step, payload={"from": previous, "to": target, **(payload or {})})
        self._audit(
            f"agent_step.transition.{target}", step.id,
            {"from": previous, "to": target, "step_key": step.step_key, **(payload or {})},
            user_id=run.owner_user_id,
        )

    def _event(
        self, run: AgentRun, event_type: str, summary: str,
        step: AgentStep | None = None, payload: dict[str, Any] | None = None,
    ) -> AgentRunEvent:
        safe_payload = self._safe_event_payload(payload or {})
        value = AgentRunEvent(
            run_id=run.id,
            owner_user_id=run.owner_user_id,
            step_id=step.id if step else None,
            event_type=event_type[:100],
            summary=" ".join(summary.split())[:500],
            safe_payload=safe_payload,
            run_revision=run.revision,
        )
        self.db.add(value)
        return value

    def _safe_event_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "from", "to", "workflow_type", "attempt", "retry_in_seconds", "error_code",
            "approval_id", "approval_type", "step_key", "progress_percent", "reused",
            "status", "decision", "run_id",
        }
        return {key: _iso(value) for key, value in payload.items() if key in allowed}

    def _safe_refs(self, values: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "package_id", "application_id", "job_id", "resume_version_id", "profile_revision",
            "job_revision", "match_analysis_id", "material_id", "material_version_id",
            "material_version_ids", "approval_id", "evidence_count", "reused",
        }
        result: dict[str, Any] = {}
        for key, value in values.items():
            if key not in allowed:
                continue
            if isinstance(value, list):
                result[key] = [str(item)[:64] for item in value[:20]]
            elif isinstance(value, (str, UUID, int, bool)):
                result[key] = _iso(value)
        return result

    def _audit(
        self, event_type: str, resource_id: UUID,
        metadata: dict[str, Any] | None = None, user_id: UUID | None = None,
    ) -> None:
        self.db.add(AuditEvent(
            user_id=user_id if user_id is not None else self.owner_id,
            event_type=event_type[:80],
            resource_type="agent_workflow",
            resource_id=str(resource_id),
            safe_metadata=self._safe_event_payload(metadata or {}),
        ))

    def _expect_revision(self, current: int, expected: int) -> None:
        if current != expected:
            raise AgentConflict("Stale revision; reload the resource before retrying.")

    def _owner(self) -> UUID:
        if self.owner_id is None:
            raise AgentConflict("An owning user is required for this operation.")
        return self.owner_id
