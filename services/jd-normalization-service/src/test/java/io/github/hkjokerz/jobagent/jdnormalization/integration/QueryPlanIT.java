package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(properties = {
    "jd-normalization.security.api-key=" + PostgreSqlIntegrationSupport.API_KEY,
    "jd-normalization.persistence.enabled=true"
})
@ActiveProfiles("integration")
@Testcontainers(disabledWithoutDocker = true)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class QueryPlanIT extends PostgreSqlIntegrationSupport {

    private static final Logger LOGGER = LoggerFactory.getLogger(QueryPlanIT.class);
    private static final UUID HISTORY_AGGREGATE =
            UUID.fromString("80000000-0000-4000-8000-000000000001");

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @BeforeEach
    void seedBoundedDataset() {
        Integer existing = jdbcTemplate.queryForObject(
                "SELECT count(*) FROM job_descriptions",
                Integer.class);
        if (existing != null && existing > 0) {
            return;
        }
        PostgreSqlFixture fixture = new PostgreSqlFixture(
                jdbcTemplate,
                new TransactionTemplate(transactionManager));
        Instant base = Instant.parse("2026-07-29T08:00:00Z");
        for (int index = 1; index <= 64; index++) {
            String suffix = "%012d".formatted(index);
            fixture.insertAggregate(
                    UUID.fromString("81000000-0000-4000-8000-" + suffix),
                    "https://plans.example.test/jobs/" + index,
                    base.plusSeconds(index),
                    List.of(PostgreSqlFixture.version(
                            UUID.fromString("82000000-0000-4000-8000-" + suffix),
                            1,
                            "Plan Engineer " + index,
                            "Example",
                            "Hong Kong",
                            "Java " + index,
                            "plan-content-" + index,
                            "plan-fingerprint-" + index,
                            base.plusSeconds(index))));
        }
        fixture.insertAggregate(
                HISTORY_AGGREGATE,
                "https://plans.example.test/history",
                base.plusSeconds(100),
                java.util.stream.IntStream.rangeClosed(1, 20)
                        .mapToObj(number -> PostgreSqlFixture.version(
                                UUID.fromString(
                                        "83000000-0000-4000-8000-%012d"
                                                .formatted(number)),
                                number,
                                "History " + number,
                                "Example",
                                null,
                                "Java history " + number,
                                "plan-history-content-" + number,
                                "plan-history-fingerprint-" + number,
                                base.plusSeconds(100 + number)))
                        .toList());
        jdbcTemplate.execute("ANALYZE job_descriptions");
        jdbcTemplate.execute("ANALYZE job_description_versions");
    }

    @Test
    void currentListKeysetQueryIsIndexEligibleWithoutLatencyClaim() {
        String sql = """
                EXPLAIN (FORMAT JSON)
                SELECT j.id, v.title
                FROM job_descriptions j
                JOIN job_description_versions v
                  ON v.id = j.current_version_id
                 AND v.job_description_id = j.id
                WHERE (j.created_at, j.id) < (?, ?)
                ORDER BY j.created_at DESC, j.id DESC
                LIMIT 21
                """;
        Object[] arguments = {
            OffsetDateTime.ofInstant(
                    Instant.parse("2026-07-29T08:01:00Z"),
                    ZoneOffset.UTC),
            UUID.fromString("ffffffff-ffff-4fff-8fff-ffffffffffff")
        };
        assertDefaultAndForcedIndex(
                "current_keyset_list",
                sql,
                arguments,
                "idx_job_descriptions_created_at_id");
    }

    @Test
    void versionHistoryQueryIsIndexEligibleWithoutLatencyClaim() {
        String sql = """
                EXPLAIN (FORMAT JSON)
                SELECT id, version_number
                FROM job_description_versions
                WHERE job_description_id = ?
                  AND version_number < ?
                ORDER BY version_number DESC
                LIMIT 11
                """;
        String defaultPlan = explain(sql, HISTORY_AGGREGATE, 18);
        String forcedPlan = forcedExplain(sql, HISTORY_AGGREGATE, 18);
        logEvidence("version_history", defaultPlan, forcedPlan);
        assertThat(defaultPlan).contains("\"Plan\"");
        assertThat(forcedPlan)
                .containsAnyOf(
                        "idx_job_description_versions_history",
                        "uq_job_description_versions_number");
    }

    @Test
    void exactCanonicalUrlLookupIsIndexEligibleWithoutLatencyClaim() {
        assertDefaultAndForcedIndex(
                "canonical_url_lookup",
                """
                        EXPLAIN (FORMAT JSON)
                        SELECT id
                        FROM job_descriptions
                        WHERE canonical_url = ?
                        """,
                new Object[] {"https://plans.example.test/jobs/32"},
                "uq_job_descriptions_canonical_url");
    }

    @Test
    void exactContentHashLookupIsIndexEligibleWithoutLatencyClaim() {
        assertDefaultAndForcedIndex(
                "content_hash_lookup",
                """
                        EXPLAIN (FORMAT JSON)
                        SELECT id
                        FROM job_description_versions
                        WHERE content_hash = ?
                        """,
                new Object[] {PostgreSqlFixture.digest("plan-content-32")},
                "idx_job_description_versions_content_hash");
    }

    private void assertDefaultAndForcedIndex(
            String evidenceName,
            String sql,
            Object[] arguments,
            String expectedIndex) {
        String defaultPlan = explain(sql, arguments);
        String forcedPlan = forcedExplain(sql, arguments);
        logEvidence(evidenceName, defaultPlan, forcedPlan);
        assertThat(defaultPlan).contains("\"Plan\"");
        assertThat(forcedPlan).contains(expectedIndex);
    }

    private String forcedExplain(String sql, Object... arguments) {
        return new TransactionTemplate(transactionManager).execute(status -> {
            jdbcTemplate.execute("SET LOCAL enable_seqscan = off");
            return explain(sql, arguments);
        });
    }

    private String explain(String sql, Object... arguments) {
        return jdbcTemplate.queryForObject(sql, String.class, arguments);
    }

    private static void logEvidence(
            String evidenceName,
            String defaultPlan,
            String forcedPlan) {
        LOGGER.info(
                "query_plan_evidence name={} default_plan={} forced_index_plan={}",
                evidenceName,
                defaultPlan,
                forcedPlan);
    }
}
