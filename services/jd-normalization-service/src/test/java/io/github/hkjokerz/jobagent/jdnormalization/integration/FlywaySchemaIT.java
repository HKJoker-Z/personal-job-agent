package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import jakarta.persistence.EntityManagerFactory;
import io.github.hkjokerz.jobagent.jdnormalization.JdNormalizationServiceApplication;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.SpringApplication;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.hibernate.tool.schema.spi.SchemaManagementException;

@SpringBootTest(properties = {
    "jd-normalization.security.api-key=" + PostgreSqlIntegrationSupport.API_KEY,
    "jd-normalization.persistence.enabled=true",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
@ActiveProfiles("integration")
@Testcontainers(disabledWithoutDocker = true)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class FlywaySchemaIT extends PostgreSqlIntegrationSupport {

    @Autowired
    private Flyway flyway;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private DataSource dataSource;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Test
    void freshMigrationValidatesAndSecondMigrateIsNoOp() {
        assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("1");
        assertThat(flyway.validateWithResult().validationSuccessful).isTrue();
        assertThat(flyway.migrate().migrationsExecuted).isZero();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT count(*) FROM flyway_schema_history WHERE success",
                Integer.class)).isEqualTo(1);
        assertThat(entityManagerFactory.isOpen()).isTrue();
    }

    @Test
    void applicationStartupFailsWhenFlywayIsDisabledAgainstMissingSchema() {
        jdbcTemplate.execute("CREATE SCHEMA startup_invalid_schema");
        SpringApplication application =
                new SpringApplication(JdNormalizationServiceApplication.class);
        assertThatThrownBy(() -> application.run(
                        "--spring.datasource.url=" + POSTGRES.getJdbcUrl()
                                + "?currentSchema=startup_invalid_schema",
                        "--spring.datasource.username=" + POSTGRES.getUsername(),
                        "--spring.datasource.password=" + POSTGRES.getPassword(),
                        "--spring.datasource.driver-class-name=org.postgresql.Driver",
                        "--spring.flyway.enabled=false",
                        "--spring.jpa.hibernate.ddl-auto=validate",
                        "--spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect",
                        "--jd-normalization.security.api-key=" + API_KEY,
                        "--server.address=127.0.0.1",
                        "--server.port=0",
                        "--management.endpoint.health.group.readiness.include=readinessState,db"))
                .hasRootCauseInstanceOf(SchemaManagementException.class);
    }

    @Test
    void createsEveryApprovedTableConstraintTriggerAndReadIndex() {
        assertThat(jdbcTemplate.queryForList("""
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND tablename IN ('job_descriptions', 'job_description_versions')
                """, String.class)).contains(
                        "uq_job_descriptions_canonical_url",
                        "idx_job_descriptions_created_at_id",
                        "idx_job_description_versions_history",
                        "idx_job_description_versions_content_hash",
                        "idx_job_description_versions_title_ci",
                        "idx_job_description_versions_company_ci",
                        "idx_job_description_versions_location_ci");

        assertThat(jdbcTemplate.queryForObject("""
                SELECT count(*)
                FROM pg_trigger
                WHERE tgname = 'trg_job_description_versions_immutable'
                  AND NOT tgisinternal
                """, Integer.class)).isEqualTo(1);

        assertThat(jdbcTemplate.queryForList("""
                SELECT conname
                FROM pg_constraint
                WHERE conrelid IN (
                    'job_descriptions'::regclass,
                    'job_description_versions'::regclass
                )
                """, String.class)).contains(
                        "fk_job_descriptions_current_version",
                        "fk_job_description_versions_owner",
                        "uq_job_description_versions_number",
                        "uq_job_description_versions_current_identity",
                        "uq_job_descriptions_current_fingerprint");
    }

    @Test
    void deferredOwnershipAllowsAtomicAggregateButRejectsWrongOwner() throws Exception {
        PostgreSqlFixture fixture = fixture();
        UUID owner = UUID.fromString("10000000-0000-4000-8000-000000000001");
        UUID ownerVersion = UUID.fromString("10000000-0000-4000-8000-000000000002");
        fixture.insertAggregate(
                owner,
                "https://schema.example.test/owner",
                Instant.parse("2026-07-29T01:00:00Z"),
                List.of(
                        PostgreSqlFixture.version(
                                ownerVersion,
                                1,
                                "Owner",
                                "Example",
                                "Hong Kong",
                                "Java",
                                "schema-owner-content",
                                "schema-owner-fingerprint",
                                Instant.parse("2026-07-29T01:00:00Z")),
                        PostgreSqlFixture.version(
                                UUID.fromString(
                                        "10000000-0000-4000-8000-000000000004"),
                                2,
                                "Current Owner",
                                "Example",
                                "Hong Kong",
                                "Java 21",
                                "schema-owner-current-content",
                                "schema-owner-current-fingerprint",
                                Instant.parse("2026-07-29T01:01:00Z"))));

        UUID wrongOwner = UUID.fromString("10000000-0000-4000-8000-000000000003");
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            insertRoot(
                    connection,
                    wrongOwner,
                    ownerVersion,
                    PostgreSqlFixture.digest("schema-owner-fingerprint"),
                    "https://schema.example.test/wrong-owner");
            assertThatThrownBy(connection::commit)
                    .isInstanceOf(SQLException.class)
                    .extracting(exception -> ((SQLException) exception).getSQLState())
                    .isEqualTo("23503");
            connection.rollback();
        }
    }

    @Test
    void immutableTriggerRejectsVersionUpdateAndDeleteAndDeleteNeverCascades() {
        UUID aggregate = UUID.fromString("20000000-0000-4000-8000-000000000001");
        UUID version = UUID.fromString("20000000-0000-4000-8000-000000000002");
        fixture().insertAggregate(
                aggregate,
                "https://schema.example.test/immutable",
                Instant.parse("2026-07-29T02:00:00Z"),
                List.of(PostgreSqlFixture.version(
                        version,
                        1,
                        "Immutable",
                        "Example",
                        null,
                        "Java",
                        "immutable-content",
                        "immutable-fingerprint",
                        Instant.parse("2026-07-29T02:00:00Z"))));

        assertSqlState("55000", () -> jdbcTemplate.update(
                "UPDATE job_description_versions SET title = 'Changed' WHERE id = ?",
                version));
        assertSqlState("55000", () -> jdbcTemplate.update(
                "DELETE FROM job_description_versions WHERE id = ?",
                version));
        assertSqlState("23503", () -> jdbcTemplate.update(
                "DELETE FROM job_descriptions WHERE id = ?",
                aggregate));
    }

    @Test
    void enforcesUniquenessHashesVersionNumbersAndJsonArraysButAllowsContentReuse() {
        UUID first = UUID.fromString("30000000-0000-4000-8000-000000000001");
        byte[] repeatedContentHash = PostgreSqlFixture.repeatedByte(0x41);
        PostgreSqlFixture.VersionSeed firstVersion = new PostgreSqlFixture.VersionSeed(
                UUID.fromString("30000000-0000-4000-8000-000000000002"),
                1,
                "First",
                "Example",
                null,
                "Java",
                repeatedContentHash,
                PostgreSqlFixture.digest("unique-fingerprint-first"),
                Instant.parse("2026-07-29T03:00:00Z"));
        fixture().insertAggregate(
                first,
                "https://schema.example.test/unique",
                Instant.parse("2026-07-29T03:00:00Z"),
                List.of(firstVersion));

        assertThatThrownBy(() -> fixture().insertAggregate(
                        UUID.fromString("30000000-0000-4000-8000-000000000003"),
                        "https://schema.example.test/unique",
                        Instant.parse("2026-07-29T03:01:00Z"),
                        List.of(PostgreSqlFixture.version(
                                UUID.fromString("30000000-0000-4000-8000-000000000004"),
                                1,
                                "Duplicate URL",
                                "Other",
                                null,
                                "Java",
                                "different-content",
                                "different-fingerprint",
                                Instant.parse("2026-07-29T03:01:00Z")))))
                .isInstanceOf(DataIntegrityViolationException.class);

        assertThatThrownBy(() -> fixture().insertAggregate(
                        UUID.fromString("30000000-0000-4000-8000-000000000005"),
                        "https://schema.example.test/fingerprint",
                        Instant.parse("2026-07-29T03:02:00Z"),
                        List.of(new PostgreSqlFixture.VersionSeed(
                                UUID.fromString("30000000-0000-4000-8000-000000000006"),
                                1,
                                "Duplicate Fingerprint",
                                "Other",
                                null,
                                "Java",
                                PostgreSqlFixture.digest("other-content"),
                                firstVersion.deduplicationFingerprint(),
                                Instant.parse("2026-07-29T03:02:00Z")))))
                .isInstanceOf(DataIntegrityViolationException.class);

        fixture().insertAggregate(
                UUID.fromString("30000000-0000-4000-8000-000000000007"),
                "https://schema.example.test/content-reuse",
                Instant.parse("2026-07-29T03:03:00Z"),
                List.of(new PostgreSqlFixture.VersionSeed(
                        UUID.fromString("30000000-0000-4000-8000-000000000008"),
                        1,
                        "Different Metadata",
                        "Other",
                        null,
                        "Java",
                        repeatedContentHash,
                        PostgreSqlFixture.digest("content-reuse-fingerprint"),
                        Instant.parse("2026-07-29T03:03:00Z"))));
        assertThat(jdbcTemplate.queryForObject(
                "SELECT count(*) FROM job_description_versions WHERE content_hash = ?",
                Integer.class,
                repeatedContentHash)).isEqualTo(2);

        assertInvalidVersion(
                UUID.fromString("30000000-0000-4000-8000-000000000010"),
                UUID.fromString("30000000-0000-4000-8000-000000000011"),
                0,
                PostgreSqlFixture.repeatedByte(0x51),
                "[]",
                "23514");
        assertInvalidVersion(
                UUID.fromString("30000000-0000-4000-8000-000000000012"),
                UUID.fromString("30000000-0000-4000-8000-000000000013"),
                1,
                new byte[31],
                "[]",
                "23514");
        assertInvalidVersion(
                UUID.fromString("30000000-0000-4000-8000-000000000014"),
                UUID.fromString("30000000-0000-4000-8000-000000000015"),
                1,
                PostgreSqlFixture.repeatedByte(0x52),
                "{}",
                "23514");
    }

    private PostgreSqlFixture fixture() {
        return new PostgreSqlFixture(
                jdbcTemplate,
                new TransactionTemplate(transactionManager));
    }

    private void assertInvalidVersion(
            UUID aggregateId,
            UUID versionId,
            int versionNumber,
            byte[] contentHash,
            String requiredSkills,
            String sqlState) {
        byte[] fingerprint = PostgreSqlFixture.digest(aggregateId.toString());
        assertSqlState(sqlState, () -> new TransactionTemplate(transactionManager)
                .executeWithoutResult(status -> {
                    jdbcTemplate.update("""
                            INSERT INTO job_descriptions (
                                id, current_version_id,
                                current_deduplication_fingerprint,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                            """, aggregateId, versionId, fingerprint);
                    jdbcTemplate.update("""
                            INSERT INTO job_description_versions (
                                id, job_description_id, version_number,
                                normalized_text, content_hash,
                                deduplication_fingerprint,
                                normalization_policy_version,
                                skill_dictionary_version,
                                required_skills, preferred_skills, mentioned_skills
                            ) VALUES (
                                ?, ?, ?, 'Java', ?, ?,
                                'jd-normalization-v1', 'skills-v1',
                                CAST(? AS jsonb), '[]'::jsonb, '[]'::jsonb
                            )
                            """,
                            versionId,
                            aggregateId,
                            versionNumber,
                            contentHash,
                            fingerprint,
                            requiredSkills);
                }));
    }

    private static void insertRoot(
            Connection connection,
            UUID aggregateId,
            UUID currentVersionId,
            byte[] fingerprint,
            String canonicalUrl) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement("""
                INSERT INTO job_descriptions (
                    id, canonical_url, current_version_id,
                    current_deduplication_fingerprint,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """)) {
            statement.setObject(1, aggregateId);
            statement.setString(2, canonicalUrl);
            statement.setObject(3, currentVersionId);
            statement.setBytes(4, fingerprint);
            statement.executeUpdate();
        }
    }

    private static void assertSqlState(
            String expectedState,
            org.assertj.core.api.ThrowableAssert.ThrowingCallable call) {
        assertThatThrownBy(call)
                .hasRootCauseInstanceOf(SQLException.class)
                .rootCause()
                .extracting(exception -> ((SQLException) exception).getSQLState())
                .isEqualTo(expectedState);
    }
}
