import io
import logging
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from docx import Document
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

import legacy_application
from agent_workflow import AgentWorkflow
from app.api.routers import auth
from app.analyze.input_preparation import prepare_analyze_input
from app.auth.middleware import V2SecurityMiddleware
from app.auth.service import AuthService
from app.core.config import load_v2_settings
from app.db.base import Base
from app.db.engine import build_engine
from app.db.session import session_factory
from app.jobs.acquisition import SafeJobUrlFetcher
from logging_utils import RequestLoggingMiddleware


def docx_bytes(text: str = "Synthetic Python FastAPI resume") -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def pdf_bytes(text: str = "Synthetic Python FastAPI resume") -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output)
    document.drawString(72, 720, text)
    document.showPage()
    document.save()
    return output.getvalue()


def input_steps(response) -> list[tuple[str, str, str, str]]:
    return [
        (step["key"], step["name"], step["status"], step["message"])
        for step in response.json()["workflow_steps"][:3]
    ]


def rethrow_input_failure(*_args, exc: Exception, **_kwargs):
    raise exc


class AnalyzeInputPreparationResultTest(unittest.IsolatedAsyncioTestCase):
    async def prepare(self, *, resume, resume_version_id=None, job_text=None, job_url=None):
        workflow = AgentWorkflow("phase3a-structured-result")
        request = SimpleNamespace(state=SimpleNamespace())
        result = await prepare_analyze_input(
            request=request,
            resume=resume,
            resume_version_id=resume_version_id,
            job_text=job_text,
            job_url=job_url,
            use_knowledge_base=True,
            use_project_knowledge=True,
            rag_top_k=5,
            project_knowledge_top_k=9,
            rag_mode="project",
            workflow=workflow,
            config=legacy_application.settings,
            failure_handler=rethrow_input_failure,
        )
        return result, result.context, workflow

    async def test_uploaded_result_matches_workflow_context(self):
        content = docx_bytes()
        upload = UploadFile(
            io.BytesIO(content),
            filename="synthetic.docx",
            size=len(content),
        )
        result, context, workflow = await self.prepare(
            resume=upload,
            job_text="  Synthetic Python platform role  ",
        )
        self.assertEqual(result.resume_version_id, "")
        self.assertEqual(result.warnings, [])
        self.assertEqual(context.resume_filename, "synthetic.docx")
        self.assertEqual(context.resume_text, "Synthetic Python FastAPI resume")
        self.assertEqual(context.job_text, "Synthetic Python platform role")
        self.assertIsNone(context.job_url)
        self.assertEqual(context.source_type, "text")
        self.assertEqual(context.rag_mode, "project")
        self.assertEqual(context.rag_top_k, 9)
        self.assertEqual([step.status for step in workflow.steps], ["completed"] * 3)

    async def test_stored_resume_and_job_url_match_workflow_context(self):
        version_id = str(uuid4())
        with patch(
            "app.analyze.input_preparation._load_stored_resume",
            return_value="Synthetic stored Python resume",
        ), patch(
            "app.analyze.input_preparation._fetch_job_text",
            return_value="Synthetic URL Python role",
        ):
            result, context, workflow = await self.prepare(
                resume=None,
                resume_version_id=f"  {version_id}  ",
                job_url="  https://jobs.example.test/synthetic-role  ",
            )
        self.assertEqual(result.resume_version_id, version_id)
        self.assertEqual(context.resume_filename, "Stored Resume Version")
        self.assertEqual(context.resume_text, "Synthetic stored Python resume")
        self.assertEqual(context.job_text, "Synthetic URL Python role")
        self.assertEqual(context.job_url, "https://jobs.example.test/synthetic-role")
        self.assertEqual(context.source_type, "saved_resume_version")
        self.assertEqual(
            workflow.steps[2].message,
            "Fetched job description from the provided URL.",
        )


class AnalyzeInputPreparationBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pja-analyze-input-")
        root = Path(self.temporary.name)
        self.environment = patch.dict(
            os.environ,
            {
                "APP_ENV": "test",
                "AUTH_ENABLED": "true",
                "TEST_DATABASE_URL": f"sqlite+pysqlite:///{root / 'test.db'}",
                "APP_DATABASE_PATH": str(root / "legacy.db"),
                "FILE_STORAGE_ROOT": str(root / "files"),
                "SESSION_COOKIE_SECURE": "false",
                "AUTH_TRUSTED_ORIGINS": "http://testserver",
                "AUTH_FINGERPRINT_KEY": "TEST_ONLY_FINGERPRINT_KEY_32_BYTES_LONG",
            },
        )
        self.environment.start()
        build_engine.cache_clear()
        self.settings = load_v2_settings()
        self.engine = build_engine(self.settings.database_url)
        Base.metadata.create_all(self.engine)
        db = session_factory(self.settings.database_url)()
        try:
            AuthService(db, self.settings).create_user(
                "input@example.com",
                "correct horse battery staple",
                "Input Contract User",
                "user",
            )
            db.commit()
        finally:
            db.close()

        app = FastAPI()
        app.include_router(auth.router)
        app.post("/api/analyze")(legacy_application.analyze)
        app.add_exception_handler(
            HTTPException,
            legacy_application.http_exception_handler,
        )
        app.add_exception_handler(
            RequestValidationError,
            legacy_application.validation_exception_handler,
        )
        app.add_middleware(V2SecurityMiddleware, settings=self.settings)
        app.add_middleware(
            RequestLoggingMiddleware,
            logger=logging.getLogger("personal-job-agent"),
        )
        self.client = TestClient(app)
        login = self.client.post(
            "/api/auth/login",
            json={
                "email": "input@example.com",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.csrf = login.json()["csrf_token"]

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        build_engine.cache_clear()
        self.environment.stop()
        self.temporary.cleanup()

    def headers(self, request_id: str) -> dict[str, str]:
        return {
            "Origin": "http://testserver",
            "X-CSRF-Token": self.csrf,
            "X-Request-ID": request_id,
        }

    def post(self, *, data: dict[str, str], upload=None, request_id: str):
        files = {"resume": upload} if upload is not None else None
        with patch(
            "legacy_application.call_deepseek_raw",
            side_effect=TimeoutError("synthetic provider timeout"),
        ):
            return self.client.post(
                "/api/analyze",
                files=files,
                data=data,
                headers=self.headers(request_id),
            )

    def assert_error(
        self,
        response,
        *,
        status: int,
        code: str,
        message: str,
        request_id: str,
        stage: str,
        field: str | None = None,
    ) -> None:
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(response.headers["X-Request-ID"], request_id)
        self.assertEqual(set(response.json()), {"error"})
        error = response.json()["error"]
        self.assertEqual(error["code"], code)
        self.assertEqual(error["message"], message)
        self.assertEqual(error["request_id"], request_id)
        self.assertEqual(error["details"]["error_stage"], stage)
        if field is not None:
            self.assertEqual(error["details"]["field"], field)

    def test_temporary_docx_and_pdf_keep_success_steps_and_result_shape(self):
        scenarios = (
            (
                "synthetic.docx",
                docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            ("synthetic.pdf", pdf_bytes(), "application/pdf"),
        )
        for index, upload in enumerate(scenarios):
            with self.subTest(filename=upload[0]):
                response = self.post(
                    upload=upload,
                    data={
                        "job_text": "Synthetic Python platform role",
                        "save_to_history": "false",
                        "use_project_knowledge": "false",
                        "project_knowledge_top_k": "7",
                    },
                    request_id=f"phase3a-upload-{index}",
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["analysis_status"], "fallback")
                self.assertEqual(response.json()["rag_mode"], "off")
                self.assertEqual(
                    input_steps(response),
                    [
                        (
                            "validate_input",
                            "Validate Input",
                            "completed",
                            "Input accepted. RAG mode: off; top_k: 7.",
                        ),
                        (
                            "parse_resume",
                            "Parse Resume",
                            "completed",
                            f"Resume text extracted successfully from {upload[0]}.",
                        ),
                        (
                            "acquire_job_description",
                            "Acquire Job Description",
                            "completed",
                            "Used pasted job description text.",
                        ),
                    ],
                )

    def test_job_url_keeps_safe_fetch_and_workflow_message(self):
        acquired = SimpleNamespace(description="Synthetic URL Python platform role")
        with patch.object(SafeJobUrlFetcher, "fetch", return_value=acquired) as fetch:
            response = self.post(
                upload=(
                    "synthetic.docx",
                    docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                data={
                    "job_url": "https://jobs.example.test/synthetic-role",
                    "save_to_history": "false",
                    "use_project_knowledge": "false",
                },
                request_id="phase3a-job-url",
            )
        self.assertEqual(response.status_code, 200, response.text)
        fetch.assert_called_once_with("https://jobs.example.test/synthetic-role")
        self.assertEqual(
            input_steps(response)[2],
            (
                "acquire_job_description",
                "Acquire Job Description",
                "completed",
                "Fetched job description from the provided URL.",
            ),
        )

    def test_stored_resume_version_keeps_result_and_workflow_context(self):
        version_id = str(uuid4())
        with patch(
            "app.resumes.service.ResumeService.analysis_text",
            return_value="Synthetic stored Python FastAPI resume",
        ) as analysis_text:
            response = self.post(
                data={
                    "resume_version_id": version_id,
                    "job_text": "Synthetic Python platform role",
                    "save_to_history": "false",
                    "use_project_knowledge": "false",
                },
                request_id="phase3a-stored-resume",
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["analysis_status"], "fallback")
        analysis_text.assert_called_once()
        self.assertEqual(
            input_steps(response)[1],
            (
                "parse_resume",
                "Parse Resume",
                "completed",
                "Resume text extracted successfully from Stored Resume Version.",
            ),
        )

    def test_invalid_inputs_keep_status_error_envelope_and_request_id(self):
        version_id = str(uuid4())
        docx_upload = (
            "synthetic.docx",
            docx_bytes(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        scenarios = (
            {
                "name": "missing resume",
                "upload": None,
                "data": {"job_text": "Synthetic role"},
                "code": "RESUME_SOURCE_INVALID",
                "message": "Provide exactly one resume source: an upload or resume_version_id.",
                "stage": "validate_input",
                "field": "resume",
            },
            {
                "name": "both resume sources",
                "upload": docx_upload,
                "data": {"resume_version_id": version_id, "job_text": "Synthetic role"},
                "code": "RESUME_SOURCE_INVALID",
                "message": "Provide exactly one resume source: an upload or resume_version_id.",
                "stage": "validate_input",
                "field": "resume",
            },
            {
                "name": "unsupported resume",
                "upload": ("synthetic.txt", b"Synthetic resume", "text/plain"),
                "data": {"job_text": "Synthetic role"},
                "code": "RESUME_SOURCE_INVALID",
                "message": "Resume must be a PDF or DOCX file.",
                "stage": "validate_input",
                "field": "resume",
            },
            {
                "name": "missing job",
                "upload": docx_upload,
                "data": {},
                "code": "JOB_SOURCE_INVALID",
                "message": "Provide exactly one job source: job description text or job URL.",
                "stage": "validate_input",
                "field": "job",
            },
            {
                "name": "both job sources",
                "upload": docx_upload,
                "data": {
                    "job_text": "Synthetic role",
                    "job_url": "https://jobs.example.test/role",
                },
                "code": "JOB_SOURCE_INVALID",
                "message": "Provide exactly one job source: job description text or job URL.",
                "stage": "validate_input",
                "field": "job",
            },
            {
                "name": "invalid rag mode",
                "upload": docx_upload,
                "data": {"job_text": "Synthetic role", "rag_mode": "invalid"},
                "code": "REQUEST_VALIDATION_FAILED",
                "message": "rag_mode must be either 'project' or 'off'.",
                "stage": "validate_input",
                "field": None,
            },
            {
                "name": "empty resume",
                "upload": ("synthetic.docx", b"", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "data": {"job_text": "Synthetic role"},
                "code": "RESUME_PARSING_FAILED",
                "message": "Uploaded resume file is empty.",
                "stage": "parse_resume",
                "field": None,
            },
            {
                "name": "malformed docx",
                "upload": ("synthetic.docx", b"not-a-docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                "data": {"job_text": "Synthetic role"},
                "code": "RESUME_PARSING_FAILED",
                "message": "Failed to parse resume. Please upload a valid PDF or DOCX file.",
                "stage": "parse_resume",
                "field": None,
            },
        )
        for index, scenario in enumerate(scenarios):
            with self.subTest(name=scenario["name"]):
                request_id = f"phase3a-invalid-{index}"
                response = self.post(
                    upload=scenario["upload"],
                    data=scenario["data"],
                    request_id=request_id,
                )
                self.assert_error(
                    response,
                    status=400,
                    code=scenario["code"],
                    message=scenario["message"],
                    request_id=request_id,
                    stage=scenario["stage"],
                    field=scenario["field"],
                )

    def test_ssrf_rejection_keeps_safe_job_acquisition_error(self):
        response = self.post(
            upload=(
                "synthetic.docx",
                docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            data={"job_url": "http://127.0.0.1/private"},
            request_id="phase3a-ssrf",
        )
        self.assert_error(
            response,
            status=400,
            code="JOB_DESCRIPTION_ACQUISITION_FAILED",
            message="Failed to fetch job URL safely. Please paste the job description instead.",
            request_id="phase3a-ssrf",
            stage="acquire_job_description",
        )
