import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostgreSQLToolRepositorySafetyTest(unittest.TestCase):
    def test_operational_container_configuration_has_no_floating_postgres_tools(self):
        paths = [
            ROOT / "backend" / "Dockerfile",
            ROOT / "compose.yaml",
            ROOT / "compose.prod.yaml",
            ROOT / "compose.postgres16-restore.yaml",
            ROOT / "deploy" / "production" / "compose.yaml",
            ROOT / ".github" / "workflows" / "ci.yml",
        ]
        content = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        self.assertNotIn("postgres:latest", content)
        self.assertNotRegex(content, r"image:\s+postgres:17(?:\s|$)")
        self.assertNotRegex(content, r"apt-get install[^\n]*\bpostgresql-client(?:\s|\\)")

    def test_backend_client_major_and_production_server_digest_are_fixed(self):
        dockerfile = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
        production = (ROOT / "deploy" / "production" / "compose.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ARG POSTGRES_CLIENT_MAJOR=16", dockerfile)
        self.assertIn('"postgresql-client-${POSTGRES_CLIENT_MAJOR}"', dockerfile)
        self.assertRegex(
            production,
            r"image: postgres:16\.9-alpine@sha256:[0-9a-f]{64}",
        )
        self.assertIn("POSTGRES_TOOL_IMAGE: *backend-image", production)
        self.assertIn("POSTGRES_SERVER_IMAGE: postgres:16.9-alpine@sha256:", production)

    def test_strict_restore_compose_has_private_fixed_postgresql_16_targets(self):
        rehearsal = (ROOT / "compose.postgres16-restore.yaml").read_text(encoding="utf-8")
        self.assertEqual(rehearsal.count("image: postgres:16.9-alpine@sha256:"), 2)
        self.assertNotIn("ports:", rehearsal)
        self.assertIn("source-data:\n    internal: true", rehearsal)
        self.assertIn("restore-data:\n    internal: true", rehearsal)

    def test_strict_restore_cleanup_only_uses_the_exact_run_project(self):
        script = (ROOT / "scripts" / "postgres16-restore-regression.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('"${PROJECT_NAME}_source-data" "${PROJECT_NAME}_target-data"', script)
        self.assertIn('"${PROJECT_NAME}_source-data" "${PROJECT_NAME}_restore-data"', script)
        self.assertNotIn("docker volume prune", script)
        self.assertNotIn("docker network prune", script)
        self.assertNotIn("down -v", script)

    def test_database_name_preflight_uses_explicit_nonsecret_arguments(self):
        script = (ROOT / "scripts" / "postgres16-restore-regression.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('--source-database-name "${SOURCE_DATABASE}"', script)
        self.assertIn('--target-database-name "${TARGET_DATABASE}"', script)
        self.assertIn('--run-id "${STAMP}"', script)
        self.assertIn('--env-file "${ENV_FILE}"', script)
        self.assertNotIn("sudo -E", script)
        self.assertNotIn("--preserve-env", script)

    def test_application_smoke_prepares_only_its_verified_isolated_restore_database(self):
        script = (ROOT / "scripts" / "docker-smoke-v2.sh").read_text(encoding="utf-8")
        self.assertIn('RESTORE_DATABASE="pja_restore_target_test_', script)
        self.assertIn("createdb -U pja_bootstrap --template=template0", script)
        self.assertIn("DROP SCHEMA public RESTRICT", script)
        self.assertIn('"${PROJECT_NAME}|database"', script)
        self.assertIn('"${PROJECT_NAME}_postgres-data"', script)
        self.assertNotIn("DROP SCHEMA public CASCADE", script)
        self.assertNotIn("pg_restore --clean", script)

    def test_application_smoke_resolves_the_full_tool_image_id(self):
        script = (ROOT / "scripts" / "docker-smoke-v2.sh").read_text(encoding="utf-8")
        self.assertIn("image inspect --format '{{.Id}}'", script)
        self.assertIn('[[ "${TOOL_IMAGE_ID}" =~ ^sha256:[a-f0-9]{64}$ ]]', script)

    def test_application_smoke_keeps_container_backup_directory_private(self):
        script = (ROOT / "scripts" / "docker-smoke-v2.sh").read_text(encoding="utf-8")
        self.assertIn('BACKUP_PATH="$(sudo -n realpath', script)
        self.assertIn('BACKUP_ROOT="$(sudo -n realpath', script)
        self.assertIn('sudo -n test -f "${SMOKE_INVENTORY_DIFF}"', script)
        self.assertIn("--allowed-owner-mapping pja_migrate=pja_bootstrap", script)
        self.assertIn("--allowed-owner-mapping pg_database_owner=pja_bootstrap", script)
        self.assertIn("--allow-isolated-database-name-difference", script)
        self.assertIn('"${COMPOSE[@]}" stop worker', script)
        self.assertNotIn("sudo -E", script)
        self.assertNotIn("chmod -R", script)

    def test_backup_inventory_and_dump_share_one_exported_snapshot(self):
        script = (ROOT / "scripts" / "v2_backup_restore.py").read_text(encoding="utf-8")
        inventory = script.index("inventory = _database_inventory(snapshot_connection)")
        dump = script.index('"--snapshot",\n                    snapshot_id')
        self.assertLess(inventory, dump)
        self.assertIn("SELECT pg_export_snapshot()", script)


if __name__ == "__main__":
    unittest.main()
