"""Characterization coverage for the legacy History and v2 Application boundary."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware


class _PrincipalMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, principal, database_url: str | None = None):
        super().__init__(app)
        self.principal = principal
        self.database_url = database_url

    async def dispatch(self, request, call_next):
        request.state.v2_user = self.principal
        if self.database_url:
            from app.db.session import session_factory

            db = session_factory(self.database_url)()
            request.state.v2_db = db
            try:
                response = await call_next(request)
                if response.status_code >= 500:
                    db.rollback()
                else:
                    db.commit()
                return response
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()
        return await call_next(request)


class HistoryApplicationRouteContractTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="pja-route-contract-")
        root = Path(self.temporary.name)
        self.legacy_database = root / "legacy.db"
        self.v2_database = root / "v2.db"
        self.environment = patch.dict(os.environ, {
            "APP_ENV": "test",
            "APP_DATABASE_PATH": str(self.legacy_database),
            "TEST_DATABASE_URL": f"sqlite+pysqlite:///{self.v2_database}",
            "AUTH_ENABLED": "true",
            "SESSION_COOKIE_SECURE": "false",
            "AUTH_TRUSTED_ORIGINS": "http://testserver",
            "AUTH_FINGERPRINT_KEY": "TEST_ONLY_FINGERPRINT_KEY_32_BYTES_LONG",
        })
        self.environment.start()

        from database import init_db

        init_db()
        from app.core.config import load_v2_settings
        from app.db.base import Base
        from app.db.engine import build_engine
        import app.db.models  # noqa: F401 - register all tables before create_all

        build_engine.cache_clear()
        self.settings = load_v2_settings()
        self.engine = build_engine(self.settings.database_url)
        Base.metadata.create_all(self.engine)

        self.owner = uuid4()
        self.other_owner = uuid4()
        self.admin = uuid4()
        self.owner_principal = SimpleNamespace(id=self.owner, role="user")
        self.admin_principal = SimpleNamespace(id=self.admin, role="admin")
        self._seed_v2_application()

        from legacy_application import app as legacy_app
        from app.api.routers import applications

        # Copy only the legacy route table into a fresh test app. The composed
        # production app intentionally adds FeatureRetirementMiddleware for
        # public v2 retirement tests; this characterization targets route
        # ownership before that outer policy boundary.
        self.route_app = FastAPI()
        self.route_app.include_router(legacy_app.router)
        self.route_app.include_router(applications.router)
        self.owner_client = TestClient(_PrincipalMiddleware(
            self.route_app, self.owner_principal
        ))
        self.admin_client = TestClient(_PrincipalMiddleware(
            self.route_app, self.admin_principal
        ))
        self.v2_client = TestClient(_PrincipalMiddleware(
            self.route_app, self.owner_principal, self.settings.database_url
        ))

    def tearDown(self):
        for client in (getattr(self, "owner_client", None),
                       getattr(self, "admin_client", None),
                       getattr(self, "v2_client", None)):
            if client is not None:
                client.close()
        if getattr(self, "engine", None) is not None:
            self.engine.dispose()
        from app.db.engine import build_engine

        build_engine.cache_clear()
        self.environment.stop()
        self.temporary.cleanup()

    def _seed_v2_application(self):
        from app.db.models import Application, User
        from app.db.session import session_factory

        db: Session = session_factory(self.settings.database_url)()
        try:
            db.add(User(
                id=self.owner,
                email="owner@example.test",
                normalized_email="owner@example.test",
                password_hash="synthetic",
                display_name="Synthetic Owner",
                role="user",
            ))
            application = Application(owner_user_id=self.owner, job_id=uuid4())
            db.add(application)
            db.commit()
            self.v2_application_id = application.id
        finally:
            db.close()

    def _seed_legacy(self, *, owner_user_id=None, company="Synthetic Labs",
                     title="Platform Engineer", status="Saved") -> int:
        from database import insert_application_record, update_application_record

        record_id = insert_application_record(
            {
                "company_name": company,
                "job_title": title,
                "job_summary": "Synthetic job summary.",
                "match_score": 78,
                "match_reason": "Synthetic evidence.",
                "cover_letter": "Synthetic cover letter.",
                "next_action": {"action": "follow_up", "label": "Follow up"},
                "scoring_breakdown": {},
                "ats_analysis": {},
            },
            job_url="https://jobs.example.test/synthetic",
            resume_filename="synthetic.docx",
            owner_user_id=owner_user_id,
        )
        if status != "Saved":
            update_application_record(
                record_id,
                application_status=status,
                notes="Synthetic notes.",
                update_notes=True,
                owner_user_id=owner_user_id,
            )
        return record_id

    def _history_fixture(self):
        unowned = self._seed_legacy(owner_user_id=None, company="Unowned Labs")
        owned = self._seed_legacy(
            owner_user_id=self.owner,
            company="Owner Labs",
            title="Python Engineer",
            status="Applied",
        )
        other = self._seed_legacy(
            owner_user_id=self.other_owner,
            company="Other Labs",
            title="Data Engineer",
            status="Interview",
        )
        return unowned, owned, other

    def test_history_list_status_search_pagination_and_ownership(self):
        unowned, owned, other = self._history_fixture()

        response = self.owner_client.get("/api/history")
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual(value["total"], 1)
        self.assertEqual([item["id"] for item in value["items"]], [owned])
        self.assertEqual(value["limit"], 50)
        self.assertEqual(value["offset"], 0)

        filtered = self.owner_client.get("/api/history", params={
            "status": "Applied", "search": "Python", "limit": 1, "offset": 0,
        })
        self.assertEqual(filtered.status_code, 200, filtered.text)
        self.assertEqual(filtered.json()["total"], 1)
        self.assertEqual(filtered.json()["items"][0]["id"], owned)

        page = self.owner_client.get("/api/history", params={"limit": 1, "offset": 1})
        self.assertEqual(page.status_code, 200, page.text)
        self.assertEqual(page.json()["items"], [])
        self.assertEqual(page.json()["total"], 1)

        invalid_limit = self.owner_client.get("/api/history", params={"limit": 0})
        self.assertEqual(invalid_limit.status_code, 422, invalid_limit.text)
        self.assertIsInstance(invalid_limit.json()["detail"], list)

        admin = self.admin_client.get("/api/history")
        self.assertEqual(admin.status_code, 200, admin.text)
        self.assertEqual(admin.json()["total"], 1)
        self.assertEqual([item["id"] for item in admin.json()["items"]], [unowned])
        self.assertNotIn(other, [item["id"] for item in admin.json()["items"]])

    def test_history_integer_get_patch_delete_and_next_action(self):
        _unowned, owned, _other = self._history_fixture()

        fetched = self.owner_client.get(f"/api/history/{owned}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["id"], owned)

        patched = self.owner_client.patch(
            f"/api/history/{owned}",
            json={"application_status": "Offer", "notes": "Synthetic update"},
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["application_status"], "Offer")
        self.assertEqual(patched.json()["notes"], "Synthetic update")

        next_action = self.owner_client.patch(
            f"/api/history/{owned}/next-action",
            json={"decision": "accepted", "notes": "Synthetic decision"},
        )
        self.assertEqual(next_action.status_code, 200, next_action.text)
        self.assertEqual(next_action.json()["application_id"], owned)
        self.assertEqual(next_action.json()["decision"], "accepted")
        self.assertEqual(next_action.json()["notes"], "Synthetic decision")

        deleted = self.owner_client.delete(f"/api/history/{owned}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json(), {"deleted": True, "id": owned})
        self.assertEqual(self.owner_client.get(f"/api/history/{owned}").status_code, 404)

    def test_applications_legacy_query_compatibility_and_v2_list(self):
        _unowned, owned, _other = self._history_fixture()

        v2_list = self.v2_client.get("/api/applications")
        self.assertEqual(v2_list.status_code, 200, v2_list.text)
        self.assertIsInstance(v2_list.json(), list)
        self.assertEqual(v2_list.json()[0]["id"], str(self.v2_application_id))

        compatibility = self.owner_client.get("/api/applications", params={
            "status": "Applied", "search": "Python", "limit": 1, "offset": 0,
        })
        self.assertEqual(compatibility.status_code, 200, compatibility.text)
        self.assertEqual(compatibility.json()["total"], 1)
        self.assertEqual(compatibility.json()["items"][0]["id"], owned)

    def test_uuid_application_get_patch_and_delete_archive(self):
        application_path = f"/api/applications/{self.v2_application_id}"

        fetched = self.v2_client.get(application_path)
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["id"], str(self.v2_application_id))
        self.assertEqual(fetched.json()["revision"], 1)

        invalid_patch = self.v2_client.patch(application_path, json={"priority": "high"})
        self.assertEqual(invalid_patch.status_code, 422, invalid_patch.text)
        self.assertIsInstance(invalid_patch.json()["detail"], list)

        patched = self.v2_client.patch(application_path, json={
            "expected_revision": 1, "source": "synthetic-test", "priority": "high",
        })
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["revision"], 2)
        self.assertEqual(patched.json()["source"], "synthetic-test")

        stale = self.v2_client.patch(application_path, json={
            "expected_revision": 1, "priority": "low",
        })
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"], "Resource revision is stale.")

        archived = self.v2_client.request(
            "DELETE", application_path, json={"expected_revision": 2}
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        self.assertIsNotNone(archived.json()["archived_at"])

    def test_invalid_ids_keep_404_contract(self):
        for path in ("/api/history/not-an-id", "/api/applications/not-an-id"):
            response = self.owner_client.get(path)
            self.assertEqual(response.status_code, 404, (path, response.text))
            self.assertEqual(response.json()["detail"], "Application not found.")

        missing = self.owner_client.get("/api/history/999999")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["detail"], "History record not found.")

        invalid_update = self.v2_client.patch(
            "/api/applications/not-an-id", json={"expected_revision": 1}
        )
        self.assertEqual(invalid_update.status_code, 404, invalid_update.text)
        self.assertEqual(invalid_update.json()["detail"], "Application not found.")

    def test_docx_pdf_get_and_head_keep_headers_on_both_legacy_paths(self):
        _unowned, owned, _other = self._history_fixture()
        for path_prefix in ("/api/history", "/api/applications"):
            for suffix, media_type, filename_prefix in (
                ("cover-letter.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "cover-letter-"),
                ("report.pdf", "application/pdf", "analysis-report-"),
            ):
                path = f"{path_prefix}/{owned}/{suffix}"
                response = self.owner_client.get(path)
                self.assertEqual(response.status_code, 200, (path, response.text))
                self.assertEqual(response.headers["content-type"].split(";", 1)[0], media_type)
                disposition = response.headers["content-disposition"]
                self.assertIn(f'filename="{filename_prefix}', disposition)

                head = self.owner_client.head(path)
                self.assertEqual(head.status_code, 200, (path, head.text))
                self.assertEqual(head.headers["content-type"].split(";", 1)[0], media_type)
                self.assertEqual(head.headers["content-disposition"], disposition)

    def test_authentication_and_v2_not_found_contract(self):
        from app.auth.middleware import V2SecurityMiddleware

        unauthenticated = TestClient(V2SecurityMiddleware(self.route_app, self.settings))
        try:
            response = unauthenticated.get("/api/history")
            self.assertEqual(response.status_code, 401, response.text)
            self.assertEqual(response.json(), {"detail": "Authentication required."})
        finally:
            unauthenticated.close()

        missing = self.v2_client.get(f"/api/applications/{uuid4()}")
        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(missing.json()["detail"], "Application not found.")


if __name__ == "__main__":
    unittest.main()
