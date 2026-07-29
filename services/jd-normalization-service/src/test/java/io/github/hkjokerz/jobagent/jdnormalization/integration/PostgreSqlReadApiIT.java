package io.github.hkjokerz.jobagent.jdnormalization.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.EntityManagerFactory;
import java.time.Instant;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(properties = {
    "jd-normalization.security.api-key=" + PostgreSqlIntegrationSupport.API_KEY,
    "jd-normalization.persistence.enabled=true",
    "spring.jpa.properties.hibernate.generate_statistics=true"
})
@AutoConfigureMockMvc
@ActiveProfiles("integration")
@Testcontainers(disabledWithoutDocker = true)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PostgreSqlReadApiIT extends PostgreSqlIntegrationSupport {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private EntityManagerFactory entityManagerFactory;

    private PostgreSqlFixture fixture;

    @BeforeEach
    void setUp() {
        fixture = new PostgreSqlFixture(
                jdbcTemplate,
                new TransactionTemplate(transactionManager));
    }

    @Test
    void readsExactCurrentVersionWithEtag304AndAuthenticationPrecedence() throws Exception {
        UUID aggregate = UUID.fromString("40000000-0000-4000-8000-000000000001");
        fixture.insertAggregate(
                aggregate,
                "https://jobs.example.test/backend",
                Instant.parse("2026-07-29T04:00:00Z"),
                List.of(
                        PostgreSqlFixture.version(
                                UUID.fromString("40000000-0000-4000-8000-000000000002"),
                                1,
                                "Backend Engineer",
                                "Example Ltd",
                                "Hong Kong",
                                "Java",
                                "read-current-v1",
                                "read-current-f1",
                                Instant.parse("2026-07-29T04:00:00Z")),
                        PostgreSqlFixture.version(
                                UUID.fromString("40000000-0000-4000-8000-000000000003"),
                                2,
                                "Senior Backend Engineer",
                                "Example Ltd",
                                "Hong Kong",
                                "Required:\n- Java 21",
                                "read-current-v2",
                                "read-current-f2",
                                Instant.parse("2026-07-29T04:01:00Z"))));

        String expectedHash =
                HexFormat.of().formatHex(PostgreSqlFixture.digest("read-current-v2"));
        mockMvc.perform(authorizedGet("/api/v1/job-descriptions/{id}", aggregate)
                        .header("X-Request-ID", "postgres-current:1"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-ID", "postgres-current:1"))
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(jsonPath("$.id").value(aggregate.toString()))
                .andExpect(jsonPath("$.current_version_number").value(2))
                .andExpect(jsonPath("$.normalized_text")
                        .value("Required:\n- Java 21"))
                .andExpect(jsonPath("$.content_hash").value(expectedHash))
                .andExpect(jsonPath("$.metadata.title")
                        .value("Senior Backend Engineer"))
                .andExpect(jsonPath("$.required_skills[0].id").value("java"))
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString(
                                "deduplication_fingerprint"))));

        mockMvc.perform(authorizedGet("/api/v1/job-descriptions/{id}", aggregate)
                        .header("If-None-Match", "\"0\""))
                .andExpect(status().isNotModified())
                .andExpect(header().string("ETag", "\"0\""))
                .andExpect(content().string(""));

        UUID missing = UUID.fromString("40000000-0000-4000-8000-000000000099");
        mockMvc.perform(get("/api/v1/job-descriptions/{id}", aggregate))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("UNAUTHORIZED"));
        mockMvc.perform(authorizedGet("/api/v1/job-descriptions/{id}", missing))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("JOB_DESCRIPTION_NOT_FOUND"));
    }

    @Test
    void filtersExactlyAndPaginatesBothDirectionsWithDeterministicUuidTies()
            throws Exception {
        Instant tied = Instant.parse("2026-07-29T05:00:00Z");
        List<UUID> ids = List.of(
                UUID.fromString("50000000-0000-4000-8000-000000000001"),
                UUID.fromString("50000000-0000-4000-8000-000000000002"),
                UUID.fromString("50000000-0000-4000-8000-000000000003"),
                UUID.fromString("50000000-0000-4000-8000-000000000004"));
        for (int index = 0; index < ids.size(); index++) {
            UUID id = ids.get(index);
            String suffix = Integer.toString(index + 1);
            fixture.insertAggregate(
                    id,
                    "https://jobs.example.test/list/" + suffix,
                    tied,
                    List.of(PostgreSqlFixture.version(
                            UUID.fromString(
                                    "51000000-0000-4000-8000-00000000000" + suffix),
                            1,
                            index < 3 ? "Backend Engineer" : "Frontend Engineer",
                            index < 3 ? "Example Ltd" : "Other Ltd",
                            index == 1 ? "Kowloon" : "Hong Kong",
                            "Java " + suffix,
                            "list-content-" + suffix,
                            "list-fingerprint-" + suffix,
                            tied.plusSeconds(index))));
        }

        JsonNode descendingFirst = json(mockMvc.perform(
                        authorizedGet("/api/v1/job-descriptions")
                                .queryParam("limit", "2")
                                .queryParam("sort", "created_at_desc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(2)))
                .andReturn());
        assertThat(ids(descendingFirst)).containsExactly(ids.get(3), ids.get(2));
        String descendingCursor = descendingFirst.path("next_cursor").textValue();
        assertThat(descendingCursor).isNotBlank();

        JsonNode descendingSecond = json(mockMvc.perform(
                        authorizedGet("/api/v1/job-descriptions")
                                .queryParam("limit", "2")
                                .queryParam("sort", "created_at_desc")
                                .queryParam("cursor", descendingCursor))
                .andExpect(status().isOk())
                .andReturn());
        assertThat(ids(descendingSecond)).containsExactly(ids.get(1), ids.get(0));
        Set<UUID> unique = new HashSet<>(ids(descendingFirst));
        unique.addAll(ids(descendingSecond));
        assertThat(unique).hasSize(4);

        JsonNode ascending = json(mockMvc.perform(
                        authorizedGet("/api/v1/job-descriptions")
                                .queryParam("limit", "4")
                                .queryParam("sort", "created_at_asc"))
                .andExpect(status().isOk())
                .andReturn());
        assertThat(ids(ascending))
                .containsExactly(ids.get(0), ids.get(1), ids.get(2), ids.get(3));

        String expectedHash =
                HexFormat.of().formatHex(PostgreSqlFixture.digest("list-content-2"));
        mockMvc.perform(authorizedGet("/api/v1/job-descriptions")
                        .queryParam("title", " BACKEND\u00a0ENGINEER ")
                        .queryParam("company", "example ltd")
                        .queryParam("location", "KOWLOON")
                        .queryParam("content_hash", expectedHash)
                        .queryParam(
                                "canonical_url",
                                "HTTPS://JOBS.EXAMPLE.TEST:443/list/a/../2#fragment"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(1)))
                .andExpect(jsonPath("$.items[0].id").value(ids.get(1).toString()))
                .andExpect(jsonPath("$.items[0].normalized_text").doesNotExist())
                .andExpect(jsonPath("$.items[0].required_skills").doesNotExist());
    }

    @Test
    void rejectsFilterBoundCursorMismatchAndUsesOneBoundedListStatement()
            throws Exception {
        Instant created = Instant.parse("2026-07-29T06:00:00Z");
        for (int index = 1; index <= 3; index++) {
            fixture.insertAggregate(
                    UUID.fromString(
                            "60000000-0000-4000-8000-00000000000" + index),
                    null,
                    created.plusSeconds(index),
                    List.of(PostgreSqlFixture.version(
                            UUID.fromString(
                                    "61000000-0000-4000-8000-00000000000" + index),
                            1,
                            "Cursor Engineer",
                            "Cursor Company",
                            "Hong Kong",
                            "Java",
                            "cursor-content-" + index,
                            "cursor-fingerprint-" + index,
                            created.plusSeconds(index))));
        }

        JsonNode first = json(mockMvc.perform(
                        authorizedGet("/api/v1/job-descriptions")
                                .queryParam("limit", "1")
                                .queryParam("title", "cursor engineer"))
                .andExpect(status().isOk())
                .andReturn());
        String cursor = first.path("next_cursor").textValue();

        mockMvc.perform(authorizedGet("/api/v1/job-descriptions")
                        .queryParam("limit", "1")
                        .queryParam("company", "cursor company")
                        .queryParam("cursor", cursor))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code").value("INVALID_CURSOR"));

        Statistics statistics =
                entityManagerFactory.unwrap(SessionFactory.class).getStatistics();
        statistics.clear();
        mockMvc.perform(authorizedGet("/api/v1/job-descriptions")
                        .queryParam("limit", "2")
                        .queryParam("title", "cursor engineer"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items", hasSize(2)));
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1);
        assertThat(statistics.getEntityFetchCount()).isZero();
    }

    @Test
    void paginatesImmutableVersionHistoryAndRollbackLeavesNoOrphans()
            throws Exception {
        UUID aggregate = UUID.fromString("70000000-0000-4000-8000-000000000001");
        Instant start = Instant.parse("2026-07-29T07:00:00Z");
        fixture.insertAggregate(
                aggregate,
                null,
                start,
                java.util.stream.IntStream.rangeClosed(1, 4)
                        .mapToObj(number -> PostgreSqlFixture.version(
                                UUID.fromString(
                                        "71000000-0000-4000-8000-00000000000" + number),
                                number,
                                "Version " + number,
                                "Example",
                                null,
                                "Java version " + number,
                                "history-content-" + number,
                                "history-fingerprint-" + number,
                                start.plusSeconds(number)))
                        .toList());

        JsonNode first = json(mockMvc.perform(
                        authorizedGet(
                                        "/api/v1/job-descriptions/{id}/versions",
                                        aggregate)
                                .queryParam("limit", "2"))
                .andExpect(status().isOk())
                .andReturn());
        assertThat(versionNumbers(first)).containsExactly(4, 3);
        JsonNode second = json(mockMvc.perform(
                        authorizedGet(
                                        "/api/v1/job-descriptions/{id}/versions",
                                        aggregate)
                                .queryParam("limit", "2")
                                .queryParam("cursor", first.path("next_cursor").textValue()))
                .andExpect(status().isOk())
                .andReturn());
        assertThat(versionNumbers(second)).containsExactly(2, 1);

        JsonNode ascending = json(mockMvc.perform(
                        authorizedGet(
                                        "/api/v1/job-descriptions/{id}/versions",
                                        aggregate)
                                .queryParam("limit", "2")
                                .queryParam("sort", "version_asc"))
                .andExpect(status().isOk())
                .andReturn());
        assertThat(versionNumbers(ascending)).containsExactly(1, 2);

        mockMvc.perform(authorizedGet(
                        "/api/v1/job-descriptions/{id}/versions",
                        UUID.fromString("70000000-0000-4000-8000-000000000099")))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("JOB_DESCRIPTION_NOT_FOUND"));

        UUID rolledBackAggregate =
                UUID.fromString("70000000-0000-4000-8000-000000000090");
        assertThatThrownByFixtureRollback(rolledBackAggregate);
        assertThat(jdbcTemplate.queryForObject(
                "SELECT count(*) FROM job_descriptions WHERE id = ?",
                Integer.class,
                rolledBackAggregate)).isZero();
        assertThat(jdbcTemplate.queryForObject(
                "SELECT count(*) FROM job_description_versions "
                        + "WHERE job_description_id = ?",
                Integer.class,
                rolledBackAggregate)).isZero();
    }

    @Test
    void healthIsStatusOnlyAndOpenApiContainsReadSchemasWithoutWriteApi()
            throws Exception {
        mockMvc.perform(get("/actuator/health/liveness"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"UP\"}", true));
        mockMvc.perform(get("/actuator/health/readiness"))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"UP\"}", true));

        mockMvc.perform(authorizedGet("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.paths['/api/v1/job-descriptions'].get")
                        .exists())
                .andExpect(jsonPath("$.paths['/api/v1/job-descriptions'].post")
                        .doesNotExist())
                .andExpect(jsonPath(
                                "$.paths['/api/v1/job-descriptions/{id}/versions'].get")
                        .exists());
    }

    private void assertThatThrownByFixtureRollback(UUID aggregateId) {
        org.assertj.core.api.Assertions.assertThatThrownBy(
                        () -> new TransactionTemplate(transactionManager)
                                .executeWithoutResult(status -> {
                                    fixture.insertAggregate(
                                            aggregateId,
                                            null,
                                            Instant.parse("2026-07-29T07:30:00Z"),
                                            List.of(PostgreSqlFixture.version(
                                                    UUID.fromString(
                                                            "70000000-0000-4000-8000-000000000091"),
                                                    1,
                                                    "Rollback",
                                                    "Example",
                                                    null,
                                                    "Java",
                                                    "rollback-content",
                                                    "rollback-fingerprint",
                                                    Instant.parse(
                                                            "2026-07-29T07:30:00Z"))));
                                    throw new SyntheticRollbackException();
                                }))
                .isInstanceOf(SyntheticRollbackException.class);
    }

    private org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder
            authorizedGet(String path, Object... uriVariables) {
        return get(path, uriVariables)
                .header("Authorization", "Bearer " + API_KEY);
    }

    private JsonNode json(MvcResult result) throws Exception {
        return objectMapper.readTree(result.getResponse().getContentAsByteArray());
    }

    private static List<UUID> ids(JsonNode page) {
        return java.util.stream.StreamSupport.stream(
                        page.path("items").spliterator(),
                        false)
                .map(item -> UUID.fromString(item.path("id").textValue()))
                .toList();
    }

    private static List<Integer> versionNumbers(JsonNode page) {
        return java.util.stream.StreamSupport.stream(
                        page.path("items").spliterator(),
                        false)
                .map(item -> item.path("version_number").intValue())
                .toList();
    }

    private static final class SyntheticRollbackException extends RuntimeException {
    }
}
