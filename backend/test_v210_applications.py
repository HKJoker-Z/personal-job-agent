import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.dependencies import current_user, request_db
from app.api.routers import submitted_applications
from app.applications.schemas import ApplicationCreate
from app.applications.service import ApplicationConflict, ApplicationService
from app.db.base import Base
from app.db.engine import build_engine
from app.db.models import Application, ApplicationRecord, Resume, ResumeVersion, User, utc_now
from app.db.session import session_factory


class ApplicationsV210Test(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database = Path(self.temporary_directory.name) / "applications.db"
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test",
            "TEST_DATABASE_URL": f"sqlite+pysqlite:///{database}",
        })
        self.environment.start()
        build_engine.cache_clear()
        self.engine = build_engine(os.environ["TEST_DATABASE_URL"])
        Base.metadata.create_all(self.engine)
        self.db = session_factory(os.environ["TEST_DATABASE_URL"])()
        self.user = User(
            email="applications@example.com",
            normalized_email="applications@example.com",
            password_hash="not-used",
            display_name="Applications",
            role="user",
        )
        self.db.add(self.user)
        self.db.flush()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        build_engine.cache_clear()
        self.environment.stop()
        self.temporary_directory.cleanup()

    def test_analysis_application_keeps_history_and_snapshots_resume(self):
        now = utc_now()
        history = ApplicationRecord(
            owner_user_id=self.user.id,
            created_at=now,
            updated_at=now,
            company_name="Example Co",
            job_title="Backend Engineer",
        )
        resume = Resume(user_id=self.user.id, title="Primary", is_primary=True)
        self.db.add_all([history, resume])
        self.db.flush()
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=1,
            source_type="manual",
            schema_version=1,
            content_json={"schema_version": 1},
            parsed_text="Python and FastAPI",
            change_summary="Initial",
            status="final",
            created_by=self.user.id,
        )
        self.db.add(version)
        self.db.flush()

        created = ApplicationService(self.db, self.user.id).create_submitted({
            "company_name": history.company_name,
            "job_title": history.job_title,
            "job_description": "Build reliable APIs",
            "source_analysis_id": history.id,
            "resume_version_id": version.id,
            "priority": "normal",
            "next_action_at": None,
            "expected_response_at": None,
        })["application"]
        self.db.commit()

        application = self.db.get(Application, UUID(created["id"]))
        self.assertEqual(application.current_stage, "applied")
        self.assertIsNotNone(application.applied_at)
        self.assertEqual(application.resume_snapshot, "Python and FastAPI")
        self.assertEqual(
            self.db.scalar(select(func.count(ApplicationRecord.id))), 1
        )
        with self.assertRaises(ApplicationConflict):
            ApplicationService(self.db, self.user.id).create_submitted({
                "company_name": "Example Co",
                "job_title": "Backend Engineer",
                "job_description": "Build reliable APIs",
                "source_analysis_id": history.id,
                "resume_version_id": None,
            })

    def test_manual_applications_are_listed_by_applied_time_descending(self):
        service = ApplicationService(self.db, self.user.id)
        first = service.create_submitted({
            "company_name": "First Co",
            "job_title": "First Role",
            "job_description": "",
            "source_analysis_id": None,
            "resume_version_id": None,
        })["application"]
        self.db.get(Application, UUID(first["id"])).applied_at = utc_now() - timedelta(days=1)
        service.create_submitted({
            "company_name": "Second Co",
            "job_title": "Second Role",
            "job_description": "",
            "source_analysis_id": None,
            "resume_version_id": None,
        })
        self.db.flush()
        self.assertEqual(
            [item["company_name"] for item in service.list()],
            ["Second Co", "First Co"],
        )

    def test_manual_application_requires_company_and_job_title(self):
        with self.assertRaises(ValidationError):
            ApplicationCreate(job_description="Optional")

    def test_delete_api_physically_deletes_only_the_application(self):
        now = utc_now()
        analysis = ApplicationRecord(
            owner_user_id=self.user.id,
            created_at=now,
            updated_at=now,
            company_name="Delete Example",
            job_title="Platform Engineer",
        )
        history = ApplicationRecord(
            owner_user_id=self.user.id,
            created_at=now,
            updated_at=now,
            company_name="History Example",
            job_title="Earlier Role",
        )
        resume = Resume(user_id=self.user.id, title="Primary", is_primary=True)
        self.db.add_all([analysis, history, resume])
        self.db.flush()
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=1,
            source_type="manual",
            schema_version=1,
            content_json={"schema_version": 1},
            parsed_text="Python\n\nExperience\nBuilt APIs",
            change_summary="Initial",
            status="final",
            created_by=self.user.id,
        )
        self.db.add(version)
        self.db.flush()
        created = ApplicationService(self.db, self.user.id).create_submitted({
            "company_name": analysis.company_name,
            "job_title": analysis.job_title,
            "job_description": "Build reliable systems",
            "source_analysis_id": analysis.id,
            "resume_version_id": version.id,
        })["application"]
        application_id = UUID(created["id"])
        analysis_id, history_id = analysis.id, history.id
        resume_id, version_id = resume.id, version.id
        self.db.commit()

        app = FastAPI()
        app.include_router(submitted_applications.router)
        app.dependency_overrides[request_db] = lambda: self.db
        app.dependency_overrides[current_user] = lambda: self.user
        with TestClient(app) as client:
            response = client.delete(f"/api/applications/{application_id}")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {
            "deleted": True,
            "id": str(application_id),
        })
        self.db.commit()
        self.db.expire_all()
        self.assertIsNone(self.db.get(Application, application_id))
        self.assertIsNotNone(self.db.get(ApplicationRecord, analysis_id))
        self.assertIsNotNone(self.db.get(ApplicationRecord, history_id))
        self.assertIsNotNone(self.db.get(Resume, resume_id))
        self.assertIsNotNone(self.db.get(ResumeVersion, version_id))


if __name__ == "__main__":
    unittest.main()
